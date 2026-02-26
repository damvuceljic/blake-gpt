from __future__ import annotations

import re
import shutil
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

VALID_PACK_TYPES = {"preview", "close"}
VALID_EXTENSIONS = {".pptx", ".xlsx", ".xlsm", ".xls"}
SOURCE_MODES = {"offline_values", "lineage", "both"}
VALID_ROLES = {
    "preview_deck",
    "close_deck",
    "preview_formula_workbook",
    "preview_offline_workbook",
    "close_formula_workbook",
    "close_offline_workbook",
    "supporting_excel",
}
VALID_VALUE_MODES = {"deck", "lineage_formula", "offline_values", "supporting_excel"}

PERIOD_RE = re.compile(r"^\d{4}-P\d{2}$")
YEAR_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
OFFLINE_TRAILER_RE = re.compile(r"[-_]?offline(?:[-_].*)?$", re.IGNORECASE)


def normalize_period(period: str) -> str:
    candidate = period.strip()
    if PERIOD_RE.fullmatch(candidate):
        return candidate
    y_m_match = YEAR_MONTH_RE.fullmatch(candidate)
    if y_m_match:
        year, month = y_m_match.group(1), int(y_m_match.group(2))
        if 1 <= month <= 12:
            return f"{year}-P{month:02d}"
    loose_match = re.fullmatch(r"(\d{4})[-_ ]?[pP](\d{1,2})", candidate)
    if loose_match:
        return f"{loose_match.group(1)}-P{int(loose_match.group(2)):02d}"
    raise ValueError(f"Period must use YYYY-PNN format. Received: {period}")


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
                return f"{y_match.group(1)}-P{int(month_num):02d}"
    return "unknown-period"


def infer_pack_type(names: list[str], explicit: str | None = None) -> str:
    if explicit:
        candidate = explicit.lower().strip()
        if candidate not in VALID_PACK_TYPES:
            raise ValueError(f"pack_type must be one of {sorted(VALID_PACK_TYPES)}")
        return candidate
    lower_names = " ".join(name.lower() for name in names)
    has_preview = "preview" in lower_names
    has_close = "close" in lower_names
    if has_preview and not has_close:
        return "preview"
    if has_close and not has_preview:
        return "close"
    return "unknown-pack"


