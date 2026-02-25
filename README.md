# surface

A Claude Code plugin that generates PR descriptions from the agent's reasoning traces.

When a developer finishes an implementation with Claude Code, surface extracts the key decisions, tradeoffs, and reasoning from the session transcripts and produces a structured PR description. The reviewer gets the equivalent of a walkthrough without the meeting.

## Requirements

- Claude Code
- Python 3.9+
- `gh` CLI (optional, for creating PRs directly)

## Install

Add the marketplace and install the plugin:

```sh
/plugin marketplace add /path/to/surface-plugin
/plugin install surface@surface
```

Alternatively, load the plugin for a single session without installing:

```sh
claude --plugin-dir /path/to/surface-plugin
```

## Usage

### Browse sessions

```
/surface:browse
```

Displays an index of recent plan-mode sessions and lets you select which ones to include in the PR description. The index populates automatically when Claude Code sessions end.

### Generate a PR description

```
/surface:describe <session-id> [session-id...]
```

Extracts reasoning signals from the specified sessions and synthesizes a four-section PR description:

- **Overview**: What changed and why
- **Approach**: Key design decisions and what informed them
- **Tradeoffs**: Alternatives considered and rejected
- **Review Focus**: Areas of uncertainty or complexity

After generating the description, the plugin offers to create a pull request via `gh pr create`.

## How it works

A `SessionEnd` hook runs when each Claude Code session ends, producing a Haiku-summarized index entry in `.surface/session-index.jsonl`. When the developer runs `/surface:describe`, a Python script extracts structured signals (user requests, plans, plan revisions, thinking decisions, exploration context) from the session transcripts into `.surface/<session>.signals.jsonl`. Claude then synthesizes these signals into the PR description.

Extraction is pure Python with no API calls. Synthesis uses the Claude model running in Claude Code.

## Scope

v0 supports plan-mode sessions only. Sessions where the agent deliberates on approach before implementing produce structured reasoning signals that the extraction pipeline reliably parses.
