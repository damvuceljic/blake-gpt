from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import read_json, write_json

DEFAULT_PROVIDER_LOCK = "codex_chatgpt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run codex exec on curated context and persist the model response.")
    parser.add_argument("--prompt-file", help="Prompt template file path")
    parser.add_argument("--prompt", help="Inline prompt text (used if prompt-file omitted)")
    parser.add_argument("--input-json", help="Optional JSON context file appended to prompt")
    parser.add_argument("--output", required=True, help="Output JSON path for model response")
    parser.add_argument("--model", help="Optional model name passed to codex exec")
    parser.add_argument(
        "--provider-lock",
        default=DEFAULT_PROVIDER_LOCK,
        choices=["codex_chatgpt", "allow_any"],
        help="Lock provider mode. codex_chatgpt requires ChatGPT login and avoids API-key dependency.",
    )
    return parser.parse_args()


def _load_dotenv(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_val = stripped.split("=", 1)
        key = key.strip()
        value = raw_val.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def _load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.is_absolute():
            prompt_path = (REPO_ROOT / prompt_path).resolve()
        prompt_text = prompt_path.read_text(encoding="utf-8")
    elif args.prompt:
        prompt_text = args.prompt
    else:
        raise ValueError("Either --prompt-file or --prompt must be provided.")

    if args.input_json:
        input_path = Path(args.input_json)
        if not input_path.is_absolute():
            input_path = (REPO_ROOT / input_path).resolve()
        context_payload = read_json(input_path)
        prompt_text += "\n\n<context_json>\n"
        prompt_text += str(context_payload)
        prompt_text += "\n</context_json>\n"
    return prompt_text


def _run_login_status() -> tuple[int, str, str]:
    result = subprocess.run(
        ["codex", "login", "status"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _preflight_provider_lock(provider_lock: str) -> dict[str, Any]:
    code, stdout, stderr = _run_login_status()
    combined = "\n".join([stdout, stderr]).strip().lower()
    details = {
        "login_status_returncode": code,
        "login_status_stdout": stdout,
        "login_status_stderr": stderr,
    }
    if code != 0:
        details["ok"] = False
        details["reason"] = (
            "Failed to read codex login status. Run `codex login` and verify "
            "`codex login status` returns `Logged in using ChatGPT`."
        )
        return details

    if provider_lock == "codex_chatgpt":
        if "logged in using chatgpt" not in combined:
            details["ok"] = False
            details["reason"] = (
                "Provider lock requires ChatGPT login. Current status is not ChatGPT login."
            )
            return details
        if os.environ.get("OPENAI_API_KEY"):
            details["ok"] = False
            details["reason"] = (
                "OPENAI_API_KEY is set while provider lock is codex_chatgpt. "
                "Unset API-key env for this workflow to avoid accidental API-token routing."
            )
            return details

    details["ok"] = True
    details["reason"] = "Provider preflight passed."
    return details


def main() -> int:
    dotenv_values = _load_dotenv(REPO_ROOT / ".env")
    for key, value in dotenv_values.items():
        if key not in os.environ:
            os.environ[key] = value

    args = parse_args()
    provider_lock = os.environ.get("BLAKE_LLM_PROVIDER_LOCK", args.provider_lock)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (REPO_ROOT / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_response = output_path.with_suffix(".tmp.txt")

    preflight = _preflight_provider_lock(provider_lock)
    if not preflight.get("ok", False):
        payload = {
            "command": [],
            "returncode": 2,
            "stdout": "",
            "stderr": preflight["reason"],
            "response_text": "",
            "provider_lock": provider_lock,
            "preflight": preflight,
        }
        write_json(output_path, payload)
        print(preflight["reason"])
        return 2

    prompt_text = _load_prompt(args)
    command = ["codex", "exec", "--skip-git-repo-check", "-o", str(temp_response), "-"]
    if args.model:
        command.extend(["-m", args.model])

    status = subprocess.run(command, input=prompt_text, text=True, capture_output=True, check=False)
    response_text = temp_response.read_text(encoding="utf-8") if temp_response.exists() else ""
    payload = {
        "command": command,
        "returncode": status.returncode,
        "stdout": status.stdout,
        "stderr": status.stderr,
        "response_text": response_text.strip(),
        "provider_lock": provider_lock,
        "preflight": preflight,
    }
    write_json(output_path, payload)
    if temp_response.exists():
        temp_response.unlink()

    print(f"codex exec return code: {status.returncode}")
    print(f"Response persisted to: {output_path}")
    return status.returncode


if __name__ == "__main__":
    raise SystemExit(main())
