# claude-code — the author's Claude Code setup

Snapshot of the global Claude Code configuration: rules, slash commands,
plugins, and reference templates for fast git hooks. Mirror of what lives in
`~/.claude/`, plus reusable templates for new projects and the agentic-coding
talk in [`tips/`](./tips/).

An environment snapshot, which is why it sits here rather than under `apps/`:
it configures a tool on the machine, the same way [`../ubuntu/`](../ubuntu/)
and [`../macos/`](../macos/) do. It is **not** part of the
`vmware → ubuntu → macos` bootstrap chain those follow — install it whenever,
on either machine.

Not to be confused with [`../../../apps/claude-amg/`](../../../apps/claude-amg/),
which is the phone/browser **remote-control app**. That is a program; this is
configuration. The only thing they share is the word "Claude".

Part of the [`notes-repo`](../../../README.md) monorepo (private). Reusable
**skills** live in [`../../skills/`](../../skills/) — split into `research-monorepo/`
and `amg/`, tool-agnostic rather than Claude-Code-specific.

`../../skills/amg` is a tracked *symlink* (`../../../research-monorepo/.claude/skills`),
not a copy: research-monorepo owns those files and is the only repo that commits
them, so an edit from either checkout hits the same skill files on disk. A
fresh clone of notes-repo therefore needs a `research-monorepo` checkout as a sibling
directory (both under `~/projects/`) for the link to resolve — `../../skills/`'s
own `research-monorepo/` subtree, by contrast, is a real tracked copy in this repo.

## Layout

```text
claude-code/
├── CLAUDE.md             # Global instructions injected into every Claude Code session
├── settings.json         # Mirror of ~/.claude/settings.json (placeholder for API key)
├── agents/               # ~/.claude/agents/ mirror: Explore/general-purpose × effort defs
├── bin/                  # ~/.claude/bin/ mirror: claude-patch-sticky-header.py (see below)
├── .mcp.json             # MCP server template (context7; registered per-project in practice)
├── user_guide.md         # Short workflow notes
├── commands/             # Custom slash commands (amg-loop, sleep, upd, m, amg-improve-paper)
├── precommit-hooks/      # lefthook.yml + every config AND script it references
├── tips/                 # the agentic-coding talk: deck + the source tip list
└── bak/                  # Older CLAUDE.md drafts kept for reference
```

Three pieces of a working setup live OUTSIDE this folder, and the bootstrap
below pulls them in: [`../../../apps/zapier/`](../../../apps/zapier/) (the
Zapier MCP helper scripts agents run when a token fails),
[`../ubuntu/fish/config.fish`](../ubuntu/fish/config.fish) (the fish half of
`cc`), and [`../../../apps/claude-amg/`](../../../apps/claude-amg/) (the bash
half, plus the remote-control app `cc` starts).

## Bootstrap on a new machine

```fish
# The repo is PRIVATE — authenticate first or the clone just prompts and fails.
gh auth login          # or configure an SSH key and clone git@github.com:…
git clone https://github.com/<author>/notes-repo.git ~/projects/notes-repo
cd ~/projects/notes-repo/resources/env/claude-code

# Create the config dir BEFORE writing into it. On a clean machine ~/.claude
# does not exist, and fish does not stop on error — so with this line missing
# every cp below fails and the bootstrap still "succeeds", silently.
mkdir -p ~/.claude/bin

# Global config
cp $PWD/CLAUDE.md     ~/.claude/CLAUDE.md
cp $PWD/settings.json ~/.claude/settings.json
mkdir -p ~/.claude/agents && cp $PWD/agents/*.md ~/.claude/agents/
cp $PWD/bin/claude-patch-sticky-header.py ~/.claude/bin/   # fullscreen header fix, see below

# Replace the API key placeholder with your real Context7 key
sed -i 's/REPLACE_WITH_YOUR_CONTEXT7_KEY/<your-actual-key>/' ~/.claude/settings.json

# Zapier MCP helper scripts. The guidance that names them now lives in
# apps/zapier/README.md, and it is only actionable if they are installed.
cp $PWD/../../../apps/zapier/zapier-mcp-call.py \
   $PWD/../../../apps/zapier/zapier-mcp-check.sh ~/.claude/bin/
chmod +x ~/.claude/bin/zapier-mcp-*

# The `cc` launcher lives with the app it starts. Two halves, one per shell —
# install the one you use.
echo 'source ~/projects/notes-repo/apps/claude-amg/claude-alias.sh' >> ~/.bashrc
# fish: see ../ubuntu/fish/config.fish (defines cc/ccn natively)
```

