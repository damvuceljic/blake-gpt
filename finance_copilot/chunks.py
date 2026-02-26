from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from finance_copilot.common import read_json, write_json, write_jsonl


def _trimmed_text(parts: list[str], max_chars: int) -> str:
    text = " | ".join(part for part in parts if part)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _sheet_formula_preview(formula_csv: Path, max_rows: int = 8) -> list[str]:
    preview: list[str] = []
    if not formula_csv.exists():
        return preview
    with formula_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            preview.append(f"{row.get('cell', '')}: {row.get('formula', '')}")
            if index >= max_rows:
                break
    return preview


def build_token_chunks(
    *,
    normalized_pack_dir: Path,
    output_path: Path,
    max_chars_per_chunk: int = 1800,
) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []

    for deck_dir in sorted((normalized_pack_dir / "decks").glob("*")):
        if not deck_dir.is_dir():
            continue
        for slide_path in sorted((deck_dir / "slides").glob("slide_*.json")):
            slide = read_json(slide_path)
            text = _trimmed_text(
                [slide.get("title", ""), " ".join(slide.get("body", [])), slide.get("note_text", "")],
                max_chars=max_chars_per_chunk,
            )
            chunks.append(
                {
                    "chunk_id": f"{deck_dir.name}-{slide_path.stem}",
                    "chunk_type": "slide",
                    "source_ref": str(slide_path.relative_to(normalized_pack_dir).as_posix()),
                    "content": text,
                    "metadata": {
                        "slide_number": slide.get("slide_number"),
                        "numeric_mentions": slide.get("detected_numeric_mentions", [])[:20],
                    },
                }
            )

        for chart_path in sorted((deck_dir / "charts").glob("chart_*.json")):
            chart = read_json(chart_path)
            preview_parts = []
            for series in chart.get("series", [])[:4]:
                values = ",".join(series.get("values", [])[:8])
                preview_parts.append(f"{series.get('name', '')}: {values}")
            chunks.append(
                {
                    "chunk_id": f"{deck_dir.name}-{chart_path.stem}",
                    "chunk_type": "chart",
                    "source_ref": str(chart_path.relative_to(normalized_pack_dir).as_posix()),
                    "content": _trimmed_text(preview_parts, max_chars=max_chars_per_chunk),
                    "metadata": {"external_target": chart.get("external_target", "")},
                }
            )

    for workbook_dir in sorted((normalized_pack_dir / "workbooks").glob("*")):
        if not workbook_dir.is_dir():
            continue
        workbook_meta_path = workbook_dir / "workbook_meta.json"
        if workbook_meta_path.exists():
            workbook_meta = read_json(workbook_meta_path)
            summary_text = _trimmed_text(
                [
                    f"Workbook: {workbook_meta.get('source_file', '')}",
                    f"Sheets: {workbook_meta.get('sheet_count', 0)}",
                ],
                max_chars=max_chars_per_chunk,
            )
            chunks.append(
                {
                    "chunk_id": f"{workbook_dir.name}-meta",
                    "chunk_type": "workbook_meta",
                    "source_ref": str(workbook_meta_path.relative_to(normalized_pack_dir).as_posix()),
                    "content": summary_text,
                    "metadata": {},
                }
            )
            for sheet in workbook_meta.get("sheets", []):
                formula_csv = workbook_dir / sheet.get("formula_cells_csv", "")
                preview = _sheet_formula_preview(formula_csv)
                sheet_text = _trimmed_text(
                    [
                        f"Sheet: {sheet.get('sheet_name', '')}",
                        f"Rows: {sheet.get('max_row', 0)}",
                        f"Cols: {sheet.get('max_col', 0)}",
                        f"Formula cells: {sheet.get('formula_cells', 0)}",
                        "Formula preview: " + " || ".join(preview),
                    ],
                    max_chars=max_chars_per_chunk,
                )
                chunks.append(
                    {
                        "chunk_id": f"{workbook_dir.name}-{sheet.get('sheet_slug', 'sheet')}",
                        "chunk_type": "sheet_summary",
                        "source_ref": f"workbooks/{workbook_dir.name}/sheets/{sheet.get('sheet_slug', '')}",
                        "content": sheet_text,
                        "metadata": {
                            "external_formula_cells": sheet.get("external_formula_cells", 0),
                        },
                    }
                )

    write_jsonl(output_path, chunks)
    index_payload = {
        "chunk_file": str(output_path.name),
        "chunk_count": len(chunks),
    }
    write_json(output_path.with_name("chunk_index.json"), index_payload)
    return index_payload

