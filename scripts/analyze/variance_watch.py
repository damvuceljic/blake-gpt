from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.analysis import persist_analysis, run_variance_watch
from finance_copilot.common import repo_root
from finance_copilot.llm_postprocess import run_llm_postprocess


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run variance watch checks on normalized workbook artifacts.")
    parser.add_argument("--pack-dir", required=True, help="Normalized pack directory")
    parser.add_argument(
        "--output",
        help="Output JSON path; defaults to data/analysis/<period>/<pack_type>/variance_watch_issues.json",
    )
    parser.add_argument(
        "--use-llm-postprocess",
        action="store_true",
        help="Run optional LLM post-processing via codex exec using ChatGPT login.",
    )
    parser.add_argument("--llm-model", help="Optional model override for codex exec post-processing")
    return parser.parse_args()


def _infer_period_pack(pack_dir: Path) -> tuple[str, str]:
    parts = pack_dir.parts
    if len(parts) < 2:
        return ("unknown-period", "unknown-pack")
    return parts[-2], parts[-1]


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    pack_dir = Path(args.pack_dir)
    if not pack_dir.is_absolute():
        pack_dir = (root / pack_dir).resolve()

    payload = run_variance_watch(pack_dir=pack_dir)
    period, pack_type = _infer_period_pack(pack_dir)
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (root / output_path).resolve()
    else:
        output_path = root / "data" / "analysis" / period / pack_type / "variance_watch_issues.json"

    if args.use_llm_postprocess:
        deterministic_path = output_path.with_name(f"{output_path.stem}.deterministic.json")
        llm_output_path = output_path.with_name(f"{output_path.stem}.llm.json")
        persist_analysis(payload, deterministic_path)
        llm_payload = run_llm_postprocess(
            repo_root=root,
            prompt_file=root / "prompts" / "variance_watch" / "variance_prompt.txt",
            input_json=deterministic_path,
            output_json=llm_output_path,
            model=args.llm_model,
        )
        payload["llm_postprocess"] = {
            "enabled": True,
            "result_path": str(llm_output_path.relative_to(root).as_posix()),
            "returncode": llm_payload.get("returncode"),
            "response_text": llm_payload.get("response_text", ""),
        }

    persist_analysis(payload, output_path)
    print(f"Variance watch output written: {output_path}")
    print(f"Issues found: {payload['issue_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

