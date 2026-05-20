## MODIFIED Requirements

### Requirement: Prompts loaded from source files
The system SHALL load all LLM prompts from `.md` files in `app/prompts/` at startup. Prompts SHALL NOT be stored in or read from user config (`config["prompts"]`). The `prompt_defaults.py` module SHALL expose only `load_prompts() -> dict` and `render_prompt(template, values) -> str`.

#### Scenario: Prompt file loaded at startup
- **WHEN** the application starts
- **THEN** all prompt keys are loaded from `app/prompts/*.md` into memory

#### Scenario: Variable substitution works
- **WHEN** `render_prompt(template, {"sender": "Jane"})` is called
- **THEN** `{{sender}}` in the template is replaced with `"Jane"`

#### Scenario: Missing prompt file raises at startup
- **WHEN** a required `.md` file is absent from `app/prompts/`
- **THEN** the application raises an error at startup, not at call time

## REMOVED Requirements

### Requirement: User-editable prompts via advanced settings
**Reason**: Prompts are now developer-managed source files; user customisation added complexity without proportional value.
**Migration**: Users who customised prompts via the advanced settings UI should edit `app/prompts/*.md` in the source tree and rebuild.
