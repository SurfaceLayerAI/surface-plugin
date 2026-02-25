# tests/

## What is here

Pytest tests for `scripts/` and `scripts/lib/`. Run with `pytest` from the repo root.

- `conftest.py` — Shared fixtures: `tmp_session_dir` (temp dir mimicking `~/.claude/projects/slug/`), `write_jsonl` (helper to write JSONL fixture files)
- `fixtures/` — JSONL transcript samples used by tests

## Constraints

- Tests import from `scripts/` via `sys.path.insert(0, ...)` at the top of each test file. Follow this pattern when adding new test files.
- Pytest is the only test dependency. No other test libraries.
