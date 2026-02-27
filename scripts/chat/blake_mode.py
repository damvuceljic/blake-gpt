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

from finance_copilot.common import ensure_dir, read_json, repo_root, utc_now_iso
from finance_copilot.intake import (
    is_processed_intake_dir,
    list_unsupported_intake_files,
    unsupported_intake_message,
)

SKILL_TO_INTENT = {
    "$th-intake-router": "ingest",
    "$th-hot-questions": "hot_questions",
    "$th-deck-proofing": "proofing",
    "$th-variance-watch": "variance_watch",
    "$th-blake-mode": "router",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Chat-first workflow router for Blake. Recommended entry point is "
            "$th-blake-mode <request>."
        )
    )
    parser.add_argument("--message", required=True, help="Natural language user request.")
    parser.add_argument("--raw-dir", help="Optional explicit raw intake directory.")
    parser.add_argument("--pack-dir", help="Optional explicit normalized pack directory.")
    parser.add_argument("--prior-pack-dir", help="Optional prior pack for compare/proofing workflows.")
    parser.add_argument("--period", help="Optional period for ingestion routing.")
    parser.add_argument("--pack-type", choices=["preview", "close"], help="Optional pack type for ingestion routing.")
    parser.add_argument("--region", default="TH C&US", help="Region label for ingestion workflow.")
    parser.add_argument("--source-mode", default="both", choices=["offline_values", "lineage", "both"])
    parser.add_argument(
        "--strict-core",
        dest="strict_core",
        action="store_true",
        default=True,
        help="Enforce strict core intake requirements.",
    )
    parser.add_argument(
        "--no-strict-core",
        dest="strict_core",
        action="store_false",
        help="Disable strict core requirements.",
    )
    parser.add_argument("--allow-missing-core", action="store_true")
    parser.add_argument("--pair-choice-file", help="JSON mapping pair_key to selected offline workbook.")
    parser.add_argument(
        "--policy-config",
        default="data/context/hot_questions_policy.default.json",
        help="Hot questions policy config path.",
    )
    parser.add_argument("--use-llm-postprocess", action="store_true")
    parser.add_argument("--use-historical-context", action="store_true")
    parser.add_argument("--historical-context", help="Optional explicit historical calibration bundle path.")
    parser.add_argument("--llm-model", help="Optional model override for LLM post-processing.")
    return parser.parse_args()


