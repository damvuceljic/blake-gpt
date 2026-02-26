from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from finance_copilot.common import read_json


def run_llm_postprocess(
    *,
    repo_root: Path,
    prompt_file: Path,
    input_json: Path,
    output_json: Path,
    model: str | None = None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "scripts/llm/run_codex_exec.py",
        "--prompt-file",
        str(prompt_file),
        "--input-json",
        str(input_json),
        "--output",
        str(output_json),
    ]
    if model:
        command.extend(["--model", model])

    result = subprocess.run(command, cwd=repo_root, check=False, capture_output=True, text=True)
    payload = read_json(output_json) if output_json.exists() else {}
    payload["wrapper_returncode"] = result.returncode
    payload["wrapper_stdout"] = result.stdout
    payload["wrapper_stderr"] = result.stderr
    return payload

