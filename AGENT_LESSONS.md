# Agent Lessons

## 2026-02-26
1. Skill scaffolding may fail if `short_description` exceeds allowed UI length; keep it compact.
2. Deck extraction must explicitly filter repeated footer/page-number text to stay token-efficient.
3. Preserve both value and lineage signals in workbook extraction to maintain root-cause confidence.
4. Pytest in this repo needs explicit repo-root path injection (`tests/conftest.py`) for local package imports.
5. `codex login status` output may appear in stderr, so provider preflight must inspect stdout and stderr.
6. Portability lint should ignore generated artifact folders (`data/intake|packs|normalized|analysis`) to avoid false positives from runtime metadata.
