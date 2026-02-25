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

> No indexed sessions found. The session index populates automatically when Claude Code sessions end.
>
> To index sessions from before the plugin was installed, run: `/surface:index`
>
> To describe a specific session directly, use: `/surface:describe <session-id>`

### 2. Filter and sort

From the loaded index entries, filter to entries where `plan_mode` is `true`. Sort by `timestamp` descending. Take the top 4 entries.

If no plan-mode sessions exist, inform the user:

> No plan-mode sessions found in the index. The plugin extracts reasoning signals from sessions that use plan mode (where Claude deliberates on approach before implementing). Non-plan sessions are not yet supported.

### 3. Present options

Use AskUserQuestion to present the sessions. Format each option as:

```
[session_id] (timestamp) - summary
```

Include an "Other (enter session IDs manually)" option.

### 4. Handle selection

If the user selects a session, proceed to generate the PR description. Run the extraction and synthesis workflow:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_signals.py <selected_session_id> --project-dir $PWD --output-dir $PWD/.surface
```

Then read the resulting signals file and synthesize the PR description following the same process described in the `/surface:describe` skill: four sections (Overview, Approach, Tradeoffs, Review Focus), writing style rules, and the offer to create a PR.

If the user selects "Other", ask them to provide session IDs and then proceed with the describe workflow for those IDs.
