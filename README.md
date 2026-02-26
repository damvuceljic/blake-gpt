# Blake Finance Copilot

Skills-first repository for monthly TH C&US finance pack intake, extraction, and executive analysis.

## Quick Start
1. Install dependencies:
   - `python -m pip install -r requirements.txt`
2. Place files in:
   - `data/intake/<period>/<pack_type>/raw/`
3. Run end-to-end:
   - `python scripts/intake/process_month.py --raw-dir data/intake/<period>/<pack_type>/raw`
4. Run chat-first mode:
   - `python scripts/chat/blake_mode.py --message "run hot questions for latest pack"`

## Core Outputs
- Manifest: `data/packs/<period>/<pack_type>/pack_manifest.json`
- Normalized extracts: `data/normalized/<period>/<pack_type>/...`
- Analysis results: `data/analysis/<period>/<pack_type>/...`

## LLM Post-Processing (Codex CLI Only)
1. Login once:
   - `codex login`
2. Keep provider lock:
   - `.env` with `BLAKE_LLM_PROVIDER_LOCK=codex_chatgpt`
3. Enable optional post-processing:
   - `--use-llm-postprocess` on analysis scripts or Blake Mode
