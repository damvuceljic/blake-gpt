from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wrapper for variance watch analysis.")
    parser.add_argument("--pack-dir", required=True, help="Normalized pack directory")
    parser.add_argument("--use-llm-postprocess", action="store_true")
    parser.add_argument("--llm-model", help="Optional model override for Codex post-processing")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    command = ["python", "scripts/analyze/variance_watch.py", "--pack-dir", args.pack_dir]
    if args.use_llm_postprocess:
        command.append("--use-llm-postprocess")
    if args.llm_model:
        command.extend(["--llm-model", args.llm_model])
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
