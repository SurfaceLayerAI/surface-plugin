# claude-clode

## What is this?

A Claude Code plugin that auto-generates PR context for reviewers by analyzing the agent's reasoning traces from the development session.

## Problem

When a developer opens a large pull request (>400 LOC), the reviewer has no context on what changed, why, what tradeoffs were made, or where to focus. The standard workaround is to schedule a synchronous walkthrough meeting which creates multi-hour or multi-day delays and directly throttles merge throughput.

## Solution

Claude Code records full session transcripts including the agent's chain-of-thought reasoning (thinking blocks), tool calls, and user interactions. When a developer finishes their implementation, they select relevant sessions from a Haiku-summarized index and run `/analyze-traces`. The plugin reads the session transcripts, extracts key decisions and tradeoffs, and produces a structured PR description the reviewer can immediately act on.

The reviewer gets the equivalent of a walkthrough — what changed and why, tradeoffs made, and where to focus — without the meeting.

## How it works

### Data source

Claude Code persists session transcripts to `~/.claude/projects/<project>/<session>.jsonl`. Each line is a JSON entry. The entry types we care about:

| Entry Type | Key Fields | What we extract |
|---|---|---|
| `assistant` (thinking blocks) | `message.content[].thinking` | Agent's chain-of-thought: alternatives considered, tradeoffs weighed, decisions made |
| `assistant` (text) | `message.content[].text` | Agent's visible reasoning shared with the user |
| `assistant` (tool_use) | `message.content[].name`, `.input` | Plan file writes (`Write` tool to `plans/` paths), file exploration (`Read`, `Grep`, `Glob`), task decomposition (`TodoWrite`) |
| `user` | `content` | Original task request, plan feedback/rejections |

#### Subagent transcripts

Claude Code subagents (spawned via the `Task` tool) produce separate transcripts. The `SubagentStop` hook provides `agent_transcript_path`.

**v0: main session transcript only.** The main transcript captures the orchestrating agent's high-level reasoning — why it delegated, what it expected, and results returned. Design decisions and tradeoffs live here. Subagent transcripts contain implementation detail, not strategic reasoning.

Future enhancement: extract from subagent transcripts for execution-phase context.

### Processing pipeline

The plugin operates in two phases. Extraction and synthesis are separated for three reasons:

- **Cost separation**: Extraction is Python, zero API calls, milliseconds. Synthesis requires an LLM. The expensive call only happens when the developer explicitly requests it.
- **Debuggability**: The intermediate signals file is human-readable. If the PR description is wrong, inspect signals to diagnose whether extraction missed something or synthesis misinterpreted it.
- **Replayability**: Re-run synthesis with different prompts or models without re-extracting.

**Phase 1 — Extraction** (on-demand via `/analyze-traces`):

A Python script reads the transcript line-by-line and extracts structured "signals":

| Signal | Source | Why it matters |
|---|---|---|
| User request | First non-system `user` entry | The "why" behind the PR |
| Plan content | `Write` tool calls to plan file paths | The agent's full synthesized approach with reasoning |
| Plan revision | 2nd+ `Write` to the same plan path | Direct evidence a tradeoff was negotiated |
| User feedback | `user` entries between plan writes | What the developer pushed back on and why |
| Thinking decisions | `thinking` blocks containing alternatives/tradeoffs | The agent's internal deliberation on approach |
| Exploration context | `Read`/`Grep`/`Glob` tool calls before first code write | What the agent researched before deciding |

The highest-value signal is **plan rejections**. When a user rejects the agent's proposed plan and gives feedback, that exchange directly encodes a tradeoff that was explicitly negotiated. Both the original plan and the revision are captured.

Signals are written to an intermediate JSONL file (`.claude-clode/<session>.signals.jsonl`) with a typed schema designed for extensibility — future signal types can be added without changing existing processing.

Extraction is a Python script reading JSONL line-by-line. No LLM, no context window concern. O(n) over the transcript. A typical plan-mode session produces 50K–200K+ tokens of raw transcript (thinking blocks are the bulk). Extraction reduces this to a signals file ~10–20x smaller.

**Phase 2 — Synthesis** (on-demand via `/analyze-traces` command):

A Claude Code command reads the extracted signals and produces a four-section PR description:

| Section | Purpose |
|---|---|
| **Overview** | What changed and why (1-3 sentences) |
| **Approach** | Key design decisions and what informed them |
| **Tradeoffs** | Alternatives considered and rejected, especially where user feedback changed direction |
| **Review Focus** | Areas of uncertainty or complexity that deserve close attention |

Before synthesis, `/analyze-traces` estimates the combined token count of all selected signals files. If the estimate exceeds a threshold (~30K tokens), it warns the developer and recommends selecting fewer sessions or a narrower scope. Automatic chunking/prioritization is out of scope for v0.

