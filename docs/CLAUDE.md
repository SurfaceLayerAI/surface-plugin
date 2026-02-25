# docs/

## What is here

- `design/SPEC.md` - Product specification. Defines the plugin's architecture, processing pipeline, data sources, hooks, commands, scope, and edge cases. This is the source of truth for what the plugin does and why.
- `guides/WRITING_STYLE.md` - Prose style rules for all user-facing text (no contractions, active voice, no em dashes, present habitual tense). Apply these when writing output templates, PR descriptions, or documentation.
- `guides/example-plugin/` - Reference implementation of a Claude Code plugin. Shows the directory layout, `plugin.json`, commands, skills, and MCP server configuration.

## Constraints

- All user-facing prose must follow `guides/WRITING_STYLE.md`.
- The spec is authoritative for v0 scope decisions. Do not implement features the spec marks as out of scope without updating the spec first.
