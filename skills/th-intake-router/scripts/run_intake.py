from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wrapper for intake routing workflow.")
    parser.add_argument("--raw-dir", required=True, help="Path to raw intake directory")
    parser.add_argument("--period", help="Optional period override")
    parser.add_argument("--pack-type", choices=["preview", "close"], help="Optional pack type override")
    parser.add_argument("--region", help="Optional region override")
    parser.add_argument("--source-mode", default="both", choices=["offline_values", "lineage", "both"])
    parser.add_argument(
        "--strict-core",
        dest="strict_core",
        action="store_true",
        default=True,
        help="Enable strict core intake validation.",
    )
    parser.add_argument(
        "--no-strict-core",
        dest="strict_core",
        action="store_false",
        help="Disable strict core intake validation.",
    )
    parser.add_argument("--allow-missing-core", action="store_true")
    parser.add_argument("--pair-choice-file", help="Optional pair choice JSON file")
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
    if args.strict_core:
        command.append("--strict-core")
    else:
        command.append("--no-strict-core")
    if args.allow_missing_core:
        command.append("--allow-missing-core")
    if args.pair_choice_file:
        command.extend(["--pair-choice-file", args.pair_choice_file])
    if args.period:
        command.extend(["--period", args.period])
    if args.pack_type:
        command.extend(["--pack-type", args.pack_type])
    if args.region:
        command.extend(["--region", args.region])
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