### Session indexing

When a Claude Code session ends, a `SessionEnd` hook runs a lightweight indexing step. A Python script reads the transcript, extracts key structural elements (session ID, timestamp, initial user request, plan file paths, files touched), and passes these snippets to Haiku with a prompt to produce a 2-3 sentence summary. The result is appended to `.claude-clode/session-index.jsonl`:

```jsonl
{"session_id": "...", "timestamp": "...", "summary": "...", "plan_mode": true, "plan_paths": ["plans/auth-redesign.md"]}
```

This index exists so the developer can scan their sessions and choose which ones to feed into `/analyze-traces`. A session ID and timestamp alone aren't enough — the developer needs to understand *what happened*. Haiku turns structural metadata into a human-scannable summary at negligible cost (~$0.25/MTok input; a few thousand tokens of extracted snippets costs fractions of a cent per session).

### Hooks and triggers

| Hook | Event | Purpose |
|---|---|---|
| `SessionEnd` | Claude Code session ends | Runs lightweight indexing: extracts metadata from transcript, calls Haiku to produce summary, appends to `.claude-clode/session-index.jsonl` |

| Command | Trigger | Purpose |
|---|---|---|
| `/analyze-traces <session-id> [session-id...]` | Developer runs manually with selected session IDs | Runs extraction (Phase 1) then synthesis (Phase 2) on chosen sessions, outputs PR description |

**Why SessionEnd and not other hooks:** The transcript is the data source — Claude Code writes it throughout the session. We don't need hooks to *collect* data. SessionEnd is used for session indexing only — a Haiku-summarized entry that helps the developer find and select relevant sessions. No other hook point is needed: `PreToolUse`/`PostToolUse` fire per tool call (hundreds of times per session), and the transcript already records all that data. Duplicating it via hooks adds complexity with no benefit.

**Why SessionEnd and not automatic extraction:** Development is non-linear. A developer may work across many sessions, revisit earlier work, or abandon threads. Running full extraction on every SessionEnd wastes work on sessions that may never be relevant to the final PR. The developer knows which sessions matter — they should select them explicitly via `/analyze-traces`.

**SessionEnd firing conditions:** The hook receives `session_id` and `transcript_path`. Known reasons for firing: `clear`, `logout`, `prompt_input_exit`, `bypass_permissions_disabled`, `other`. If SessionEnd doesn't fire (e.g., process killed), the session transcript still exists on disk. `/analyze-traces` can process any session by ID regardless of whether SessionEnd indexed it — the index is a convenience, not a requirement.

## Scope (v0)

**In scope:**
- Plan-mode sessions (where the agent explicitly deliberates on approach before executing)
- PR description as output (copy-pasteable into GitHub/GitLab)
- Session indexing on session end (lightweight Haiku summary for discoverability)
- On-demand extraction and synthesis via `/analyze-traces` with explicit session selection
- Multi-session support — `/analyze-traces` accepts multiple session IDs for PRs spanning several sessions

**Out of scope:**
- Non-plan-mode sessions — if the developer isn't using plan mode, the change is likely not complex enough to need this context
- Inline PR comments on specific code lines — v0 produces a top-level summary; line-level annotations are a future enhancement
- Execution-phase code capture via `PostToolUse` hook on `Edit`/`Write` — the transcript already records every tool call including edits, so a separate hook duplicates data. v0 focuses on *reasoning* (the "why"), not code (the "what"). The reviewer sees code in the diff; they lack the context for why it looks that way.
- Automatic context chunking — if combined signals exceed the context threshold, the developer selects fewer sessions rather than the tool auto-splitting

## User experience

1. Developer uses Claude Code with plan mode to implement a feature
2. Session ends. The plugin indexes the session (Haiku summary) in the background.
3. Developer reviews the session index to identify relevant sessions
4. Developer runs `/analyze-traces <session-id> [session-id...]` with selected sessions
5. Plugin extracts signals, estimates context size (warns if too large), runs synthesis, and outputs a structured PR description
6. Developer pastes the PR description into their pull request
7. Reviewer reads the PR description and starts reviewing immediately — no meeting needed

## Future directions

- **Inline PR comments**: Map reasoning to specific diff locations so context appears exactly where the reviewer needs it
- **Execution-phase signals**: Capture decisions made during implementation (test failures, backtracking, error recovery) — not just planning. This includes extracting from subagent transcripts for implementation detail.
- **Confidence scoring**: Infer which decisions the agent was uncertain about (many iterations, hedging language) to guide reviewer attention
- **PR splitting recommendations**: Detect when a PR contains multiple logical concerns and suggest splitting

## Edge Cases

| Edge Case | Do We Handle? | Reasoning |
|---|---|---|
