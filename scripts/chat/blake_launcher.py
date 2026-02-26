from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import repo_root
from finance_copilot.intake import build_pack_manifest, is_processed_intake_dir


def _run(command: list[str], cwd: Path) -> int:
    result = subprocess.run(command, cwd=cwd, check=False, text=True, capture_output=True)
    print(f"\n$ {' '.join(command)}")
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    return result.returncode


def _prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or default


def _yes_no(text: str, default_yes: bool = False) -> bool:
    default = "y" if default_yes else "n"
    value = _prompt(f"{text} (y/n)", default=default).lower()
    return value in {"y", "yes"}


def _latest_raw_dir(root: Path) -> Path | None:
    base = root / "data" / "intake"
    candidates = sorted(
        [
            path
            for path in base.glob("*/*/raw")
            if path.is_dir() and any(path.iterdir())
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _latest_pack_dir(root: Path) -> Path | None:
    base = root / "data" / "normalized"
    candidates = sorted(
        [
            path
            for path in base.glob("*/*")
            if path.is_dir() and (path / "pack_summary.json").exists()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _resolve_dir(root: Path, raw_text: str) -> Path:
    path = Path(raw_text)
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def _build_pair_choice_interactively(
    root: Path, raw_dir: Path, period: str, pack_type: str
) -> Path | None:
    manifest = build_pack_manifest(
        raw_dir=raw_dir,
        root=root,
        period=period,
        pack_type=pack_type,
        strict_core=True,
        allow_missing_core=True,
    )
    pair_choice_pairs = manifest.get("core_validation", {}).get("pair_choice_required_pairs", [])
    if not pair_choice_pairs:
        return None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest.get("files", []):
        if not str(entry.get("role", "")).endswith("_offline_workbook"):
            continue
        if str(entry.get("pairing_status", "")) != "offline_choice_required":
            continue
        grouped.setdefault(str(entry.get("pair_key", "")), []).append(entry)

    selections: dict[str, str] = {}
    for pair_key, candidates in sorted(grouped.items()):
        print(f"\nOffline choice required for pair '{pair_key}':")
        for idx, candidate in enumerate(candidates, start=1):
            print(f"  {idx}. {candidate.get('file_name', '')}")
        chosen = _prompt("Select primary offline file number", default="1")
        try:
            selected_idx = max(1, min(len(candidates), int(chosen))) - 1
        except Exception:
            selected_idx = 0
        selections[pair_key] = str(candidates[selected_idx].get("file_name", ""))

    pair_choice_path = raw_dir.parent / "pair_choices.json"
    pair_choice_path.write_text(json.dumps(selections, indent=2), encoding="utf-8")
    print(f"Pair choices saved: {pair_choice_path}")
    return pair_choice_path


def _ingest(root: Path) -> None:
    latest_raw = _latest_raw_dir(root)
    default_raw = str(latest_raw) if latest_raw else "data/intake/<period>/<pack_type>/raw"
    raw_dir = _resolve_dir(root, _prompt("Raw intake directory", default=default_raw))
    if not raw_dir.exists():
        print(f"Raw directory not found: {raw_dir}")
        return
    if is_processed_intake_dir(raw_dir, root):
        print("Processed folders cannot be used as raw intake input.")
        return

    period = _prompt("Period (YYYY-PNN)", default=raw_dir.parents[1].name if len(raw_dir.parts) >= 2 else "")
    pack_type = _prompt("Pack type (preview|close)", default=raw_dir.parent.name if raw_dir.parent.name in {"preview", "close"} else "preview")
    use_llm = _yes_no("Use LLM post-processing", default_yes=False)
    use_historical = _yes_no("Use historical calibration context", default_yes=True)

    pair_choice_input = _prompt("Pair choice JSON path (leave blank to auto-create if needed)", default="")
    pair_choice_path: Path | None = None
    if pair_choice_input:
        pair_choice_path = _resolve_dir(root, pair_choice_input)
    else:
        pair_choice_path = _build_pair_choice_interactively(root, raw_dir, period=period, pack_type=pack_type)

    command = [
        sys.executable,
        "scripts/intake/process_month.py",
        "--raw-dir",
        str(raw_dir),
        "--period",
        period,
        "--pack-type",
        pack_type,
        "--strict-core",
    ]
    if pair_choice_path:
        command.extend(["--pair-choice-file", str(pair_choice_path)])
    if use_llm:
        command.append("--use-llm-postprocess")
    if use_historical:
        command.append("--use-historical-context")
    _run(command, root)


def _hot_question(root: Path) -> None:
    default_pack = _latest_pack_dir(root)
    pack_dir = _resolve_dir(root, _prompt("Pack dir", default=str(default_pack) if default_pack else "data/normalized/<period>/<pack_type>"))
    question = _prompt("Question", default="What are the top risks this month?")
    use_llm = _yes_no("Use LLM post-processing", default_yes=False)
    use_historical = _yes_no("Use historical calibration context", default_yes=True)
    command = [
        sys.executable,
        "scripts/analyze/hot_questions.py",
        "--pack-dir",
        str(pack_dir),
        "--question",
        question,
    ]
    if use_llm:
        command.append("--use-llm-postprocess")
    if use_historical:
        command.append("--use-historical-context")
    _run(command, root)


def _proof_deck(root: Path) -> None:
    default_pack = _latest_pack_dir(root)
    pack_dir = _resolve_dir(root, _prompt("Pack dir", default=str(default_pack) if default_pack else "data/normalized/<period>/<pack_type>"))
    use_llm = _yes_no("Use LLM post-processing", default_yes=False)
    command = [sys.executable, "scripts/analyze/deck_proofing.py", "--pack-dir", str(pack_dir)]
    if use_llm:
        command.append("--use-llm-postprocess")
    _run(command, root)


def _variance_watch(root: Path) -> None:
    default_pack = _latest_pack_dir(root)
    pack_dir = _resolve_dir(root, _prompt("Pack dir", default=str(default_pack) if default_pack else "data/normalized/<period>/<pack_type>"))
    use_llm = _yes_no("Use LLM post-processing", default_yes=False)
    command = [sys.executable, "scripts/analyze/variance_watch.py", "--pack-dir", str(pack_dir)]
    if use_llm:
        command.append("--use-llm-postprocess")
    _run(command, root)


def _compare_prior(root: Path) -> None:
    default_pack = _latest_pack_dir(root)
    pack_dir = _resolve_dir(root, _prompt("Current pack dir", default=str(default_pack) if default_pack else "data/normalized/<period>/<pack_type>"))
    command = [
        sys.executable,
        "scripts/chat/blake_mode.py",
        "--message",
        "compare prior month deck proofing",
        "--pack-dir",
        str(pack_dir),
    ]
    _run(command, root)


def _health_checks(root: Path) -> None:
    commands = [
        [sys.executable, "skills/th-repo-guardrails/scripts/guardrail_check.py"],
        [sys.executable, "-m", "pytest", "-q"],
        ["codex", "login", "status"],
    ]
    for command in commands:
        _run(command, root)


def _menu() -> None:
    print("\nBlake Guided Launcher")
    print("1. Ingest month")
    print("2. Ask hot question")
    print("3. Proof deck")
    print("4. Run variance watch")
    print("5. Compare prior month")
    print("6. Run health checks")
    print("0. Exit")


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows-first guided launcher for Blake Finance Copilot.")
    parser.parse_args()
    root = repo_root(REPO_ROOT)

    actions = {
        "1": _ingest,
        "2": _hot_question,
        "3": _proof_deck,
        "4": _variance_watch,
        "5": _compare_prior,
        "6": _health_checks,
    }
    while True:
        _menu()
        choice = _prompt("Select action", default="0")
        if choice == "0":
            return 0
        action = actions.get(choice)
        if not action:
            print("Invalid choice.")
            continue
        action(root)


if __name__ == "__main__":
    raise SystemExit(main())
