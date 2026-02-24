# claude-clode

## What is this?

A Claude Code plugin that auto-generates PR context for reviewers by analyzing the agent's reasoning traces from the development session.

## Problem

When a developer opens a large pull request (>400 LOC), the reviewer has no context on what changed, why, what tradeoffs were made, or where to focus. The standard workaround is to schedule a synchronous walkthrough meeting which creates multi-hour or multi-day delays and directly throttles merge throughput.

## Solution

Claude Code records full session transcripts including the agent's chain-of-thought reasoning (thinking blocks), tool calls, and user interactions. When a developer finishes their implementation, they run `/analyze-traces`. The plugin reads the session transcript, extracts key decisions and tradeoffs, and produces a structured PR description the reviewer can immediately act on.

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

### Processing pipeline

The plugin operates in two phases:

**Phase 1 — Extraction** (automatic on session end via `SessionEnd` hook, or on-demand):

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

**Phase 2 — Synthesis** (on-demand via `/analyze-traces` command):

A Claude Code command reads the extracted signals alongside `git diff` and produces a four-section PR description:

| Section | Purpose |
|---|---|
| **Overview** | What changed and why (1-3 sentences) |
| **Approach** | Key design decisions and what informed them |
| **Tradeoffs** | Alternatives considered and rejected, especially where user feedback changed direction |
| **Review Focus** | Areas of uncertainty or complexity that deserve close attention |

### Hooks and triggers

| Hook | Event | Purpose |
|---|---|---|
| `SessionEnd` | Claude Code session ends | Auto-runs extraction in background, writes signals to `.claude-clode/` |

| Command | Trigger | Purpose |
|---|---|---|
| `/analyze-traces` | Developer runs manually | Reads signals + git diff, outputs PR description |

## Scope (v0)

**In scope:**
- Plan-mode sessions (where the agent explicitly deliberates on approach before executing)
- PR description as output (copy-pasteable into GitHub/GitLab)
- Extraction runs automatically when a session ends (via hook) and on-demand via `/analyze-traces`

**Out of scope:**
- Non-plan-mode sessions — if the developer isn't using plan mode, the change is likely not complex enough to need this context
- Inline PR comments on specific code lines — v0 produces a top-level summary; line-level annotations are a future enhancement
- Multi-session aggregation — v0 assumes one session per PR
- Trust calibration — the synthesis reports what the agent reasoned, without distinguishing confident vs. uncertain decisions

## User experience

1. Developer uses Claude Code with plan mode to implement a feature
2. Session ends. The plugin automatically extracts reasoning signals in the background.
3. Developer runs `/analyze-traces`
4. Plugin outputs a structured PR description they paste into their pull request
5. Reviewer reads the PR description and starts reviewing immediately — no meeting needed

## What does success look like?

- Developers stop scheduling synchronous PR walkthrough meetings for agent-assisted PRs
- Time from "PR opened" to "first review comment" decreases
- Reviewers report feeling oriented on large PRs without needing to ask clarifying questions

## Risks

- **Synthesis quality**: If the generated description is vague or inaccurate, reviewers won't trust it, and adoption stalls. Mitigation: v0 focuses on plan-mode sessions where reasoning is most structured.
- **Adoption friction**: Developers need to be using plan mode for the plugin to have signal. If most development happens outside plan mode, the plugin's utility is limited.
- **Transcript format stability**: The plugin depends on Claude Code's internal transcript format. If the format changes, extraction breaks. Mitigation: the extraction script is the only coupling point and is straightforward to update.

## Future directions

- **Inline PR comments**: Map reasoning to specific diff locations so context appears exactly where the reviewer needs it
- **Execution-phase signals**: Capture decisions made during implementation (test failures, backtracking, error recovery) — not just planning
- **Confidence scoring**: Infer which decisions the agent was uncertain about (many iterations, hedging language) to guide reviewer attention
- **PR splitting recommendations**: Detect when a PR contains multiple logical concerns and suggest splitting
