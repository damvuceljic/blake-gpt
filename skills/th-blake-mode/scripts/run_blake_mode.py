from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wrapper for chat-first Blake Mode routing.")
    parser.add_argument("--message", required=True, help="User prompt text")
    parser.add_argument("--raw-dir", help="Optional raw intake directory")
    parser.add_argument("--pack-dir", help="Optional normalized pack directory")
    parser.add_argument("--prior-pack-dir", help="Optional prior normalized pack directory")
    parser.add_argument("--period", help="Optional period key")
    parser.add_argument("--pack-type", help="Optional pack type")
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
    parser.add_argument("--pair-choice-file", help="Optional JSON map for offline pair disambiguation")
    parser.add_argument(
        "--policy-config",
        default="data/context/hot_questions_policy.default.json",
        help="Hot questions policy config JSON for policy-aware defaults.",
    )
    parser.add_argument("--use-llm-postprocess", action="store_true")
    parser.add_argument("--use-historical-context", action="store_true")
    parser.add_argument("--historical-context", help="Optional historical calibration bundle path")
    parser.add_argument("--llm-model", help="Optional LLM model override")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    command = [
        "python",
        "scripts/chat/blake_mode.py",
        "--message",
        args.message,
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
    for key in ["raw_dir", "pack_dir", "prior_pack_dir", "period", "pack_type", "llm_model"]:
        value = getattr(args, key)
        if value:
            command.extend([f"--{key.replace('_', '-')}", value])
    if args.policy_config:
        command.extend(["--policy-config", args.policy_config])
    if args.use_llm_postprocess:
        command.append("--use-llm-postprocess")
    if args.use_historical_context:
        command.append("--use-historical-context")
    if args.historical_context:
        command.extend(["--historical-context", args.historical_context])

    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
