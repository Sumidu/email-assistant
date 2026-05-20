## 1. llm_client.py

- [x] 1.1 Create `app/llm_client.py` with internal `_http_call(lm, system, user, max_tokens, temperature)` → raw string, with 3-attempt retry (ConnectionError, Timeout, 429, 503)
- [x] 1.2 Add `_strip_think_tags(text)` — strips `<think>`, `<thinking>`, `<reasoning>`, `<analysis>` blocks
- [x] 1.3 Move `json_candidates()` from `app/services/todos.py` into `llm_client.py` as `_extract_json(text)` → `dict | list | None`
- [x] 1.4 Add public `call(system, user, config, *, max_tokens, temperature, tag)` → stripped plain text
- [x] 1.5 Add public `call_json(system, user, config, *, max_tokens, tag)` → parsed object or None
- [x] 1.6 Add public `call_markdown(system, user, config, *, max_tokens, tag)` → think-stripped, fence-stripped markdown
- [x] 1.7 Update `app/services/todos.py` to import `_extract_json` from `llm_client` instead of defining `json_candidates` locally

## 2. Prompts as Markdown Files

- [x] 2.1 Create `app/prompts/` directory with one `.md` file per prompt key (12 files: response_system, knowledge_style_system, knowledge_style_user, knowledge_contact_system, knowledge_contact_user, todo_extraction_system, mail_summary_system, entity_extraction_system, entity_extraction_user, entity_canonicalize_system, entity_canonicalize_user, entity_ai_block_system, entity_ai_block_user)
- [x] 2.2 Replace `prompt_defaults.py` body with `load_prompts() -> dict` (reads `app/prompts/*.md`) and `render_prompt(template, values) -> str`; delete `DEFAULT_PROMPTS`, `LEGACY_DEFAULT_PROMPTS`, `ensure_prompts()`, `with_untrusted_context_rules()`
- [x] 2.3 Add startup assertion in `load_prompts()` that all expected keys are present; raise `RuntimeError` with the missing key name if not

## 3. Migrate Call Sites

- [x] 3.1 Replace `knowledge_builder._call_llm()` with a thin wrapper that calls `llm_client.call()` or `call_markdown()` and captures provider metadata into `self._last_llm`
- [x] 3.2 Replace `modules/knowledge/entities.py _call_llm()` with direct `llm_client.call_json()` and `llm_client.call()` calls
- [x] 3.3 Replace `app/routes/mail_summary.py` raw `requests.post` with `llm_client.call_json()`
- [x] 3.4 Replace `modules/response_generator.py` raw `requests.post` with `llm_client.call()`

## 4. Cleanup

- [x] 4.1 Remove the prompts section from the advanced-settings UI (or hide it); it is no longer configurable
- [x] 4.2 Verify `config["prompts"]` is silently ignored on load (no migration needed, but confirm no code writes it back)
- [ ] 4.3 Run the app, trigger a KB build and a todo extraction — confirm no `<think>` tags appear in output files