Everything above assumes the paths `/home/<user>/…`, which `claude-alias.sh`
and the fish config both hardcode. On a machine with a different username,
rewrite those before sourcing either file.

Commands and skills are **project-scoped** now (nothing global lives in
`~/.claude/commands` or `~/.claude/skills`): copy `commands/` into
`<project>/.claude/commands/` and the skills you want from
[`../../skills/`](../../skills/) into `<project>/.claude/skills/`. The context7
MCP server (see `.mcp.json` for the shape) is likewise registered per-project:

```fish
claude mcp add --transport http context7 https://mcp.context7.com/mcp \
  --header "CONTEXT7_API_KEY: <your-actual-key>"
```

## CLAUDE.md — the global instructions

The file injected as a system reminder at the top of every Claude Code
conversation. Since the overhaul it carries only what a commit gate cannot see:
Fable-class sessions orchestrate and Opus-class subagents execute, never
`--no-verify`, shared-checkout git etiquette, Musk's Algorithm for every
non-trivial change, background + safety-net-cron discipline for long-running
work, never `tmux kill-server` on the default socket, never start a Workflow
unasked, the "Cronjob firings = user speaking" rule for self-paced loops,
and a short Python preferences paragraph (`uv`, `src/` layout, `pathlib.Path`,
loguru, pytest). Everything a hook can check moved into the shared
`amg-hooks` repo, vendored as a git submodule at
`.claude/skills/amg-hooks/`. A sample, not an index — the file is
the list.

The overhaul dropped the old `## MCP` section on Zapier auth, so the pointers
that used to leave this folder now start from
[`../../../apps/zapier/README.md`](../../../apps/zapier/README.md) instead: it
names `~/.claude/bin/zapier-mcp-check.sh` and `~/.claude/bin/zapier-mcp-call.py`
as the way to self-serve a token failure, and warns against the one wrong fix —
re-running `claude mcp add` without `--header` — that Zapier's own Connect tab
actively steers you into. The bootstrap above still installs both scripts for
that reason.

**This file is hand-maintained against `~/.claude/CLAUDE.md`; there is no sync
script.** It silently fell 15 lines behind for at least 17 days, and because
the bootstrap copies snapshot → live, the staleness was not inert: running it
would have deleted the live rule. Diff the two before trusting either.

The `claude-setup-snapshot` lefthook check
([`../../../scripts/lint/check_claude_setup_snapshot.py`](../../../scripts/lint/check_claude_setup_snapshot.py))
compares the two on **every** commit to this repo. It used to carry a
`glob: resources/env/claude-code/**`, which sounds right and was the bug: half
of what it verifies lives outside the repo, so editing `~/.claude/CLAUDE.md`
alone touched nothing under the glob and the gate could not fire on the one
drift it exists to catch. That is how the 17 days happened. The glob is gone;
the check costs ~20 ms and prints the exact `cp` that resolves a drift.

## Subagent policy

Every launchable agent is a user definition in `agents/` whose name encodes
the model and, for sonnet/opus, the effort. The Agent tool has no per-launch
effort field, so effort lives in the definition's frontmatter. Haiku has no
effort parameter at all (Claude Code sends none), so `gen-haiku` carries none.

| Type                  | Model  | Effort | Tools     | CLAUDE.md |
|-----------------------|--------|--------|-----------|-----------|
| `Explore`             | haiku  | none   | read-only | omitted   |
| `gen-haiku`           | haiku  | none   | all       | loaded    |
| `gen-sonnet-<effort>` | sonnet | yes    | all       | loaded    |
| `gen-opus-<effort>`   | opus   | yes    | all       | loaded    |

`<effort>` is one of `low`, `medium`, `high`, `xhigh`, `max`, exactly as in
the frontmatter, so the longest name (`gen-sonnet-medium`) fits the 20-char
agent name column. Read-only means Read, Grep, Glob and ToolSearch. All
worker prompts are identical; only the frontmatter differs. There are no Fable subagents.

The agent type itself carries model and effort, so a launch needs no
`model` argument; if one is passed anyway it must equal the definition's
`model`, since a passed model would silently override it. A `PreToolUse`
hook on the `Agent` tool, `hooks/agent_type_gate.py` (wired in
`settings.json`), is the single allow/deny point. It denies a launch when:

