## 1. Database

- [ ] 1.1 Add `entity_extraction_log` table to `modules/database.py` (schema: `email_id INTEGER PK, extracted_at TEXT`)
- [ ] 1.2 Add `get_unextracted_emails()` — returns emails not yet in entity_extraction_log
- [ ] 1.3 Add `mark_entity_extracted(ids: list[int])` — bulk insert into entity_extraction_log
- [ ] 1.4 Add `get_calendar_events_in_window(start_ts, end_ts)` helper for meeting linkage

## 2. ai-managed Block Parser

- [ ] 2.1 Create `modules/knowledge/entity_files.py` with `parse_entity_file(content)` → `{frontmatter, ai_block, user_content}`
- [ ] 2.2 Add `render_entity_file(frontmatter, ai_block, user_content)` → reassembled markdown
- [ ] 2.3 Add `read_entity_file(path)` and `write_entity_file(path, frontmatter, ai_block, user_content)` helpers
- [ ] 2.4 Add `collect_existing_slugs(entity_type)` → dict of `{slug: display_name}` from all files of that type

## 3. Folder Structure

- [ ] 3.1 Add `PROJECTS_DIR_NAME`, `COMMITMENTS_DIR_NAME`, `MEETINGS_DIR_NAME` constants to `knowledge_builder.py`
- [ ] 3.2 Create the three new subdirectories in `_ensure_knowledge_dirs()`
- [ ] 3.3 Extend `_knowledge_category()` and `_knowledge_path()` to handle the three new types

## 4. Prompts

- [ ] 4.1 Add `entity_extraction_system` and `entity_extraction_user` prompts to `app/prompt_defaults.py`
  - Input: single email (sender, recipients, date, subject, body snippet)
  - Output: JSON `{projects, commitments, meetings}` as specified in design.md
  - Instruct LLM to return empty arrays rather than guessing
- [ ] 4.2 Add `entity_canonicalize_system` and `entity_canonicalize_user` prompts
  - Input: extracted entity names + existing slugs/display names
  - Output: JSON mapping extracted names → existing slugs or `null` (new)
- [ ] 4.3 Add `entity_ai_block_system` and `entity_ai_block_user` prompts
  - Input: entity type, existing ai-managed block, new observations
  - Output: rewritten ai-managed block (Summary + Observations)
  - Explicit instruction: never output content outside the ai-managed block

## 5. Entity Extraction

- [ ] 5.1 Create `modules/knowledge/entities.py` with `extract_entities_from_email(email, llm_config)` → raw JSON dict
- [ ] 5.2 Add `canonicalize_entities(batch, existing_slugs, llm_config)` → maps extracted names to existing slugs or generates new ones
- [ ] 5.3 Add `aggregate_entity_batch(extractions)` → merges per-email JSONs into `{projects, commitments, meetings}` lists, deduplicating within the batch by slug

## 6. Entity File Writers

- [ ] 6.1 Add `write_project_file(name, observations, people_links, llm_config)` to `knowledge_builder.py`
  - Reads existing file if present, rewrites ai-managed block, preserves user content
- [ ] 6.2 Add `write_commitment_file(slug, data, observations, llm_config)`
  - Same pattern; uses slug for filename stability
- [ ] 6.3 Add `write_meeting_file(date, topic, participants, observations, calendar_link, llm_config)`
  - Filename: `YYYY-MM-DD Topic.md` or `YYYY-MM-DD Meeting with Person.md`

## 7. Calendar Meeting Linkage

- [ ] 7.1 Add `find_calendar_match(date_str, topic, account_id)` in `modules/knowledge/entities.py`
  - Queries `calendar_events` ±1 day from date
  - Word-overlap score between topic and event subject (≥2 non-stopword tokens)
  - Returns matching event subject string or None
- [ ] 7.2 Wire `find_calendar_match` into `write_meeting_file` to populate `calendar_event` frontmatter and Links section

## 8. Pass 2 Wiring

- [ ] 8.1 Add `build_entities(emails, progress_callback)` method to `KnowledgeBuilder`
  - Iterates unextracted emails, calls extractor, canonicalizes, writes entity files
  - Calls `mark_entity_extracted` on success
- [ ] 8.2 Call `build_entities()` at the end of `build()` after Pass 1 completes
- [ ] 8.3 Extend `enrich_obsidian_links()` to resolve wikilinks in Projects/, Commitments/, Meetings/
- [ ] 8.4 Add progress messages for entity extraction steps (e.g. "Extracting entities from 42 emails…")

## 9. Verification

- [ ] 9.1 Run KB build on real inbox — confirm Projects/ folder is populated with plausible project files
- [ ] 9.2 Confirm Commitments/ shows both outgoing and incoming commitments with correct direction
- [ ] 9.3 Edit `## Notes` in a generated file, rebuild — confirm notes are preserved
- [ ] 9.4 Confirm duplicate commitment names are canonicalized to a single file across two builds
- [ ] 9.5 Confirm a meeting file links to a calendar event when date and topic match
