from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.chunks import build_token_chunks
from finance_copilot.common import ensure_dir, read_json, repo_root, slugify, write_json
from finance_copilot.deck import extract_deck
from finance_copilot.workbook import extract_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full extraction/tokenization workflow from pack manifest.")
    parser.add_argument("--manifest", required=True, help="Path to pack_manifest.json")
    parser.add_argument(
        "--normalized-dir",
        help="Output normalized directory; defaults to data/normalized/<period>/<pack_type>",
    )
    parser.add_argument("--max-rows", type=int, help="Optional row cap for workbook extraction")
    parser.add_argument("--max-cols", type=int, help="Optional column cap for workbook extraction")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = (root / manifest_path).resolve()

    manifest = read_json(manifest_path)
    period = manifest["period"]
    pack_type = manifest["pack_type"]

    if args.normalized_dir:
        normalized_dir = Path(args.normalized_dir)
        if not normalized_dir.is_absolute():
            normalized_dir = (root / normalized_dir).resolve()
    else:
        normalized_dir = (root / "data" / "normalized" / period / pack_type).resolve()
    ensure_dir(normalized_dir)
    ensure_dir(normalized_dir / "decks")
    ensure_dir(normalized_dir / "workbooks")
    ensure_dir(normalized_dir / "chunks")

    copied_manifest_path = normalized_dir / "pack_manifest.json"
    shutil.copy2(manifest_path, copied_manifest_path)

    extraction_log: list[dict[str, str]] = []
    for file_entry in manifest.get("files", []):
        src_path = root / file_entry["path"]
        role = file_entry["role"]
        stem_slug = slugify(Path(file_entry["file_name"]).stem)
        if role.endswith("_deck"):
            out_dir = normalized_dir / "decks" / stem_slug
            extract_deck(input_path=src_path, output_dir=out_dir)
            extraction_log.append({"role": role, "source": file_entry["path"], "output": str(out_dir.relative_to(root).as_posix())})
        elif role.endswith("_excel") or role.endswith("_workbook") or role == "supporting_excel":
            out_dir = normalized_dir / "workbooks" / stem_slug
            extract_workbook(
                input_path=src_path,
                output_dir=out_dir,
                max_rows=args.max_rows,
                max_cols=args.max_cols,
            )
            extraction_log.append({"role": role, "source": file_entry["path"], "output": str(out_dir.relative_to(root).as_posix())})

    chunk_index = build_token_chunks(
        normalized_pack_dir=normalized_dir,
        output_path=normalized_dir / "chunks" / "chunks.jsonl",
    )

    lineage_degraded = manifest.get("source_mode") == "offline_values"
    pack_summary = {
        "period": period,
        "pack_type": pack_type,
        "source_mode": manifest.get("source_mode"),
        "lineage_degraded": lineage_degraded,
        "extraction_log": extraction_log,
        "chunk_index": chunk_index,
    }
    write_json(normalized_dir / "pack_summary.json", pack_summary)

    print(f"Normalized pack output: {normalized_dir}")
    print(f"Artifacts extracted: {len(extraction_log)}")
    print(f"Token chunks: {chunk_index['chunk_count']}")
    if lineage_degraded:
        print("Warning: lineage_degraded=true (source_mode is offline_values)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
