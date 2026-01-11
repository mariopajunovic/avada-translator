import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent

def run(cmd):
    print("\n▶", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("\n✖ Error, stopping pipeline")
        sys.exit(r.returncode)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="products", help="Source folder with .txt files")
    ap.add_argument("--lang", default="English", help="Target language for OpenAI translation")
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--job-name", help="Custom job name (default: auto-generated)")
    args = ap.parse_args()

    lang = args.lang
    lang_slug = lang.strip().lower().replace(" ", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    job_name = args.job_name or f"{lang_slug}_{timestamp}"
    job_dir = SCRIPT_DIR / "jobs" / job_name
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 Job directory: {job_dir}")

    export_dir = str(job_dir / "containers")
    extracted_dir = str(job_dir / "extracted")
    translated_json_dir = str(job_dir / "translated")
    translated_containers_dir = str(job_dir / "applied")
    merged_pages_dir = str(job_dir / "output")

    run([
        "python3",
        str(SCRIPT_DIR / "extract.py"),
        "product_export",
        "--src", args.src,
        "--out", export_dir,
        "--print-each"
    ])
    print("\n✔ Container export completed")

    run([
        "python3",
        str(SCRIPT_DIR / "segments.py"),
        "extract",
        "--src", export_dir,
        "--out", extracted_dir
    ])
    print("\n✔ Translation extraction completed")

    cmd_translate = [
        "python3",
        str(SCRIPT_DIR / "translate.py"),
        "--in", extracted_dir,
        "--out", translated_json_dir,
        "--lang", lang,
        "--model", args.model,
        "--workers", str(args.workers),
        "--batch", str(args.batch),
    ]
    if args.overwrite:
        cmd_translate.append("--overwrite")

    run(cmd_translate)
    print("\n✔ OpenAI JSON translation completed")

    run([
        "python3",
        str(SCRIPT_DIR / "segments.py"),
        "apply",
        "--src", export_dir,
        "--extracted", extracted_dir,
        "--translated", translated_json_dir,
        "--out", translated_containers_dir
    ])
    print("\n✔ Translated Fusion containers (.txt) generated")

    run([
        "python3",
        str(SCRIPT_DIR / "merge.py"),
        "--src", translated_containers_dir,
        "--out", merged_pages_dir
    ])
    print("\n✔ Pages merged back into original .txt structure")

    print(f"\n✔ ALL DONE → {merged_pages_dir}/")

if __name__ == "__main__":
    main()
