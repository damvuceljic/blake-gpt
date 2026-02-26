from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import ensure_dir, repo_root
from finance_copilot.intake import (
    PERIOD_RE,
    VALID_EXTENSIONS,
    derive_pair_key,
    infer_pack_type,
    infer_period_from_names,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move root-level Excel/PPT files to intake inbox and generate routing_plan.csv."
    )
    parser.add_argument(
        "--inbox-dir",
        default="data/intake/inbox/raw",
        help="Inbox raw directory for migrated files.",
    )
    parser.add_argument(
        "--routing-plan-out",
        default="data/intake/inbox/routing_plan.csv",
        help="Routing plan CSV output path.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without moving files.")
    return parser.parse_args()


def _detect_pack_type(file_name: str) -> str:
    return infer_pack_type([file_name], explicit=None)


def _detect_role_guess(file_path: Path, detected_pack_type: str) -> str:
    lower = file_path.name.lower()
    suffix = file_path.suffix.lower()
    if suffix == ".pptx":
        if detected_pack_type in {"preview", "close"}:
            return f"{detected_pack_type}_deck"
        return "unknown_deck"

    if suffix in {".xlsx", ".xlsm", ".xls"}:
        if "template" in lower and detected_pack_type in {"preview", "close"}:
            if "offline" in lower:
                return f"{detected_pack_type}_offline_workbook"
            return f"{detected_pack_type}_formula_workbook"
        return "supporting_excel"

    return "unsupported"


def _period_note(period: str) -> str:
    if period == "unknown-period":
        return "blocked: unresolved period"
    if not PERIOD_RE.fullmatch(period):
        return "blocked: period must be YYYY-PNN"
    return ""


def _pack_type_note(pack_type: str) -> str:
    if pack_type not in {"preview", "close"}:
        return "blocked: unresolved pack_type"
    return ""


def _offline_variant_note(file_name: str) -> str:
    lower = file_name.lower()
    if "offline" not in lower:
        return ""
    if "offline_" in lower or "offline-" in lower:
        return "offline variant detected; explicit primary selection may be required"
    return ""


def _move_file(source: Path, target: Path) -> Path:
    target = target.resolve()
    counter = 1
    while target.exists():
        target = target.with_name(f"{target.stem}_{counter}{target.suffix}")
        counter += 1
    shutil.move(str(source), str(target))
    return target


def _csv_row(record: dict[str, Any]) -> list[str]:
    return [
        str(record["file_name"]),
        str(record["detected_period"]),
        str(record["detected_pack_type"]),
        str(record["role_guess"]),
        str(record["pair_key"]),
        "true" if record["needs_user_choice"] else "false",
        str(record["notes"]),
    ]


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    inbox_dir = Path(args.inbox_dir)
    if not inbox_dir.is_absolute():
        inbox_dir = (root / inbox_dir).resolve()
    routing_plan_out = Path(args.routing_plan_out)
    if not routing_plan_out.is_absolute():
        routing_plan_out = (root / routing_plan_out).resolve()

    root_files = sorted(
        [
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS
        ]
    )
    if not root_files:
        print("No root-level Excel/PPT files found.")
        return 0

    ensure_dir(inbox_dir)
    ensure_dir(routing_plan_out.parent)

    records: list[dict[str, Any]] = []
    offline_by_pair: dict[str, list[int]] = {}
    for file_path in root_files:
        detected_period = infer_period_from_names([file_path.name])
        detected_pack_type = _detect_pack_type(file_path.name)
        role_guess = _detect_role_guess(file_path, detected_pack_type)
        pair_key = derive_pair_key(file_path.stem)

        notes = [note for note in [
            _period_note(detected_period),
            _pack_type_note(detected_pack_type),
            _offline_variant_note(file_path.name),
        ] if note]
        record = {
            "source_path": str(file_path.resolve()),
            "file_name": file_path.name,
            "detected_period": detected_period,
            "detected_pack_type": detected_pack_type,
            "role_guess": role_guess,
            "pair_key": pair_key,
            "needs_user_choice": False,
            "notes": " | ".join(notes),
        }
        records.append(record)

        if role_guess.endswith("_offline_workbook"):
            offline_by_pair.setdefault(f"{detected_pack_type}:{pair_key}", []).append(len(records) - 1)

    for pair_key, indices in offline_by_pair.items():
        if len(indices) <= 1:
            continue
        for idx in indices:
            records[idx]["needs_user_choice"] = True
            note = str(records[idx]["notes"]).strip()
            extra = f"multiple offline variants for {pair_key}; explicit choice required"
            records[idx]["notes"] = f"{note} | {extra}" if note else extra

    if not args.dry_run:
        for record in records:
            source = Path(record["source_path"])
            target = inbox_dir / record["file_name"]
            moved_target = _move_file(source, target)
            record["file_name"] = moved_target.name
            record["source_path"] = str(moved_target.resolve())

    header = [
        "file_name",
        "detected_period",
        "detected_pack_type",
        "role_guess",
        "pair_key",
        "needs_user_choice",
        "notes",
    ]
    with routing_plan_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for record in records:
            writer.writerow(_csv_row(record))

    print(f"Root files discovered: {len(root_files)}")
    print(f"Routing plan written: {routing_plan_out}")
    print(f"Inbox directory: {inbox_dir}")
    if args.dry_run:
        print("Dry run only; no files were moved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
