from __future__ import annotations

import csv
from pathlib import Path

from finance_copilot.analysis import run_deck_proofing, run_hot_questions, run_variance_watch
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
