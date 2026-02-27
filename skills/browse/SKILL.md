---
name: surface:browse
description: This skill should be used when the user asks to "browse sessions", "surface browse", "find sessions", "list development sessions", or "show recent sessions". Displays an index of recent Claude Code sessions and lets the user select sessions for PR description generation.
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# Browse Development Sessions

You help the user find and select Claude Code development sessions for PR description generation.

## Steps

### 1. Read session index

Read the file `.surface/session-index.jsonl` in the current working directory.

If the file does not exist or is empty, inform the user:

> No indexed sessions found for this project. This is expected when Surface has just been installed. Would you like to backfill session data from your existing Claude Code history?

Then use AskUserQuestion with two options:

| Option | Label | Description |
|--------|-------|-------------|
| 1 | Yes, backfill now | Scans your Claude Code history and indexes past sessions for this project |
| 2 | No thanks | Skip backfill |

If the user accepts, run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_session.py --backfill --project-dir $PWD
```

Then re-read `.surface/session-index.jsonl` and continue to Step 2. If the backfill produced no sessions, inform the user:

> No sessions found for this project. To describe a specific session directly, use: `/surface:describe <session-id>`

If the user declines, inform them:

> To describe a specific session directly, use: `/surface:describe <session-id>`

### 2. Ask which sessions to display

Use AskUserQuestion to ask the user which sessions to display. Four options:

| Option | Label | Description |
|--------|-------|-------------|
| 1 | Plan mode with edits (Recommended) | Sessions where Claude deliberated on approach and made code changes — richest signals for PR descriptions |
| 2 | Sessions with edits | All sessions that made code changes |
| 3 | Plan mode sessions | Sessions that used plan mode |
| 4 | All sessions | No filtering |

### 3. Filter and sort

From the loaded index entries, apply the filter the user chose in Step 2:

- **Plan mode with edits**: `plan_mode == true` AND `made_edits == true`
- **Sessions with edits**: `made_edits == true`
- **Plan mode sessions**: `plan_mode == true`
- **All sessions**: no filtering

Sort by `timestamp` descending. Take the top 4 entries.

If no sessions match the selected filter, inform the user:

> No sessions match the selected filter. Try a broader filter or run `/surface:index` to backfill older sessions.

### 4. Present options

Use AskUserQuestion to present the sessions. Format each option as:

```
[session_id] (timestamp) - summary
```

Include an "Other (enter session IDs manually)" option.

### 5. Handle selection

If the user selects a session, proceed to generate the PR description. Run the extraction and synthesis workflow:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_signals.py <selected_session_id> --project-dir $PWD --output-dir $PWD/.surface
```

Then read the resulting signals file and synthesize the PR description following the same process described in the `/surface:describe` skill: four sections (Overview, Approach, Tradeoffs, Review Focus), writing style rules, and the offer to create a PR.

If the user selects "Other", ask them to provide session IDs and then proceed with the describe workflow for those IDs.
