import argparse
import json
import os
import time
import re
from pathlib import Path
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydantic import BaseModel
from openai import OpenAI

class Segment(BaseModel):
    id: str
    text: str

class TranslationPayload(BaseModel):
    segments: List[Segment]

BRACKET_RX = re.compile(r"\[[^\]]*?\]")
BAD_TOKENS = ["on_toggle]", "off_toggle]"]

def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]

def build_system_prompt(target_lang: str) -> str:
    return (
        f"You are a strict localization engine. Translate to {target_lang}. "
        "Return VALID JSON matching the given schema exactly. "
        "Do not change ids. Do not add or remove segments. Do not reorder segments. "
        "Absolutely never modify ANYTHING inside square brackets [ ... ]. "
        "That includes shortcodes, shortcode attributes, closing tags, and tokens like on_toggle], off_toggle]. "
        "Keep any HTML tags unchanged. "
        "Do not change URLs, emails, numbers, units (px, %, vh), or CSS variables like var(--...). "
        "Only translate human-readable text outside of [ ... ] and outside of HTML tags/attributes."
    )

def is_corrupt(original_text: str, translated_text: str) -> bool:
    orig_br = BRACKET_RX.findall(original_text or "")
    tr_br = BRACKET_RX.findall(translated_text or "")
    if orig_br != tr_br:
        return True
    low = (translated_text or "").lower()
    if any(t in low for t in BAD_TOKENS):
        return True
    return False

def translate_segments_once(
    client: OpenAI,
    model: str,
    target_lang: str,
    segments: List[dict],
) -> Tuple[dict, Optional[object]]:
    payload = {"segments": [{"id": s["id"], "text": s["text"]} for s in segments]}
    sys_prompt = build_system_prompt(target_lang)
    user = json.dumps(payload, ensure_ascii=False)

    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ],
        text_format=TranslationPayload,
    )
    parsed = resp.output_parsed
    usage = getattr(resp, "usage", None)
    return parsed.model_dump(), usage

def translate_segments(
    client: OpenAI,
    model: str,
    target_lang: str,
    segments: List[dict],
    max_retries: int,
    sleep_base: float,
) -> Tuple[dict, Optional[object]]:
    last_err = None
    for attempt in range(max_retries):
        try:
            translated, usage = translate_segments_once(client, model, target_lang, segments)
            if "segments" not in translated or len(translated["segments"]) != len(segments):
                raise ValueError("Schema mismatch: segment count differs")

            tr_map = {s["id"]: s["text"] for s in translated["segments"]}
            for s in segments:
                if s["id"] not in tr_map:
                    raise ValueError("Schema mismatch: missing id in translated output")

            bad = []
            for s in segments:
                o = s.get("text", "")
                t = tr_map[s["id"]]
                if is_corrupt(o, t):
                    bad.append(s["id"])

            if bad:
                raise ValueError(f"Shortcode corruption detected (ids: {bad[:5]})")

            return translated, usage
        except Exception as e:
            last_err = e
            time.sleep(sleep_base * (2 ** attempt))
    raise last_err

def translate_file(
    in_path: Path,
    in_dir: Path,
    out_dir: Path,
    model: str,
    lang: str,
    batch: int,
    max_retries: int,
    sleep_base: float,
    overwrite: bool,
) -> Tuple[str, int, int, int, str]:
    rel = in_path.relative_to(in_dir)
    out_path = out_dir / rel

    if out_path.exists() and not overwrite:
        return (str(rel), 0, 0, 0, "skipped")

    data = json.loads(in_path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])

    if not segments:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = {
            "source_key": data.get("source_key", str(rel).replace("\\", "/")),
            "segments": [],
        }
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return (str(rel), 0, 0, 0, "empty")

    client = OpenAI()

    translated_segments = []
    file_in = 0
    file_out = 0

    for group in chunk_list(segments, batch):
        translated, usage = translate_segments(
            client=client,
            model=model,
            target_lang=lang,
            segments=group,
            max_retries=max_retries,
            sleep_base=sleep_base,
        )

        out_map = {s["id"]: s["text"] for s in translated["segments"]}
        for s in group:
            translated_segments.append({
                "id": s["id"],
                "kind": s.get("kind", ""),
                "text": out_map[s["id"]],
            })

        if usage:
            file_in += int(getattr(usage, "input_tokens", 0) or 0)
            file_out += int(getattr(usage, "output_tokens", 0) or 0)

    result = {
        "source_key": data.get("source_key", str(rel).replace("\\", "/")),
        "segments": translated_segments,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return (str(rel), len(segments), file_in, file_out, "ok")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", default="extracted", help="Input folder with JSON files")
    ap.add_argument("--out", dest="out_dir", default="translated", help="Output folder for translated JSON")
    ap.add_argument("--pattern", default="container_*.json")
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--lang", default="English")
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--max-retries", type=int, default=6)
    ap.add_argument("--sleep-base", type=float, default=0.2)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set. Run: export OPENAI_API_KEY='...'")

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(in_dir.rglob(args.pattern))
    if not paths:
        raise SystemExit(f"No input files found in {in_dir} with pattern {args.pattern}")

    total_in = 0
    total_out = 0
    total_files = 0
    ok_files = 0
    skipped = 0
    empty = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [
            ex.submit(
                translate_file,
                p, in_dir, out_dir,
                args.model, args.lang, args.batch,
                args.max_retries, args.sleep_base, args.overwrite
            )
            for p in paths
        ]

        for fut in as_completed(futures):
            try:
                rel, seg_count, tin, tout, status = fut.result()
            except Exception as e:
                failed += 1
                print(f"FAILED: {e}")
                continue

            total_files += 1
            total_in += tin
            total_out += tout

            if status == "ok":
                ok_files += 1
                print(f"translated {rel} | segments={seg_count} | in={tin} out={tout}")
            elif status == "skipped":
                skipped += 1
            elif status == "empty":
                empty += 1

    print(f"done | files={total_files} ok={ok_files} skipped={skipped} empty={empty} failed={failed} total_in={total_in} total_out={total_out}")

if __name__ == "__main__":
    main()
