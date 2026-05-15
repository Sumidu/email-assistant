# Knowledge Base

Knowledge files are Markdown documents with YAML-like frontmatter. The app keeps
people knowledge separate from other knowledge and stores generated files in the
iCloud Drive knowledge folder when available.

## Metadata Sources

- File frontmatter is the portable metadata surface.
- `_metadata.json` is an internal sidecar index.
- Contact profiles use email aliases and match patterns to attach context.
- Pinned files are included broadly in generation prompts.

## Refactor Guidance

`modules.knowledge_builder` is currently broad: file layout, metadata,
frontmatter, linkification, LLM calls, and writeback live together. Future
refactors should first extract pure frontmatter and metadata helpers, then move
LLM and filesystem orchestration behind tested interfaces.

Related behavior requirements live in the knowledge base sections of
`openspec/specs/email-assistant/spec.md`.
