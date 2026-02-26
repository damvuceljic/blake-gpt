from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import read_json, repo_root, utc_now_iso, write_json
from finance_copilot.intake import PERIOD_RE, archive_raw_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process all staged intake raw folders and generate a worked-vs-failed effectiveness report."
    )
    parser.add_argument("--use-llm-postprocess", action="store_true")
    parser.add_argument("--use-historical-context", action="store_true")
    parser.add_argument("--historical-context", help="Optional historical calibration bundle path.")
    parser.add_argument(
        "--allow-missing-core",
        action="store_true",
        help="Explicit override to process packs missing strict core files.",
    )
    parser.add_argument("--archive-on-success", action="store_true")
    parser.add_argument(
        "--report-out",
        default="data/analysis/intake_effectiveness_report.json",
        help="Effectiveness report output path.",
    )
    return parser.parse_args()


def _run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, check=False, text=True, capture_output=True)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _discover_raw_dirs(root: Path) -> list[Path]:
    base = root / "data" / "intake"
    candidates: list[Path] = []
    for period_dir in sorted(base.iterdir()) if base.exists() else []:
        if not period_dir.is_dir():
            continue
        if period_dir.name in {"processed", "inbox"}:
            continue
        if not PERIOD_RE.fullmatch(period_dir.name):
            continue
        for pack_type in ["preview", "close"]:
            raw_dir = period_dir / pack_type / "raw"
            if raw_dir.exists() and raw_dir.is_dir() and any(raw_dir.iterdir()):
                candidates.append(raw_dir)
    return candidates


