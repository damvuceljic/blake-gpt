from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import read_json
from finance_copilot.intake import validate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an existing pack manifest JSON file.")
    parser.add_argument("--manifest", required=True, help="Path to pack_manifest.json")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = (REPO_ROOT / manifest_path).resolve()
    payload = read_json(manifest_path)
    errors = validate_manifest(payload)
    if errors:
        for error in errors:
            print(f"[invalid] {error}")
        return 2
    print(f"[valid] {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

