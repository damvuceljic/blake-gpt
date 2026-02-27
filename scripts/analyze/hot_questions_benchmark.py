from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.analysis import run_hot_questions
from finance_copilot.common import repo_root, utc_now_iso, write_json

NUMERIC_RE = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?(?:mm|pp|%)?", re.IGNORECASE)
BANNED_TERM_RE = re.compile(
    r"\b(?:quality|core operating demand|elasticity risk|traffic\s*/\s*sales\s*conversion)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark nuance quality for hot-question challenge cards.")
    parser.add_argument("--pack-type", default="close", choices=["close", "preview"])
    parser.add_argument("--periods", default="2025-P12,2025-P11,2026-P01")
    parser.add_argument(
        "--golden",
        default="data/context/hot_questions_benchmark.close.json",
        help="Golden benchmark config path.",
    )
    parser.add_argument(
        "--output",
        default="data/analysis/benchmarks/hot_questions_nuance_benchmark.json",
        help="Output benchmark result path.",
    )
    return parser.parse_args()


def _score_specificity(card: dict[str, Any]) -> int:
    score = 0
    if card.get("metric") and card.get("region"):
        score += 2
    question = str(card.get("challenge_question", ""))
    basis = card.get("basis_summary", {})
    if isinstance(basis, dict):
        if str(basis.get("vs_budget", "")).lower() not in {"", "n/a"}:
            score += 1
        if str(basis.get("vs_le", "")).lower() not in {"", "n/a", "le not populated"}:
            score += 1
    if NUMERIC_RE.search(question):
        score += 1
    return min(score, 5)


def _score_causality(card: dict[str, Any]) -> int:
    text = f"{card.get('prepared_answer', '')} {card.get('why_now', '')}".lower()
    cues = ["because", "driven", "due to", "driver", "mix", "timing", "headwind", "tailwind"]
    hits = sum(1 for cue in cues if cue in text)
    if hits >= 4:
        return 5
    if hits == 3:
        return 4
    if hits == 2:
        return 3
    if hits == 1:
        return 2
    return 1


def _score_evidence_quality(card: dict[str, Any]) -> int:
    narrative_refs = card.get("narrative_evidence_refs", [])
    supplementary_refs = card.get("supplementary_evidence_refs", [])
    classes = card.get("narrative_block_classes", [])
    score = 1
    if isinstance(narrative_refs, list) and narrative_refs:
        score += 2
    if isinstance(supplementary_refs, list) and supplementary_refs:
        score += 1
    if isinstance(classes, list) and any(cls == "narrative" for cls in classes):
        score += 1
    return min(score, 5)


def _score_actionability(card: dict[str, Any]) -> int:
    verify_next = str(card.get("verify_next", "")).strip()
    prepared = str(card.get("prepared_answer", "")).strip()
    if verify_next and len(verify_next) >= 40 and prepared:
        return 5
    if verify_next and prepared:
        return 4
    if verify_next or prepared:
        return 3
    return 1


def _score_non_obviousness(card: dict[str, Any]) -> int:
    why_now = str(card.get("why_now", "")).lower()
    question = str(card.get("challenge_question", "")).lower()
    generic_markers = ["what changed", "explain variance", "why variance"]
    if any(marker in question for marker in generic_markers):
        return 2
    cues = ["le", "budget", "one-time", "structural", "assumption", "reversal"]
    hits = sum(1 for cue in cues if cue in why_now or cue in question)
    if hits >= 4:
        return 5
    if hits == 3:
        return 4
    if hits == 2:
        return 3
    return 2


