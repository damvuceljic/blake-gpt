from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wrapper for Hot Questions analysis.")
    parser.add_argument("--pack-dir", required=True, help="Normalized pack directory")
    parser.add_argument("--question", help="Optional executive question")
    parser.add_argument("--scoring-config", help="Optional scoring config JSON")
    parser.add_argument("--use-llm-postprocess", action="store_true")
    parser.add_argument("--require-llm-attempt", action="store_true")
    parser.add_argument("--strict-narrative", dest="strict_narrative", action="store_true", default=True)
    parser.add_argument("--no-strict-narrative", dest="strict_narrative", action="store_false")
    parser.add_argument("--challenge-card-mode", action="store_true", default=True)
    parser.add_argument("--use-historical-context", action="store_true")
    parser.add_argument("--historical-context", help="Optional historical calibration bundle path")
    parser.add_argument("--llm-model", help="Optional model override for Codex post-processing")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    command = ["python", "scripts/analyze/hot_questions.py", "--pack-dir", args.pack_dir]
    if args.question:
        command.extend(["--question", args.question])
    if args.scoring_config:
        command.extend(["--scoring-config", args.scoring_config])
    if args.use_llm_postprocess:
        command.append("--use-llm-postprocess")
    if args.require_llm_attempt:
        command.append("--require-llm-attempt")
    if args.strict_narrative:
        command.append("--strict-narrative")
    else:
        command.append("--no-strict-narrative")
    if args.challenge_card_mode:
        command.append("--challenge-card-mode")
    if args.use_historical_context:
        command.append("--use-historical-context")
    if args.historical_context:
        command.extend(["--historical-context", args.historical_context])
    if args.llm_model:
        command.extend(["--llm-model", args.llm_model])
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
