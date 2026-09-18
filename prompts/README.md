# Prompts

The author's Claude Code prompts and config, anonymized for public release:
names, handles, home paths, hostnames and account identifiers are replaced with
placeholders, and every credential value is `<REDACTED>` (see "Redactions"
below and `../ANONYMIZATION.md`).

## Contents

- `global-CLAUDE.md` — the global `~/.claude/CLAUDE.md` (a symlink to the notes-repo
  mirror; both are the same file, so there is no live/mirror diff to report).
- `agent-presets/` — the model x effort subagent preset definitions
  (`Explore`, `gen-haiku`, `gen-sonnet-<effort>`, `gen-opus-<effort>`), each a
  frontmatter + system-prompt `.md` file loaded by the `Agent` tool.
- `slash-commands/` — custom slash-command prompt files (`/amg-improve-paper`,
  `/amg-loop`, `/m`, `/sleep`, `/upd`). No live `~/.claude/commands/` existed, so
  these came from the notes-repo mirror.
- `claude-code-hooks/` — the two Python hook scripts wired into `settings.json`:
  `agent_type_gate.py` (gates which subagent types/models can be spawned) and
  `turn_recap.py` (runs on Stop to produce a turn recap). Log files were skipped.
- `settings.json` — the live `~/.claude/settings.json` (hooks, permissions,
  enabled plugins, model/effort defaults, etc.), with the `CONTEXT7_API_KEY`
  value redacted.
- `output-styles/` — not created; no `~/.claude/output-styles/` directory exists.
- `claude-code-setup-README.md` — the notes-repo `claude-code/README.md`, the setup
  doc for this Claude Code environment.
- `user_guide.md` — the notes-repo `claude-code/user_guide.md`, a user-facing guide.
- `agentic-coding-tips.md` — the notes-repo `claude-code/tips/all_tips_concise.md`
  concise tips reference (the companion `.pptx` was not copied; not a prompt).
- `mcp.json` — the notes-repo `claude-code/.mcp.json` MCP server config (Context7
  over HTTP; only an env-var reference, no literal key, so nothing to redact).
  No live `~/.claude/.mcp.json` existed.
- `repo-level/research-monorepo-docker-CLAUDE.md` — the one repo-level `CLAUDE.md`
  found in `research-monorepo` (at `docker/CLAUDE.md`); no other repo-level
  `CLAUDE.md`/`AGENTS.md` exists in `research-monorepo` or `notes-repo` (root or
  `.claude/`).

## Agent presets

| name | model | effort |
|---|---|---|
| Explore | haiku | (none) |
| gen-haiku | haiku | (none) |
| gen-sonnet-low | sonnet | low |
| gen-sonnet-medium | sonnet | medium |
| gen-sonnet-high | sonnet | high |
| gen-sonnet-xhigh | sonnet | xhigh |
| gen-sonnet-max | sonnet | max |
| gen-opus-low | opus | low |
| gen-opus-medium | opus | medium |
| gen-opus-high | opus | high |
| gen-opus-xhigh | opus | xhigh |
| gen-opus-max | opus | max |

## Diffs found (live vs. notes-repo mirror)

- `~/.claude/CLAUDE.md` vs. mirror: identical — the live file is a symlink to
  the mirror.
- `~/.claude/agents/` vs. mirror `agents/`: identical content; the only
  difference was a local `.ruff_cache/` directory under the live path (not a
  prompt file, not copied).

## Redactions

- `settings.json`: `env.CONTEXT7_API_KEY` and `remote.defaultEnvironmentId`
  values replaced with `<REDACTED>`; the `agent_type_gate.py` hook path is
  `$HOME`-relative rather than absolute.
