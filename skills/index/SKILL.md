---
name: surface:index
description: This skill should be used when the user asks to "index sessions", "backfill sessions", "surface index", "index old sessions", or "import sessions". Indexes Claude Code sessions retroactively, making them discoverable in /surface:browse.
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# Index Development Sessions

You help the user populate the session index with sessions that occurred before the plugin was installed, or re-index specific sessions.

## Arguments

If `$ARGUMENTS` contains a session ID, skip the listing step and index that session directly:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_session.py --session-id $ARGUMENTS --project-dir $PWD
```

If `$ARGUMENTS` contains `--force`, pass it through to re-index an already-indexed session.

Otherwise, proceed with the steps below.

## Steps

### 1. List sessions and their index status

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_session.py --list --project-dir $PWD
```

If no sessions exist, inform the user:

> No Claude Code sessions found for this project. Sessions appear after running Claude Code in this directory.

### 2. Present options

If unindexed sessions exist, use AskUserQuestion to present options:

- **Backfill all unindexed sessions** — Index all sessions not yet in the index. Each session requires a Haiku summarization call, so this may take a moment for many sessions.
- **Select specific sessions** — Let the user choose which sessions to index.
- **Cancel** — Exit without indexing.

If all sessions are already indexed, inform the user:

> All sessions for this project are already indexed. Use `/surface:browse` to view them.

### 3. Handle selection

**If backfill:**

Run with `--limit 10` to index the 10 most recent unindexed sessions:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_session.py --backfill --limit 10 --project-dir $PWD
```

Report the results to the user. If there are additional unindexed sessions beyond the limit, inform the user and offer to index all remaining sessions (omit `--limit`) or a custom count (e.g. `--limit 50`).

**If specific sessions:**

Ask the user to provide session IDs (they can reference the list from step 1). For each selected session:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_session.py --session-id <id> --project-dir $PWD
```

### 4. Confirm results

After indexing completes, report the results and suggest:

> Run `/surface:browse` to view and select sessions for PR description generation.
