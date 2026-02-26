from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wrapper for intake routing workflow.")
    parser.add_argument("--raw-dir", required=True, help="Path to raw intake directory")
    parser.add_argument("--period", help="Optional period override")
    parser.add_argument("--pack-type", help="Optional pack type override")
    parser.add_argument("--region", help="Optional region override")
    parser.add_argument("--source-mode", default="both", choices=["offline_values", "lineage", "both"])
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    command = [
        "python",
        "scripts/intake/route_intake.py",
        "--raw-dir",
        args.raw_dir,
        "--source-mode",
        args.source_mode,
    ]
    if args.period:
        command.extend(["--period", args.period])
    if args.pack_type:
        command.extend(["--pack-type", args.pack_type])
    if args.region:
        command.extend(["--region", args.region])
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

