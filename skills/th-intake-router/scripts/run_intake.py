from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Wrapper for intake workflow. Default behavior is full ingest "
            "(route + tokenize + baseline analyses + archive)."
        )
    )
    parser.add_argument("--raw-dir", help="Path to raw intake directory")
    parser.add_argument("--period", help="Optional period override")
    parser.add_argument("--pack-type", choices=["preview", "close"], help="Optional pack type override")
    parser.add_argument("--region", help="Optional region override")
    parser.add_argument("--source-mode", default="both", choices=["offline_values", "lineage", "both"])
    parser.add_argument("--manifest", help="Optional manifest path (used by --tokenize-only)")
    parser.add_argument("--question", help="Optional ingest focus question")
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
    parser.add_argument("--use-llm-postprocess", action="store_true")
    parser.add_argument("--use-historical-context", action="store_true")
    parser.add_argument("--historical-context", help="Optional historical calibration bundle path")
    parser.add_argument("--llm-model", help="Optional LLM model override")
    parser.add_argument("--route-only", action="store_true", help="Advanced mode: only route and validate manifest.")
    parser.add_argument("--tokenize-only", action="store_true", help="Advanced mode: only run tokenizer from manifest.")
    args = parser.parse_args()

    if args.route_only and args.tokenize_only:
        print("Choose only one advanced mode: --route-only or --tokenize-only.")
        return 2

    repo_root = Path(__file__).resolve().parents[3]

    if args.route_only:
        if not args.raw_dir:
            print("--raw-dir is required for --route-only")
            return 2
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

    if args.tokenize_only:
        manifest = args.manifest
        if not manifest:
            if not args.period or not args.pack_type:
                print("--tokenize-only requires --manifest OR both --period and --pack-type.")
                return 2
            manifest = f"data/packs/{args.period}/{args.pack_type}/pack_manifest.json"
        manifest_path = Path(manifest)
        if not manifest_path.is_absolute():
            manifest_path = (repo_root / manifest_path).resolve()
        if not manifest_path.exists():
            print(f"Manifest not found: {manifest_path}")
            return 2
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        missing_sources: list[str] = []
        for entry in payload.get("files", []):
            source = Path(str(entry.get("path", "")))
            if not source.is_absolute():
                source = (repo_root / source).resolve()
            if not source.exists():
                missing_sources.append(str(entry.get("path", "")))
        if missing_sources:
            print(
                "Tokenize-only requires source files from manifest to still exist in raw intake. "
                "Missing source paths: " + ", ".join(missing_sources)
            )
            return 2
        command = [
            "python",
            "scripts/extract/tokenize_pack.py",
            "--manifest",
            str(manifest_path),
        ]
        return subprocess.run(command, cwd=repo_root, check=False).returncode

    if not args.raw_dir:
        print("--raw-dir is required for default full-ingest mode.")
        return 2

    command = [
        "python",
        "scripts/intake/process_month.py",
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
    if args.question:
        command.extend(["--question", args.question])
    if args.use_llm_postprocess:
        command.append("--use-llm-postprocess")
    if args.use_historical_context:
        command.append("--use-historical-context")
    if args.historical_context:
        command.extend(["--historical-context", args.historical_context])
    if args.llm_model:
        command.extend(["--llm-model", args.llm_model])
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