def _hard_checks(cards: list[dict[str, Any]]) -> dict[str, Any]:
    missing_narrative = [
        card.get("metric", "")
        for card in cards
        if card.get("card_type") != "le_watchout" and not card.get("narrative_evidence_refs")
    ]
    missing_basis = [
        card.get("metric", "")
        for card in cards
        if card.get("card_type") != "le_watchout"
        and all(
            str(card.get("basis_summary", {}).get(key, "")).lower() in {"", "n/a", "le not populated"}
            for key in ("vs_budget", "vs_le")
        )
    ]
    bridge_only = [
        card.get("metric", "")
        for card in cards
        if card.get("card_type") != "le_watchout"
        and card.get("narrative_block_classes")
        and all(cls in {"bridge_summary", "table_like"} for cls in card.get("narrative_block_classes", []))
    ]
    citation_missing = [
        card.get("metric", "")
        for card in cards
        if card.get("card_type") != "le_watchout"
        and not any(
            isinstance(citation, dict)
            and str(citation.get("path", "")).strip()
            and str(citation.get("location", "")).strip()
            and str(citation.get("excerpt", "")).strip()
            for citation in card.get("citation_bundle", [])
        )
    ]
    banned_language = [
        card.get("metric", "")
        for card in cards
        if card.get("card_type") != "le_watchout"
        and BANNED_TERM_RE.search(
            f"{card.get('challenge_question', '')} {card.get('prepared_answer', '')}"
        )
    ]
    return {
        "narrative_evidence_per_card": {"pass": not missing_narrative, "details": missing_narrative},
        "basis_delta_presence": {"pass": not missing_basis, "details": missing_basis},
        "no_bridge_only_causal_claim": {"pass": not bridge_only, "details": bridge_only},
        "citation_bundle_per_card": {"pass": not citation_missing, "details": citation_missing},
        "banned_language_absent": {"pass": not banned_language, "details": banned_language},
    }


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    periods = [item.strip() for item in args.periods.split(",") if item.strip()]
    golden_path = Path(args.golden)
    if not golden_path.is_absolute():
        golden_path = (root / golden_path).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (root / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    golden: dict[str, Any] = {}
    if golden_path.exists():
        import json

        golden = json.loads(golden_path.read_text(encoding="utf-8"))

    min_average = float(golden.get("thresholds", {}).get("min_average", 18.0))
    min_dimension = float(golden.get("thresholds", {}).get("min_dimension", 3.0))
    reports: list[dict[str, Any]] = []

    for period in periods:
        pack_dir = root / "data" / "normalized" / period / args.pack_type
        if not pack_dir.exists():
            reports.append(
                {
                    "period": period,
                    "pack_dir": str(pack_dir),
                    "status": "missing_pack",
                }
            )
            continue

        payload = run_hot_questions(pack_dir=pack_dir, question="Benchmark nuance quality")
        cards = [card for card in payload.get("challenge_cards", []) if card.get("card_type") != "le_watchout"]
        if not cards:
            reports.append(
                {
                    "period": period,
                    "pack_dir": str(pack_dir),
                    "status": "no_cards",
                }
            )
            continue

        card_scores: list[dict[str, Any]] = []
        for card in cards:
            dim_scores = {
                "specificity": _score_specificity(card),
                "causality": _score_causality(card),
                "evidence_quality": _score_evidence_quality(card),
                "actionability": _score_actionability(card),
                "non_obviousness": _score_non_obviousness(card),
            }
            total = sum(dim_scores.values())
            card_scores.append(
                {
                    "metric": card.get("metric"),
                    "region": card.get("region"),
                    "dimension_scores": dim_scores,
                    "total": total,
                }
            )

        avg_total = round(sum(item["total"] for item in card_scores) / len(card_scores), 2)
        dim_averages = {
            dim: round(sum(item["dimension_scores"][dim] for item in card_scores) / len(card_scores), 2)
            for dim in ["specificity", "causality", "evidence_quality", "actionability", "non_obviousness"]
        }
        checks = _hard_checks(cards)
        checks_pass = all(check["pass"] for check in checks.values())
        threshold_pass = avg_total >= min_average and all(value >= min_dimension for value in dim_averages.values())
        reports.append(
            {
                "period": period,
                "pack_dir": str(pack_dir.relative_to(root).as_posix()),
                "status": "evaluated",
                "card_count": len(cards),
                "average_total_score": avg_total,
                "dimension_averages": dim_averages,
                "hard_checks": checks,
                "threshold_pass": threshold_pass,
                "hard_checks_pass": checks_pass,
                "cards": card_scores,
            }
        )

    evaluated = [item for item in reports if item.get("status") == "evaluated"]
    acceptance_pass = bool(
        evaluated
        and all(item.get("threshold_pass") and item.get("hard_checks_pass") for item in evaluated)
    )
    benchmark_payload = {
        "generated_at": utc_now_iso(),
        "pack_type": args.pack_type,
        "periods": periods,
        "thresholds": {"min_average": min_average, "min_dimension": min_dimension},
        "acceptance_pass": acceptance_pass,
        "reports": reports,
    }
    write_json(output_path, benchmark_payload)
    print(f"Benchmark report written: {output_path}")
    print(f"Acceptance pass: {acceptance_pass}")
    return 0 if acceptance_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