def _pair_choice_file(root: Path, period: str, pack_type: str) -> Path | None:
    candidates = [
        root / "data" / "intake" / period / pack_type / "pair_choices.json",
        root / "data" / "intake" / "pair_choices" / f"{period}_{pack_type}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _step_status(result: dict[str, Any]) -> str:
    return "pass" if int(result.get("returncode", 1)) == 0 else "fail"


def _load_key_insights(root: Path, period: str, pack_type: str) -> dict[str, Any]:
    analysis_dir = root / "data" / "analysis" / period / pack_type
    hot_path = analysis_dir / "hot_questions_response.json"
    proof_path = analysis_dir / "proofing_issues.json"
    variance_path = analysis_dir / "variance_watch_issues.json"
    insights: dict[str, Any] = {}
    if hot_path.exists():
        payload = read_json(hot_path)
        insights["hot_score"] = payload.get("score_total")
        insights["hot_band"] = payload.get("score_band")
    if proof_path.exists():
        payload = read_json(proof_path)
        insights["proof_issue_count"] = payload.get("issue_count")
    if variance_path.exists():
        payload = read_json(variance_path)
        insights["variance_issue_count"] = payload.get("issue_count")
    return insights


def _archive_if_enabled(
    *,
    root: Path,
    raw_dir: Path,
    period: str,
    pack_type: str,
    archive_on_success: bool,
) -> dict[str, Any]:
    if not archive_on_success:
        return {"enabled": False, "status": "skipped"}
    manifest_path = root / "data" / "packs" / period / pack_type / "pack_manifest.json"
    if not manifest_path.exists():
        return {"enabled": True, "status": "failed", "reason": "manifest missing"}
    manifest = read_json(manifest_path)
    archive_payload = archive_raw_files(
        raw_dir=raw_dir,
        root=root,
        period=period,
        pack_type=pack_type,
        manifest_files=manifest.get("files", []),
    )
    archive_manifest_path = root / archive_payload["archive_dir"] / "archive_manifest.json"
    write_json(archive_manifest_path, archive_payload)
    return {
        "enabled": True,
        "status": "archived",
        "archive_manifest_path": str(archive_manifest_path),
        "file_count": archive_payload.get("file_count", 0),
    }


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    report_out = Path(args.report_out)
    if not report_out.is_absolute():
        report_out = (root / report_out).resolve()
    report_out.parent.mkdir(parents=True, exist_ok=True)

    raw_dirs = _discover_raw_dirs(root)
    results: list[dict[str, Any]] = []
    for raw_dir in raw_dirs:
        period = raw_dir.parents[1].name
        pack_type = raw_dir.parent.name
        raw_rel = str(raw_dir.relative_to(root).as_posix())

        pair_choice = _pair_choice_file(root, period=period, pack_type=pack_type)
        route_cmd = [
            sys.executable,
            "scripts/intake/route_intake.py",
            "--raw-dir",
            raw_rel,
            "--period",
            period,
            "--pack-type",
            pack_type,
            "--strict-core",
        ]
        if args.allow_missing_core:
            route_cmd.append("--allow-missing-core")
        if pair_choice:
            route_cmd.extend(["--pair-choice-file", str(pair_choice)])
        route_result = _run_command(route_cmd, root)

        validate_result = {"returncode": 2, "stdout": "", "stderr": "route failed", "command": []}
        tokenize_result = {"returncode": 2, "stdout": "", "stderr": "route failed", "command": []}
        hot_result = {"returncode": 2, "stdout": "", "stderr": "tokenize failed", "command": []}
        proof_result = {"returncode": 2, "stdout": "", "stderr": "tokenize failed", "command": []}
        variance_result = {"returncode": 2, "stdout": "", "stderr": "tokenize failed", "command": []}

        manifest_path = root / "data" / "packs" / period / pack_type / "pack_manifest.json"
        normalized_dir = root / "data" / "normalized" / period / pack_type
        if route_result["returncode"] == 0:
            validate_result = _run_command(
                [
                    sys.executable,
                    "scripts/intake/validate_manifest.py",
                    "--manifest",
                    str(manifest_path),
                ],
                root,
            )

        if validate_result["returncode"] == 0:
            tokenize_result = _run_command(
                [
                    sys.executable,
                    "scripts/extract/tokenize_pack.py",
                    "--manifest",
                    str(manifest_path),
                ],
                root,
            )

        if tokenize_result["returncode"] == 0:
            hot_cmd = [
                sys.executable,
                "scripts/analyze/hot_questions.py",
                "--pack-dir",
                str(normalized_dir),
            ]
            if args.use_llm_postprocess:
                hot_cmd.append("--use-llm-postprocess")
            if args.use_historical_context:
                hot_cmd.append("--use-historical-context")
            if args.historical_context:
                hot_cmd.extend(["--historical-context", args.historical_context])
            hot_result = _run_command(hot_cmd, root)

            proof_cmd = [
                sys.executable,
                "scripts/analyze/deck_proofing.py",
                "--pack-dir",
                str(normalized_dir),
            ]
            if args.use_llm_postprocess:
                proof_cmd.append("--use-llm-postprocess")
            proof_result = _run_command(proof_cmd, root)

            variance_cmd = [
                sys.executable,
                "scripts/analyze/variance_watch.py",
                "--pack-dir",
                str(normalized_dir),
            ]
            if args.use_llm_postprocess:
                variance_cmd.append("--use-llm-postprocess")
            variance_result = _run_command(variance_cmd, root)

        steps = {
            "route_manifest": _step_status(route_result),
            "validate_manifest": _step_status(validate_result),
            "tokenize_pack": _step_status(tokenize_result),
            "hot_questions": _step_status(hot_result),
            "deck_proofing": _step_status(proof_result),
            "variance_watch": _step_status(variance_result),
        }
        all_pass = all(status == "pass" for status in steps.values())
        archive = _archive_if_enabled(
            root=root,
            raw_dir=raw_dir,
            period=period,
            pack_type=pack_type,
            archive_on_success=args.archive_on_success and all_pass,
        )
        recommendation = "archive-retain" if all_pass else "reprocess-needed"

        results.append(
            {
                "period": period,
                "pack_type": pack_type,
                "raw_dir": raw_rel,
                "pair_choice_file": str(pair_choice) if pair_choice else "",
                "steps": steps,
                "insights": _load_key_insights(root, period=period, pack_type=pack_type),
                "recommendation": recommendation,
                "archive": archive,
                "diagnostics": {
                    "route_manifest": route_result,
                    "validate_manifest": validate_result,
                    "tokenize_pack": tokenize_result,
                    "hot_questions": hot_result,
                    "deck_proofing": proof_result,
                    "variance_watch": variance_result,
                },
            }
        )

    summary = {
        "total_packs": len(results),
        "passed": sum(1 for item in results if item["recommendation"] == "archive-retain"),
        "failed": sum(1 for item in results if item["recommendation"] == "reprocess-needed"),
    }
    report = {
        "generated_at": utc_now_iso(),
        "archive_on_success": args.archive_on_success,
        "use_llm_postprocess": args.use_llm_postprocess,
        "allow_missing_core": args.allow_missing_core,
        "results": results,
        "summary": summary,
    }
    write_json(report_out, report)
    print(f"Intake effectiveness report written: {report_out}")
    print(
        f"Processed packs: {summary['total_packs']} | "
        f"passed: {summary['passed']} | failed: {summary['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
