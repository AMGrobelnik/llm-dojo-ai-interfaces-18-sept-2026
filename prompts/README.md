# Prompts

The author's Claude Code configuration: the always-on instructions, the subagent presets,
reusable slash-command prompts, and the two session hooks that enforce them. Credentials
are `<REDACTED>`; see `../ANONYMIZATION.md`.

## Contents

- `global-CLAUDE.md` — the global `~/.claude/CLAUDE.md`, injected into every session:
  git and commit rules, delegation and model-choice policy, worktree discipline, Python
  conventions.
- `agent-presets/` — the model × effort subagent presets (`Explore`, `gen-haiku`,
  `gen-sonnet-<effort>`, `gen-opus-<effort>`): a frontmatter plus system prompt each.
- `quick-reply-presets.md` — the eight one-tap canned prompts (Continue, Recap, Commit,
  Safe Cron, /compact, Test, Improve?, Concise) from the phone remote-control app.
- `slash-commands/` — custom slash-command prompts (`/amg-improve-paper`, `/amg-loop`,
  `/m`, `/sleep`, `/upd`).
- `claude-code-hooks/` — the Python hooks wired into `settings.json`:
  `agent_type_gate.py` (only the preset agent types may be spawned) and `turn_recap.py`
  (recap on every Stop).
- `settings.json` — `~/.claude/settings.json`: hooks, permissions, plugins, defaults.
- `mcp.json` — MCP server template (Context7 over HTTP, key via env var).
- `claude-code-setup-README.md`, `user_guide.md` — setup and workflow notes for this
  configuration.
- `agentic-coding-tips.md` — the concise tips list from the author's agentic-coding talk.
- `repo-level/research-monorepo-docker-CLAUDE.md` — the one repo-level `CLAUDE.md` in
  the research monorepo (its `docker/` tree).

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

## Redactions

- `settings.json`: `env.CONTEXT7_API_KEY` and `remote.defaultEnvironmentId` are
  `<REDACTED>`; the hook path is `$HOME`-relative.
