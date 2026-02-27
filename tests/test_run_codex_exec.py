from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from finance_copilot.common import write_json
from scripts.llm import run_codex_exec


def test_load_prompt_serializes_context_as_json(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    input_json = tmp_path / "context.json"
    prompt_file.write_text("Prompt header", encoding="utf-8")
    write_json(input_json, {"message": "caf\u00e9", "word": "na\u00efve"})

    args = Namespace(
        prompt_file=str(prompt_file),
        prompt=None,
        input_json=str(input_json),
    )
    prompt = run_codex_exec._load_prompt(args)

    assert "<context_json>" in prompt
    assert "\"message\": \"caf\u00e9\"" in prompt
    assert "\"word\": \"na\u00efve\"" in prompt
    assert "'message':" not in prompt
