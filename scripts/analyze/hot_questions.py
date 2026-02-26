from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.analysis import (
    load_hotq_scoring_config,
    persist_analysis,
    run_hot_questions,
)
from finance_copilot.common import read_json, repo_root
from finance_copilot.llm_postprocess import run_llm_postprocess


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate CFO-style hot-questions output from normalized pack data.")
    parser.add_argument("--pack-dir", required=True, help="Normalized pack directory")
    parser.add_argument("--question", help="Optional specific executive question for focus")
    parser.add_argument(
        "--output",
        help="Output JSON path; defaults to data/analysis/<period>/<pack_type>/hot_questions_response.json",
    )
    parser.add_argument(
        "--scoring-config",
        help="Optional scoring config JSON. Defaults to data/context/hot_questions_scoring.default.json",
    )
    parser.add_argument(
        "--use-llm-postprocess",
        action="store_true",
        help="Run optional LLM post-processing via codex exec using ChatGPT login.",
    )
    parser.add_argument(
        "--use-historical-context",
        action="store_true",
        help="Inject historical calibration bundle from data/context/historical/calibration_bundle.json when available.",
    )
    parser.add_argument("--historical-context", help="Optional explicit historical calibration bundle path.")
    parser.add_argument("--llm-model", help="Optional model override for codex exec post-processing")
    return parser.parse_args()


def _infer_period_pack(pack_dir: Path) -> tuple[str, str]:
    parts = pack_dir.parts
    if len(parts) < 2:
        return ("unknown-period", "unknown-pack")
    return parts[-2], parts[-1]


def _load_month_override(root: Path, period: str) -> dict | None:
    override_path = root / "data" / "context" / "month_overrides" / f"{period}.json"
    if override_path.exists():
        return read_json(override_path)
    return None


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    pack_dir = Path(args.pack_dir)
    if not pack_dir.is_absolute():
        pack_dir = (root / pack_dir).resolve()

    period, pack_type = _infer_period_pack(pack_dir)
    if args.scoring_config:
        scoring_path = Path(args.scoring_config)
        if not scoring_path.is_absolute():
            scoring_path = (root / scoring_path).resolve()
    else:
        scoring_path = root / "data" / "context" / "hot_questions_scoring.default.json"

    scoring_config = load_hotq_scoring_config(scoring_path if scoring_path.exists() else None)
    month_override = _load_month_override(root, period)
    historical_context = None
    if args.historical_context:
        historical_path = Path(args.historical_context)
        if not historical_path.is_absolute():
            historical_path = (root / historical_path).resolve()
        if historical_path.exists():
            historical_context = read_json(historical_path)
    elif args.use_historical_context:
        default_historical = root / "data" / "context" / "historical" / "calibration_bundle.json"
        if default_historical.exists():
            historical_context = read_json(default_historical)

    payload = run_hot_questions(
        pack_dir=pack_dir,
        question=args.question,
        scoring_config=scoring_config,
        month_override=month_override,
        historical_context=historical_context,
    )
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (root / output_path).resolve()
    else:
        output_path = root / "data" / "analysis" / period / pack_type / "hot_questions_response.json"

    if args.use_llm_postprocess:
        deterministic_path = output_path.with_name(f"{output_path.stem}.deterministic.json")
        llm_output_path = output_path.with_name(f"{output_path.stem}.llm.json")
        persist_analysis(payload, deterministic_path)
        llm_payload = run_llm_postprocess(
            repo_root=root,
            prompt_file=root / "prompts" / "hot_questions" / "executive_brief_prompt.txt",
            input_json=deterministic_path,
            output_json=llm_output_path,
            model=args.llm_model,
        )
        payload["llm_postprocess"] = {
            "enabled": True,
            "result_path": str(llm_output_path.relative_to(root).as_posix()),
            "returncode": llm_payload.get("returncode"),
            "response_text": llm_payload.get("response_text", ""),
        }

    persist_analysis(payload, output_path)
    print(f"Hot Questions output written: {output_path}")
    print(f"Score: {payload.get('score_total')} ({payload.get('score_band')})")
    print(f"Confidence: {payload['confidence']}")
    if payload.get("clarifying_question"):
        print(f"Clarifier: {payload['clarifying_question']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
