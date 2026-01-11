import re
import argparse
import json
from pathlib import Path

pattern = re.compile(r"\[fusion_builder_container[\s\S]*?\[/fusion_builder_container\]", re.MULTILINE)

def export_from_file(input_file: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    content = input_file.read_text(encoding="utf-8")
    containers = pattern.findall(content)

    for i, container in enumerate(containers, start=1):
        (output_dir / f"container_{i}.txt").write_text(container, encoding="utf-8")

    return len(containers)

def cmd_export(args):
    input_file = Path(args.input)
    out_dir = Path(args.out)

    count = export_from_file(input_file, out_dir)
    print(f"Exported {count} containers to folder '{out_dir}'.")

def cmd_product_export(args):
    src_dir = Path(args.src)
    out_root = Path(args.out)

    if not src_dir.exists() or not src_dir.is_dir():
        raise SystemExit(f"Folder does not exist: {src_dir}")

    files = sorted(src_dir.rglob("*.txt"))
    if not files:
        raise SystemExit(f"No .txt files in: {src_dir}")

    index = []
    total_files = 0
    total_containers = 0

    for f in files:
        rel_dir = f.parent.relative_to(src_dir)
        rel_dir_str = "" if str(rel_dir) == "." else str(rel_dir)

        page_dir = out_root / rel_dir_str / f.stem

        count = export_from_file(f, page_dir)

        index.append({
            "source": str(f),
            "output": str(page_dir),
            "containers": count,
        })

        total_files += 1
        total_containers += count

        if args.print_each or rel_dir_str == "":
            print(f"{f} -> {page_dir} ({count})")

    (out_root / "index.json").parent.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. files={total_files}, containers={total_containers}, output='{out_root}'")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("export", help="Export containers from a single file")
    p1.add_argument("--input", required=True, help="Input .txt file")
    p1.add_argument("--out", default="containers", help="Output folder")
    p1.set_defaults(func=cmd_export)

    p2 = sub.add_parser("product_export", help="Batch export containers from folder")
    p2.add_argument("--src", required=True, help="Source folder with .txt files")
    p2.add_argument("--out", default="containers", help="Output folder")
    p2.add_argument("--print-each", action="store_true")
    p2.set_defaults(func=cmd_product_export)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
