from __future__ import annotations

import argparse
import json
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
        "--require-llm-attempt",
        action="store_true",
        help="Require at least one LLM post-process attempt; downgrade quality gate when unavailable.",
    )
    parser.add_argument(
        "--strict-narrative",
        dest="strict_narrative",
        action="store_true",
        default=True,
        help="Enforce strict narrative challenge-card quality checks (default true).",
    )
    parser.add_argument(
        "--no-strict-narrative",
        dest="strict_narrative",
        action="store_false",
        help="Disable strict narrative quality gating overrides.",
    )
    parser.add_argument(
        "--challenge-card-mode",
        action="store_true",
        default=True,
        help="Generate challenge-card output mode (default true).",
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


def _try_parse_json_block(text: str) -> dict | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = raw[start : end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _append_quality_check(payload: dict, *, check: str, status: str, message: str) -> None:
    gate = payload.setdefault("quality_gate", {"status": "pass", "checks": []})
    checks = gate.setdefault("checks", [])
    checks.append({"check": check, "status": status, "message": message})
    if status == "fail":
        current_status = str(gate.get("status", "pass"))
        if current_status != "fail":
            gate["status"] = "downgraded_llm"


def _merge_variance_llm(payload: dict, parsed_variance: dict) -> bool:
    answers = parsed_variance.get("answers")
    if not isinstance(answers, list):
        return False

    cards = payload.get("challenge_cards")
    if not isinstance(cards, list):
        return False

    changed = False
    for card in cards:
        if not isinstance(card, dict):
            continue
        metric = str(card.get("metric", "")).strip().lower()
        if not metric:
            continue
        match = None
        for item in answers:
            if not isinstance(item, dict):
                continue
            if str(item.get("metric", "")).strip().lower() == metric:
                match = item
                break
        if not match:
            continue

        llm_answer = str(match.get("answer", "")).strip()
        if llm_answer:
            base_answer = str(card.get("prepared_answer", "")).strip()
            card["prepared_answer"] = f"{base_answer} LLM explainer: {llm_answer}".strip()
            changed = True

        llm_confidence = str(match.get("confidence", "")).strip().lower()
        if llm_confidence in {"high", "medium", "low"}:
            card["confidence"] = llm_confidence
            changed = True

        refs = match.get("supplementary_evidence_refs", [])
        if isinstance(refs, list):
            merged_refs = [str(ref) for ref in refs if str(ref).strip()]
            if merged_refs:
                existing = [str(ref) for ref in card.get("supplementary_evidence_refs", []) if str(ref).strip()]
                card["supplementary_evidence_refs"] = sorted(set([*existing, *merged_refs]))[:8]
                changed = True

    if changed:
        payload["anticipated_hot_questions"] = [
            {
                "question": str(card.get("challenge_question", "")),
                "answer": f"{card.get('prepared_answer', '')} Verify next: {card.get('verify_next', '')}",
            }
            for card in cards
            if isinstance(card, dict)
        ]
    return changed


def _path_for_payload(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root).as_posix())
    except ValueError:
        return str(path.as_posix())


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

    if args.strict_narrative:
        gate = payload.get("quality_gate", {})
        if isinstance(gate, dict) and gate.get("status") == "downgraded_narrative_gap":
            payload.setdefault("warnings", []).append(
                "Narrative quality gate downgraded: one or more cards have weak narrative causal support."
            )

    llm_attempted = False
    llm_required = bool(args.require_llm_attempt)
    llm_requested = bool(args.use_llm_postprocess) or llm_required
    if llm_requested:
        llm_attempted = True
        deterministic_path = output_path.with_name(f"{output_path.stem}.deterministic.json")
        llm_output_path = output_path.with_name(f"{output_path.stem}.llm.json")
        variance_output_path = output_path.with_name(f"{output_path.stem}.variance_explainer.llm.json")
        persist_analysis(payload, deterministic_path)
        llm_payload = run_llm_postprocess(
            repo_root=root,
            prompt_file=root / "prompts" / "hot_questions" / "executive_brief_prompt.txt",
            input_json=deterministic_path,
            output_json=llm_output_path,
            model=args.llm_model,
        )
        variance_llm_payload = run_llm_postprocess(
            repo_root=root,
            prompt_file=root / "prompts" / "hot_questions" / "variance_explainer_prompt.txt",
            input_json=deterministic_path,
            output_json=variance_output_path,
            model=args.llm_model,
        )
        parsed_variance = _try_parse_json_block(str(variance_llm_payload.get("response_text", "")))
        llm_failed = False
        llm_failure_reasons: list[str] = []
        if int(llm_payload.get("wrapper_returncode", 0)) != 0 or int(llm_payload.get("returncode", 0)) != 0:
            llm_failed = True
            llm_failure_reasons.append("executive_brief call failed")
        if int(variance_llm_payload.get("wrapper_returncode", 0)) != 0 or int(variance_llm_payload.get("returncode", 0)) != 0:
            llm_failed = True
            llm_failure_reasons.append("variance_explainer call failed")
        if parsed_variance is None:
            llm_failed = True
            llm_failure_reasons.append("variance_explainer parse failed")
        merged = False
        if parsed_variance is not None:
            merged = _merge_variance_llm(payload, parsed_variance)
            if not merged:
                llm_failed = True
                llm_failure_reasons.append("variance_explainer did not map to challenge cards")

        payload["llm_postprocess"] = {
            "enabled": True,
            "attempted": llm_attempted,
            "required_attempt": llm_required,
            "executive_brief": {
                "result_path": _path_for_payload(llm_output_path, root),
                "returncode": llm_payload.get("returncode"),
                "response_text": llm_payload.get("response_text", ""),
            },
            "variance_explainer": {
                "result_path": _path_for_payload(variance_output_path, root),
                "returncode": variance_llm_payload.get("returncode"),
                "response_text": variance_llm_payload.get("response_text", ""),
                "parsed_json": parsed_variance or {},
            },
        }
        if llm_failed:
            reason = "; ".join(llm_failure_reasons)
            payload.setdefault("warnings", []).append(
                f"LLM variance explainer unavailable or invalid ({reason}); using deterministic challenge cards."
            )
            _append_quality_check(
                payload,
                check="llm_variance_explainer",
                status="fail",
                message=f"LLM pass failed: {reason}",
            )
        else:
            _append_quality_check(
                payload,
                check="llm_variance_explainer",
                status="pass",
                message="LLM pass succeeded and was merged into challenge cards.",
            )
    elif llm_required:
        payload.setdefault("warnings", []).append(
            "LLM attempt was required but not executed; using deterministic challenge cards only."
        )
        _append_quality_check(
            payload,
            check="llm_variance_explainer",
            status="fail",
            message="LLM attempt required but not executed.",
        )

    payload.setdefault("execution_mode", {})
    payload["execution_mode"]["challenge_card_mode"] = bool(args.challenge_card_mode)
    payload["execution_mode"]["strict_narrative"] = bool(args.strict_narrative)

    persist_analysis(payload, output_path)
    print(f"Hot Questions output written: {output_path}")
    print(f"Score: {payload.get('score_total')} ({payload.get('score_band')})")
    print(f"Confidence: {payload['confidence']}")
    if payload.get("quality_gate"):
        print(f"Quality gate: {payload['quality_gate'].get('status')}")
    if payload.get("clarifying_question"):
        print(f"Clarifier: {payload['clarifying_question']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
