from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import ensure_dir, read_json, repo_root, utc_now_iso, write_json

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z&/\-]{2,}")
LOW_SIGNAL_RE = re.compile(r"^(?:[a-z]{1,3}\d+|[a-z]+_[a-z0-9_]+|r\d+c\d+)$")
FORMULA_MARKERS = ("=", "sum(", "index(", "xlookup(", "vlookup(", "if(", "offset(")
STOPWORDS = {
    "with",
    "from",
    "this",
    "that",
    "were",
    "have",
    "into",
    "while",
    "which",
    "their",
    "there",
    "about",
    "across",
    "month",
    "period",
    "close",
    "preview",
    "slide",
    "notes",
    "commentary",
}
DISCOURAGED_TERMS = [
    "quality",
    "core operating demand",
    "elasticity risk",
    "traffic/sales conversion",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the historical hot-questions language bank from normalized packs.")
    parser.add_argument("--normalized-root", default="data/normalized", help="Root folder for normalized packs.")
    parser.add_argument(
        "--output",
        default="data/context/historical/hotq_language_bank.json",
        help="Output language bank JSON path.",
    )
    parser.add_argument("--top-terms", type=int, default=120, help="Top preferred vocabulary terms per pack type.")
    return parser.parse_args()


def _iter_pack_dirs(normalized_root: Path) -> list[Path]:
    packs: list[Path] = []
    for period_dir in sorted(normalized_root.iterdir()) if normalized_root.exists() else []:
        if not period_dir.is_dir():
            continue
        for pack_dir in sorted(period_dir.iterdir()):
            if pack_dir.is_dir() and (pack_dir / "pack_summary.json").exists():
                packs.append(pack_dir)
    return packs


def _slide_text_candidates(slide: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    blocks = slide.get("text_blocks", [])
    if isinstance(blocks, list):
        narrative_blocks = [
            block
            for block in blocks
            if str(block.get("block_class", "")).strip().lower() in {"narrative", "bridge_summary"}
        ]
        for block in narrative_blocks:
            block_lines = [str(line).strip() for line in block.get("lines", []) if str(line).strip()]
            lines.extend(block_lines)
    if not lines:
        lines.extend(
            [
                str(slide.get("title", "")).strip(),
                *[str(item).strip() for item in slide.get("body", []) if str(item).strip()],
                str(slide.get("note_text", "")).strip(),
            ]
        )
    return [line for line in lines if line]


def _tokenize(lines: list[str]) -> list[str]:
    tokens: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(marker in lowered for marker in FORMULA_MARKERS):
            continue
        for token in TOKEN_RE.findall(lowered):
            if token in STOPWORDS:
                continue
            if LOW_SIGNAL_RE.fullmatch(token):
                continue
            tokens.append(token)
    return tokens


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    normalized_root = Path(args.normalized_root)
    if not normalized_root.is_absolute():
        normalized_root = (root / normalized_root).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (root / output_path).resolve()
    ensure_dir(output_path.parent)

    pack_dirs = _iter_pack_dirs(normalized_root)
    vocab_by_pack_type: dict[str, Counter[str]] = defaultdict(Counter)
    source_frequency_by_pack_type: dict[str, Counter[str]] = defaultdict(Counter)
    packs_scanned = 0

    for pack_dir in pack_dirs:
        packs_scanned += 1
        pack_type = pack_dir.name
        slide_paths = sorted(pack_dir.glob("decks/*/slides/slide_*.json"))
        for slide_path in slide_paths:
            try:
                slide = read_json(slide_path)
            except Exception:
                continue
            lines = _slide_text_candidates(slide)
            tokens = _tokenize(lines)
            if not tokens:
                continue
            vocab_by_pack_type[pack_type].update(tokens)
            for token in set(tokens):
                source_frequency_by_pack_type[pack_type][token] += 1

    preferred_vocabulary = {
        pack_type: [token for token, _ in counter.most_common(args.top_terms)]
        for pack_type, counter in vocab_by_pack_type.items()
    }
    source_frequencies = {
        pack_type: dict(counter.most_common(args.top_terms))
        for pack_type, counter in source_frequency_by_pack_type.items()
    }
    language_bank = {
        "generated_at": utc_now_iso(),
        "packs_scanned": packs_scanned,
        "preferred_vocabulary": preferred_vocabulary,
        "discouraged_terms": DISCOURAGED_TERMS,
        "source_frequencies_by_pack_type": source_frequencies,
    }
    write_json(output_path, language_bank)
    print(f"Language bank written: {output_path}")
    print(f"Packs scanned: {packs_scanned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

