from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import repo_root
from finance_copilot.workbook import extract_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract a workbook into normalized CSV/JSON artifacts.")
    parser.add_argument("--input", required=True, help="Path to input workbook (.xlsx/.xlsm/.xls)")
    parser.add_argument("--output-dir", required=True, help="Output directory for workbook extract")
    parser.add_argument("--max-rows", type=int, help="Optional row cap for extraction")
    parser.add_argument("--max-cols", type=int, help="Optional column cap for extraction")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    if not input_path.is_absolute():
        input_path = (root / input_path).resolve()
    if not output_dir.is_absolute():
        output_dir = (root / output_dir).resolve()

    result = extract_workbook(
        input_path=input_path,
        output_dir=output_dir,
        max_rows=args.max_rows,
        max_cols=args.max_cols,
    )
    print(f"Workbook extracted: {input_path.name}")
    print(f"Output directory: {output_dir}")
    print(f"Sheets: {result['workbook_meta']['sheet_count']}")
    print(f"External links: {result['lineage_flags']['external_link_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

