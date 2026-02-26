from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from finance_copilot.common import rel_path, sha256_file, slugify, utc_now_iso

MONTH_TO_NUM = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}

SOURCE_MODES = {"offline_values", "lineage", "both"}
VALID_ROLES = {
    "preview_deck",
    "close_deck",
    "preview_excel",
    "close_excel",
    "supporting_excel",
}


def infer_period_from_names(names: list[str]) -> str:
    for name in names:
        normalized = name.lower()
        p_match = re.search(r"\bp\s*0?(\d{1,2})\b", normalized)
        y_match = re.search(r"\b(20\d{2})\b", normalized)
        if p_match and y_match:
            return f"{y_match.group(1)}-P{int(p_match.group(1)):02d}"
    for name in names:
        normalized = name.lower()
        y_match = re.search(r"\b(20\d{2})\b", normalized)
        if not y_match:
            continue
        for month, month_num in MONTH_TO_NUM.items():
            if month in normalized:
                return f"{y_match.group(1)}-{month_num}"
    return "unknown-period"


def infer_pack_type(names: list[str], explicit: str | None = None) -> str:
    if explicit:
        return explicit.lower()
    lower_names = " ".join(name.lower() for name in names)
    if "preview" in lower_names:
        return "preview"
    if "close" in lower_names:
        return "close"
    return "unknown-pack"


def infer_region(names: list[str], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    normalized = " ".join(names).lower()
    if "c&us" in normalized or "canada" in normalized or "us" in normalized:
        return "TH C&US"
    if "canada" in normalized:
        return "TH Canada"
    return "unknown-region"


def infer_source_mode(
    names: list[str], explicit: str | None = None, default: str = "both"
) -> str:
    if explicit:
        mode = explicit.lower()
    else:
        normalized = " ".join(names).lower()
        if "offline" in normalized and "lineage" in normalized:
            mode = "both"
        elif "offline" in normalized:
            mode = "offline_values"
        elif "lineage" in normalized:
            mode = "lineage"
        else:
            mode = default.lower()
    if mode not in SOURCE_MODES:
        raise ValueError(f"source_mode must be one of {sorted(SOURCE_MODES)}")
    return mode


def classify_role(path: Path, pack_type: str) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        if "close" in name:
            return "close_deck"
        if "preview" in name:
            return "preview_deck"
        return "preview_deck" if pack_type == "preview" else "close_deck"
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        if "close" in name:
            return "close_excel"
        if "preview" in name:
            return "preview_excel"
        if "template" in name:
            return "preview_excel" if pack_type == "preview" else "close_excel"
        return "supporting_excel"
    raise ValueError(f"Unsupported file extension for intake routing: {path.name}")


def build_pack_manifest(
    *,
    raw_dir: Path,
    root: Path,
    period: str | None = None,
    pack_type: str | None = None,
    region: str | None = None,
    source_mode: str | None = None,
) -> dict[str, Any]:
    files = sorted([path for path in raw_dir.iterdir() if path.is_file()])
    if not files:
        raise ValueError(f"No files found in raw intake directory: {raw_dir}")

    names = [path.name for path in files]
    resolved_period = period or infer_period_from_names(names)
    resolved_pack_type = infer_pack_type(names, explicit=pack_type)
    resolved_region = infer_region(names, explicit=region)
    resolved_source_mode = infer_source_mode(names, explicit=source_mode)

    entries: list[dict[str, Any]] = []
    for path in files:
        role = classify_role(path, pack_type=resolved_pack_type)
        entries.append(
            {
                "role": role,
                "path": rel_path(path, root),
                "checksum": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "file_name": path.name,
                "file_slug": slugify(path.stem),
            }
        )

    manifest: dict[str, Any] = {
        "period": resolved_period,
        "pack_type": resolved_pack_type,
        "region": resolved_region,
        "source_mode": resolved_source_mode,
        "created_at": utc_now_iso(),
        "raw_dir": rel_path(raw_dir, root),
        "files": entries,
    }
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    required_fields = ["period", "pack_type", "region", "files", "source_mode", "created_at"]
    for field in required_fields:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")

    source_mode = manifest.get("source_mode")
    if source_mode not in SOURCE_MODES:
        errors.append(f"Invalid source_mode: {source_mode}")

    files = manifest.get("files", [])
    if not files:
        errors.append("Manifest files list is empty.")
        return errors

    role_counts: dict[str, int] = {}
    for entry in files:
        role = entry.get("role")
        role_counts[role] = role_counts.get(role, 0) + 1
        if role not in VALID_ROLES:
            errors.append(f"Invalid role in manifest: {role}")
        for required in ["path", "checksum", "size_bytes"]:
            if required not in entry:
                errors.append(f"File entry missing {required}: {entry}")

    if role_counts.get("preview_deck", 0) + role_counts.get("close_deck", 0) == 0:
        errors.append("Manifest must include at least one PPTX deck.")
    if (
        role_counts.get("preview_excel", 0)
        + role_counts.get("close_excel", 0)
        + role_counts.get("supporting_excel", 0)
        == 0
    ):
        errors.append("Manifest must include at least one workbook file.")

    return errors

