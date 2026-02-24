# claude-clode

## What is this?

A Claude Code plugin that auto-generates PR context for reviewers by analyzing the agent's reasoning traces from the development session.

## Problem

When a developer opens a large pull request (>400 LOC), the reviewer has no context on what changed, why, what tradeoffs were made, or where to focus. The standard workaround is to schedule a synchronous walkthrough meeting which creates multi-hour or multi-day delays and directly throttles merge throughput.

## Solution

Claude Code records full session transcripts including the agent's chain-of-thought reasoning (thinking blocks), tool calls, and user interactions. When a developer finishes their implementation, they run `/claude-clode:sessions` to browse a Haiku-summarized index of recent sessions, select the relevant ones, and run `/claude-clode:analyze-traces` with those session IDs. The plugin reads the session transcripts, extracts key decisions and tradeoffs, and produces a structured PR description.

The reviewer gets the equivalent of a walkthrough: what changed and why, tradeoffs made, and where to focus. No meeting needed.

## Plugin structure and distribution

claude-clode ships as a Claude Code plugin directory:

```
claude-clode/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── analyze-traces/
│   │   └── SKILL.md
│   └── sessions/
│       └── SKILL.md
├── hooks/
│   └── hooks.json
└── scripts/
    ├── extract_signals.py
    └── index_session.py
```

`plugin.json` declares the plugin name, version, description, and registered hooks. The `skills/` directory contains command definitions: each subdirectory maps to a `/claude-clode:<command>` namespace. The `hooks/` directory registers lifecycle hooks (e.g., `SessionEnd` for indexing). The `scripts/` directory holds standalone Python scripts invoked by hooks and commands.

Installation: run `/plugin install <path-or-url>` from Claude Code, or launch Claude Code with `claude --plugin-dir ./claude-clode`. Both methods register the plugin for the current project. Command namespacing (`/claude-clode:<command>`) prevents collisions with other plugins or built-in commands.

## How it works

### Data source

Claude Code persists session transcripts to `~/.claude/projects/<project>/<session>.jsonl`. Each line is a JSON entry. The entry types we care about:

| Entry Type | Key Fields | What we extract |
|---|---|---|
| `assistant` (thinking blocks) | `message.content[].thinking` | Agent's chain-of-thought: alternatives considered, tradeoffs weighed, decisions made |
| `assistant` (text) | `message.content[].text` | Agent's visible reasoning shared with the user |
| `assistant` (tool_use) | `message.content[].name`, `.input` | Plan file writes (`Write` tool to `plans/` paths), file exploration (`Read`, `Grep`, `Glob`), task decomposition (`TodoWrite`) |
| `user` | `content` | Original task request, plan feedback/rejections |
| `assistant` (tool_use: `Task`) | `message.content[].input.subagent_type`, `.input.prompt` | Plan subagent delegation: when and why the orchestrating agent spawned a Plan agent |
| `queue-operation` | `agentId` | Links `Task` tool calls to subagent transcript paths at `<session-dir>/subagents/agent-<agentId>.jsonl` |

#### Subagent transcripts

Claude Code subagents (spawned via the `Task` tool) produce separate transcripts at `<session-dir>/subagents/agent-<agentId>.jsonl`. The main session transcript and Plan subagent transcripts capture different layers of reasoning. Both are necessary because the orchestrating agent and the Plan agent operate at different levels of abstraction.

| | Main session transcript | Plan subagent transcript |
|---|---|---|
| **What it records** | The orchestrating agent's decisions: entering plan mode, delegating to the Plan agent, receiving the finished plan, acting on it. User interactions (the original request, plan feedback/rejections, approval). Thinking blocks with high-level tradeoff reasoning. | The Plan agent's working process: exploration tool calls (Read, Grep, Glob, Bash), step-by-step analysis in text responses, intermediate conclusions, and the final synthesized plan. |
| **Level of abstraction** | Strategic: what to do and why (user intent, tradeoff negotiation, plan acceptance/rejection) | Tactical: how the plan formed (what code the agent read, what patterns it found, what alternatives it considered during exploration) |
| **Unique signals** | User request, plan rejections/feedback, thinking blocks with alternatives weighed, the decision to accept or revise | Exploration breadcrumbs (which files and patterns informed the design), reasoning chain from evidence to conclusion, draft reasoning before the final plan crystallized |

