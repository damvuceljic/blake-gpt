from __future__ import annotations

import argparse
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
from finance_copilot.intake import build_pack_manifest, validate_manifest
from finance_copilot.llm_postprocess import run_llm_postprocess
from finance_copilot.workbook import extract_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run monthly end-to-end intake, extraction, and baseline analyses.")
    parser.add_argument("--raw-dir", required=True, help="Raw intake directory with source files.")
    parser.add_argument("--period", help="Reporting period (example: 2026-P02)")
    parser.add_argument("--pack-type", help="Pack type preview|close")
    parser.add_argument("--region", help="Region label")
    parser.add_argument("--source-mode", default="both", choices=["offline_values", "lineage", "both"])
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
    parser.add_argument("--llm-model", help="Optional model override for codex exec post-processing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    raw_dir = Path(args.raw_dir)
    if not raw_dir.is_absolute():
        raw_dir = (root / raw_dir).resolve()

    manifest = build_pack_manifest(
        raw_dir=raw_dir,
        root=root,
        period=args.period,
        pack_type=args.pack_type,
        region=args.region,
        source_mode=args.source_mode,
    )
    errors = validate_manifest(manifest)
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

    hot = run_hot_questions(
        normalized_dir,
        question=args.question,
        scoring_config=scoring_config,
        month_override=month_override,
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

    print(f"Normalized pack complete: {normalized_dir}")
    print(f"Analysis outputs ready: {analysis_dir}")
    print(
        f"Hot score: {hot.get('score_total')} ({hot.get('score_band')}) | "
        f"Proofing issues: {proofing['issue_count']} | Variance issues: {variance['issue_count']}"
    )
    if hot.get("clarifying_question"):
        print(f"Clarifying question: {hot['clarifying_question']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
