from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import ensure_dir, read_json, repo_root, utc_now_iso, write_json

TOKEN_RE = re.compile(r"[A-Za-z]{4,}")
STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "were",
    "have",
    "will",
    "into",
    "before",
    "after",
    "where",
    "when",
    "which",
    "while",
    "should",
    "would",
    "could",
    "month",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build historical calibration artifacts from normalized + analysis outputs."
    )
    parser.add_argument(
        "--analysis-root",
        default="data/analysis",
        help="Base folder containing <period>/<pack_type>/analysis outputs.",
    )
    parser.add_argument(
        "--normalized-root",
        default="data/normalized",
        help="Base folder containing normalized pack artifacts.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/context/historical",
        help="Output directory for calibration artifacts.",
    )
    parser.add_argument("--top-terms", type=int, default=40, help="Number of lexicon terms per pack type.")
    return parser.parse_args()


def _discover_analysis_dirs(analysis_root: Path) -> list[Path]:
    candidates: list[Path] = []
    if not analysis_root.exists():
        return candidates
    for period_dir in sorted(analysis_root.iterdir()):
        if not period_dir.is_dir():
            continue
        for pack_dir in sorted(period_dir.iterdir()):
            if pack_dir.is_dir() and (pack_dir / "hot_questions_response.json").exists():
                candidates.append(pack_dir)
    return candidates


def _safe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _tokenize_lines(lines: list[str]) -> list[str]:
    tokens: list[str] = []
    for line in lines:
        for token in TOKEN_RE.findall(line.lower()):
            if token in STOPWORDS:
                continue
            tokens.append(token)
    return tokens


def _mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _calibrated_deltas(
    *,
    per_pack_dimension_means: dict[str, dict[str, float]],
    global_dimension_means: dict[str, float],
) -> dict[str, dict[str, float]]:
    payload: dict[str, dict[str, float]] = {}
    for pack_type, means in per_pack_dimension_means.items():
        payload[pack_type] = {}
        for dimension, mean_value in means.items():
            global_mean = global_dimension_means.get(dimension, mean_value)
            payload[pack_type][dimension] = round((global_mean - mean_value) * 0.10, 2)
    return payload


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    analysis_root = Path(args.analysis_root)
    if not analysis_root.is_absolute():
        analysis_root = (root / analysis_root).resolve()
    normalized_root = Path(args.normalized_root)
    if not normalized_root.is_absolute():
        normalized_root = (root / normalized_root).resolve()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (root / out_dir).resolve()
    ensure_dir(out_dir)

    analysis_dirs = _discover_analysis_dirs(analysis_root)
    if not analysis_dirs:
        print("No historical analysis outputs found.")
        return 0

    score_values: dict[str, list[float]] = defaultdict(list)
    dimension_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    lexicon_counter: dict[str, Counter[str]] = defaultdict(Counter)
    trailing: dict[str, list[str]] = defaultdict(list)
    retrieval_index: list[dict[str, Any]] = []

    for pack_analysis_dir in analysis_dirs:
        period = pack_analysis_dir.parent.name
        pack_type = pack_analysis_dir.name
        hot_path = pack_analysis_dir / "hot_questions_response.json"
        if not hot_path.exists():
            continue
        hot = read_json(hot_path)
        score = _safe_float(hot.get("score_total"))
        if score is not None:
            score_values[pack_type].append(score)
            trailing[pack_type].append(f"{period}:{score:.1f}")

        for dim in hot.get("dimension_scores", []):
            name = str(dim.get("dimension", "")).strip()
            value = _safe_float(dim.get("score"))
            if name and value is not None:
                dimension_values[pack_type][name].append(value)

        text_lines = []
        text_lines.extend([str(item) for item in hot.get("risks", [])])
        text_lines.extend([str(item) for item in hot.get("opportunities", [])])
        text_lines.extend([str(item) for item in hot.get("actions", [])])
        text_lines.extend([str(item) for item in hot.get("summary_bullets", [])])
        lexicon_counter[pack_type].update(_tokenize_lines(text_lines))

        normalized_pack_dir = normalized_root / period / pack_type
        if normalized_pack_dir.exists():
            retrieval_index.append(
                {
                    "period": period,
                    "pack_type": pack_type,
                    "pack_dir": str(normalized_pack_dir.relative_to(root).as_posix()),
                    "chunks_path": str((normalized_pack_dir / "chunks" / "chunks.jsonl").relative_to(root).as_posix())
                    if (normalized_pack_dir / "chunks" / "chunks.jsonl").exists()
                    else "",
                    "pack_summary_path": str((normalized_pack_dir / "pack_summary.json").relative_to(root).as_posix())
                    if (normalized_pack_dir / "pack_summary.json").exists()
                    else "",
                }
            )

    per_pack_dimension_means: dict[str, dict[str, float]] = {}
    global_dimension_values: dict[str, list[float]] = defaultdict(list)
    for pack_type, dims in dimension_values.items():
        per_pack_dimension_means[pack_type] = {}
        for dimension, values in dims.items():
            mean_val = round(_mean(values), 2)
            per_pack_dimension_means[pack_type][dimension] = mean_val
            global_dimension_values[dimension].extend(values)

    global_dimension_means = {
        dimension: round(_mean(values), 2) for dimension, values in global_dimension_values.items()
    }

    score_baselines = {
        pack_type: {
            "samples": len(values),
            "mean_score_total": round(_mean(values), 2),
            "min_score_total": round(min(values), 2) if values else 0.0,
            "max_score_total": round(max(values), 2) if values else 0.0,
            "dimension_means": per_pack_dimension_means.get(pack_type, {}),
        }
        for pack_type, values in score_values.items()
    }
    calibrated_deltas = _calibrated_deltas(
        per_pack_dimension_means=per_pack_dimension_means,
        global_dimension_means=global_dimension_means,
    )
    recurring_lexicon = {
        pack_type: dict(counter.most_common(args.top_terms))
        for pack_type, counter in lexicon_counter.items()
    }
    trailing_period_context = {
        pack_type: sorted(values)[-6:] for pack_type, values in trailing.items()
    }

    bundle = {
        "generated_at": utc_now_iso(),
        "score_baselines": score_baselines,
        "global_dimension_means": global_dimension_means,
        "calibrated_deltas": calibrated_deltas,
        "recurring_lexicon": recurring_lexicon,
        "trailing_period_context": trailing_period_context,
        "retrieval_index": retrieval_index,
    }

    write_json(out_dir / "score_baselines.json", score_baselines)
    write_json(out_dir / "recurring_lexicon.json", recurring_lexicon)
    write_json(out_dir / "retrieval_index.json", retrieval_index)
    write_json(out_dir / "calibration_bundle.json", bundle)

    print(f"Historical calibration artifacts written to: {out_dir}")
    print(
        f"Pack types calibrated: {len(score_baselines)} | "
        f"retrieval entries: {len(retrieval_index)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
