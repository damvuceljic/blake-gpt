from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from typing import Any
from pathlib import Path

from finance_copilot.common import read_json, utc_now_iso, write_json

DEFAULT_HOTQ_SCORING_CONFIG: dict[str, Any] = {
    "weights": {
        "pnl_delivery": 30,
        "variance_explainability": 25,
        "forecast_reliability": 20,
        "narrative_integrity": 15,
        "data_confidence": 10,
    },
    "thresholds": {"green_min": 80, "yellow_min": 65},
    "materiality": {"currency_mm": 0.5, "percent": 1.0},
    "penalties": {
        "lineage_degraded": 10,
        "notes_missing_ratio_high": 8,
        "missing_pack_components": 25,
    },
}


@dataclass
class Issue:
    location: str
    issue_type: str
    description: str
    severity: str
    recommended_fix: str
    evidence_refs: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "issue_type": self.issue_type,
            "description": self.description,
            "severity": self.severity,
            "recommended_fix": self.recommended_fix,
            "evidence_refs": self.evidence_refs,
        }


def _iter_slide_files(pack_dir: Path) -> list[Path]:
    return sorted(pack_dir.glob("decks/*/slides/slide_*.json"))


def _iter_workbook_meta(pack_dir: Path) -> list[Path]:
    return sorted(pack_dir.glob("workbooks/*/workbook_meta.json"))


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def _score_band(score_total: float, thresholds: dict[str, Any]) -> str:
    green_min = float(thresholds.get("green_min", 80))
    yellow_min = float(thresholds.get("yellow_min", 65))
    if score_total >= green_min:
        return "Green"
    if score_total >= yellow_min:
        return "Yellow"
    return "Red"


