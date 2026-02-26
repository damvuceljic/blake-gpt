from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import ensure_dir, repo_root, utc_now_iso, write_json
from finance_copilot.intake import PERIOD_RE, normalize_period


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply inbox routing_plan.csv into deterministic intake folders.")
    parser.add_argument(
        "--routing-plan",
        default="data/intake/inbox/routing_plan.csv",
        help="CSV plan with file_name, detected_period, detected_pack_type, ...",
    )
    parser.add_argument(
        "--inbox-dir",
        default="data/intake/inbox/raw",
        help="Inbox source directory that contains files listed in routing plan.",
    )
    parser.add_argument(
        "--report-out",
        default="data/intake/inbox/routing_apply_report.json",
        help="JSON report path.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview moves without mutating files.")
    return parser.parse_args()


def _normalize_pack_type(value: str) -> str:
    candidate = value.strip().lower()
    if candidate not in {"preview", "close"}:
        raise ValueError(f"pack_type must be preview|close. Received: {value}")
    return candidate


def _target_raw_dir(root: Path, period: str, pack_type: str) -> Path:
    return root / "data" / "intake" / period / pack_type / "raw"


def _blocked_row(row: dict[str, str]) -> bool:
    notes = row.get("notes", "").lower()
    if "blocked:" in notes:
        return True
    return False


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    routing_plan_path = Path(args.routing_plan)
    if not routing_plan_path.is_absolute():
        routing_plan_path = (root / routing_plan_path).resolve()
    inbox_dir = Path(args.inbox_dir)
    if not inbox_dir.is_absolute():
        inbox_dir = (root / inbox_dir).resolve()
    report_out = Path(args.report_out)
    if not report_out.is_absolute():
        report_out = (root / report_out).resolve()

    if not routing_plan_path.exists():
        raise FileNotFoundError(f"Routing plan not found: {routing_plan_path}")
    if not inbox_dir.exists():
        raise FileNotFoundError(f"Inbox directory not found: {inbox_dir}")

    processed: list[dict[str, Any]] = []
    with routing_plan_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    for row in rows:
        file_name = str(row.get("file_name", "")).strip()
        source = inbox_dir / file_name
        entry: dict[str, Any] = {
            "file_name": file_name,
            "status": "pending",
            "reason": "",
            "source": str(source),
            "target": "",
        }

        if not file_name:
            entry["status"] = "skipped"
            entry["reason"] = "missing file_name"
            processed.append(entry)
            continue
        if _blocked_row(row):
            entry["status"] = "skipped"
            entry["reason"] = "blocked row (notes contains blocked:)"
            processed.append(entry)
            continue
        if not source.exists():
            entry["status"] = "skipped"
            entry["reason"] = "source file not found in inbox"
            processed.append(entry)
            continue

        try:
            period = normalize_period(str(row.get("detected_period", "")).strip())
        except Exception as exc:
            entry["status"] = "skipped"
            entry["reason"] = f"invalid period: {exc}"
            processed.append(entry)
            continue
        if not PERIOD_RE.fullmatch(period):
            entry["status"] = "skipped"
            entry["reason"] = "period is not YYYY-PNN"
            processed.append(entry)
            continue

        try:
            pack_type = _normalize_pack_type(str(row.get("detected_pack_type", "")))
        except Exception as exc:
            entry["status"] = "skipped"
            entry["reason"] = str(exc)
            processed.append(entry)
            continue

        target_dir = _target_raw_dir(root, period=period, pack_type=pack_type)
        ensure_dir(target_dir)
        target = target_dir / source.name
        counter = 1
        while target.exists():
            target = target_dir / f"{source.stem}_{counter}{source.suffix}"
            counter += 1

        entry["target"] = str(target)
        if not args.dry_run:
            source.rename(target)
        entry["status"] = "moved"
        processed.append(entry)

    moved = sum(1 for item in processed if item["status"] == "moved")
    skipped = sum(1 for item in processed if item["status"] == "skipped")
    report = {
        "generated_at": utc_now_iso(),
        "routing_plan": str(routing_plan_path),
        "inbox_dir": str(inbox_dir),
        "dry_run": args.dry_run,
        "totals": {
            "rows": len(processed),
            "moved": moved,
            "skipped": skipped,
        },
        "results": processed,
    }
    write_json(report_out, report)
    print(f"Routing apply report: {report_out}")
    print(f"Rows: {len(processed)} | moved: {moved} | skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