- `subagent_type` is `fork` (it always inherits the parent's model)
- `subagent_type` is `Plan` or `general-purpose` (built-ins, not used)
- the type has no definition file in `<project>/.claude/agents/` or
  `~/.claude/agents/`
- the definition declares no `model`
- a `model` argument was passed and differs from the definition's `model`
- the model is sonnet/opus and the definition has no valid `effort`

`CLAUDE.md` carries the matching guidance for the orchestrator: pick the
cheapest model, then the lowest effort that passes the acceptance check.

Reproduce this policy on another machine:

- copy `CLAUDE.md` to `~/.claude/CLAUDE.md`
- copy `settings.json` to `~/.claude/settings.json` (fill in real
  secrets after copying — see Secrets note below)
- copy `agents/` to `~/.claude/agents/`
- copy `hooks/` to `~/.claude/hooks/`
- start a new Claude Code session — agent definition files are
  discovered at the start of each turn, not just at session start

## commands/ — slash commands

Each `.md` file is a [Claude Code slash command](https://docs.claude.com/claude-code/slash-commands).
Type `/<name>` in Claude Code to invoke. These live project-scoped, paired with
`research-monorepo/.claude/commands/` — but "mirrored" overstates it, and the arrow
does not always point the same way. Four of the five are byte-identical; `upd.md`
differs, and here the copy in THIS folder is the newer one: research-monorepo's still
passes `--platform linux/amd64,linux/arm64`, which has been wrong since
`ARCHES=(amd64)` landed on 2026-08-03. Diff before copying in either direction.

`/upd` is also worth a second look before it is copied anywhere. It documents a
hand-rolled `docker buildx build`, and research-monorepo's own CLAUDE.md now routes
every build through the `aii-image-watcher` systemd unit or
`aii_launcher --rebuild --local`. The command may simply be retired.

- **`/amg-loop`**: self-paced 1-min cron loop — keep working the
  highest-priority item at max quality; pause only when genuinely blocked on
  user input. Pairs with `/m`.
- **`/sleep`**: autonomous overnight/away mode — keep working the agreed task
  to completion under a recurring safety-net cron.
- **`/amg-improve-paper`**: detailed paper-improvement workflow
  (research-paper-specific).
- **`/m`**: raise the quality bar — modern best practices, exhaustive
  verification, root-cause fixes.
- **`/upd`**: rebuild + push the research-monorepo Docker images (buildx registry
  cache, maximally parallel).

Retired commands (`/deep-research`, `/explore-plan-code-test`, `/frontend`,
`/parallel-*`, `/sync`, `/system_reminder`) were removed — deep research and
parallel orchestration are built into Claude Code now (the `deep-research`
skill and the Workflow/ultracode machinery).

## precommit-hooks/ — fast multi-agent-safe git hooks (reference template)

`precommit-hooks/lefthook.yml` is the **canonical lefthook config**, bundled
with **every file it references** — the rule configs (the `[tool.ruff*]`,
`[tool.ty*]` and `[tool.importlinter*]` pyproject sections, `_typos.toml`,
`dead_allowlist.txt`, `oxlintrc.json`, `oxfmtrc.json`, `fallowrc.json`,
`eslint.react-compiler.mjs`, and a sanitized `gitleaks.toml.example`),
`COMMIT_CHECKLIST.md` (which one hook exists to print), and the six hooks that
ARE a script rather than a config (`scripts/lint/*.py` and
`.lefthook/pre-push/release-tag-guard.sh`).
See [`precommit-hooks/README.md`](./precommit-hooks/README.md) for the
per-hook → config map and the copy sequence. Copy it into new repos and adapt
the hook list.

Why lefthook over the `pre-commit` framework:

- `pre-commit` does `git stash --keep-index --include-untracked` before every
  hook run to ensure hooks see only staged content. That stash dance races with
  concurrent edits when multiple agents work on the same repo: an auto-fix +
  popped stash collide, `pre-commit` rolls back ALL hook fixes, and you get
  stuck on "Stashed changes conflicted with hook auto-fixes."
- `lefthook` makes a weaker contract — hooks see WT content as-is, no stashing —
  and in exchange runs cleanly with concurrent agents.
- Tradeoff: when 2+ agents touch the *same* file, an auto-fix hook with
  `stage_fixed: true` can pull in another agent's unstaged edits. Different
  files = no risk.

Other reasons it's faster:

- Parallel hook execution by default (`pre-commit` is sequential)
- Single Go binary, no Python boot cost per invocation
- Tools invoked as native binaries (`ruff`, `oxlint`, `gitleaks`, etc.) instead
  of via `uvx <pkg>` — saves 200–500 ms per hook

**A fresh `git worktree` of notes-repo is not yet a checkout that passes these
hooks** — submodules, the `.venv` and the `node_modules` the FE lanes need are
per-worktree, not shared. [`resources/env/worktree.sh`](../worktree.sh) does
that setup (`git submodule update --init`, `uv sync`, symlinking the
`node_modules` the hook lanes need from the main checkout, `lefthook install`)
idempotently, so every session and subagent runs it once instead of
rediscovering the steps; `--check` reports what is still missing without
changing anything.

Install lefthook in a project:

```fish
# Install the binary (one-time). This doc bootstraps BOTH machines notes-repo
# tracks, and they install it differently.
#
# macOS: brew, as ../macos/apps/Brewfile already declares.
brew install lefthook
#
# Ubuntu: NOT brew and NOT apt — there is no Homebrew on that box and no apt
# package. It is a release binary in ~/.local/bin. Mind the arch spelling:
# lefthook publishes Linux_x86_64 / Linux_arm64 / Linux_aarch64, and the four
# projects in the full tool list do not agree on which spelling to use.
# precommit-hooks/README.md carries the measured block for all 12 tools.
curl -fsSL https://github.com/evilmartians/lefthook/releases/download/v2.1.9/lefthook_2.1.9_Linux_x86_64.gz \
  | gunzip > ~/.local/bin/lefthook   # Linux_arm64 on aarch64
chmod +x ~/.local/bin/lefthook

# In the project root. Copying lefthook.yml ALONE gives you a config that
# shells out to eleven files that do not exist — see precommit-hooks/README.md
# for the full copy sequence (configs, scripts/lint/*.py, .lefthook/pre-push/).
cp ~/projects/notes-repo/resources/env/claude-code/precommit-hooks/lefthook.yml .
lefthook install   # writes one .git/hooks/ file per stage — five of them:
                   # pre-commit, pre-push, post-checkout, post-merge, commit-msg
```

Then customize the `pre-commit:` block — keep the `parallel: true` and
`skip: [merge, rebase]` defaults; swap in your project's tools.

A sample of the hook stack used in `research-monorepo` — 7 of the 42 hooks it
declares. `precommit-hooks/README.md` enumerates all 42 and maps each to its
config file:

- **gitleaks** — secret scanning (sanitized deny-list template here; real one gitignored)
- **ruff** — Python lint + format (native binary, not `uvx ruff`)
- **ty** — Python typecheck
- **dead** — unused-symbol detection
- **oxlint** — JS/TS lint+autofix (~50–100× faster than ESLint)
- **shellcheck** — shell script lint
- **typos** — spelling checker (with allowlist for real domain terms only)

Those seven are all `pre-commit` hooks, which is the block that runs in
parallel on staged files and skips during `merge` and `rebase` (auto-fixers +
replayed commits = re-introduced conflicts). That is not true stack-wide:
`pre-push` runs parallel but does not skip, and `post-checkout` / `post-merge`
declare neither and fire on checkout/merge events rather than staged files.

## skills

Reusable skills live in [`../../skills/`](../../skills/) — they're
tool-agnostic (usable from any agent harness), so they're not nested under this
folder. It splits into `research-monorepo/` and `amg/`; the skill directories are
hyphen-named (`aii-*`, `amg-*`, and the vendored `anthropic-*`), not
underscore-named.

## tips/ — the agentic-coding talk

The conference talk on working with coding agents, kept here because it is the
rationale for most of what this folder configures.

| File | What it is |
|---|---|
| `all_tips_concise.md` | the source: 25 tips, one tip ≈ one slide |
| `agentic_coding_tips.pptx` | the built deck (9.2 MB, illustrated) |

Tips learned building `research-monorepo`, grouped as Setup / Prompting / Autonomy /
Code with agents / LLM reliability / Skills / Research outputs. Several are
implemented right here rather than merely recommended, which is the reason to
keep the deck next to the config instead of off in `resources/`:

- **Tip 3** (tune defaults once, in config) is `settings.json` + `agents/` —
  the pinned model (Fable 5.1 orchestrator, per-type subagent models), `effortLevel`,
  and "one curated CLAUDE.md beats auto-memory" is `autoMemoryEnabled: false`.
- **Tip 6b** (raise the budgets that silently cap verification) is the
  `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` entry in the `env` block, and
  the section below is the long version of that slide.
- **Tip 13** (hooks built for agent-speed commits) is `precommit-hooks/`,
  down to the lefthook-over-pre-commit argument.
- **Tip 14** (git discipline with several agents in one checkout) is a hard
  rule in `CLAUDE.md`; **Tip 15** (skip worktrees) dropped out in the overhaul.

So when a tip and this folder disagree, the folder is what actually runs —
fix the slide.

## settings.json — the global Claude Code settings

- **`permissions.defaultMode: "bypassPermissions"`**: skip all permission
  prompts (use cautiously — this trusts Claude broadly).
- **`model`**: default model for every session: `"claude-fable-5-1[1m]"` —
  **Fable 5.1 is the orchestrator** (and the `fork` agent, which always
  inherits it). Subagents are pinned per agent in `agents/` — see below.
- **`tui: "fullscreen"`**: the flicker-free alt-screen renderer with
  virtualized scrollback — the settings-file equivalent of
  `CLAUDE_CODE_NO_FLICKER=1`, which `config.fish` also exports. Both say the
  same thing; the env var wins when they disagree. Cost: the terminal's own
  scrollback stays empty, so read history in the transcript view (ctrl+o; `[`
  prints it to real scrollback) rather than by scrolling the terminal.
  `/tui default` switches to the classic renderer and `/tui fullscreen` back;
  both save this key.
- **`outputStyle: "Concise"`**: response style for every session. **Set it
  here, not via `/config`** — see below.
- **`switchModelsOnFlag: false`**: don't silently switch models on capacity
  flags.
- **`enableAllProjectMcpServers: true`**: auto-enable every MCP server
  declared in any project's `.mcp.json`.
- **`enabledPlugins.*`**: which official plugins are active globally.
- **`effortLevel: "high"`**: default to high-effort reasoning.
- **`autoCompactWindow: 300000`**: auto-compact at ~300k tokens instead of
  the model's 1M (on 2.1.259 the threshold for a 300k window is 224,000
  tokens). Without it, every auto-compaction measured fired at about 1M —
  see the note below.
- **`ultracode: false`**: multi-agent workflow orchestration stays OFF — a
  Workflow runs only when the author asks for one in that turn (switched off
  2026-08-29 after an on-by-default ultracode turned a routine bug fix into
  a 14-agent review; when on it needs effort `xhigh` exactly — `max` makes
  it inert).
- **`autoMemoryEnabled: false`**: don't auto-write to long-term memory.
- **`skipDangerousModePermissionPrompt: true`**: suppress the warning when
  entering dangerous-mode.
- **`agentPushNotifEnabled: true`**: push notifications on agent completion.
- **`voiceEnabled: true`**: voice input support.
- **`cleanupPeriodDays: 3650`**: transcript retention. `--resume` reads
  these, so a short window silently deletes resumable history.
- **`verbose: true`**: show full command output rather than truncating it.
- **`fileCheckpointingEnabled: false`**: **disables** the automatic
  file-checkpoint safety net, so there is no built-in undo for an agent's
  edits. Deliberate — multiple agents share these worktrees and checkpoint
  restores clobber each other — but it means the git history is the only
  recovery path.

### `autoCompactWindow` — why it is set explicitly

Measured from the transcripts under `~/.claude/projects` (`compact_boundary`
records with `trigger: auto`, deduplicated by `uuid`; the model is taken from
the preceding assistant message, so `[1m]` variants count under their base
id):

- **Before the setting existed** (2026-08-13 to 2026-09-03 19:00 UTC): all
  71 auto-compactions across every session (Claude Code 2.1.223, 2.1.237 and
  2.1.246; 69 on `claude-opus-5`, 2 on `claude-fable-5`) fired at
  994,878–1,082,059 tokens — none more than 5,122 tokens below the 1M API
  limit —
  with `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` in every launcher.
- **After it** (the next 4.7 hours, all on 2.1.259): all 13 auto-compactions
  (7 on `claude-fable-5-1`, 5 on `claude-opus-5`, 1 on `claude-fable-5`)
  fired at 240,018–882,723 tokens. The spread is sessions that started before
  the change: a session keeps the window it resolved at startup unless
  `/autocompact` is run inside it.

Why the auto-resolved window never compacted in those older builds was not
pinned down; the setting removes the question by making the window explicit.

How 2.1.259 resolves it (from the binary): env
`CLAUDE_CODE_AUTO_COMPACT_WINDOW` → this setting → server client data →
experiment → model default → unknown model → `auto`, each capped at the
model's real maximum.
`/autocompact 300k` writes this key, `/autocompact auto` clears it, and
`claude --autocompact 300k` sets it for one session. A configured window
below 200,000 never passes the auto-compaction check. The threshold for a
300,000 window is 224,000 tokens: 300,000 − min(max output, 20,000) output
reserve = 280,000 (20,000 for these models),
then the smaller of 280,000 − 20% precompute buffer (224,000) and
280,000 − 13,000 summary buffer (267,000). The 20% fraction is a remotely
configurable default. The measured 240,018 floor above is consistent with a
224,000 threshold (`preTokens` is sampled after the turn that crossed it).

The old percent override was deleted from every launcher (`config.fish`,
`bashrc`, `claude-alias.sh`, `cc-relaunch.sh`, the bridge's `config.ts`)
because with a configured window it applies on top — `min(effective window
× 50%, effective window − 13k)`, i.e. min(140,000, 267,000) = 140,000 for a
300k window (effective 280,000).

⚠️ Two carry-overs. A session already running keeps whatever it resolved at
startup — the settings file is read once, at launch — so editing it applies
only to sessions started after the change; `/autocompact` inside a session
updates that session in place as well as writing the file.
And the remote-control bridge reads `~/.claude-remote/config.yaml` **once, at
boot**, then passes that env to every session it spawns — so until
`systemctl --user restart claude-remote.service`, bridge-spawned sessions
still carry the old override. That restart kills the bridge's child sessions,
so do it deliberately, not mid-task.

### `agents/` — per-agent model pins (Fable 5 orchestrates, Opus 5 executes)

Subagents default to the *parent's* model, so with `model: claude-fable-5-1[1m]`
every `general-purpose` / `Plan` call would also burn Fable 5. The files in
`agents/` are copies of the CLI's built-in agent definitions (system prompt
verbatim, same tool restrictions) with one change: `model: opus`.

How it works (verified on Claude Code 2.1.247 by reading the bundled
resolver): agent definitions are merged by name in the order
built-in → plugin → `~/.claude/agents/` → `<project>/.claude/agents/`, and
a later entry **replaces** an earlier one with the same name. So a
user-level `general-purpose.md` shadows the built-in `general-purpose`
wholesale — which is why the body must carry the original prompt, not just
the frontmatter.

| Agent | Where its model comes from | Result |
|---|---|---|
| `general-purpose` | `agents/general-purpose.md` | Opus 5 |
| `Plan` | `agents/Plan.md` | Opus 5 |
| `Explore` | built-in, Opus-capped¹ | Opus 5 (no file needed) |
| `fork` | always the parent | Fable 5 — intended |
| `claude` | built-in, inherits² | Fable 5 — intended |
| `claude-code-guide` | hard-pinned `haiku` in the CLI | untouched |
| `statusline-setup` | hard-pinned `sonnet` in the CLI | untouched |
| `agent-sdk-dev:*` | plugin frontmatter `model: sonnet` | untouched |
| `Workflow` `agent()` | per-call `model:` | pass `model: 'opus'` |

¹ `Explore` is capped to the newest Opus whenever the parent is above the Opus tier.
² `claude` is the FleetView *main* agent, i.e. an orchestrator.

Deliberately **not** `CLAUDE_CODE_SUBAGENT_MODEL`: that env var outranks
every per-agent setting (including the hard pins above *and* `fork`), so it
cannot express "Opus everywhere except fork".

Caveat: the copied prompts rot silently when a CLI release changes the
built-in ones. After a `claude update`, diff the body of each file against
the built-in (`strings ~/.local/share/claude/versions/<v> | grep -A40
'You are an agent for Claude Code'`) and refresh.

### `bin/claude-patch-sticky-header.py` — fullscreen "pinned prompt" header fix

Full write-up — exact bytes, Bun module-table layout, headless verification,
rollout — in [`sticky-header-patch.md`](sticky-header-patch.md).

In the fullscreen renderer, scrolling up used to pin your nearest earlier
prompt as a clickable header at row 1 (click → jump to it). 2.1.246 shows it;
2.1.247 onward never does: the header tracker got React-Compiler-memoized and
its `isSticky()` / `getScrollTop()` reads are cached against the scroll-handle
identity, which never changes, so it always believes the view is pinned at the
bottom. Reported upstream (feedback receipt
`<REDACTED>`).

The CLI is a Bun standalone binary that runs embedded JSC bytecode and never
validates the embedded JS text against it, so a source edit alone does nothing.
The script therefore, on a **copy** (`<version>-sticky`, never in place —
running sessions have the file mapped): (1) rewrites the three memo guards to
`if(!0 …)` at identical byte length, and (2) zeroes that one chunk's bytecode
pointer in Bun's module table so JSC parses the patched source for it.

```fish
~/.claude/bin/claude-patch-sticky-header.py            # patches the current binary
ln -sfn ~/.local/share/claude/versions/<v>-sticky ~/.local/bin/claude
```

Re-run after every CLI update: the updater re-links `~/.local/bin/claude` to
the new release. `--check` reports whether the pattern is still present; exit
2 with nothing written means the build was fixed upstream (or changed) —
verify by hand, don't force it. The installer's old-version cleanup keeps
whatever the symlink resolves to, so the `-sticky` copy is not garbage-collected.
Sessions already running keep the unpatched code until they are restarted —
`bin/cc-restart.sh cc-<id> …` (or `all`) restarts `cc-*` tmux sessions **in
place**: waits until the session is idle, keeps the pane alive across the exit
(`remain-on-exit`), SIGTERMs claude, respawns the pane with its original launch
command (`--session-id` → `--resume`) and verifies the new process runs the
binary `claude` resolves to. Attached terminals and the phone bridge (which
addresses sessions by tmux name) stay connected. Beware: tmux reports the
pane start command wrapped in literal quotes — the script strips them; passing
them through makes fish choke on `"env …"` as one unknown command. In-memory
`CronCreate` schedules do not survive any restart — check `/cron` first.

### `hooks/turn_recap.py` — a recap after every long turn

`hooks/turn_recap.py` mirrors `~/.claude/hooks/turn_recap.py`. It is a `Stop`
hook: after any turn longer than `CLAUDE_CODE_RECAP_TURN_SECONDS` (default
10, `"0"` disables it), Claude Code shows a gray "Stop says:" note under the
turn — one or two sentences, under 40 words: the goal and current task
(naming where the work moved, if it moved), then the next action. It is
written by a tool-less `claude -p --model sonnet` subprocess run on the
normal login (one small Sonnet call per long turn; Sonnet won a 5-of-6
blind test against Haiku), so it costs cents and needs no separate
credentials.

The context fed to the model has three sections, each capped so the whole
prompt stays under 20,000 chars: a session summary (the compaction
message, if the session resumed from one, up to 2500 chars); all real
user messages so far, one per line and truncated per-message, up to
9000 chars (over budget, it keeps the first 5 and last 15 with an
omission line, shrinking the per-message length until it fits); and
the last 5 user turns in full detail plus the final reply, up to
9000 chars, trimming the oldest turns first.

Install:

```fish
cp $PWD/hooks/turn_recap.py ~/.claude/hooks/
# plus the Stop hook entry above (already in settings.json — see the table)
```

Hooks are snapshotted at session start, so a running session keeps the old
hook until it is restarted — `bin/cc-restart.sh cc-<id> …` (or `all`)
restarts running `cc-*` tmux sessions in place (see above).

The renderer this note goes through only shows plain text: markdown and ANSI
escapes are stripped, and there is a hard cap of 20 lines / 4000 characters
(silently truncated beyond that).

Two safety details: `CLAUDE_CODE_RECAP_HOOK_RUNNING` is a recursion guard
(the `claude -p` subprocess is itself a Claude Code run that would otherwise
fire this same Stop hook), and every run appends one line to
`~/.claude/hooks/turn_recap.log` for diagnosis.

### `outputStyle` — set it in this file, not with `/config`

`/config` writes the picked style to `.claude/settings.local.json` **relative to
the session's cwd**, which is *project*-scoped, not user-scoped. Choosing
"Concise" from a session started in `~` therefore lands in
`~/.claude/settings.local.json` and applies only to sessions whose cwd is `~`.
Every other project silently keeps the default style.

Verified on Claude Code 2.1.237 by asking a headless session to name its own
style — `NONE` from `~/projects/notes-repo`, `Concise` from `~`, with the key only
in `~/.claude/settings.local.json`.

Putting `outputStyle` in `~/.claude/settings.json` (user scope) is what makes it
global. Note this file is *also* the project-scope file when cwd is `~`, but the
key applies at user scope regardless of where the session starts.

Why it matters here: this setting is now the whole mechanism. Three
`plain-language.py` hooks on `UserPromptSubmit`/`PostToolUse`/`Stop` used to
re-inject a "be concise" reminder and force a rewrite when the reply drifted;
they were removed once `outputStyle` was set globally, since the built-in style
does the same job in the system prompt at no per-tool-call cost. The
"write concisely" rule at the top of `CLAUDE.md` is the only other lever left,
so a project that silently falls back to the default style has nothing else
trimming preamble, plan narration and closing recaps.

### `env` block

- **`CONTEXT7_API_KEY`**: key for the Context7 MCP plugin. **Get your own
  from context7.com** and replace the placeholder before using.
- **`ENABLE_CLAUDEAI_MCP_SERVERS: "false"`**: don't auto-connect the
  claude.ai-hosted MCP servers.
- **`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION: "100000"`**: raise the
  per-session `WebSearch` cap from the default **200** to effectively
  unlimited.

#### Why the web-search cap is raised

The default is **200 `WebSearch` calls per session** and a long
research session really does hit it. It was hit while planning a drive:
a single session covering road-width audits over ~96 routes, diesel
prices across two countries and ferry timetables exhausted all 200, and
the tool then refuses with

```text
Web search was not performed: this session has used its web search
budget (200 of 200 WebSearch calls).
```

The failure mode is what makes this worth raising. It does **not** stop
work — it silently degrades it. Verification quietly becomes assertion,
which is exactly what the "verify exhaustively" rule exists to prevent.
Concretely, a pass's road width could no longer be checked against OSM,
and a ferry-bridge closure had to be reported as "commonly cited as"
rather than confirmed.

Notes:

- **`WebFetch` has its own path and is NOT affected.** With the search
  budget exhausted you can still fetch a known URL — you just can't
  *discover* one. That's the workaround when the cap does bite, and it
  is how those ferry timetables were recovered.
- **The counter is per session**, so a fresh session resets it to the
  default anyway. Raising it in `settings.json` is what makes the change
  stick across sessions.
- **It takes effect immediately — no restart needed.** Verified by
  running a `WebSearch` in the same session that had just refused one:
  it succeeded, and `env` confirmed the var present in the process.
- Prefer this `env` block over a shell export. It applies to every
  Claude Code session regardless of shell, and the author's shell is fish,
  where the equivalent would be `set -Ux
  CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION 100000`.

We intentionally do **not** set `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`.
That flag gates feature-flag evaluation, and Remote Control (plus other
flag-gated features) depend on it — so we **keep nonessential traffic enabled**.
Don't re-add the flag when syncing or bootstrapping; if you ever need to mute
telemetry, prefer a narrower opt-out that leaves feature-flag eval intact.

## Secrets note

This repo is **private** — keep real secrets out so it *could* be opened up.
`settings.json` ships the literal placeholder `REPLACE_WITH_YOUR_CONTEXT7_KEY`,
which the bootstrap `sed` replaces. `.mcp.json` needs no substitution: it uses
`${CONTEXT7_API_KEY}`, expanded from the `env` block at run time.

Something enforces this now. This paragraph used to say notes-repo ran "no
gitleaks scan", which was true and is not any more: the root `lefthook.yml`
declares two hooks, `claude-setup-snapshot` and `gitleaks-staged`. The latter
is `gitleaks protect --staged`, which reads the staged diff and nothing else —
59.6 ms clean, and it exits 1 on a planted credential rather than warning.

It runs on gitleaks' **default rules**, deliberately. `.gitignore:17` ignores
`gitleaks.toml` so a project-private deny-list can never be committed, but no
such file exists here, so there is nothing to pass via `--config`. Add one only
if the default rules start producing noise worth suppressing.

⚠️ That covers NEW secrets only. A staged-diff scan never opens **history**, so
any key committed before the hook existed is still in there. Before a private
repo is opened up, every such key must be **rotated** and **purged from
history** (e.g. `git filter-repo --replace-text`); no commit hook can do it,
and a full-history scan would simply fail on every push until the purge
happens. Track it as an issue rather than in a paragraph.

The root [`.gitignore`](../../../.gitignore) also excludes `__pycache__/`, OS
metadata, `.claude/settings.local.json`, `.env`, and TLS keys/certs.
