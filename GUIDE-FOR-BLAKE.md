# Blake Finance Copilot Guide

## Executive Summary
Blake Finance Copilot ingests monthly finance decks/workbooks, extracts token-efficient evidence, and returns CFO-ready insights using three analysis modes:
1. `Hot Questions`: scorecard + risks/opportunities/actions.
2. `Deck Proofing`: commentary/number consistency and hygiene checks.
3. `Variance Watch`: bridge integrity and driver-quality checks.

The pipeline is deterministic first (local extraction and rules), with optional Codex CLI LLM post-processing for concise executive language.

## Non-Technical Monthly Workflow
1. Put files in `data/intake/<YYYY-PNN>/<preview|close>/raw/`.
2. Run guided launcher:
   - `python scripts/chat/blake_launcher.py`
3. Choose `Ingest month`.
4. Confirm period and pack type.
5. If prompted about multiple offline workbook variants, pick the primary offline file for that workbook pair.
6. After completion, review outputs in:
   - `data/analysis/<period>/<pack_type>/`
7. Ask follow-up questions with menu option `Ask hot question`.

## Intake Requirements
Strict core validation is enabled by default.

Required for `preview` packs:
1. `preview_deck` (`.pptx`)
2. `preview_formula_workbook` (template workbook with formulas)
3. `preview_offline_workbook` (matching offline values workbook)

Required for `close` packs:
1. `close_deck` (`.pptx`)
2. `close_formula_workbook` (template workbook with formulas)
3. `close_offline_workbook` (matching offline values workbook)

All additional Excel files are ingested as `supporting_excel` for drill-down context.

## Paired Formula/Offline Handling
1. Workbook pairs are matched by `pair_key` (filename stem with `_offline*` removed).
2. If one formula workbook maps to multiple offline variants, intake stops and requires explicit selection.
3. Save selections as JSON and pass via:
   - `--pair-choice-file <json>`
4. The guided launcher can generate this file interactively.

## Asking New Questions
1. Guided launcher option: `Ask hot question`.
2. CLI option:
   - `python scripts/chat/blake_mode.py --message "What are the top risks this month?"`
3. Explicit pack targeting:
   - `python scripts/analyze/hot_questions.py --pack-dir data/normalized/<period>/<pack_type> --question "<your question>"`

## LLM Post-Processing Setup (Codex CLI)
1. Install dependencies:
   - `python -m pip install -r requirements.txt`
2. Install skills:
   - `powershell -ExecutionPolicy Bypass -File scripts/install-repo-codex-skills.ps1 -All -Force`
3. Login:
   - `codex login`
4. Verify `.env` contains:
   - `BLAKE_LLM_PROVIDER_LOCK=codex_chatgpt`
5. Smoke test:
   - `python scripts/llm/run_codex_exec.py --prompt "Reply exactly: llm_ok" --output data/analysis/llm_smoke.json`
6. If login/preflight fails, deterministic outputs still run; LLM enrichment is skipped/fails safely with diagnostics in output JSON.

## Historical Calibration (No Fine-Tuning)
1. Build historical calibration bundle:
   - `python scripts/analyze/build_historical_calibration.py`
2. Artifacts are written to:
   - `data/context/historical/score_baselines.json`
   - `data/context/historical/recurring_lexicon.json`
   - `data/context/historical/retrieval_index.json`
   - `data/context/historical/calibration_bundle.json`
3. Use in hot questions:
   - `python scripts/analyze/hot_questions.py --pack-dir ... --use-historical-context`

## Testing And Troubleshooting
1. Guardrails:
   - `python skills/th-repo-guardrails/scripts/guardrail_check.py`
2. Unit/regression tests:
   - `pytest -q`
3. Intake routing validation:
   - `python scripts/intake/route_intake.py --raw-dir data/intake/<period>/<pack_type>/raw --strict-core`
4. Staged effectiveness report:
   - `python scripts/intake/process_staged_packs.py --use-llm-postprocess`

Operational notes:
1. `data/intake/processed/**` is archive-only and must not be used as raw input.
2. Successful monthly processing moves raw files to:
   - `data/intake/processed/<period>/<pack_type>/<timestamp>/`