def infer_region(names: list[str], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    normalized = " ".join(names).lower()
    if "c&us" in normalized:
        return "TH C&US"
    if "canada" in normalized:
        return "TH Canada"
    if "us" in normalized:
        return "TH C&US"
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


def is_processed_intake_dir(path: Path, root: Path) -> bool:
    processed_root = (root / "data" / "intake" / "processed").resolve()
    try:
        path.resolve().relative_to(processed_root)
        return True
    except ValueError:
        return False


def derive_pair_key(stem: str) -> str:
    normalized = slugify(stem)
    stripped = OFFLINE_TRAILER_RE.sub("", normalized).strip("-")
    return stripped or normalized


def _infer_entry_pack_type(path: Path, fallback_pack_type: str) -> str:
    lower = path.name.lower()
    if "preview" in lower:
        return "preview"
    if "close" in lower:
        return "close"
    return fallback_pack_type


def _classify_file(path: Path, pack_type: str) -> dict[str, Any]:
    lower = path.name.lower()
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        entry_pack_type = _infer_entry_pack_type(path, fallback_pack_type=pack_type)
        role = f"{entry_pack_type}_deck"
        return {
            "role": role,
            "pair_key": "",
            "value_mode": "deck",
            "is_core_required": True,
            "pairing_status": "not_applicable",
            "offline_primary_selected": False,
        }

    if suffix in {".xlsx", ".xlsm", ".xls"}:
        entry_pack_type = _infer_entry_pack_type(path, fallback_pack_type=pack_type)
        is_offline = "offline" in lower
        is_core_template = "template" in lower and entry_pack_type in VALID_PACK_TYPES
        if is_core_template:
            role_suffix = "offline_workbook" if is_offline else "formula_workbook"
            return {
                "role": f"{entry_pack_type}_{role_suffix}",
                "pair_key": derive_pair_key(path.stem),
                "value_mode": "offline_values" if is_offline else "lineage_formula",
                "is_core_required": True,
                "pairing_status": "pending",
                "offline_primary_selected": False,
            }

        return {
            "role": "supporting_excel",
            "pair_key": derive_pair_key(path.stem),
            "value_mode": "supporting_excel",
            "is_core_required": False,
            "pairing_status": "not_applicable",
            "offline_primary_selected": False,
        }

    raise ValueError(f"Unsupported file extension for intake routing: {path.name}")


def _resolve_offline_choice(
    pair_key: str,
    pack_type: str,
    offlines: list[dict[str, Any]],
    pair_choices: dict[str, str],
) -> int | None:
    selected = (
        pair_choices.get(pair_key)
        or pair_choices.get(f"{pack_type}:{pair_key}")
        or ""
    ).strip().lower()
    if not selected:
        return None
    for idx, entry in enumerate(offlines):
        file_name = str(entry.get("file_name", "")).strip().lower()
        file_slug = str(entry.get("file_slug", "")).strip().lower()
        if selected in {file_name, file_slug}:
            return idx
    return None


def _apply_pairing_logic(
    entries: list[dict[str, Any]], pair_choices: dict[str, str]
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for entry in entries:
        role = str(entry.get("role", ""))
        if not role.endswith("_formula_workbook") and not role.endswith("_offline_workbook"):
            continue
        pair_key = str(entry.get("pair_key", "")).strip()
        if not pair_key:
            continue
        pack_type = role.split("_", 1)[0]
        bucket = grouped.setdefault((pack_type, pair_key), {"formulas": [], "offlines": []})
        if role.endswith("_formula_workbook"):
            bucket["formulas"].append(entry)
        else:
            bucket["offlines"].append(entry)

    issues: list[str] = []
    choice_required_pairs: list[str] = []
    for (pack_type, pair_key), bucket in grouped.items():
        formulas = bucket["formulas"]
        offlines = bucket["offlines"]
        if formulas and offlines:
            if len(offlines) == 1:
                formulas[0]["pairing_status"] = "paired"
                offlines[0]["pairing_status"] = "paired"
                offlines[0]["offline_primary_selected"] = True
                continue

            selected_idx = _resolve_offline_choice(
                pair_key,
                pack_type,
                offlines,
                pair_choices,
            )
            if selected_idx is None:
                choice_required_pairs.append(f"{pack_type}:{pair_key}")
                issues.append(
                    f"Offline ambiguity for pair '{pack_type}:{pair_key}'. "
                    "Provide --pair-choice-file mapping to one offline file."
                )
                for entry in formulas:
                    entry["pairing_status"] = "offline_choice_required"
                for entry in offlines:
                    entry["pairing_status"] = "offline_choice_required"
                    entry["offline_primary_selected"] = False
                continue

            for entry in formulas:
                entry["pairing_status"] = "paired"
            for idx, entry in enumerate(offlines):
                entry["pairing_status"] = "paired" if idx == selected_idx else "alternate_offline"
                entry["offline_primary_selected"] = idx == selected_idx
            continue

        if formulas and not offlines:
            issues.append(f"Missing offline workbook for pair '{pack_type}:{pair_key}'.")
            for entry in formulas:
                entry["pairing_status"] = "offline_missing"
        elif offlines and not formulas:
            issues.append(f"Missing formula workbook for pair '{pack_type}:{pair_key}'.")
            for entry in offlines:
                entry["pairing_status"] = "formula_missing"
                entry["offline_primary_selected"] = False

    return {"issues": issues, "choice_required_pairs": sorted(choice_required_pairs)}


def _required_roles(pack_type: str) -> list[str]:
    return [
        f"{pack_type}_deck",
        f"{pack_type}_formula_workbook",
        f"{pack_type}_offline_workbook",
    ]


def build_pack_manifest(
    *,
    raw_dir: Path,
    root: Path,
    period: str | None = None,
    pack_type: str | None = None,
    region: str | None = None,
    source_mode: str | None = None,
    strict_core: bool = True,
    allow_missing_core: bool = False,
    pair_choices: dict[str, str] | None = None,
) -> dict[str, Any]:
    files = sorted(
        [path for path in raw_dir.iterdir() if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS]
    )
    if not files:
        raise ValueError(f"No supported intake files found in raw intake directory: {raw_dir}")

    names = [path.name for path in files]
    resolved_period = normalize_period(period) if period else infer_period_from_names(names)
    resolved_pack_type = infer_pack_type(names, explicit=pack_type)
    resolved_region = infer_region(names, explicit=region)
    resolved_source_mode = infer_source_mode(names, explicit=source_mode)

    if resolved_period == "unknown-period":
        raise ValueError("Unable to infer period. Provide --period in YYYY-PNN format.")
    resolved_period = normalize_period(resolved_period)

    if resolved_pack_type not in VALID_PACK_TYPES:
        raise ValueError("Unable to infer pack_type. Provide --pack-type preview|close.")

    resolved_pair_choices = {str(k).strip(): str(v).strip() for k, v in (pair_choices or {}).items()}

    entries: list[dict[str, Any]] = []
    for path in files:
        classified = _classify_file(path, pack_type=resolved_pack_type)
        entries.append(
            {
                "role": classified["role"],
                "path": rel_path(path, root),
                "checksum": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "file_name": path.name,
                "file_slug": slugify(path.stem),
                "pair_key": classified["pair_key"],
                "value_mode": classified["value_mode"],
                "is_core_required": classified["is_core_required"],
                "pairing_status": classified["pairing_status"],
                "offline_primary_selected": classified["offline_primary_selected"],
            }
        )

    pairing = _apply_pairing_logic(entries, resolved_pair_choices)
    required_roles = _required_roles(resolved_pack_type)
    role_counts: dict[str, int] = {}
    for entry in entries:
        role = str(entry.get("role", ""))
        role_counts[role] = role_counts.get(role, 0) + 1
    missing_roles = [role for role in required_roles if role_counts.get(role, 0) == 0]

    core_status = "pass"
    if strict_core and not allow_missing_core and (missing_roles or pairing["issues"]):
        core_status = "fail"
    elif strict_core and (missing_roles or pairing["issues"]):
        core_status = "warn"

    manifest: dict[str, Any] = {
        "period": resolved_period,
        "pack_type": resolved_pack_type,
        "region": resolved_region,
        "source_mode": resolved_source_mode,
        "created_at": utc_now_iso(),
        "raw_dir": rel_path(raw_dir, root),
        "files": entries,
        "core_validation": {
            "strict_core": strict_core,
            "allow_missing_core": allow_missing_core,
            "required_roles": required_roles,
            "missing_roles": missing_roles,
            "pairing_issues": pairing["issues"],
            "pair_choice_required_pairs": pairing["choice_required_pairs"],
            "status": core_status,
        },
    }
    return manifest


def validate_manifest(
    manifest: dict[str, Any],
    strict_core: bool | None = None,
    allow_missing_core: bool | None = None,
) -> list[str]:
    errors: list[str] = []

    required_fields = [
        "period",
        "pack_type",
        "region",
        "files",
        "source_mode",
        "created_at",
        "core_validation",
    ]
    for field in required_fields:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")

    period = str(manifest.get("period", ""))
    if not PERIOD_RE.fullmatch(period):
        errors.append(f"Period must match YYYY-PNN. Received: {period}")

    pack_type = str(manifest.get("pack_type", ""))
    if pack_type not in VALID_PACK_TYPES:
        errors.append(f"Invalid pack_type: {pack_type}")

    source_mode = manifest.get("source_mode")
    if source_mode not in SOURCE_MODES:
        errors.append(f"Invalid source_mode: {source_mode}")

    files = manifest.get("files", [])
    if not files:
        errors.append("Manifest files list is empty.")
        return errors

    role_counts: dict[str, int] = {}
    has_deck = False
    has_workbook = False
    for entry in files:
        role = str(entry.get("role", ""))
        role_counts[role] = role_counts.get(role, 0) + 1
        if role not in VALID_ROLES:
            errors.append(f"Invalid role in manifest: {role}")
        for required in [
            "path",
            "checksum",
            "size_bytes",
            "pair_key",
            "value_mode",
            "is_core_required",
            "pairing_status",
            "offline_primary_selected",
        ]:
            if required not in entry:
                errors.append(f"File entry missing {required}: {entry}")
        value_mode = str(entry.get("value_mode", ""))
        if value_mode not in VALID_VALUE_MODES:
            errors.append(f"Invalid value_mode '{value_mode}' for file: {entry.get('file_name', '')}")
        if role.endswith("_deck"):
            has_deck = True
        else:
            has_workbook = True

    if not has_deck:
        errors.append("Manifest must include at least one PPTX deck.")
    if not has_workbook:
        errors.append("Manifest must include at least one workbook file.")

    core_validation = manifest.get("core_validation", {})
    strict_effective = bool(core_validation.get("strict_core", strict_core if strict_core is not None else True))
    allow_missing_effective = bool(
        core_validation.get(
            "allow_missing_core",
            allow_missing_core if allow_missing_core is not None else False,
        )
    )
    required_roles = _required_roles(pack_type) if pack_type in VALID_PACK_TYPES else []
    missing_roles = [role for role in required_roles if role_counts.get(role, 0) == 0]
    if strict_effective and not allow_missing_effective and missing_roles:
        errors.append(f"Strict core validation failed. Missing roles: {', '.join(missing_roles)}")

    pair_choice_required = [
        str(entry.get("file_name", ""))
        for entry in files
        if str(entry.get("pairing_status", "")) == "offline_choice_required"
    ]
    if pair_choice_required and strict_effective and not allow_missing_effective:
        errors.append(
            "Offline choice required for one or more workbook pairs. "
            "Provide --pair-choice-file mapping pair_key to selected offline file."
        )

    pairing_status_failures = [
        str(entry.get("file_name", ""))
        for entry in files
        if str(entry.get("pairing_status", "")) in {"offline_missing", "formula_missing"}
    ]
    if pairing_status_failures and strict_effective and not allow_missing_effective:
        errors.append(
            "Workbook pair completeness failed for: " + ", ".join(pairing_status_failures)
        )

    return errors


def archive_raw_files(
    *,
    raw_dir: Path,
    root: Path,
    period: str,
    pack_type: str,
    manifest_files: list[dict[str, Any]],
) -> dict[str, Any]:
    timestamp = utc_now_iso().replace(":", "").replace("+00:00", "Z")
    archive_dir = root / "data" / "intake" / "processed" / period / pack_type / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_rows: list[dict[str, Any]] = []
    raw_entries = {str(item.get("path", "")): item for item in manifest_files}
    for file_path in sorted([item for item in raw_dir.iterdir() if item.is_file()]):
        rel = rel_path(file_path, root)
        manifest_entry = raw_entries.get(rel, {})
        target = archive_dir / file_path.name
        suffix_counter = 1
        while target.exists():
            target = archive_dir / f"{file_path.stem}_{suffix_counter}{file_path.suffix}"
            suffix_counter += 1
        checksum = (
            str(manifest_entry.get("checksum", ""))
            if manifest_entry
            else sha256_file(file_path)
        )
        size_bytes = int(manifest_entry.get("size_bytes", file_path.stat().st_size))
        source_rel = rel_path(file_path, root)
        shutil.move(str(file_path), str(target))
        archive_rows.append(
            {
                "file_name": file_path.name,
                "checksum": checksum,
                "size_bytes": size_bytes,
                "source_raw_path": source_rel,
                "archived_path": rel_path(target, root),
                "archived_at": utc_now_iso(),
            }
        )

    return {
        "period": period,
        "pack_type": pack_type,
        "archive_dir": rel_path(archive_dir, root),
        "file_count": len(archive_rows),
        "files": archive_rows,
    }
