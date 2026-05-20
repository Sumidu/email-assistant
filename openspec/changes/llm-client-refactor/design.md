## Context

The app makes LLM calls from four modules (`knowledge_builder`, `entities`, `mail_summary`, `response_generator`), each with its own copy of the `requests.post` pattern. Think-tag stripping (`<think>`, `<thinking>`, `<reasoning>`, `<analysis>`) is only implemented in `knowledge_builder._strip_reasoning_output()`. JSON parsing quality varies: `todos.py` has a robust candidate scanner, `entities.py` has fragile single-pass parsing, `mail_summary` has partial regex repair. The result is visible `<think>` tags in KB files and silent entity extraction failures when models return JSON wrapped in markdown fences or prefixed with reasoning.

Prompts live as Python strings in `app/prompt_defaults.py` alongside migration machinery (`LEGACY_DEFAULT_PROMPTS`, `ensure_prompts()`) that existed to handle prompts stored in user config. This makes prompts hard to read and edit.

## Goals / Non-Goals

**Goals:**
- One place for all LLM HTTP calls, think-tag stripping, and response cleaning
- Consistent JSON extraction across all call sites (robust candidate scanner everywhere)
- Retry on transient errors (connection reset, timeout, HTTP 429/503)
- Prompts as readable `.md` files in the source tree
- Remove dead migration machinery from `prompt_defaults.py`

**Non-Goals:**
- Streaming responses
- Token counting or context window management
- User-editable prompts
- Switching HTTP library (stays on `requests`)

## Decisions

### D1: `call()` / `call_json()` / `call_markdown()` — three variants, not one

Callers have three distinct response shapes: raw text (response generator), cleaned markdown (KB contact profiles), and JSON (entities, todos, mail summary). Separate functions make the intent explicit and let each variant apply the right post-processing without callers caring about it.

```python
# app/llm_client.py public interface
def call(system, user, config, *, max_tokens=2000, temperature=0.3, tag="knowledge") -> str:
    """Raw text with think tags stripped."""

def call_json(system, user, config, *, max_tokens=1000, tag="knowledge") -> dict | list | None:
    """Parsed JSON or None on failure. Never raises."""

def call_markdown(system, user, config, *, max_tokens=2000, tag="knowledge") -> str:
    """Think tags + code fences stripped."""
```

Alternative considered: a single `call(mode=...)` — rejected because keyword-only mode arg is less discoverable and adds a branch at the call site.

### D2: Retry with exponential backoff, 3 attempts

Transient conditions to retry: `requests.ConnectionError`, `requests.Timeout`, HTTP 429, HTTP 503. Other HTTP errors (400, 401, 404, 500) are not retried — they indicate a configuration problem. Delays: 1s, 2s (doubling). This is enough for local LM Studio which occasionally drops connections under load.

Alternative considered: a retry library (`tenacity`) — rejected to avoid a new dependency.

### D3: JSON extraction uses candidate scanner from `todos.py`

The `json_candidates()` function in `todos.py` scans for balanced `{...}` and `[...]` blocks, tries each in longest-first order. This already handles think tags, code fences, and prefixed prose. It will be moved to `llm_client.py` as `_extract_json()` and reused everywhere. `todos.py` will import it from there.

Alternative considered: regex-based fence stripping then `json.loads` — fragile, already proven to fail.

### D4: Prompts as `app/prompts/<key>.md` files, loaded once at import

Each prompt key becomes a file: `app/prompts/entity_extraction_system.md`. `prompt_defaults.py` is reduced to two functions: `load_prompts()` (reads directory, returns dict) and `render_prompt(key_or_template, values)`. No config storage, no migration.

The `prompts` key in existing user configs is silently ignored on load — no migration needed since the app never wrote prompts back to config files without explicit user action in the advanced settings UI.

Alternative considered: keep strings in Python — harder to read multiline prompts with proper formatting, and no syntax highlighting.

### D5: `knowledge_builder._call_llm()` and `entities._call_llm()` deleted

Both are replaced by direct `llm_client` calls. `knowledge_builder` passes the LLM metadata tracking through a thin wrapper that records `_last_llm` for `_current_llm_metadata()`.

## Risks / Trade-offs

- **Prompt file missing at runtime** → `load_prompts()` raises on import if a file is absent. Risk: developer forgets to add a file. Mitigation: assert all expected keys are present at startup; test catches it.
- **`_last_llm` tracking in `knowledge_builder`** → Currently `_call_llm` sets `self._last_llm` as a side effect. After refactor, a thin wrapper in `KnowledgeBuilder` calls `llm_client.call()` and captures provider metadata separately. Slightly more explicit, not a regression.
- **`config["prompts"]` silently ignored** → Users who had customized prompts via the advanced settings UI will lose those customizations. This is intentional (prompts become developer-only), but warrants a note in the commit message.

## Migration Plan

1. Create `app/llm_client.py` and `app/prompts/*.md`
2. Update `prompt_defaults.py` (strip to `load_prompts` + `render_prompt`)
3. Update `knowledge_builder` — replace `_call_llm` with wrapper around `llm_client`
4. Update `entities.py`, `mail_summary`, `response_generator`
5. Move `json_candidates` from `todos.py` → `llm_client._extract_json`; update `todos.py` import
6. Remove advanced-settings prompt UI (or leave it — it will just show nothing editable)

No database migrations. No config migrations. Rollback: revert the commit.
