from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from finance_copilot.common import repo_root, utc_now_iso, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-tokenize close pilot periods for narrative text-block extraction.")
    parser.add_argument("--periods", default="2025-P11,2025-P12,2026-P01")
    parser.add_argument("--pack-type", default="close", choices=["close", "preview"])
    parser.add_argument(
        "--output",
        default="data/analysis/retokenize_close_pilot_report.json",
        help="Summary report output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(REPO_ROOT)
    periods = [item.strip() for item in args.periods.split(",") if item.strip()]
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (root / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, str | int]] = []
    for period in periods:
        manifest = root / "data" / "packs" / period / args.pack_type / "pack_manifest.json"
        if not manifest.exists():
            runs.append(
                {
                    "period": period,
                    "pack_type": args.pack_type,
                    "status": "missing_manifest",
                    "manifest": str(manifest),
                    "returncode": 2,
                }
            )
            continue

        command = [sys.executable, "scripts/extract/tokenize_pack.py", "--manifest", str(manifest)]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        runs.append(
            {
                "period": period,
                "pack_type": args.pack_type,
                "status": "ok" if result.returncode == 0 else "failed",
                "manifest": str(manifest.relative_to(root).as_posix()),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )

    overall_ok = all(item.get("status") == "ok" for item in runs if item.get("status") != "missing_manifest")
    report = {
        "generated_at": utc_now_iso(),
        "periods": periods,
        "pack_type": args.pack_type,
        "overall_ok": overall_ok,
        "runs": runs,
    }
    write_json(output_path, report)
    print(f"Retokenize report written: {output_path}")
    print(f"Overall ok: {overall_ok}")
    return 0 if overall_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
