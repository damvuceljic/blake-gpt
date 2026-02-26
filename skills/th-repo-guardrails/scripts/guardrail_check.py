from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    required = ["GUARDRAILS.md", "AGENTS.md", "todo.md", "AGENT_LESSONS.md"]
    missing = [name for name in required if not (repo_root / name).exists()]
    if missing:
        for item in missing:
            print(f"[missing] {item}")
        return 2

    command = ["python", "scripts/quality/check_portability.py", "--root", str(repo_root)]
    result = subprocess.run(command, cwd=repo_root, check=False)
    if result.returncode != 0:
        return result.returncode
    print("[ok] guardrail baseline checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