Neither transcript alone provides the full picture. The main transcript without the Plan subagent transcript shows the reviewer that a plan was made and whether the user pushed back, but not how the agent arrived at it. The plan appears as a finished artifact with no visible reasoning trail. The Plan subagent transcript without the main transcript shows the exploration and reasoning process but loses the user interaction layer: what the user originally asked for, whether they rejected the first plan, and what feedback changed the direction.

The plugin's highest-value output (the "Tradeoffs" and "Approach" sections of the PR description) requires both layers. The main transcript supplies the negotiation (user rejected plan A because X, agent revised to plan B). The Plan subagent transcript supplies the reasoning (agent read files Y and Z, found pattern W, concluded approach B).

**v0 scope: main transcript + Plan subagent transcripts.** Other subagent types (Explore, code-writing, meta agents) contain implementation detail and remain out of scope. The extraction script parses the main transcript for `Task` tool calls with `subagent_type: "Plan"`, extracts the `agentId` from `queue-operation` entries, and reads the corresponding Plan subagent transcript from `<session-dir>/subagents/agent-<agentId>.jsonl`. Plan agents do not produce `thinking` blocks, so that entry type is absent from Plan subagent transcripts.

##### Plan subagent transcript entries

| Entry Type | Key Fields | What we extract |
|---|---|---|
| `assistant` (text) | `message.content[].text` | Step-by-step reasoning: analysis of explored code, intermediate conclusions, plan narrative |
| `assistant` (tool_use) | `message.content[].name`, `.input` | Exploration calls (Read, Grep, Glob, Bash) showing what the Plan agent examined |
| `assistant` (tool_result) | `message.content[].content` | Results that informed the Plan agent's decisions and conclusions |

Plan agents do not produce `thinking` blocks, so that type is intentionally absent.

### Processing pipeline

The plugin operates in two phases. Extraction and synthesis are separated for three reasons:

- **Cost separation**: Extraction is Python, zero API calls, milliseconds. Synthesis requires an LLM. The expensive call only happens when the developer explicitly requests it.
- **Debuggability**: The intermediate signals file is human-readable. If the PR description is wrong, inspect signals to diagnose whether extraction missed something or synthesis misinterpreted it.
- **Replayability**: Re-run synthesis with different prompts or models without re-extracting.

**Phase 1: Extraction** (on-demand via `/claude-clode:analyze-traces`):

A Python script reads the main session transcript and any Plan subagent transcripts line-by-line and extracts structured "signals":

| Signal | Source | Why it matters |
|---|---|---|
| User request | First non-system `user` entry | The "why" behind the PR |
| Plan content | `Write` tool calls to plan file paths | The agent's full synthesized approach with reasoning |
| Plan revision | 2nd+ `Write` to the same plan path | Direct evidence a tradeoff was negotiated |
| User feedback | `user` entries between plan writes | What the developer pushed back on and why |
| Thinking decisions | `thinking` blocks containing alternatives/tradeoffs | The agent's internal deliberation on approach |
| Exploration context | `Read`/`Grep`/`Glob` tool calls before first code write | What the agent researched before deciding |
| Plan agent reasoning | Plan subagent `assistant` text responses | Step-by-step analysis and intermediate conclusions the Plan agent produced while forming the plan |
| Plan agent exploration | Plan subagent tool calls (`Read`, `Grep`, `Glob`, `Bash`) | Files and patterns the Plan agent examined, linking plan conclusions to specific codebase evidence |

The highest-value signal is **plan rejections**. When a user rejects the agent's proposed plan and gives feedback, that exchange directly encodes a tradeoff that was explicitly negotiated. Both the original plan and the revision are captured.

Signals are written to an intermediate JSONL file (`.claude-clode/<session>.signals.jsonl`) with a typed schema designed for extensibility: future signal types can be added without changing existing processing.

