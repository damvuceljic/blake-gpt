# Blake Finance Copilot

Skills-first repository for monthly TH C&US finance pack intake, extraction, and executive analysis.

## Quick Start
1. Install dependencies:
   - `python -m pip install -r requirements.txt`
2. Install repo-local skills into Codex:
   - `powershell -ExecutionPolicy Bypass -File scripts/install-repo-codex-skills.ps1 -All -Force`
3. Place files in:
   - `data/intake/<period>/<pack_type>/raw/`
4. Run end-to-end:
   - `python scripts/intake/process_month.py --raw-dir data/intake/<period>/<pack_type>/raw --strict-core`
5. Run chat-first mode (recommended single entry):
   - `python scripts/chat/blake_mode.py --message "$th-blake-mode ingest this month's files" --raw-dir data/intake/<period>/<pack_type>/raw --period <period> --pack-type <pack_type> --strict-core`
6. Ask likely hot questions + prepared answers:
   - `python scripts/chat/blake_mode.py --message "$th-blake-mode prepare me for hot questions on this pack" --pack-dir data/normalized/<period>/<pack_type>`
6. Use guided launcher (Windows-first non-technical flow):
   - `python scripts/chat/blake_launcher.py`

## Blake Skill Prefix Rule
Blake chat requests must begin with a skill token:
1. `$th-intake-router`
2. `$th-hot-questions`
3. `$th-deck-proofing`
4. `$th-variance-watch`
5. `$th-blake-mode`

Recommended default for Blake:
1. Use `$th-blake-mode` for daily workflows.
2. Use other `$th-*` tokens only for advanced/explicit routing.

## File Type Policy
1. Accepted intake file types in `raw/`: `.pptx`, `.xlsx`, `.xlsm`, `.xls`
2. Unsupported files (for example `.pdf`) fail intake with an actionable error.
3. Persistent non-month artifacts (for example fiscal-year budget files) should be stored in:
   - `data/context/persistent/<year>-Budget/`

## Root File Migration
1. Move root-level Excel/PPT inputs to intake inbox and build routing plan:
   - `python scripts/intake/migrate_root_to_inbox.py`
2. Apply routing plan into deterministic monthly folders (`YYYY-PNN`):
   - `python scripts/intake/apply_routing_plan.py`
3. Process all staged packs and emit effectiveness report:
   - `python scripts/intake/process_staged_packs.py --use-llm-postprocess`

## Core Outputs
- Manifest: `data/packs/<period>/<pack_type>/pack_manifest.json`
- Normalized extracts: `data/normalized/<period>/<pack_type>/...`
- Analysis results: `data/analysis/<period>/<pack_type>/...`
- Intake effectiveness report: `data/analysis/intake_effectiveness_report.json`
- Archived raw files: `data/intake/processed/<period>/<pack_type>/<timestamp>/archive_manifest.json`

## LLM Post-Processing (Codex CLI Only)
1. Login once:
   - `codex login`
2. Keep provider lock:
   - `.env` with `BLAKE_LLM_PROVIDER_LOCK=codex_chatgpt`
3. Enable optional post-processing:
   - `--use-llm-postprocess` on analysis scripts or Blake Mode
4. Smoke test:
   - `python scripts/llm/run_codex_exec.py --prompt "Reply exactly: llm_ok" --output data/analysis/llm_smoke.json`
