from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

WINDOWS_ABS_RE = re.compile(r"\b[A-Za-z]:\\")
UNIX_ABS_RE = re.compile(r"\b/(Users|home|opt|var|tmp)/")

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".csv",
}

SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".venv"}
SKIP_PREFIXES = {
    "data/intake",
    "data/packs",
    "data/normalized",
    "data/analysis",
}


def should_scan(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except Exception:
        rel = path.as_posix()
    if any(rel.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail when absolute machine-local paths are committed.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repo root to scan")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    violations: list[tuple[Path, int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_no, line in enumerate(handle, start=1):
                if WINDOWS_ABS_RE.search(line) or UNIX_ABS_RE.search(line):
                    violations.append((path, line_no, line.strip()))

    if violations:
        print("Absolute path violations detected:")
        for path, line_no, line in violations:
            rel = path.relative_to(root).as_posix()
            print(f" - {rel}:{line_no}: {line}")
        return 2

    print("No portability violations detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