Extraction is a Python script reading JSONL line-by-line. No LLM, no context window concern. O(n) over each transcript. The script first scans the main transcript for `Task` tool calls with `subagent_type: "Plan"`, collects `agentId` values from corresponding `queue-operation` entries, and locates Plan subagent transcripts at `<session-dir>/subagents/agent-<agentId>.jsonl`. The script then extracts signals from both the main transcript and each discovered Plan subagent transcript. A typical plan-mode session produces 50K–200K+ tokens of raw transcript (thinking blocks are the bulk). Extraction reduces this to a signals file ~10–20x smaller.

**Phase 2: Synthesis** (on-demand via `/claude-clode:analyze-traces` command):

A Claude Code command reads the extracted signals and produces a four-section PR description:

| Section | Purpose |
|---|---|
| **Overview** | What changed and why (1-3 sentences) |
| **Approach** | Key design decisions and what informed them |
| **Tradeoffs** | Alternatives considered and rejected, especially where user feedback changed direction |
| **Review Focus** | Areas of uncertainty or complexity that deserve close attention |

Before synthesis, `/claude-clode:analyze-traces` estimates the combined token count of all selected signals files. If the estimate exceeds 100K tokens (roughly 50% of the context window, the general threshold for performance degradation), it warns the developer and recommends selecting fewer sessions or a narrower scope. Automatic chunking/prioritization is out of scope for v0.

#### Multi-session synthesis

When `/claude-clode:analyze-traces` receives multiple session IDs, synthesis narrates the full reasoning arc across sessions. The output is biased toward the final session's state as authoritative, since later sessions reflect the most current decisions. The reviewer sees how the approach evolved: initial direction, mid-course corrections, and the rationale behind the final state.

### Session indexing

When a Claude Code session ends, a `SessionEnd` hook runs a lightweight indexing step. A Python script reads the transcript, extracts key structural elements (session ID, timestamp, initial user request, plan file paths, files touched), and passes these snippets to Haiku with a prompt to produce a 2-3 sentence summary. The result is appended to `.claude-clode/session-index.jsonl`:

```jsonl
{"session_id": "...", "timestamp": "...", "summary": "...", "plan_mode": true, "plan_paths": ["plans/auth-redesign.md"]}
```

The index lets the developer scan their sessions and choose which ones to feed into `/claude-clode:analyze-traces`. A session ID and timestamp alone are not enough: the developer needs to understand *what happened*. Haiku turns structural metadata into a human-scannable summary at negligible cost (~$0.25/MTok input; a few thousand tokens of extracted snippets costs fractions of a cent per session).

### Hooks and triggers

| Hook | Event | Purpose |
|---|---|---|
| `SessionEnd` | Claude Code session ends | Runs lightweight indexing: extracts metadata from transcript, calls Haiku to produce summary, appends to `.claude-clode/session-index.jsonl` |

| Command | Trigger | Purpose |
|---|---|---|
| `/claude-clode:sessions` | Developer runs manually | Displays the session index (summaries and IDs) in the TUI. The developer reads summaries, copies relevant session IDs, and runs `/claude-clode:analyze-traces`. |
| `/claude-clode:analyze-traces <session-id> [session-id...]` | Developer runs manually with selected session IDs | Runs extraction (Phase 1) then synthesis (Phase 2) on chosen sessions, outputs PR description |

**Why SessionEnd and not other hooks:** The transcript is the data source. Claude Code writes it throughout the session. The plugin does not need hooks to *collect* data. SessionEnd handles session indexing only: a Haiku-summarized entry that helps the developer find and select relevant sessions. No other hook point is needed. `PreToolUse`/`PostToolUse` fire per tool call (hundreds of times per session), and the transcript already records all that data. Duplicating it via hooks adds complexity with no benefit.

**Why SessionEnd and not automatic extraction:** Development is non-linear. A developer may work across many sessions, revisit earlier work, or abandon threads. Running full extraction on every SessionEnd wastes work on sessions that may never be relevant to the final PR. The developer knows which sessions matter and selects them explicitly via `/claude-clode:analyze-traces`.

