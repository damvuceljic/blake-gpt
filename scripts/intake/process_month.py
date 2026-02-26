from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.analysis import (
    load_hotq_scoring_config,
    persist_analysis,
    run_deck_proofing,
    run_hot_questions,
    run_variance_watch,
)
from finance_copilot.chunks import build_token_chunks
from finance_copilot.common import ensure_dir, read_json, repo_root, slugify, write_json
from finance_copilot.deck import extract_deck
from finance_copilot.intake import (
    archive_raw_files,
    build_pack_manifest,
    is_processed_intake_dir,
    validate_manifest,
)
from finance_copilot.llm_postprocess import run_llm_postprocess
from finance_copilot.workbook import extract_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run monthly end-to-end intake, extraction, and baseline analyses.")
    parser.add_argument("--raw-dir", required=True, help="Raw intake directory with source files.")
    parser.add_argument("--period", help="Reporting period (example: 2026-P02)")
    parser.add_argument("--pack-type", choices=["preview", "close"], help="Pack type preview|close")
    parser.add_argument("--region", help="Region label")
    parser.add_argument("--source-mode", default="both", choices=["offline_values", "lineage", "both"])
    parser.add_argument(
        "--strict-core",
        dest="strict_core",
        action="store_true",
        default=True,
        help="Require deck + formula workbook + offline workbook for the selected pack type.",
    )
    parser.add_argument(
        "--no-strict-core",
        dest="strict_core",
        action="store_false",
        help="Disable strict core validation checks.",
    )
    parser.add_argument(
        "--allow-missing-core",
        action="store_true",
        help="Allow processing to continue even if strict core checks fail.",
    )
    parser.add_argument(
        "--pair-choice-file",
        help="JSON object mapping pair_key to selected offline file_name/file_slug.",
    )
    parser.add_argument("--max-rows", type=int, help="Optional max rows for workbook extraction")
    parser.add_argument("--max-cols", type=int, help="Optional max cols for workbook extraction")
    parser.add_argument("--question", help="Optional Hot Questions focus text")
    parser.add_argument(
        "--scoring-config",
        help="Optional Hot Questions scoring config JSON; defaults to data/context/hot_questions_scoring.default.json",
    )
    parser.add_argument(
        "--use-llm-postprocess",
        action="store_true",
        help="Run optional Codex-CLI post-processing for Hot Questions, Proofing, and Variance.",
    )
    parser.add_argument(
        "--use-historical-context",
        action="store_true",
        help="Inject historical calibration bundle from data/context/historical/calibration_bundle.json when available.",
    )
    parser.add_argument("--historical-context", help="Optional explicit historical calibration bundle path.")
    parser.add_argument("--llm-model", help="Optional model override for codex exec post-processing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    raw_dir = Path(args.raw_dir)
    if not raw_dir.is_absolute():
        raw_dir = (root / raw_dir).resolve()
    if is_processed_intake_dir(raw_dir, root):
        raise ValueError(
            f"Processed intake folders are read-protected. Use data/intake/<period>/<pack_type>/raw instead: {raw_dir}"
        )

    pair_choices: dict[str, str] | None = None
    if args.pair_choice_file:
        pair_choice_path = Path(args.pair_choice_file)
        if not pair_choice_path.is_absolute():
            pair_choice_path = (root / pair_choice_path).resolve()
        if not pair_choice_path.exists():
            raise FileNotFoundError(f"Pair choice file not found: {pair_choice_path}")
        payload = json.loads(pair_choice_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("--pair-choice-file must be a JSON object.")
        pair_choices = {str(key): str(value) for key, value in payload.items()}

    try:
        manifest = build_pack_manifest(
            raw_dir=raw_dir,
            root=root,
            period=args.period,
            pack_type=args.pack_type,
            region=args.region,
            source_mode=args.source_mode,
            strict_core=args.strict_core,
            allow_missing_core=args.allow_missing_core,
            pair_choices=pair_choices,
        )
    except ValueError as exc:
        print(f"[intake-error] {exc}")
        return 2
    errors = validate_manifest(
        manifest,
        strict_core=args.strict_core,
        allow_missing_core=args.allow_missing_core,
    )
    if errors:
        for error in errors:
            print(f"[manifest-error] {error}")
        return 2

    manifest_path = root / "data" / "packs" / manifest["period"] / manifest["pack_type"] / "pack_manifest.json"
    ensure_dir(manifest_path.parent)
    write_json(manifest_path, manifest)
    print(f"Manifest ready: {manifest_path}")

    normalized_dir = root / "data" / "normalized" / manifest["period"] / manifest["pack_type"]
    ensure_dir(normalized_dir / "decks")
    ensure_dir(normalized_dir / "workbooks")
    ensure_dir(normalized_dir / "chunks")
    write_json(normalized_dir / "pack_manifest.json", manifest)

    for file_entry in manifest["files"]:
        source_path = root / file_entry["path"]
        role = file_entry["role"]
        slug = slugify(Path(file_entry["file_name"]).stem)
        if role.endswith("_deck"):
            extract_deck(input_path=source_path, output_dir=normalized_dir / "decks" / slug)
        else:
            extract_workbook(
                input_path=source_path,
                output_dir=normalized_dir / "workbooks" / slug,
                max_rows=args.max_rows,
                max_cols=args.max_cols,
            )

    chunk_index = build_token_chunks(
        normalized_pack_dir=normalized_dir, output_path=normalized_dir / "chunks" / "chunks.jsonl"
    )
    write_json(
        normalized_dir / "pack_summary.json",
        {
            "period": manifest["period"],
            "pack_type": manifest["pack_type"],
            "source_mode": manifest["source_mode"],
            "lineage_degraded": manifest["source_mode"] == "offline_values",
            "chunk_index": chunk_index,
        },
    )

    analysis_dir = root / "data" / "analysis" / manifest["period"] / manifest["pack_type"]
    scoring_path = Path(args.scoring_config).resolve() if args.scoring_config else (root / "data" / "context" / "hot_questions_scoring.default.json")
    if not scoring_path.is_absolute():
        scoring_path = (root / scoring_path).resolve()
    scoring_config = load_hotq_scoring_config(scoring_path if scoring_path.exists() else None)
    month_override_path = root / "data" / "context" / "month_overrides" / f"{manifest['period']}.json"
    month_override = read_json(month_override_path) if month_override_path.exists() else None
    historical_context = None
    if args.historical_context:
        historical_path = Path(args.historical_context)
        if not historical_path.is_absolute():
            historical_path = (root / historical_path).resolve()
        if historical_path.exists():
            historical_context = read_json(historical_path)
    elif args.use_historical_context:
        default_historical = root / "data" / "context" / "historical" / "calibration_bundle.json"
        if default_historical.exists():
            historical_context = read_json(default_historical)

    hot = run_hot_questions(
        normalized_dir,
        question=args.question,
        scoring_config=scoring_config,
        month_override=month_override,
        historical_context=historical_context,
    )
    proofing = run_deck_proofing(normalized_dir, prior_pack_dir=None)
    variance = run_variance_watch(normalized_dir)
    hot_out = analysis_dir / "hot_questions_response.json"
    proof_out = analysis_dir / "proofing_issues.json"
    variance_out = analysis_dir / "variance_watch_issues.json"

    if args.use_llm_postprocess:
        hot_det = analysis_dir / "hot_questions_response.deterministic.json"
        proof_det = analysis_dir / "proofing_issues.deterministic.json"
        variance_det = analysis_dir / "variance_watch_issues.deterministic.json"
        persist_analysis(hot, hot_det)
        persist_analysis(proofing, proof_det)
        persist_analysis(variance, variance_det)

        hot_llm = run_llm_postprocess(
            repo_root=root,
            prompt_file=root / "prompts" / "hot_questions" / "executive_brief_prompt.txt",
            input_json=hot_det,
            output_json=analysis_dir / "hot_questions_response.llm.json",
            model=args.llm_model,
        )
        proof_llm = run_llm_postprocess(
            repo_root=root,
            prompt_file=root / "prompts" / "deck_proofing" / "proofing_prompt.txt",
            input_json=proof_det,
            output_json=analysis_dir / "proofing_issues.llm.json",
            model=args.llm_model,
        )
        variance_llm = run_llm_postprocess(
            repo_root=root,
            prompt_file=root / "prompts" / "variance_watch" / "variance_prompt.txt",
            input_json=variance_det,
            output_json=analysis_dir / "variance_watch_issues.llm.json",
            model=args.llm_model,
        )
        hot["llm_postprocess"] = {
            "enabled": True,
            "returncode": hot_llm.get("returncode"),
            "response_text": hot_llm.get("response_text", ""),
        }
        proofing["llm_postprocess"] = {
            "enabled": True,
            "returncode": proof_llm.get("returncode"),
            "response_text": proof_llm.get("response_text", ""),
        }
        variance["llm_postprocess"] = {
            "enabled": True,
            "returncode": variance_llm.get("returncode"),
            "response_text": variance_llm.get("response_text", ""),
        }

    persist_analysis(hot, hot_out)
    persist_analysis(proofing, proof_out)
    persist_analysis(variance, variance_out)

    archive_payload = archive_raw_files(
        raw_dir=raw_dir,
        root=root,
        period=manifest["period"],
        pack_type=manifest["pack_type"],
        manifest_files=manifest["files"],
    )
    archive_manifest_path = root / archive_payload["archive_dir"] / "archive_manifest.json"
    write_json(archive_manifest_path, archive_payload)

    print(f"Normalized pack complete: {normalized_dir}")
    print(f"Analysis outputs ready: {analysis_dir}")
    print(f"Raw files archived: {archive_manifest_path}")
    print(
        f"Hot score: {hot.get('score_total')} ({hot.get('score_band')}) | "
        f"Proofing issues: {proofing['issue_count']} | Variance issues: {variance['issue_count']}"
    )
    if hot.get("clarifying_question"):
        print(f"Clarifying question: {hot['clarifying_question']}")
    print(
        "Next step: ask Blake with "
        "'$th-blake-mode prepare me for hot questions on this pack' "
        "to review likely executive challenges and prepared answers."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
