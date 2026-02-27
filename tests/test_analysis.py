from __future__ import annotations

import csv
from pathlib import Path

from finance_copilot.analysis import (
    _apply_term_guard_to_text,
    load_hotq_policy,
    run_deck_proofing,
    run_hot_questions,
    run_variance_watch,
)
from finance_copilot.common import ensure_dir, write_json


def _write_sheet_values(path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row_number", "c1", "c2", "c3"])
        writer.writerow([1, "Bridge", "YTD", "FX"])
        writer.writerow([2, "TBU", "placeholder", ""])


def _write_formula_cells(path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sheet", "cell", "row", "col", "formula", "is_external"])
        writer.writerow(["Bridge", "B2", 2, 2, "=A1+B1", "false"])


def _write_variance_values(
    path: Path,
    *,
    total_sales_py: float,
    total_sales_actual: float,
    total_sales_le: float,
    total_sales_budget: float,
) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row_number", "c1", "c2", "c3"])
        writer.writerow([30, "", "", ""])
        writer.writerow(
            [
                31,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Prior Year",
                "Actual",
                "LE",
                "Budget",
                "Var. PY",
                "Var. LE",
                "Var. Budget",
            ]
        )
        writer.writerow(
            [
                86,
                "1000000",
                "TH Canada",
                "4",
                "TotalSales",
                "Top",
                "CA",
                "",
                "Total Sales",
                str(total_sales_py),
                str(total_sales_actual),
                str(total_sales_le),
                str(total_sales_budget),
                "",
                "",
                "",
            ]
        )


def test_analysis_payloads(tmp_path: Path) -> None:
    pack_dir = tmp_path / "data" / "normalized" / "2026-P02" / "preview"
    slide_dir = pack_dir / "decks" / "sample" / "slides"
    workbook_dir = pack_dir / "workbooks" / "sample"
    ensure_dir(slide_dir)
    ensure_dir(workbook_dir / "sheets" / "bridge")

    write_json(
        slide_dir / "slide_001.json",
        {
            "slide_number": 1,
            "title": "TH C&US Preview",
            "body": ["LE favorable by 1.2%", "Inflation pressure remains elevated"],
            "note_text": "FX pressure persists.",
            "detected_numeric_mentions": ["1.2%"],
        },
    )
    write_json(
        workbook_dir / "workbook_meta.json",
        {
            "source_file": "sample.xlsx",
            "sheet_count": 1,
            "sheet_names": ["Bridge"],
            "extracted_at": "2026-02-26T00:00:00+00:00",
            "sheets": [
                {
                    "sheet_name": "Bridge",
                    "sheet_slug": "bridge",
                    "max_row": 10,
                    "max_col": 5,
                    "formula_cells": 1,
                    "external_formula_cells": 0,
                    "values_csv": "sheets/bridge/values.csv",
                    "formula_cells_csv": "sheets/bridge/formula_cells.csv",
                    "named_ranges_json": "sheets/bridge/named_ranges.json",
                }
            ],
        },
    )
    write_json(
        workbook_dir / "lineage_flags.json",
        {
            "has_external_links": False,
            "external_link_count": 0,
            "formula_cells_total": 1,
            "external_formula_cells_total": 0,
        },
    )
    write_json(workbook_dir / "external_links.json", [])
    write_json(workbook_dir / "sheets" / "bridge" / "named_ranges.json", [])
    _write_sheet_values(workbook_dir / "sheets" / "bridge" / "values.csv")
    _write_formula_cells(workbook_dir / "sheets" / "bridge" / "formula_cells.csv")

    hot = run_hot_questions(pack_dir=pack_dir, question="What are my biggest risks?")
    proof = run_deck_proofing(pack_dir=pack_dir, prior_pack_dir=None)
    variance = run_variance_watch(pack_dir=pack_dir)

    assert hot["confidence"] in {"high", "medium", "low"}
    assert isinstance(hot["score_total"], (int, float))
    assert hot["score_band"] in {"Green", "Yellow", "Red"}
    assert len(hot["dimension_scores"]) == 5
    assert hot["confidence_reason"]
    assert len(hot["summary_bullets"]) >= 1
    assert len(hot["anticipated_hot_questions"]) >= 1
    assert isinstance(hot["challenge_cards"], list)
    assert hot["quality_gate"]["status"] in {"pass", "downgraded_narrative_gap", "fail"}
    assert "narrative_signal_summary" in hot
    assert hot["policy_version"]
    assert isinstance(hot["term_guard_hits"], list)
    assert isinstance(hot["scope_filters_applied"], list)
    assert isinstance(hot["evidence_gap_registry"], list)
    assert hot["hot_question_prompt_version"] == "variance_challenge_v1"
    assert hot["hot_question_prompt"]
    assert isinstance(hot["variance_question_candidates"], list)
    assert hot["follow_up_prompt"] == "Is there any specific questions you'd like help coming up with an answer for?"
    for card in hot["challenge_cards"]:
        assert "scope_classification" in card
        assert "citation_bundle" in card
    assert proof["issue_count"] >= 0
    assert variance["issue_count"] >= 1


def test_hot_questions_override_delta(tmp_path: Path) -> None:
    pack_dir = tmp_path / "data" / "normalized" / "2026-P03" / "preview"
    slide_dir = pack_dir / "decks" / "sample" / "slides"
    workbook_dir = pack_dir / "workbooks" / "sample"
    ensure_dir(slide_dir)
    ensure_dir(workbook_dir / "sheets" / "bridge")

    write_json(
        slide_dir / "slide_001.json",
        {
            "slide_number": 1,
            "title": "Preview",
            "body": ["Budget favorable"],
            "note_text": "stable",
            "detected_numeric_mentions": [],
        },
    )
    write_json(
        workbook_dir / "workbook_meta.json",
        {
            "source_file": "sample.xlsx",
            "sheet_count": 1,
            "sheet_names": ["Bridge"],
            "extracted_at": "2026-02-26T00:00:00+00:00",
            "sheets": [
                {
                    "sheet_name": "Bridge",
                    "sheet_slug": "bridge",
                    "max_row": 10,
                    "max_col": 5,
                    "formula_cells": 10,
                    "external_formula_cells": 1,
                    "values_csv": "sheets/bridge/values.csv",
                    "formula_cells_csv": "sheets/bridge/formula_cells.csv",
                    "named_ranges_json": "sheets/bridge/named_ranges.json",
                }
            ],
        },
    )
    write_json(
        workbook_dir / "lineage_flags.json",
        {
            "has_external_links": False,
            "external_link_count": 0,
            "formula_cells_total": 10,
            "external_formula_cells_total": 1,
        },
    )
    write_json(workbook_dir / "external_links.json", [])
    write_json(workbook_dir / "sheets" / "bridge" / "named_ranges.json", [])
    _write_sheet_values(workbook_dir / "sheets" / "bridge" / "values.csv")
    _write_formula_cells(workbook_dir / "sheets" / "bridge" / "formula_cells.csv")

    base = run_hot_questions(pack_dir=pack_dir, question=None)
    override = run_hot_questions(
        pack_dir=pack_dir,
        question=None,
        month_override={"global_delta": -10.0},
    )
    assert override["score_total"] < base["score_total"]


def test_hot_questions_generates_metric_delta_questions(tmp_path: Path) -> None:
    current_pack = tmp_path / "data" / "normalized" / "2026-P01" / "close"
    prior_pack = tmp_path / "data" / "normalized" / "2025-P12" / "close"
    slide_dir = current_pack / "decks" / "close-pack" / "slides"
    ensure_dir(slide_dir)
    write_json(
        slide_dir / "slide_001.json",
        {
            "slide_number": 1,
            "title": "TH Canada What Worked / Didn't Work",
            "body": ["Traffic softness and pricing mix drove Sales and AOI variance vs LE and Budget."],
            "note_text": "Labor inflation and promo mix were key drivers.",
            "detected_numeric_mentions": ["-6.0MM", "-14.0MM"],
            "text_blocks": [
                {
                    "block_index": 1,
                    "lines": ["What Worked / Didn't Work", "Traffic softness and pricing mix drove Sales and AOI variance."],
                    "char_count": 102,
                    "numeric_density": 0.1,
                    "block_class": "narrative",
                    "narrative_signal_score": 6.5,
                }
            ],
        },
    )
    write_json(
        slide_dir / "slide_002.json",
        {
            "slide_number": 2,
            "title": "TH US Drivers and Impacts",
            "body": ["US labor timing and weather affected AOI and EBITDA trajectory."],
            "note_text": "Bridge page only used for anchor values.",
            "detected_numeric_mentions": ["-2.0MM"],
            "text_blocks": [
                {
                    "block_index": 1,
                    "lines": ["Drivers and Impacts", "US labor timing and weather affected AOI and EBITDA trajectory."],
                    "char_count": 98,
                    "numeric_density": 0.0,
                    "block_class": "narrative",
                    "narrative_signal_score": 6.0,
                }
            ],
        },
    )
    write_json(
        slide_dir / "slide_003.json",
        {
            "slide_number": 3,
            "title": "TH C&US Bridge Summary",
            "body": ["Variance to Budget and LE anchors for total portfolio."],
            "note_text": "",
            "detected_numeric_mentions": ["-10.0MM"],
            "text_blocks": [
                {
                    "block_index": 1,
                    "lines": ["Bridge Summary", "Variance to Budget and LE anchors for total portfolio."],
                    "char_count": 80,
                    "numeric_density": 0.5,
                    "block_class": "bridge_summary",
                    "narrative_signal_score": -1.0,
                }
            ],
        },
    )

    current_workbook = current_pack / "workbooks" / "th-ca-new-close-template-p01-2026-aoi-version-offline"
    prior_workbook = prior_pack / "workbooks" / "th-ca-new-close-template-p12-2025-aoi-version-offline"
    for workbook in [current_workbook, prior_workbook]:
        ensure_dir(workbook / "sheets" / "thca-p-l-aoi")
        write_json(
            workbook / "workbook_meta.json",
            {
                "source_file": "close_template.xlsx",
                "sheet_count": 1,
                "sheet_names": ["THCA P&L AOI"],
                "extracted_at": "2026-02-26T00:00:00+00:00",
                "sheets": [
                    {
                        "sheet_name": "THCA P&L AOI",
                        "sheet_slug": "thca-p-l-aoi",
                        "max_row": 120,
                        "max_col": 30,
                        "formula_cells": 10,
                        "external_formula_cells": 3,
                        "values_csv": "sheets/thca-p-l-aoi/values.csv",
                        "formula_cells_csv": "sheets/thca-p-l-aoi/formula_cells.csv",
                        "named_ranges_json": "sheets/thca-p-l-aoi/named_ranges.json",
                    }
                ],
            },
        )
        write_json(
            workbook / "lineage_flags.json",
            {
                "has_external_links": True,
                "external_link_count": 5,
                "formula_cells_total": 10,
                "external_formula_cells_total": 3,
            },
        )
        _write_formula_cells(workbook / "sheets" / "thca-p-l-aoi" / "formula_cells.csv")
        write_json(workbook / "sheets" / "thca-p-l-aoi" / "named_ranges.json", [])

    _write_variance_values(
        current_workbook / "sheets" / "thca-p-l-aoi" / "values.csv",
        total_sales_py=95.0,
        total_sales_actual=90.0,
        total_sales_le=96.0,
        total_sales_budget=104.0,
    )
    _write_variance_values(
        prior_workbook / "sheets" / "thca-p-l-aoi" / "values.csv",
        total_sales_py=92.0,
        total_sales_actual=100.0,
        total_sales_le=98.0,
        total_sales_budget=102.0,
    )

    supporting_workbook = current_pack / "workbooks" / "p01-2026-swsvsle-canada"
    ensure_dir(supporting_workbook / "sheets" / "p01-act-x-ple")
    write_json(
        supporting_workbook / "workbook_meta.json",
        {
            "source_file": "P01 2026 SWSvsLE - Canada.xlsx",
            "sheet_count": 1,
            "sheet_names": ["P01 Act x PLE"],
            "extracted_at": "2026-02-26T00:00:00+00:00",
            "sheets": [
                {
                    "sheet_name": "P01 Act x PLE",
                    "sheet_slug": "p01-act-x-ple",
                    "max_row": 20,
                    "max_col": 10,
                    "formula_cells": 5,
                    "external_formula_cells": 0,
                    "values_csv": "sheets/p01-act-x-ple/values.csv",
                    "formula_cells_csv": "sheets/p01-act-x-ple/formula_cells.csv",
                    "named_ranges_json": "sheets/p01-act-x-ple/named_ranges.json",
                }
            ],
        },
    )
    write_json(
        supporting_workbook / "lineage_flags.json",
        {
            "has_external_links": False,
            "external_link_count": 0,
            "formula_cells_total": 5,
            "external_formula_cells_total": 0,
        },
    )
    write_json(supporting_workbook / "external_links.json", [])
    write_json(supporting_workbook / "sheets" / "p01-act-x-ple" / "named_ranges.json", [])
    _write_formula_cells(supporting_workbook / "sheets" / "p01-act-x-ple" / "formula_cells.csv")
    with (supporting_workbook / "sheets" / "p01-act-x-ple" / "values.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row_number", "c1", "c2", "c3", "c4"])
        writer.writerow([1, "Sales variance vs Budget", "traffic down", "LE revision", "14.0"])

    write_json(
        current_pack / "pack_manifest.json",
        {
            "files": [
                {
                    "file_slug": "th-ca-new-close-template-p01-2026-aoi-version-offline",
                    "role": "close_offline_workbook",
                },
                {
                    "file_slug": "p01-2026-swsvsle-canada",
                    "role": "supporting_excel",
                },
            ]
        },
    )

    hot = run_hot_questions(pack_dir=current_pack, question="Challenge my close variances")
    first_card = hot["challenge_cards"][0]
    assert "Total Sales" in first_card["challenge_question"]
    assert "vs Budget" in first_card["challenge_question"] or "vs LE" in first_card["challenge_question"]
    assert first_card["narrative_evidence_refs"]
    assert first_card["basis_summary"]["vs_budget"]
    assert hot["quality_gate"]["status"] in {"pass", "downgraded_narrative_gap", "fail"}
    assert hot["le_change_flags"]
    assert hot["le_completeness_watchouts"] == []
    assert hot["supplementary_metric_snippets"].get("Total Sales")
    assert "Supporting workbook evidence" in first_card["prepared_answer"]
    assert first_card["scope_classification"]
    assert first_card["citation_bundle"]
    first_citation = first_card["citation_bundle"][0]
    assert first_citation["path"]
    assert first_citation["location"]
    assert first_citation["excerpt"]


def test_hot_questions_marks_missing_le_as_completeness_watchout(tmp_path: Path) -> None:
    current_pack = tmp_path / "data" / "normalized" / "2026-P02" / "close"
    prior_pack = tmp_path / "data" / "normalized" / "2026-P01" / "close"
    slide_dir = current_pack / "decks" / "close-pack" / "slides"
    ensure_dir(slide_dir)
    write_json(
        slide_dir / "slide_001.json",
        {
            "slide_number": 1,
            "title": "TH Canada What Worked / Didn't Work",
            "body": ["Narrative explains a variance context."],
            "note_text": "LE upload delay noted.",
            "detected_numeric_mentions": [],
            "text_blocks": [
                {
                    "block_index": 1,
                    "lines": ["What Worked / Didn't Work", "LE upload delay noted for Sales forecast."],
                    "char_count": 78,
                    "numeric_density": 0.0,
                    "block_class": "narrative",
                    "narrative_signal_score": 5.0,
                }
            ],
        },
    )

    for pack, le_value in [(current_pack, 0.0), (prior_pack, 98.0)]:
        workbook = pack / "workbooks" / "th-ca-new-close-template-offline"
        ensure_dir(workbook / "sheets" / "thca-p-l-aoi")
        write_json(
            workbook / "workbook_meta.json",
            {
                "source_file": "close_template.xlsx",
                "sheet_count": 1,
                "sheet_names": ["THCA P&L AOI"],
                "extracted_at": "2026-02-26T00:00:00+00:00",
                "sheets": [
                    {
                        "sheet_name": "THCA P&L AOI",
                        "sheet_slug": "thca-p-l-aoi",
                        "max_row": 120,
                        "max_col": 30,
                        "formula_cells": 4,
                        "external_formula_cells": 1,
                        "values_csv": "sheets/thca-p-l-aoi/values.csv",
                        "formula_cells_csv": "sheets/thca-p-l-aoi/formula_cells.csv",
                        "named_ranges_json": "sheets/thca-p-l-aoi/named_ranges.json",
                    }
                ],
            },
        )
        write_json(
            workbook / "lineage_flags.json",
            {
                "has_external_links": True,
                "external_link_count": 1,
                "formula_cells_total": 4,
                "external_formula_cells_total": 1,
            },
        )
        _write_formula_cells(workbook / "sheets" / "thca-p-l-aoi" / "formula_cells.csv")
        write_json(workbook / "sheets" / "thca-p-l-aoi" / "named_ranges.json", [])
        _write_variance_values(
            workbook / "sheets" / "thca-p-l-aoi" / "values.csv",
            total_sales_py=95.0,
            total_sales_actual=90.0,
            total_sales_le=le_value,
            total_sales_budget=96.0,
        )

    hot = run_hot_questions(pack_dir=current_pack, question="Check LE completeness")
    statuses = [item.get("status") for item in hot["le_change_flags"]]
    assert "missing_current_period_le" in statuses
    assert hot["le_completeness_watchouts"]
    assert "LE not populated" in hot["le_completeness_watchouts"][0]["message"]


def test_term_guard_rewrites_banned_shorthand() -> None:
    policy = load_hotq_policy()
    rewritten, hits, downgraded = _apply_term_guard_to_text(
        "We have earnings quality concerns and core operating demand pressure.",
        card_metric="Total Sales",
        field="challenge_question",
        policy=policy,
    )
    assert not downgraded
    assert "quality" not in rewritten.lower()
    assert "core operating demand" not in rewritten.lower()
    assert hits