**SessionEnd firing conditions:** The hook receives `session_id` and `transcript_path`. Known reasons for firing: `clear`, `logout`, `prompt_input_exit`, `bypass_permissions_disabled`, `other`. If SessionEnd does not fire (e.g., process killed), the session transcript still exists on disk. `/claude-clode:analyze-traces` can process any session by ID regardless of whether SessionEnd indexed it. The index is a convenience, not a requirement.

## Scope (v0)

**In scope:**
- Plan-mode sessions (where the agent explicitly deliberates on approach before executing)
- PR description as output (copy-pasteable into GitHub/GitLab)
- Session indexing on session end (lightweight Haiku summary for discoverability)
- On-demand extraction and synthesis via `/claude-clode:analyze-traces` with explicit session selection
- Multi-session support: `/claude-clode:analyze-traces` accepts multiple session IDs for PRs spanning several sessions

**Out of scope:**
- Non-plan-mode sessions. Plan-mode sessions produce structured reasoning signals (plans, plan rejections, deliberation) that the extraction pipeline reliably parses. Non-plan-mode sessions lack these artifacts. The problem exists outside plan mode; the extraction pipeline does not handle unstructured sessions yet.
- Inline PR comments on specific code lines. v0 produces a top-level summary; line-level annotations are a future enhancement.
- Execution-phase code capture via `PostToolUse` hook on `Edit`/`Write`. The transcript already records every tool call including edits, so a separate hook duplicates data. v0 focuses on *reasoning* (the "why"), not code (the "what"). The reviewer sees code in the diff; they lack the context for why it looks that way.
- Automatic context chunking. If combined signals exceed the context threshold, the developer selects fewer sessions rather than the tool auto-splitting.
- Reviewer feedback loops. The current architecture provides no mechanism to record or act on reviewer feedback. A future version may close the loop by feeding review comments back into the plugin.

## User experience

1. Developer uses Claude Code with plan mode to implement a feature.
2. Session ends. The plugin indexes the session (Haiku summary) in the background.
3. Developer runs `/claude-clode:sessions` to browse the session index.
4. Developer copies relevant session IDs and runs `/claude-clode:analyze-traces <session-id> [session-id...]`.
5. Plugin extracts signals, estimates context size (warns if >100K tokens), runs synthesis, and outputs a structured PR description.
6. Plugin displays the generated PR description for developer review.
7. On confirmation, the plugin creates the PR via `gh pr create --body`.
8. Reviewer reads the PR description and starts reviewing. No meeting needed.

## Future directions

- **Inline PR comments**: Map reasoning to specific diff locations so context appears exactly where the reviewer needs it.
- **Execution-phase signals**: Capture decisions made during implementation (test failures, backtracking, error recovery), not just planning. Extract from non-Plan subagent transcripts (code-writing agents, exploration agents) for implementation detail.
- **Confidence scoring**: Infer which decisions the agent was uncertain about (many iterations, hedging language) to guide reviewer attention.
- **PR splitting recommendations**: Detect when a PR contains multiple logical concerns and suggest splitting.

## Edge cases

| Edge Case | Handled? | Reasoning |
|---|---|---|
| Transcript missing (process killed) | Yes | `/claude-clode:analyze-traces` reads from disk by session ID. If SessionEnd did not fire, the index lacks the entry, but the transcript file persists. The developer provides the session ID directly. |
| Session has no plan-mode activity | No | Extraction produces empty signals. Synthesis warns the developer that no structured reasoning was found. |
| Very long session (>500K tokens) | Partially | Extraction runs O(n) regardless of length. The resulting signals may exceed the 100K token threshold, triggering a warning. The developer selects fewer sessions or narrows scope. |
| Multiple sessions with contradictory decisions | Yes | Synthesis narrates the full reasoning arc, biased toward the final session's state as authoritative. The reviewer sees how the approach evolved. |
| Session contains sensitive data | No | The plugin reads transcripts as-is with no filtering or redaction. Ensuring transcripts do not contain sensitive data is the developer's responsibility. |
| Plan subagent transcript missing | Partially | The main transcript still contains the final plan as a `tool_result`. Extraction logs a warning and proceeds with main-transcript-only signals. The PR description loses intermediate reasoning but retains the final plan. |
