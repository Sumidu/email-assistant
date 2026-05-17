## Build Pipeline

The existing `build()` method runs two passes sequentially. Pass 1 is unchanged.

```
Pass 1 (existing)
  new emails → writing style update → _writing_style.md
             → per-contact profile  → People/*.md

Pass 2 (new)
  new emails (per email) → entity extraction LLM → JSON
  JSON aggregated across new emails
  existing entity slugs fetched
  LLM canonicalizes → matches or creates entity files
  per-entity file: LLM rewrites ai-managed block
  calendar events queried → meetings fuzzy-linked
  entity_extraction_log updated
```

## DB: entity_extraction_log

New table, independent of `kb_processed`:

```sql
CREATE TABLE entity_extraction_log (
    email_id    INTEGER PRIMARY KEY REFERENCES emails(id),
    extracted_at TEXT NOT NULL
);
```

`get_unextracted_emails()` returns emails not yet in this table.
`mark_entity_extracted(ids)` inserts rows with current timestamp.

## Entity Extraction — Per-Email LLM Call

One LLM call per email. Returns structured JSON:

```json
{
  "projects": [
    {"name": "Project Alpha", "role": "lead", "context": "brief description"}
  ],
  "commitments": [
    {
      "what": "deliver quarterly report",
      "direction": "outgoing",
      "person": "Jane Doe",
      "person_email": "jane@example.com",
      "deadline": "2026-06-30",
      "certainty": "confirmed",
      "project": "Project Alpha"
    }
  ],
  "meetings": [
    {
      "topic": "project kickoff",
      "date": "2026-05-10",
      "participants": ["Jane Doe", "Bob Smith"],
      "notes": "brief context"
    }
  ]
}
```

Empty arrays are fine — not every email yields entities.

## LLM Canonicalization Pass

Before writing entity files, the LLM receives:
- All extracted entity names/what-fields from this batch
- All existing slugs and display names from entity files on disk

It maps extracted names → existing slugs (or declares them new). This is a single cheap LLM call that collapses "Alpha deliverables" → "Project Alpha" and "send Jane the report" → `deliver-report-jane-2026-06`.

## Entity File Format

### Commitment example

```markdown
---
type: commitment
slug: deliver-report-jane-2026-06
direction: outgoing
people: ["[[Jane Doe]]"]
project: "[[Project Alpha]]"
deadline: 2026-06-30
certainty: confirmed
status: pending
last_ai_update: 2026-05-18
---

<!-- ai-managed -->
## Summary
You committed to delivering the quarterly report to Jane Doe by end
of June 2026. First mentioned May 10, confirmed in follow-up May 15.

## Observations
- 2026-05-15: Jane's follow-up suggests deadline is firm
- 2026-05-10: Initial promise in reply to her request
<!-- /ai-managed -->

## Notes
```

### Project example

```markdown
---
type: project
name: Project Alpha
people: ["[[Jane Doe]]", "[[Bob Smith]]"]
status: active
last_ai_update: 2026-05-18
---

<!-- ai-managed -->
## Summary
Internal project involving Jane Doe and Bob Smith. Delivery due June 2026.
Budget approval from Bob still pending as of May 18.

## Observations
- 2026-05-18: Jane confirmed deadline moved to June [[Jane Doe]]
- 2026-05-12: Bob mentioned budget approval needed [[Bob Smith]]
<!-- /ai-managed -->

## Links
[[Jane Doe]] · [[Bob Smith]] · [[deliver-report-jane-2026-06]]

## Notes
```

### Meeting file naming

- Preferred: `YYYY-MM-DD Topic.md` (e.g. `2026-05-10 Project Alpha Kickoff.md`)
- Fallback (topic unknown): `YYYY-MM-DD Meeting with Jane Doe.md`
- If date unknown: `Meeting - Topic - participants.md`

## ai-managed Block Contract

- The block is delimited by `<!-- ai-managed -->` and `<!-- /ai-managed -->`.
- On every build, the LLM reads the existing block + new email evidence, then rewrites the block entirely (always-rewrite strategy).
- The LLM is explicitly instructed never to modify content outside the block.
- The parser extracts: frontmatter, ai-managed block, remainder (user content). Only frontmatter and the ai-managed block are sent to the LLM. The remainder is spliced back verbatim after the LLM responds.

## Calendar Meeting Linkage

When a meeting entity is extracted from email:
1. Parse the meeting date from the extraction JSON.
2. Query `calendar_events` table for events within ±1 day of that date.
3. For each candidate: compute simple word-overlap score between meeting topic and event subject.
4. If score exceeds threshold (≥2 shared non-stopword tokens): add `calendar_event: "[[Event Subject]]"` to frontmatter and a wikilink in the Links section.
5. If no match: meeting file is created without a calendar link (still useful).

## Folder Structure

```
Knowledge/
├── People/          existing, unchanged
├── Projects/        new — one file per project
├── Commitments/     new — one file per commitment
├── Meetings/        new — one file per meeting
└── Other/           existing, _writing_style.md etc.
```

The existing `_knowledge_category()` and `_knowledge_path()` methods are extended to handle the three new categories.

## Obsidian Link Enrichment

The existing `enrich_obsidian_links()` pass already wires `[[Name]]` links between People files. It is extended to also resolve links in Projects/, Commitments/, and Meetings/ files, so the Obsidian graph shows the full network.
