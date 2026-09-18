# LLM Dojo: AI interfaces (18 Sept 2026)

Companion material for the talk *The four AI interfaces: a practical guide*. Everything the
talk referred to as "my setup", anonymized for public release: the skills, the prompts and
presets, the libraries, and the pre-commit hooks with what is switched on where.

## Layout

| Folder | What is in it |
|---|---|
| [`skills/`](skills/README.md) | Agent skills: one folder per skill with `SKILL.md`, scripts and templates |
| [`skills/personal/`](skills/personal) | The author's own general-purpose skills (`amg-*`) |
| [`skills/research-monorepo/`](skills/research-monorepo) | Skills for the author's research platform (`aii-*`) |
| [`skills/third-party/`](skills/third-party) | Vendored skills by others (Anthropic document skills, Playwright, ...) |
| [`prompts/`](prompts/README.md) | Claude Code prompts: global instructions, agent presets, quick-reply presets, slash commands, hooks, settings |
| [`libraries/`](libraries/README.md) | Libraries and tools in use, one file per language or tool class |
| [`hooks/`](hooks/README.md) | Every pre-commit hook lane the research monorepo runs, with its rule and on/off state |
| [`ANONYMIZATION.md`](ANONYMIZATION.md) | What was removed or replaced before publishing |

## How it fits together

- A **skill** is a folder an agent loads on demand: a `SKILL.md` with the rules, plus any
  scripts or templates it needs. Skills are tool-agnostic markdown; Claude Code discovers
  them under `.claude/skills/`.
- **Prompts** are the always-on layer: `global-CLAUDE.md` applies to every session, the
  `agent-presets/` fix model and effort per subagent type, and `slash-commands/` are
  reusable prompts invoked by name.
- **Hooks** are the commit-time layer: a shared lefthook repo, vendored as a submodule,
  gates every commit in the research monorepo.
- **Libraries** lists what all of the above depends on.

## Anonymization

Names, employer, city, emails, home paths, hostnames, account identifiers and every
credential were replaced with placeholders (`the author`, `institute`, `user@example.com`,
`/home/<user>`, `<REDACTED>`); one slide template carrying a logo was dropped. Skill
prefixes and tool names were kept so cross-references still work. Details in
[`ANONYMIZATION.md`](ANONYMIZATION.md).

## License

Third-party skills keep their own licenses (see each folder). Everything else: MIT.
