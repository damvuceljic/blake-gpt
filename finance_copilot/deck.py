from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from finance_copilot.common import ensure_dir, utc_now_iso, write_json

NS_A = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
NS_P = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
NS_C = {
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
NUMERIC_RE = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d+)?%?\)?")
NARRATIVE_CUE_TOKENS = [
    "what worked",
    "didn't work",
    "drivers and impacts",
    "driven by",
    "due to",
    "because",
    "headwind",
    "tailwind",
    "pricing",
    "traffic",
    "labor",
    "commodity",
    "mix",
    "promo",
]
BRIDGE_CUE_TOKENS = [
    "bridge",
    "variance to budget",
    "variance to le",
    "vs budget",
    "vs le",
    "vs py",
]
FOOTER_CUE_TOKENS = [
    "confidential and proprietary information of restaurant brands international",
    "source:",
]


def _extract_text_values(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    texts = [node.text.strip() for node in root.findall(".//a:t", NS_A) if node.text and node.text.strip()]
    return texts


def _infer_block_class(text: str, numeric_density: float, line_count: int) -> str:
    lowered = text.lower()
    if any(token in lowered for token in FOOTER_CUE_TOKENS):
        return "footer"
    if any(token in lowered for token in BRIDGE_CUE_TOKENS):
        return "bridge_summary"
    if numeric_density >= 1.25 or (line_count >= 10 and numeric_density > 0.6):
        return "table_like"
    if any(token in lowered for token in NARRATIVE_CUE_TOKENS):
        return "narrative"
    if len(text) >= 120 and numeric_density < 0.8:
        return "narrative"
    return "table_like"


def _narrative_signal_score(text: str, numeric_density: float, block_class: str) -> float:
    lowered = text.lower()
    cue_hits = sum(1 for token in NARRATIVE_CUE_TOKENS if token in lowered)
    bridge_hits = sum(1 for token in BRIDGE_CUE_TOKENS if token in lowered)
    score = cue_hits * 2.2 - bridge_hits * 1.5 - numeric_density * 1.2
    if block_class == "narrative":
        score += 3.0
    if block_class == "footer":
        score -= 5.0
    return round(score, 3)


def _extract_text_blocks(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    blocks: list[dict[str, Any]] = []
    for shape in root.findall(".//p:sp", NS_P):
        lines = [node.text.strip() for node in shape.findall(".//a:t", NS_A) if node.text and node.text.strip()]
        if not lines:
            continue
        text = " ".join(lines)
        numeric_mentions = len(NUMERIC_RE.findall(text))
        numeric_density = round(numeric_mentions / max(1, len(lines)), 3)
        block_class = _infer_block_class(text, numeric_density, len(lines))
        blocks.append(
            {
                "block_index": len(blocks) + 1,
                "lines": lines,
                "char_count": len(text),
                "numeric_density": numeric_density,
                "block_class": block_class,
                "narrative_signal_score": _narrative_signal_score(text, numeric_density, block_class),
            }
        )

    if blocks:
        return blocks

    fallback = _extract_text_values(xml_bytes)
    if not fallback:
        return []
    text = " ".join(fallback)
    numeric_mentions = len(NUMERIC_RE.findall(text))
    numeric_density = round(numeric_mentions / max(1, len(fallback)), 3)
    block_class = _infer_block_class(text, numeric_density, len(fallback))
    return [
        {
            "block_index": 1,
            "lines": fallback,
            "char_count": len(text),
            "numeric_density": numeric_density,
            "block_class": block_class,
            "narrative_signal_score": _narrative_signal_score(text, numeric_density, block_class),
        }
    ]


def _slide_files(zip_names: list[str]) -> list[str]:
    slide_names = [name for name in zip_names if re.match(r"ppt/slides/slide\d+\.xml$", name)]
    return sorted(slide_names, key=lambda value: int(re.findall(r"\d+", value)[0]))


def _chart_files(zip_names: list[str]) -> list[str]:
    chart_names = [name for name in zip_names if re.match(r"ppt/charts/chart\d+\.xml$", name)]
    return sorted(chart_names, key=lambda value: int(re.findall(r"\d+", value)[0]))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _build_boilerplate_set(slide_texts: list[list[str]]) -> set[str]:
    counter: Counter[str] = Counter()
    for slide in slide_texts:
        for text in slide:
            normalized = _normalize_text(text)
            if normalized:
                counter[normalized] += 1
    min_count = max(8, int(len(slide_texts) * 0.12))
    flagged = {text for text, count in counter.items() if count >= min_count}
    flagged.add("Confidential and Proprietary Information of Restaurant Brands International")
    return flagged


def _is_boilerplate(text: str, boilerplate: set[str]) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return True
    if normalized in boilerplate:
        return True
    if re.fullmatch(r"\d{1,3}", normalized):
        return True
    if normalized in {"-", "--"}:
        return True
    return False


def _chart_external_target(archive: zipfile.ZipFile, chart_id: int, rid: str | None) -> str:
    if not rid:
        return ""
    rel_path = f"ppt/charts/_rels/chart{chart_id}.xml.rels"
    if rel_path not in archive.namelist():
        return ""
    rel_root = ET.fromstring(archive.read(rel_path))
    for node in rel_root:
        if node.attrib.get("Id") == rid:
            return node.attrib.get("Target", "")
    return ""


def _extract_series_values(series_node: ET.Element) -> tuple[list[str], list[str]]:
    categories: list[str] = []
    values: list[str] = []
    for cat in series_node.findall(".//c:cat//c:v", NS_C):
        if cat.text:
            categories.append(cat.text)
    for val in series_node.findall(".//c:val//c:v", NS_C):
        if val.text:
            values.append(val.text)
    return categories, values


def _series_name(series_node: ET.Element) -> str:
    text_nodes = series_node.findall(".//c:tx//c:v", NS_C)
    for node in text_nodes:
        if node.text:
            return node.text
    return ""


def extract_deck(*, input_path: Path, output_dir: Path) -> dict[str, Any]:
    ensure_dir(output_dir)
    slides_dir = ensure_dir(output_dir / "slides")
    charts_dir = ensure_dir(output_dir / "charts")

    with zipfile.ZipFile(input_path, "r") as archive:
        names = archive.namelist()
        slide_files = _slide_files(names)
        note_map = {
            int(re.findall(r"\d+", name)[0]): name
            for name in names
            if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", name)
        }

        raw_slide_texts: list[list[str]] = []
        raw_slide_blocks: list[list[dict[str, Any]]] = []
        for slide_xml in slide_files:
            slide_bytes = archive.read(slide_xml)
            raw_slide_texts.append(_extract_text_values(slide_bytes))
            raw_slide_blocks.append(_extract_text_blocks(slide_bytes))
        boilerplate = _build_boilerplate_set(raw_slide_texts)

        slide_chart_map: list[dict[str, Any]] = []
        slide_records: list[dict[str, Any]] = []
        for index, slide_xml in enumerate(slide_files, start=1):
            raw_items = raw_slide_texts[index - 1]
            filtered_items = [text for text in raw_items if not _is_boilerplate(text, boilerplate)]
            title = filtered_items[0] if filtered_items else next((text for text in raw_items if text.strip()), "")
            body = filtered_items[1:] if len(filtered_items) > 1 else []

            text_blocks: list[dict[str, Any]] = []
            for raw_block in raw_slide_blocks[index - 1]:
                filtered_lines = [line for line in raw_block.get("lines", []) if not _is_boilerplate(line, boilerplate)]
                if not filtered_lines:
                    continue
                block_text = " ".join(filtered_lines)
                numeric_mentions = len(NUMERIC_RE.findall(block_text))
                numeric_density = round(numeric_mentions / max(1, len(filtered_lines)), 3)
                block_class = _infer_block_class(block_text, numeric_density, len(filtered_lines))
                text_blocks.append(
                    {
                        "block_index": len(text_blocks) + 1,
                        "lines": filtered_lines,
                        "char_count": len(block_text),
                        "numeric_density": numeric_density,
                        "block_class": block_class,
                        "narrative_signal_score": _narrative_signal_score(block_text, numeric_density, block_class),
                    }
                )

            if not text_blocks and filtered_items:
                fallback_text = " ".join(filtered_items)
                numeric_mentions = len(NUMERIC_RE.findall(fallback_text))
                numeric_density = round(numeric_mentions / max(1, len(filtered_items)), 3)
                block_class = _infer_block_class(fallback_text, numeric_density, len(filtered_items))
                text_blocks.append(
                    {
                        "block_index": 1,
                        "lines": filtered_items,
                        "char_count": len(fallback_text),
                        "numeric_density": numeric_density,
                        "block_class": block_class,
                        "narrative_signal_score": _narrative_signal_score(fallback_text, numeric_density, block_class),
                    }
                )

            note_text = ""
            if index in note_map:
                note_items = _extract_text_values(archive.read(note_map[index]))
                filtered_note_items = [item for item in note_items if not re.fullmatch(r"\d{1,3}", item)]
                note_text = " ".join(filtered_note_items).strip()

            number_mentions = NUMERIC_RE.findall(" ".join([title, *body, note_text]))
            slide_record = {
                "slide_number": index,
                "title": title,
                "body": body,
                "note_text": note_text,
                "raw_text_items_count": len(raw_items),
                "filtered_text_items_count": len(filtered_items),
                "detected_numeric_mentions": number_mentions[:200],
                "text_blocks": text_blocks,
            }
            write_json(slides_dir / f"slide_{index:03d}.json", slide_record)
            slide_records.append(slide_record)

            rel_name = f"ppt/slides/_rels/slide{index}.xml.rels"
            chart_ids: list[int] = []
            if rel_name in names:
                rel_root = ET.fromstring(archive.read(rel_name))
                for relation in rel_root:
                    target = relation.attrib.get("Target", "")
                    chart_match = re.search(r"chart(\d+)\.xml", target)
                    if chart_match:
                        chart_ids.append(int(chart_match.group(1)))
            slide_chart_map.append({"slide_number": index, "chart_ids": sorted(set(chart_ids))})

        chart_records: list[dict[str, Any]] = []
        for chart_xml in _chart_files(names):
            chart_id = int(re.findall(r"\d+", chart_xml)[0])
            chart_root = ET.fromstring(archive.read(chart_xml))
            external = chart_root.find(".//c:externalData", NS_C)
            ext_rid = ""
            if external is not None:
                ext_rid = external.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
                )
            external_target = _chart_external_target(archive, chart_id, ext_rid or None)

            series_payload = []
            for series in chart_root.findall(".//c:ser", NS_C):
                categories, values = _extract_series_values(series)
                series_payload.append(
                    {
                        "name": _series_name(series),
                        "categories": categories[:200],
                        "values": values[:200],
                    }
                )
            chart_record = {
                "chart_id": chart_id,
                "series": series_payload,
                "external_target": external_target,
            }
            write_json(charts_dir / f"chart_{chart_id:03d}.json", chart_record)
            chart_records.append(chart_record)

    boilerplate_report = {
        "boilerplate_text_items": sorted(boilerplate),
        "boilerplate_count": len(boilerplate),
    }
    write_json(output_dir / "slide_chart_map.json", slide_chart_map)
    write_json(output_dir / "boilerplate_filter_report.json", boilerplate_report)

    deck_meta = {
        "source_file": input_path.name,
        "extracted_at": utc_now_iso(),
        "slide_count": len(slide_records),
        "chart_count": len(chart_records),
        "notes_count": sum(1 for record in slide_records if record["note_text"]),
    }
    write_json(output_dir / "deck_meta.json", deck_meta)

    return {
        "deck_meta": deck_meta,
        "slide_chart_map": slide_chart_map,
        "boilerplate_filter_report": boilerplate_report,
    }
