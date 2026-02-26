from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import ensure_dir, repo_root, write_json
from finance_copilot.intake import (
    build_pack_manifest,
    is_processed_intake_dir,
    validate_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route raw intake files into a validated pack manifest.")
    parser.add_argument("--raw-dir", required=True, help="Raw intake directory containing PPTX/XLSX files.")
    parser.add_argument("--period", help="Reporting period key (example: 2026-P02).")
    parser.add_argument("--pack-type", choices=["preview", "close"], help="Pack type (preview or close).")
    parser.add_argument("--region", help="Region label (example: TH C&US).")
    parser.add_argument(
        "--source-mode",
        choices=["offline_values", "lineage", "both"],
        default="both",
        help="Source lineage mode for this pack.",
    )
    parser.add_argument(
        "--strict-core",
        dest="strict_core",
        action="store_true",
        default=True,
        help="Enforce required core files (deck + formula/offline pair). Default: true.",
    )
    parser.add_argument(
        "--no-strict-core",
        dest="strict_core",
        action="store_false",
        help="Disable strict core requirements.",
    )
    parser.add_argument(
        "--allow-missing-core",
        action="store_true",
        help="Allow manifest creation even when strict core checks fail.",
    )
    parser.add_argument(
        "--pair-choice-file",
        help="JSON file mapping pair_key to selected offline file_name/file_slug.",
    )
    parser.add_argument(
        "--manifest-out",
        help="Output manifest path. Defaults to data/packs/<period>/<pack_type>/pack_manifest.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    raw_dir = (root / args.raw_dir).resolve() if not Path(args.raw_dir).is_absolute() else Path(args.raw_dir)

    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw intake directory does not exist: {raw_dir}")
    if is_processed_intake_dir(raw_dir, root):
        raise ValueError(
            f"Processed intake folders are read-protected for routing. Choose a raw folder under data/intake/*/*/raw. ({raw_dir})"
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
            raise ValueError("--pair-choice-file must be a JSON object: {\"pair_key\": \"offline_file_name\"}")
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

    if args.manifest_out:
        manifest_out = (root / args.manifest_out).resolve() if not Path(args.manifest_out).is_absolute() else Path(args.manifest_out)
    else:
        manifest_out = root / "data" / "packs" / manifest["period"] / manifest["pack_type"] / "pack_manifest.json"

    ensure_dir(manifest_out.parent)
    write_json(manifest_out, manifest)
    print(f"Manifest written: {manifest_out}")
    print(f"Files routed: {len(manifest['files'])}")
    print(f"Period: {manifest['period']} | Pack: {manifest['pack_type']} | Region: {manifest['region']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
