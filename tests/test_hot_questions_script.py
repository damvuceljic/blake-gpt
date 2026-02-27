from __future__ import annotations

import csv
from pathlib import Path

from finance_copilot.common import ensure_dir, read_json, write_json
from scripts.analyze import hot_questions as hot_questions_script


def _write_formula_cells(path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sheet", "cell", "row", "col", "formula", "is_external"])
        writer.writerow(["THCA P&L AOI", "B2", 2, 2, "=A1+B1", "false"])


def _write_variance_values(path: Path, *, le_value: float) -> None:
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
                "95.0",
                "90.0",
                str(le_value),
                "100.0",
                "",
                "",
                "",
            ]
        )


def _build_pack(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "data" / "normalized" / "2026-P03" / "close"
    slide_dir = pack_dir / "decks" / "close-pack" / "slides"
    workbook = pack_dir / "workbooks" / "th-ca-new-close-template-offline"
    ensure_dir(slide_dir)
    ensure_dir(workbook / "sheets" / "thca-p-l-aoi")

    write_json(
        slide_dir / "slide_001.json",
        {
            "slide_number": 1,
            "title": "TH Canada What Worked / Didn't Work",
            "body": ["Traffic softness and pricing explain most of the variance."],
            "note_text": "Bridge slide anchors only.",
            "detected_numeric_mentions": ["-10.0MM"],
            "text_blocks": [
                {
                    "block_index": 1,
                    "lines": ["What Worked / Didn't Work", "Traffic softness and pricing explain most of the variance."],
                    "char_count": 95,
                    "numeric_density": 0.0,
                    "block_class": "narrative",
                    "narrative_signal_score": 6.1,
                }
            ],
        },
    )
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
                    "formula_cells": 8,
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
            "formula_cells_total": 8,
            "external_formula_cells_total": 1,
        },
    )
    write_json(workbook / "sheets" / "thca-p-l-aoi" / "named_ranges.json", [])
    _write_formula_cells(workbook / "sheets" / "thca-p-l-aoi" / "formula_cells.csv")
    _write_variance_values(workbook / "sheets" / "thca-p-l-aoi" / "values.csv", le_value=96.0)
    return pack_dir


def test_llm_failure_downgrades_quality_gate(tmp_path: Path, monkeypatch) -> None:
    pack_dir = _build_pack(tmp_path)
    output = tmp_path / "hot_questions.json"

    def _failed_llm(**_: object) -> dict:
        return {
            "wrapper_returncode": 2,
            "returncode": 2,
            "response_text": "",
        }

    monkeypatch.setattr(hot_questions_script, "run_llm_postprocess", _failed_llm)
    monkeypatch.setattr(
        "sys.argv",
        [
            "hot_questions.py",
            "--pack-dir",
            str(pack_dir),
            "--output",
            str(output),
            "--use-llm-postprocess",
            "--require-llm-attempt",
        ],
    )

    rc = hot_questions_script.main()
    assert rc == 0
    payload = read_json(output)
    assert payload["quality_gate"]["status"] == "downgraded_llm"
    assert payload["warnings"]
    assert payload["policy_version"]
    assert isinstance(payload["term_guard_hits"], list)
    assert isinstance(payload["scope_filters_applied"], list)
    assert isinstance(payload["evidence_gap_registry"], list)
