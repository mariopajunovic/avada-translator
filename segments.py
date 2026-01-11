import argparse
import json
import re
import hashlib
from pathlib import Path

BODY_TAGS = [
    "fusion_title",
    "fusion_text",
    "fusion_highlight",
    "fusion_button",
    "fusion_li_item",
    "fusion_table",
]

BODY_RX = re.compile(
    r"\[(?P<tag>" + "|".join(BODY_TAGS) + r")\b[^\]]*\](?P<body>[\s\S]*?)\[/\1\]",
    re.MULTILINE,
)

TOGGLE_RX = re.compile(
    r"\[fusion_toggle\b(?P<attrs>[^\]]*)\](?P<body>[\s\S]*?)\[/fusion_toggle\]",
    re.MULTILINE,
)

TITLE_ATTR_RX = re.compile(r'\btitle="([^"]*)"')

SKIP_IF_CONTAINS = [
    "<script",
    "application/ld+json",
]

def stable_id(source_key: str, kind: str, idx: int, start: int, end: int, text: str):
    h = hashlib.sha1()
    h.update((source_key + "|" + kind + "|" + str(idx) + "|" + str(start) + "|" + str(end)).encode("utf-8"))
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:16]

def should_skip(text: str):
    t = (text or "").lower()
    return any(x in t for x in SKIP_IF_CONTAINS)

def extract_segments(text: str, source_key: str):
    segments = []
    idx = 0

    for m in BODY_RX.finditer(text):
        body = m.group("body")
        if should_skip(body):
            continue
        segments.append({
            "id": stable_id(source_key, m.group("tag"), idx, m.start("body"), m.end("body"), body),
            "kind": m.group("tag"),
            "start": m.start("body"),
            "end": m.end("body"),
            "text": body,
        })
        idx += 1

    toggle_order = 0
    for m in TOGGLE_RX.finditer(text):
        attrs = m.group("attrs") or ""
        body = m.group("body") or ""

        title_m = TITLE_ATTR_RX.search(attrs)
        if title_m:
            title_text = title_m.group(1)
            if title_text and not should_skip(title_text):
                segments.append({
                    "id": stable_id(source_key, "fusion_toggle:title", idx, -1, -1, title_text),
                    "kind": "fusion_toggle:title",
                    "toggle_order": toggle_order,
                    "text": title_text,
                })
                idx += 1

        if body.strip() and not should_skip(body):
            segments.append({
                "id": stable_id(source_key, "fusion_toggle:body", idx, m.start("body"), m.end("body"), body),
                "kind": "fusion_toggle:body",
                "start": m.start("body"),
                "end": m.end("body"),
                "toggle_order": toggle_order,
                "text": body,
            })
            idx += 1

        toggle_order += 1

    segments.sort(key=lambda x: (x.get("start", 10**18), x.get("end", 10**18)))
    return segments

def replace_toggle_title(block: str, new_title: str):
    def repl(_m):
        return f'title="{new_title}"'
    if TITLE_ATTR_RX.search(block):
        return TITLE_ATTR_RX.sub(repl, block, count=1)
    return block

def iter_container_files(src_dir: Path, pattern: str):
    return sorted(src_dir.rglob(pattern))

def rel_key(src_dir: Path, file_path: Path):
    return file_path.relative_to(src_dir).as_posix()

def cmd_extract(src_dir: str, out_dir: str, pattern: str):
    src_dir = Path(src_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = iter_container_files(src_dir, pattern)
    if not files:
        raise SystemExit(f"No files matching pattern '{pattern}' in: {src_dir}")

    for p in files:
        source_key = rel_key(src_dir, p)
        raw = p.read_text(encoding="utf-8")
        segs = extract_segments(raw, source_key)

        payload = {
            "source_key": source_key,
            "segments": [{"id": s["id"], "kind": s["kind"], "text": s["text"]} for s in segs],
        }

        out_path = (out_dir / p.relative_to(src_dir)).with_suffix(".json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def cmd_apply(src_dir: str, extracted_dir: str, translated_dir: str, out_dir: str, pattern: str):
    src_dir = Path(src_dir)
    extracted_dir = Path(extracted_dir)
    translated_dir = Path(translated_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = iter_container_files(src_dir, pattern)
    if not files:
        raise SystemExit(f"No files matching pattern '{pattern}' in: {src_dir}")

    toggle_block_rx = re.compile(r"\[fusion_toggle\b[^\]]*\][\s\S]*?\[/fusion_toggle\]", re.MULTILINE)

    for p in files:
        rel = p.relative_to(src_dir)
        source_key = rel.as_posix()

        extracted_path = (extracted_dir / rel).with_suffix(".json")
        translated_path = (translated_dir / rel).with_suffix(".json")

        if not extracted_path.exists():
            raise FileNotFoundError(f"Missing extracted file: {extracted_path}")
        if not translated_path.exists():
            raise FileNotFoundError(f"Missing translated file: {translated_path}")

        raw = p.read_text(encoding="utf-8")

        extracted = json.loads(extracted_path.read_text(encoding="utf-8"))
        translated = json.loads(translated_path.read_text(encoding="utf-8"))

        ex_map = {s["id"]: s for s in extracted.get("segments", [])}
        tr_map = {s["id"]: s for s in translated.get("segments", [])}

        missing = [sid for sid in ex_map.keys() if sid not in tr_map]
        if missing:
            raise ValueError(f"{source_key}: Missing translated segment IDs: {missing[:5]}")

        segs = extract_segments(raw, source_key)

        span_segs = [s for s in segs if s.get("start") is not None and s.get("end") is not None]
        title_segs = [s for s in segs if s["kind"] == "fusion_toggle:title"]

        out = raw

        for s in reversed(span_segs):
            sid = s["id"]
            new_text = tr_map[sid].get("text", "")
            out = out[:s["start"]] + new_text + out[s["end"]:]

        for s in title_segs:
            sid = s["id"]
            new_text = tr_map[sid].get("text", "")

            blocks = list(toggle_block_rx.finditer(out))
            if not blocks:
                raise ValueError(f"{source_key}: toggle block not found for title replacement")

            order = s.get("toggle_order", 0)
            if order >= len(blocks):
                order = len(blocks) - 1

            bm = blocks[order]
            block = bm.group(0)
            new_block = replace_toggle_title(block, new_text)
            out = out[:bm.start()] + new_block + out[bm.end():]

        out_path = out_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_e = sub.add_parser("extract", help="Extract translatable segments to JSON")
    ap_e.add_argument("--src", required=True, help="Source folder with container .txt files")
    ap_e.add_argument("--out", default="extracted", help="Output folder for JSON files")
    ap_e.add_argument("--pattern", default="container_*.txt")

    ap_a = sub.add_parser("apply", help="Apply translations back to containers")
    ap_a.add_argument("--src", required=True, help="Source folder with container .txt files")
    ap_a.add_argument("--extracted", default="extracted", help="Folder with extracted JSON")
    ap_a.add_argument("--translated", default="translated", help="Folder with translated JSON")
    ap_a.add_argument("--out", default="applied", help="Output folder for translated containers")
    ap_a.add_argument("--pattern", default="container_*.txt")

    args = ap.parse_args()

    if args.cmd == "extract":
        cmd_extract(args.src, args.out, args.pattern)
    elif args.cmd == "apply":
        cmd_apply(args.src, args.extracted, args.translated, args.out, args.pattern)

if __name__ == "__main__":
    main()