def _merge_dict(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return dict(base)
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def load_hotq_scoring_config(config_path: Path | None = None) -> dict[str, Any]:
    if config_path and config_path.exists():
        user_config = read_json(config_path)
        config = _merge_dict(DEFAULT_HOTQ_SCORING_CONFIG, user_config)
    else:
        config = dict(DEFAULT_HOTQ_SCORING_CONFIG)
    weights = config.get("weights", {})
    total_weight = sum(float(weights.get(name, 0)) for name in DEFAULT_HOTQ_SCORING_CONFIG["weights"])
    if total_weight <= 0:
        raise ValueError("Invalid scoring config: sum of weights must be greater than zero.")
    return config


def _infer_period_from_pack_dir(pack_dir: Path) -> str:
    parts = pack_dir.parts
    if len(parts) >= 2:
        return parts[-2]
    return "unknown-period"


def _infer_pack_type_from_pack_dir(pack_dir: Path) -> str:
    parts = pack_dir.parts
    if parts:
        return parts[-1]
    return "unknown-pack"


def _read_pack_summary(pack_dir: Path) -> dict[str, Any]:
    summary_path = pack_dir / "pack_summary.json"
    if summary_path.exists():
        return read_json(summary_path)
    return {}


def run_hot_questions(
    pack_dir: Path,
    question: str | None = None,
    *,
    scoring_config: dict[str, Any] | None = None,
    month_override: dict[str, Any] | None = None,
    historical_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = load_hotq_scoring_config() if scoring_config is None else scoring_config
    weights = config["weights"]
    penalties = config.get("penalties", {})
    pack_type = _infer_pack_type_from_pack_dir(pack_dir)

    slide_files = _iter_slide_files(pack_dir)
    workbook_meta_files = _iter_workbook_meta(pack_dir)
    pack_summary = _read_pack_summary(pack_dir)

    total_slides = len(slide_files)
    total_workbooks = len(workbook_meta_files)
    notes_missing = 0
    favorable_count = 0
    unfavorable_count = 0
    fx_mentions = 0
    inflation_mentions = 0
    risk_mentions = 0
    performance_keyword_hits = 0
    sign_mismatch_signals = 0
    evidence: list[str] = []

    for slide_path in slide_files:
        slide = read_json(slide_path)
        title = slide.get("title", "")
        body = " ".join(slide.get("body", []))
        note_text = slide.get("note_text", "")
        combined_text = f"{title} {body} {note_text}".lower()
        if not note_text:
            notes_missing += 1
        if "favorable" in combined_text:
            favorable_count += 1
        if "unfavorable" in combined_text:
            unfavorable_count += 1
        if "fx" in combined_text or "foreign exchange" in combined_text:
            fx_mentions += 1
        if "inflation" in combined_text:
            inflation_mentions += 1
        for token in ["budget", "le", "plan", "py", "yoy", "wow", "sss", "sst"]:
            if token in combined_text:
                performance_keyword_hits += 1
        for token in ["risk", "pressure", "headwind", "volatility", "challenge", "competitive"]:
            if token in combined_text:
                risk_mentions += 1
        if "favorable" in combined_text and "(" in combined_text and ")" in combined_text:
            sign_mismatch_signals += 1
        if len(evidence) < 8:
            evidence.append(str(slide_path.relative_to(pack_dir).as_posix()))

    external_link_count = 0
    formula_cells = 0
    external_formula_cells = 0
    bridge_sheet_count = 0
    for meta_path in workbook_meta_files:
        workbook_dir = meta_path.parent
        meta = read_json(meta_path)
        lineage_flags = read_json(workbook_dir / "lineage_flags.json")
        external_link_count += int(lineage_flags.get("external_link_count", 0))
        formula_cells += int(lineage_flags.get("formula_cells_total", 0))
        external_formula_cells += int(lineage_flags.get("external_formula_cells_total", 0))
        bridge_sheet_count += sum(
            1 for sheet in meta.get("sheets", []) if "bridge" in str(sheet.get("sheet_name", "")).lower()
        )
        if len(evidence) < 12:
            evidence.append(str(meta_path.relative_to(pack_dir).as_posix()))

    source_mode = str(pack_summary.get("source_mode", "unknown"))
    lineage_degraded = bool(pack_summary.get("lineage_degraded", False))

    notes_missing_ratio = (notes_missing / total_slides) if total_slides else 1.0

    dimension_scores: list[dict[str, Any]] = []

    pnl_raw = (
        52
        + min(24.0, performance_keyword_hits * 1.5)
        + (favorable_count - unfavorable_count) * 2.5
        - max(0.0, unfavorable_count - favorable_count) * 1.5
    )
    pnl_score = _clamp_score(pnl_raw)
    dimension_scores.append(
        {
            "dimension": "pnl_delivery",
            "weight": weights.get("pnl_delivery", 30),
            "score": round(pnl_score, 2),
            "drivers": [
                f"performance_keyword_hits={performance_keyword_hits}",
                f"favorable={favorable_count}",
                f"unfavorable={unfavorable_count}",
            ],
        }
    )

    variance_raw = (
        30
        + min(35.0, formula_cells / 1200.0 * 35.0)
        + (20.0 if bridge_sheet_count > 0 else -10.0)
        + min(20.0, external_formula_cells / 250.0 * 20.0)
    )
    variance_score = _clamp_score(variance_raw)
    dimension_scores.append(
        {
            "dimension": "variance_explainability",
            "weight": weights.get("variance_explainability", 25),
            "score": round(variance_score, 2),
            "drivers": [
                f"formula_cells={formula_cells}",
                f"bridge_sheet_count={bridge_sheet_count}",
                f"external_formula_cells={external_formula_cells}",
            ],
        }
    )

    forecast_raw = (
        68
        - notes_missing_ratio * 26.0
        - (6.0 if risk_mentions > 25 else 0.0)
        + min(12.0, risk_mentions * 0.5)
        + min(5.0, inflation_mentions * 0.5)
    )
    forecast_score = _clamp_score(forecast_raw)
    dimension_scores.append(
        {
            "dimension": "forecast_reliability",
            "weight": weights.get("forecast_reliability", 20),
            "score": round(forecast_score, 2),
            "drivers": [
                f"notes_missing_ratio={notes_missing_ratio:.2f}",
                f"risk_mentions={risk_mentions}",
                f"inflation_mentions={inflation_mentions}",
            ],
        }
    )

    narrative_raw = 82 - notes_missing_ratio * 30.0 - sign_mismatch_signals * 8.0
    narrative_score = _clamp_score(narrative_raw)
    dimension_scores.append(
        {
            "dimension": "narrative_integrity",
            "weight": weights.get("narrative_integrity", 15),
            "score": round(narrative_score, 2),
            "drivers": [
                f"notes_missing={notes_missing}",
                f"sign_mismatch_signals={sign_mismatch_signals}",
            ],
        }
    )

    data_confidence_raw = (
        45
        + min(20.0, external_link_count * 1.5)
        + min(20.0, external_formula_cells / 250.0 * 20.0)
        + (10.0 if not lineage_degraded else -18.0)
    )
    data_confidence_score = _clamp_score(data_confidence_raw)
    dimension_scores.append(
        {
            "dimension": "data_confidence",
            "weight": weights.get("data_confidence", 10),
            "score": round(data_confidence_score, 2),
            "drivers": [
                f"external_link_count={external_link_count}",
                f"external_formula_cells={external_formula_cells}",
                f"lineage_degraded={lineage_degraded}",
            ],
        }
    )

    override_notes: list[str] = []
    if month_override:
        for adjustment in month_override.get("score_adjustments", []):
            target = str(adjustment.get("dimension", ""))
            delta = float(adjustment.get("delta", 0))
            reason = str(adjustment.get("reason", "manual adjustment"))
            for item in dimension_scores:
                if item["dimension"] == target:
                    item["score"] = round(_clamp_score(float(item["score"]) + delta), 2)
                    override_notes.append(f"{target}:{delta:+.1f} ({reason})")
                    break

    historical_notes: list[str] = []
    if historical_context:
        calibrated_deltas = (
            historical_context.get("calibrated_deltas", {}).get(pack_type, {})
            if isinstance(historical_context.get("calibrated_deltas"), dict)
            else {}
        )
        for target, raw_delta in calibrated_deltas.items():
            delta = float(raw_delta)
            for item in dimension_scores:
                if item["dimension"] == target:
                    item["score"] = round(_clamp_score(float(item["score"]) + delta), 2)
                    historical_notes.append(f"{target}:{delta:+.2f} (historical calibration)")
                    break

    weighted_points = 0.0
    for item in dimension_scores:
        weight = float(item["weight"])
        item["weighted_points"] = round(weight * float(item["score"]) / 100.0, 2)
        weighted_points += item["weighted_points"]

    penalty_total = 0.0
    if lineage_degraded:
        penalty_total += float(penalties.get("lineage_degraded", 0))
    if notes_missing_ratio >= 0.60:
        penalty_total += float(penalties.get("notes_missing_ratio_high", 0))
    if total_slides == 0 or total_workbooks == 0:
        penalty_total += float(penalties.get("missing_pack_components", 0))

    global_delta = float((month_override or {}).get("global_delta", 0))
    score_total = _clamp_score(weighted_points - penalty_total + global_delta)
    score_band = _score_band(score_total, config.get("thresholds", {}))

    confidence = "high"
    confidence_reason = "Pack contains both slide and workbook evidence with lineage coverage."
    clarifier = ""
    if total_slides == 0 or total_workbooks == 0:
        confidence = "low"
        confidence_reason = "Missing deck or workbook coverage in normalized pack."
        clarifier = (
            "I do not have a complete normalized pack yet. Please confirm that both deck and workbook files "
            "were ingested for this period."
        )
    elif external_link_count == 0 and external_formula_cells == 0:
        confidence = "medium"
        confidence_reason = "No external-link lineage detected in current extracted workbook content."
        clarifier = (
            "Lineage signals are limited (no external links/formula lineage found). "
            "Do you want me to treat this as offline-values-only for root-cause confidence?"
        )

    if month_override and month_override.get("force_clarifier"):
        clarifier = str(month_override["force_clarifier"])

    trailing_context: list[str] = []
    baseline_note = ""
    if historical_context:
        score_baseline = (
            historical_context.get("score_baselines", {}).get(pack_type, {})
            if isinstance(historical_context.get("score_baselines"), dict)
            else {}
        )
        baseline_mean = score_baseline.get("mean_score_total")
        if isinstance(baseline_mean, (int, float)):
            delta_vs_baseline = round(score_total - float(baseline_mean), 2)
            baseline_note = (
                f"Historical baseline ({pack_type}): {float(baseline_mean):.1f} "
                f"(delta {delta_vs_baseline:+.2f})."
            )
        trailing_map = historical_context.get("trailing_period_context", {})
        if isinstance(trailing_map, dict):
            trailing_values = trailing_map.get(pack_type, [])
            if isinstance(trailing_values, list):
                trailing_context = [str(item) for item in trailing_values[:4]]

    summary_bullets = [
        f"Scorecard: {score_total:.1f} ({score_band}) | confidence={confidence}.",
        f"Coverage: {total_slides} normalized slides across {total_workbooks} workbook extracts.",
        f"Commentary tone: favorable={favorable_count}, unfavorable={unfavorable_count}, risk_mentions={risk_mentions}.",
        f"Lineage density: formula_cells={formula_cells}, external_links={external_link_count}, external_formula_cells={external_formula_cells}.",
    ]
    if baseline_note:
        summary_bullets.append(baseline_note)
    if trailing_context:
        summary_bullets.append(f"Trailing context: {' | '.join(trailing_context)}")
    if question:
        summary_bullets.insert(0, f"Question focus: {question}")

    compact_table = [
        {
            "metric": "Score Band",
            "observation": f"{score_total:.1f} ({score_band})",
            "implication": "Use band to triage depth of executive follow-up and forecast challenge.",
        },
        {
            "metric": "Narrative Coverage",
            "observation": f"{notes_missing}/{total_slides} slides missing note text",
            "implication": "Lower note coverage increases risk of unsupported commentary in leadership review.",
        },
        {
            "metric": "Lineage Confidence",
            "observation": f"{external_formula_cells} external-reference formula cells | source_mode={source_mode}",
            "implication": "Low lineage can reduce attribution confidence for variance root causes.",
        },
    ]

    risks = [
        "Potential mismatch risk where narrative does not include explicit numeric support.",
        "Potential stale assumptions if prior-month commentary was rolled forward without updates.",
    ]
    opportunities = [
        "Use slide-level numeric mention mapping to tighten commentary-to-chart consistency.",
        "Promote recurring variance drivers into a standing monthly risk/opportunity template.",
    ]
    actions = [
        "Run deck proofing before final executive circulation.",
        "Run variance watch on bridge sheets to validate driver math and period consistency.",
    ]
    if score_band == "Red":
        actions.insert(0, "Initiate targeted forecast challenge review on top variance drivers this cycle.")
    if score_band == "Yellow":
        actions.insert(0, "Prioritize top 3 medium/high-risk issues before executive sign-off.")

    anticipated_hot_questions = [
        {
            "question": "What are the most likely variance challenges I should expect in leadership review?",
            "answer": (
                f"Expect challenge on driver clarity and variance explainability. Current band is {score_band} "
                f"with variance explainability score {variance_score:.1f}, bridge_sheet_count={bridge_sheet_count}, "
                f"and formula_cells={formula_cells}."
            ),
        },
        {
            "question": "How confident are we in the numbers behind the variance narrative?",
            "answer": (
                f"Data confidence is {data_confidence_score:.1f} with source_mode={source_mode}, "
                f"external_formula_cells={external_formula_cells}, and lineage_degraded={lineage_degraded}."
            ),
        },
        {
            "question": "Where is the commentary most exposed to executive pushback?",
            "answer": (
                f"Narrative integrity is {narrative_score:.1f}; {notes_missing}/{total_slides} slides are missing notes, "
                f"and sign_mismatch_signals={sign_mismatch_signals}."
            ),
        },
    ]
    follow_up_prompt = "Is there any specific questions you'd like help coming up with an answer for?"

    payload = {
        "generated_at": utc_now_iso(),
        "period": _infer_period_from_pack_dir(pack_dir),
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "score_total": round(score_total, 2),
        "score_band": score_band,
        "dimension_scores": dimension_scores,
        "summary_bullets": summary_bullets[:6],
        "compact_table": compact_table,
        "risks": (month_override or {}).get("risk_overrides", risks),
        "opportunities": (month_override or {}).get("opportunity_overrides", opportunities),
        "actions": (month_override or {}).get("action_overrides", actions),
        "clarifying_question": clarifier,
        "evidence_refs": evidence,
        "source_mode": source_mode,
        "lineage_degraded": lineage_degraded,
        "applied_penalties": round(penalty_total, 2),
        "override_notes": override_notes,
        "historical_notes": historical_notes,
        "historical_context_applied": bool(historical_context),
        "anticipated_hot_questions": anticipated_hot_questions,
        "follow_up_prompt": follow_up_prompt,
    }
    return payload


def run_deck_proofing(pack_dir: Path, prior_pack_dir: Path | None = None) -> dict[str, Any]:
    issues: list[Issue] = []
    current_slides = _iter_slide_files(pack_dir)
    prior_slide_map: dict[str, dict[str, Any]] = {}
    if prior_pack_dir and prior_pack_dir.exists():
        for slide_path in _iter_slide_files(prior_pack_dir):
            prior_slide_map[slide_path.name] = read_json(slide_path)

    confidentiality_hits = 0
    for slide_path in current_slides:
        slide = read_json(slide_path)
        title = slide.get("title", "").strip()
        body = " ".join(slide.get("body", []))
        note_text = slide.get("note_text", "").strip()
        combined = f"{title} {body} {note_text}".lower()
        slide_ref = str(slide_path.relative_to(pack_dir).as_posix())

        if not title or re.fullmatch(r"\d{1,3}", title):
            issues.append(
                Issue(
                    location=slide_ref,
                    issue_type="Missing",
                    description="Slide title appears missing or is only a page number.",
                    severity="Medium",
                    recommended_fix="Set an explicit descriptive title aligned to the financial message.",
                    evidence_refs=[slide_ref],
                )
            )

        if not note_text:
            issues.append(
                Issue(
                    location=slide_ref,
                    issue_type="Missing",
                    description="Slide has no note/commentary text.",
                    severity="Low",
                    recommended_fix="Add concise commentary to document driver context and caveats.",
                    evidence_refs=[slide_ref],
                )
            )

        if "favorable" in combined and "(" in combined and ")" in combined:
            issues.append(
                Issue(
                    location=slide_ref,
                    issue_type="Mismatch",
                    description=(
                        "Potential sign-language mismatch: commentary uses 'favorable' while parenthetical "
                        "negative formatting appears in same slide context."
                    ),
                    severity="Medium",
                    recommended_fix="Validate sign convention and revise wording or numeric formatting.",
                    evidence_refs=[slide_ref],
                )
            )

        if "confidential and proprietary information" in combined:
            confidentiality_hits += 1

        if "adjusted ebitda" in combined and "gaap" not in combined and "ifrs" not in combined:
            issues.append(
                Issue(
                    location=slide_ref,
                    issue_type="Consistency",
                    description="Adjusted EBITDA is referenced without explicit GAAP/IFRS labeling context.",
                    severity="Medium",
                    recommended_fix="Add GAAP/IFRS/non-GAAP labeling note per reporting policy.",
                    evidence_refs=[slide_ref],
                )
            )

        if prior_slide_map:
            prior = prior_slide_map.get(slide_path.name)
            if prior:
                prior_text = " ".join([prior.get("title", ""), " ".join(prior.get("body", []))]).strip()
                current_text = " ".join([title, body]).strip()
                if prior_text and prior_text == current_text:
                    issues.append(
                        Issue(
                            location=slide_ref,
                            issue_type="Outdated",
                            description="Slide commentary appears unchanged from prior pack.",
                            severity="Medium",
                            recommended_fix="Revalidate narrative against current-month metrics and update wording.",
                            evidence_refs=[slide_ref],
                        )
                    )

    if confidentiality_hits == 0:
        issues.append(
            Issue(
                location="deck_meta",
                issue_type="Missing",
                description="No confidentiality disclaimer text detected in slide content.",
                severity="Low",
                recommended_fix="Confirm deck template includes required confidentiality footer/disclaimer.",
                evidence_refs=["decks"],
            )
        )

    payload = {
        "generated_at": utc_now_iso(),
        "confidence": "high",
        "issue_count": len(issues),
        "issues": [issue.as_dict() for issue in issues],
        "evidence_refs": sorted({ref for issue in issues for ref in issue.evidence_refs})[:100],
    }
    return payload


def _read_sheet_strings(values_csv_path: Path, limit_rows: int = 180) -> list[str]:
    values: list[str] = []
    if not values_csv_path.exists():
        return values
    with values_csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for index, row in enumerate(reader, start=1):
            if index > limit_rows:
                break
            values.extend([cell for cell in row if cell and not re.fullmatch(r"-?\d+(?:\.\d+)?", cell)])
    return values


def run_variance_watch(pack_dir: Path) -> dict[str, Any]:
    issues: list[Issue] = []
    workbook_meta_files = _iter_workbook_meta(pack_dir)

    for meta_path in workbook_meta_files:
        meta = read_json(meta_path)
        workbook_dir = meta_path.parent
        for sheet in meta.get("sheets", []):
            sheet_name = sheet.get("sheet_name", "")
            location = f"{meta_path.parent.name}/{sheet_name}"

            formula_cells = int(sheet.get("formula_cells", 0))
            external_formula_cells = int(sheet.get("external_formula_cells", 0))
            values_csv_path = workbook_dir / sheet.get("values_csv", "")
            strings = [text.lower() for text in _read_sheet_strings(values_csv_path)]
            text_blob = " ".join(strings)

            if "bridge" in sheet_name.lower() and formula_cells == 0:
                issues.append(
                    Issue(
                        location=location,
                        issue_type="Mismatch",
                        description="Bridge sheet has no formulas in extracted range; bridge integrity cannot be validated.",
                        severity="High",
                        recommended_fix="Expand extraction range or confirm formula links are preserved in source workbook.",
                        evidence_refs=[str(values_csv_path.relative_to(pack_dir).as_posix())],
                    )
                )

            period_tokens = {"ytd": "YTD", "qtd": "QTD", "fy": "FY"}
            present_periods = [label for token, label in period_tokens.items() if token in text_blob]
            if len(present_periods) > 1:
                issues.append(
                    Issue(
                        location=location,
                        issue_type="Consistency",
                        description=f"Multiple period tokens detected on one sheet: {', '.join(present_periods)}.",
                        severity="Medium",
                        recommended_fix="Confirm period basis is consistent for each bridge/variance statement.",
                        evidence_refs=[str(values_csv_path.relative_to(pack_dir).as_posix())],
                    )
                )

            if "fx" in text_blob and "rate" not in text_blob:
                issues.append(
                    Issue(
                        location=location,
                        issue_type="Consistency",
                        description="FX references detected without explicit rate context.",
                        severity="Medium",
                        recommended_fix="Add plan-rate vs actual-rate support where FX variance is discussed.",
                        evidence_refs=[str(values_csv_path.relative_to(pack_dir).as_posix())],
                    )
                )

            for marker in ["tbu", "tbd", "placeholder", "xxx"]:
                if marker in text_blob:
                    issues.append(
                        Issue(
                            location=location,
                            issue_type="Missing",
                            description=f"Incomplete marker '{marker.upper()}' detected in sheet content.",
                            severity="High",
                            recommended_fix="Replace placeholder with final commentary or schedule values.",
                            evidence_refs=[str(values_csv_path.relative_to(pack_dir).as_posix())],
                        )
                    )
                    break

            if external_formula_cells == 0 and "check" in sheet_name.lower():
                issues.append(
                    Issue(
                        location=location,
                        issue_type="Clarity",
                        description=(
                            "Validation/check sheet has no external-reference formulas in extracted cells. "
                            "Lineage coverage may be incomplete."
                        ),
                        severity="Low",
                        recommended_fix="Confirm this check tab is expected to run offline or include lineage export.",
                        evidence_refs=[str(values_csv_path.relative_to(pack_dir).as_posix())],
                    )
                )

            formula_csv = workbook_dir / sheet.get("formula_cells_csv", "")
            if formula_csv.exists():
                with formula_csv.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    has_driver_headers = False
                    for row in reader:
                        formula = (row.get("formula") or "").lower()
                        if all(token in formula for token in ["price", "volume", "mix"]):
                            has_driver_headers = True
                            break
                    if not has_driver_headers and "bridge" in sheet_name.lower():
                        issues.append(
                            Issue(
                                location=location,
                                issue_type="Clarity",
                                description=(
                                    "Bridge formulas do not clearly evidence canonical price/volume/mix driver structure."
                                ),
                                severity="Low",
                                recommended_fix="Verify driver decomposition aligns to reporting convention.",
                                evidence_refs=[str(formula_csv.relative_to(pack_dir).as_posix())],
                            )
                        )

    payload = {
        "generated_at": utc_now_iso(),
        "confidence": "high",
        "issue_count": len(issues),
        "issues": [issue.as_dict() for issue in issues],
        "evidence_refs": sorted({ref for issue in issues for ref in issue.evidence_refs})[:200],
    }
    return payload


def persist_analysis(payload: dict[str, Any], output_path: Path) -> None:
    write_json(output_path, payload)