def _run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _iter_candidate_raw_dirs(root: Path) -> list[Path]:
    base = root / "data" / "intake"
    return sorted(
        [path for path in base.glob("*/*/raw") if path.is_dir() and any(path.iterdir())],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _latest_normalized_pack(root: Path) -> Path | None:
    base = root / "data" / "normalized"
    candidates = [path for path in base.glob("*/*") if path.is_dir() and (path / "pack_summary.json").exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _previous_pack(root: Path, current_pack_dir: Path) -> Path | None:
    base = root / "data" / "normalized"
    pack_type = current_pack_dir.name
    candidates = [path for path in base.glob(f"*/*") if path.is_dir() and path.name == pack_type]
    candidates = sorted(candidates, key=lambda p: p.parts[-2])
    if current_pack_dir not in candidates:
        return None
    idx = candidates.index(current_pack_dir)
    if idx <= 0:
        return None
    return candidates[idx - 1]


def _infer_intent(message: str) -> str:
    text = message.lower()
    if any(token in text for token in ["ingest", "intake", "process month", "new files", "load files"]):
        return "ingest"
    if any(token in text for token in ["hot questions", "top risks", "what are my risks", "executive brief"]):
        return "hot_questions"
    if any(token in text for token in ["proof", "proofing", "deck review", "review this deck"]):
        return "proofing"
    if any(token in text for token in ["variance", "bridge integrity", "reconcile"]):
        return "variance_watch"
    if any(token in text for token in ["compare", "prior month", "month-over-month", "month over month"]):
        return "compare"
    return "hot_questions"


def _extract_skill_prefix(message: str) -> tuple[str, str]:
    stripped = message.strip()
    if not stripped:
        return "", ""
    first, _, remainder = stripped.partition(" ")
    if first.startswith("$"):
        return first.strip(), remainder.strip()
    return "", stripped


def _write_log(root: Path, pack_dir: Path | None, payload: dict[str, Any]) -> None:
    if pack_dir and len(pack_dir.parts) >= 2:
        period = pack_dir.parts[-2]
        pack_type = pack_dir.parts[-1]
        log_dir = ensure_dir(root / "data" / "analysis" / period / pack_type)
    else:
        log_dir = ensure_dir(root / "data" / "analysis")
    log_path = log_dir / "blake_mode_log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True))
        handle.write("\n")


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    skill_token, routed_message = _extract_skill_prefix(args.message)
    if not skill_token:
        print(
            "Message must start with a skill token. Recommended: "
            "$th-blake-mode <request>. "
            "Also supported: $th-intake-router, $th-hot-questions, $th-deck-proofing, $th-variance-watch."
        )
        return 2
    if skill_token not in SKILL_TO_INTENT:
        print(f"Unsupported skill token: {skill_token}")
        print("Supported: " + ", ".join(sorted(SKILL_TO_INTENT.keys())))
        return 2

    if SKILL_TO_INTENT[skill_token] == "router":
        intent = _infer_intent(routed_message)
    else:
        intent = SKILL_TO_INTENT[skill_token]

    actions: list[dict[str, Any]] = []
    pack_dir: Path | None = None

    if intent == "ingest":
        raw_dir = Path(args.raw_dir) if args.raw_dir else None
        if raw_dir and not raw_dir.is_absolute():
            raw_dir = (root / raw_dir).resolve()
        if not raw_dir:
            raw_candidates = _iter_candidate_raw_dirs(root)
            if not raw_candidates:
                print("No raw intake folder with files found. Provide --raw-dir.")
                return 2
            raw_dir = raw_candidates[0]
        if is_processed_intake_dir(raw_dir, root):
            print("Processed intake folders cannot be used as --raw-dir.")
            return 2
        unsupported = list_unsupported_intake_files(raw_dir)
        if unsupported:
            print(f"[intake-error] {unsupported_intake_message(unsupported)}")
            return 2
        command = [
            sys.executable,
            "scripts/intake/process_month.py",
            "--raw-dir",
            str(raw_dir),
            "--region",
            args.region,
            "--source-mode",
            args.source_mode,
            "--question",
            routed_message or "Process this monthly intake.",
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
        if args.use_llm_postprocess:
            command.append("--use-llm-postprocess")
        if args.use_historical_context:
            command.append("--use-historical-context")
        if args.historical_context:
            command.extend(["--historical-context", args.historical_context])
        if args.llm_model:
            command.extend(["--llm-model", args.llm_model])
        result = _run_command(command, root)
        actions.append(result)
        pack_dir = _latest_normalized_pack(root)

    elif intent == "proofing":
        pack_dir = Path(args.pack_dir) if args.pack_dir else _latest_normalized_pack(root)
        if not pack_dir:
            print("No normalized pack found. Run ingestion first.")
            return 2
        if not pack_dir.is_absolute():
            pack_dir = (root / pack_dir).resolve()
        command = [sys.executable, "scripts/analyze/deck_proofing.py", "--pack-dir", str(pack_dir)]
        prior = Path(args.prior_pack_dir) if args.prior_pack_dir else _previous_pack(root, pack_dir)
        if prior:
            if not prior.is_absolute():
                prior = (root / prior).resolve()
            command.extend(["--prior-pack-dir", str(prior)])
        if args.use_llm_postprocess:
            command.append("--use-llm-postprocess")
        if args.llm_model:
            command.extend(["--llm-model", args.llm_model])
        actions.append(_run_command(command, root))

    elif intent == "variance_watch":
        pack_dir = Path(args.pack_dir) if args.pack_dir else _latest_normalized_pack(root)
        if not pack_dir:
            print("No normalized pack found. Run ingestion first.")
            return 2
        if not pack_dir.is_absolute():
            pack_dir = (root / pack_dir).resolve()
        command = [sys.executable, "scripts/analyze/variance_watch.py", "--pack-dir", str(pack_dir)]
        if args.use_llm_postprocess:
            command.append("--use-llm-postprocess")
        if args.llm_model:
            command.extend(["--llm-model", args.llm_model])
        actions.append(_run_command(command, root))

    elif intent == "compare":
        pack_dir = Path(args.pack_dir) if args.pack_dir else _latest_normalized_pack(root)
        if not pack_dir:
            print("No normalized pack found. Run ingestion first.")
            return 2
        if not pack_dir.is_absolute():
            pack_dir = (root / pack_dir).resolve()
        prior = Path(args.prior_pack_dir) if args.prior_pack_dir else _previous_pack(root, pack_dir)
        if not prior:
            print("No prior pack found for comparison.")
            return 2
        if not prior.is_absolute():
            prior = (root / prior).resolve()
        command = [
            sys.executable,
            "scripts/analyze/deck_proofing.py",
            "--pack-dir",
            str(pack_dir),
            "--prior-pack-dir",
            str(prior),
        ]
        if args.use_llm_postprocess:
            command.append("--use-llm-postprocess")
        if args.llm_model:
            command.extend(["--llm-model", args.llm_model])
        actions.append(_run_command(command, root))

    else:
        pack_dir = Path(args.pack_dir) if args.pack_dir else _latest_normalized_pack(root)
        if not pack_dir:
            print("No normalized pack found. Run ingestion first.")
            return 2
        if not pack_dir.is_absolute():
            pack_dir = (root / pack_dir).resolve()
        command = [
            sys.executable,
            "scripts/analyze/hot_questions.py",
            "--pack-dir",
            str(pack_dir),
            "--question",
            routed_message or "Prepare me for likely hot questions from deck variances.",
        ]
        # Hot-question workflows enforce challenge-card + strict narrative mode with required LLM attempt.
        command.extend(["--challenge-card-mode", "--strict-narrative", "--require-llm-attempt"])
        if args.policy_config:
            command.extend(["--policy-config", args.policy_config])
        command.append("--use-llm-postprocess")
        if args.use_historical_context:
            command.append("--use-historical-context")
        if args.historical_context:
            command.extend(["--historical-context", args.historical_context])
        if args.llm_model:
            command.extend(["--llm-model", args.llm_model])
        actions.append(_run_command(command, root))

    combined_returncode = 0 if all(action["returncode"] == 0 for action in actions) else 2
    log_payload = {
        "timestamp": utc_now_iso(),
        "skill": skill_token,
        "intent": intent,
        "message": args.message,
        "routed_message": routed_message,
        "pack_dir": str(pack_dir) if pack_dir else "",
        "actions": actions,
        "combined_returncode": combined_returncode,
    }
    _write_log(root, pack_dir, log_payload)

    print(f"Intent: {intent}")
    for idx, action in enumerate(actions, start=1):
        print(f"[action-{idx}] returncode={action['returncode']}")
        if action["stdout"]:
            print(action["stdout"])
        if action["stderr"]:
            print(action["stderr"])
    return combined_returncode


if __name__ == "__main__":
    raise SystemExit(main())
