import argparse
import re
from pathlib import Path

NUM_RX = re.compile(r"container_(\d+)\.txt$")

def container_index(p: Path) -> int:
    m = NUM_RX.search(p.name)
    return int(m.group(1)) if m else 10**9

def merge_page_dir(page_dir: Path) -> str:
    containers = sorted(page_dir.glob("container_*.txt"), key=container_index)
    parts = [c.read_text(encoding="utf-8") for c in containers]
    return "\n\n".join(parts).strip() + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="applied", help="Folder with translated containers")
    ap.add_argument("--out", default="output", help="Output folder for merged .txt files")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise SystemExit(f"--src does not exist: {src}")

    page_dirs = [p for p in src.rglob("*") if p.is_dir() and any(p.glob("container_*.txt"))]
    if not page_dirs:
        raise SystemExit(f"No page folders with container_*.txt in: {src}")

    for page_dir in sorted(page_dirs):
        rel = page_dir.relative_to(src)

        # output: .../<parent>/<page>.txt
        if rel.parent.as_posix() == ".":
            out_file = out / f"{rel.name}.txt"
        else:
            out_subdir = out / rel.parent
            out_subdir.mkdir(parents=True, exist_ok=True)
            out_file = out_subdir / f"{rel.name}.txt"

        merged = merge_page_dir(page_dir)
        out_file.write_text(merged, encoding="utf-8")
        print(f"{page_dir} -> {out_file}")

if __name__ == "__main__":
    main()
