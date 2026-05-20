## ADDED Requirements

### Requirement: Centralized LLM call interface
The system SHALL provide `app/llm_client.py` with three public functions — `call()`, `call_json()`, `call_markdown()` — as the single entry point for all LLM HTTP calls. No module outside `llm_client.py` SHALL call the LLM HTTP endpoint directly.

#### Scenario: Raw text call
- **WHEN** a caller invokes `call(system, user, config)`
- **THEN** the function returns the LLM response as a plain string with think tags stripped

#### Scenario: JSON call returns parsed object
- **WHEN** a caller invokes `call_json(system, user, config)`
- **THEN** the function returns a parsed `dict` or `list`, or `None` if parsing fails

#### Scenario: Markdown call strips fences
- **WHEN** a caller invokes `call_markdown(system, user, config)`
- **THEN** the function returns the response with think tags and markdown code fences removed

### Requirement: Think-tag stripping on all responses
The system SHALL strip `<think>`, `<thinking>`, `<reasoning>`, and `<analysis>` blocks (and their closing tags) from every LLM response before returning it to the caller.

#### Scenario: Think tags removed from markdown output
- **WHEN** the LLM response contains a `<think>...</think>` block
- **THEN** the block is removed and the remaining content is returned

#### Scenario: Think tags removed before JSON parsing
- **WHEN** the LLM response contains a `<think>` block followed by a JSON payload
- **THEN** `call_json()` strips the think block and successfully parses the JSON

### Requirement: Robust JSON extraction
The system SHALL extract JSON from LLM responses using a balanced-bracket candidate scanner that handles think tags, markdown code fences, and leading prose before the JSON payload.

#### Scenario: JSON inside code fence
- **WHEN** the LLM wraps its JSON response in a markdown code fence (` ```json ... ``` `)
- **THEN** `call_json()` returns the correctly parsed object

#### Scenario: JSON preceded by prose
- **WHEN** the LLM prefixes its JSON with an explanation sentence
- **THEN** `call_json()` scans past the prose and returns the correctly parsed object

#### Scenario: No valid JSON in response
- **WHEN** the LLM response contains no parseable JSON
- **THEN** `call_json()` returns `None` without raising

### Requirement: Retry on transient errors
The system SHALL retry LLM calls up to 3 attempts with exponential backoff (1s, 2s) on `ConnectionError`, `Timeout`, HTTP 429, and HTTP 503. All other errors SHALL propagate immediately.

#### Scenario: Retry on connection reset
- **WHEN** the first call raises `requests.ConnectionError`
- **THEN** the client retries and succeeds on the second attempt

#### Scenario: No retry on bad request
- **WHEN** the LLM returns HTTP 400
- **THEN** the error propagates immediately without retrying
