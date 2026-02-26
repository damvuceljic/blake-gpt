from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import repo_root
from finance_copilot.deck import extract_deck


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract a PPTX into normalized JSON artifacts.")
    parser.add_argument("--input", required=True, help="Path to input deck (.pptx)")
    parser.add_argument("--output-dir", required=True, help="Output directory for deck extract")
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

    result = extract_deck(input_path=input_path, output_dir=output_dir)
    print(f"Deck extracted: {input_path.name}")
    print(f"Output directory: {output_dir}")
    print(f"Slides: {result['deck_meta']['slide_count']} | Charts: {result['deck_meta']['chart_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

