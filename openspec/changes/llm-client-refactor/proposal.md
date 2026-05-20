## Why

LLM responses from different models (especially local reasoning models) contain `<think>` and related tags that leak into generated KB files. JSON parsing is inconsistent across call sites, and think-tag stripping only exists in `knowledge_builder` — leaving `entities.py`, `mail_summary`, and `response_generator` unprotected. Additionally, prompt strings are hardcoded in a Python file, making them hard to read and edit.

## What Changes

- **New `app/llm_client.py`** — single module for all LLM HTTP calls; handles think-tag stripping, code fence removal, JSON extraction with candidate scanning, and retry on transient errors
- **New `app/prompts/` directory** — one `.md` file per prompt key, replacing hardcoded strings in `prompt_defaults.py`
- **Remove `_call_llm()` from `knowledge_builder.py`** and the duplicate in `entities.py` — both replaced by `llm_client` calls
- **Remove `LEGACY_DEFAULT_PROMPTS`, `ensure_prompts()`, and `config["prompts"]`** — prompts are no longer stored in user config
- **Update all call sites** — `knowledge_builder`, `entities`, `mail_summary`, `response_generator` all use `llm_client`

## Capabilities

### New Capabilities

- `llm-client`: Centralized LLM call module with consistent response cleaning, JSON parsing, and retry logic

### Modified Capabilities

- `knowledge-base`: Prompt loading changes from config-based to file-based; no user-facing behavior change

## Impact

- **Modified files**: `app/prompt_defaults.py`, `modules/knowledge_builder.py`, `modules/knowledge/entities.py`, `app/routes/mail_summary.py`, `modules/response_generator.py`
- **New files**: `app/llm_client.py`, `app/prompts/*.md` (~12 files)
- **Removed**: `LEGACY_DEFAULT_PROMPTS`, `ensure_prompts()`, `config["prompts"]` storage
- **No new dependencies** — uses existing `requests` library
- **No breaking changes** to user-facing features or config format (prompts section in existing configs is silently ignored)
