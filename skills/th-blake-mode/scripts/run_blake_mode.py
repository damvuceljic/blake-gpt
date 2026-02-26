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
    parser.add_argument("--use-llm-postprocess", action="store_true")
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
    for key in ["raw_dir", "pack_dir", "prior_pack_dir", "period", "pack_type", "llm_model"]:
        value = getattr(args, key)
        if value:
            command.extend([f"--{key.replace('_', '-')}", value])
    if args.use_llm_postprocess:
        command.append("--use-llm-postprocess")

    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

