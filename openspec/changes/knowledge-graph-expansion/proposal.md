## Why

The current knowledge base is person-centric: it tracks how you write to contacts and what they're about. It cannot answer questions like "what did I promise Jane last month?", "what projects am I juggling?", or "who was at that kickoff meeting?". Email is a rich record of commitments, projects, and meetings — none of that is currently captured.

The goal is a networked second brain derived from email, Obsidian-compatible, that a human can annotate without fear of the next KB build overwriting their edits.

## What Changes

### New entity types extracted from email (Pass 2 of the build pipeline)

- **Projects** — inferred from email patterns and explicit mentions. One file per project, fuzzy names accepted (user merges duplicates in Obsidian).
- **Commitments** — extracted from both sent and received mail, including unconfirmed/implied ones. Tracks direction (outgoing = I owe it, incoming = they owe me). LLM canonicalizes against existing slugs to avoid duplicate files.
- **Meetings** — extracted from email context. Fuzzy-linked to calendar events by date (±1 day) and topic similarity when a calendar is configured.

### Round-trip safety (append + summarise)

Every entity file has an `<!-- ai-managed --> … <!-- /ai-managed -->` block. The LLM owns that block and rewrites it on each build. Everything outside — especially a `## Notes` section — is never touched. User edits in Obsidian are preserved across rebuilds.

### New folder structure

```
Knowledge/
├── People/           (existing)
├── Projects/         (new)
├── Commitments/      (new)
├── Meetings/         (new)
└── Other/            (existing)
```

### DB tracking

A new `entity_extraction_log` table tracks which emails have gone through Pass 2. This is independent of the existing `kb_processed` flag used by Pass 1.

## Capabilities

### New Capabilities

- `knowledge-graph-expansion`: Entity extraction pipeline, entity file management, calendar meeting linkage.

### Modified Capabilities

- `knowledge-base`: New folder structure, ai-managed block contract, Pass 2 wiring in `build()`.

## Impact

- **Modified files**: `modules/knowledge_builder.py`, `modules/database.py`, `app/prompt_defaults.py`
- **New files**: `modules/knowledge/entities.py`, `modules/knowledge/entity_files.py`
- **New DB table**: `entity_extraction_log`
- **New KB folders**: `Projects/`, `Commitments/`, `Meetings/`
- **No schema breaking changes** — existing People/ and Other/ files are unaffected
