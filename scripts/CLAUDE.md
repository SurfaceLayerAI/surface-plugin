# scripts/

## What is here

Python scripts for signal extraction and session indexing. All stdlib-only, no pip dependencies.

- `extract_signals.py` — CLI entry point for signal extraction. Reads a session transcript, discovers Plan subagents, extracts signals, writes to `.surface/<session_id>.signals.jsonl`.
- `index_session.py` — SessionEnd hook entry point. Extracts metadata from a transcript, generates a summary via `claude -p`, appends to `.surface/session-index.jsonl`.
- `lib/` — Shared modules:
  - `transcript_reader.py` — JSONL streaming parser, content block extraction, system entry detection
  - `session_discovery.py` — Session path resolution, Plan subagent discovery via progress entries
  - `signal_types.py` — Signal type constants and `make_signal` factory
  - `extractors.py` — `MainTranscriptExtractor` and `PlanSubagentExtractor` classes
  - `summarizer.py` — Builds prompt from `agents/indexer.md`, runs `claude -p`, falls back to structural summary
  - `index_builder.py` — Reads/writes `.surface/session-index.jsonl`

## Constraints

- Stdlib only. No pip install.
- Python 3.9+: no match statements, no `X | Y` union types.
- Scripts resolve imports via `sys.path.insert(0, ...)` using `CLAUDE_PLUGIN_ROOT` env var or `__file__` relative path.
