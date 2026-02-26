from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wrapper for pack tokenization workflow.")
    parser.add_argument("--manifest", required=True, help="Path to pack_manifest.json")
    parser.add_argument("--max-rows", type=int, help="Optional workbook row cap")
    parser.add_argument("--max-cols", type=int, help="Optional workbook column cap")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    command = ["python", "scripts/extract/tokenize_pack.py", "--manifest", args.manifest]
    if args.max_rows:
        command.extend(["--max-rows", str(args.max_rows)])
    if args.max_cols:
        command.extend(["--max-cols", str(args.max_cols)])
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

