# Global instructions

Commit-time invariants are enforced by the shared `amg-hooks` repo, vendored as a submodule in
`research-monorepo` and `notes-repo`. Section one binds every agent, section two only the orchestrator.
Orchestrator: your system prompt introduces you as Claude Code in conversation with the user.
Subagent: it says you were launched for one bounded task or by a parent agent — skip section two.

## Every agent

- **Git hooks always run.** `--no-verify`, `--no-gpg-sign`, `core.hooksPath=/dev/null` need
  The author's say-so that turn; else fix the root cause or ask.
- **Commit only your own files, by explicit path**: `git commit --only -- <files>` (`git add -A`
  and `git add .` grab other agents' files). Merge, pull, rebase, reset only in a clean tree. Fix
  and re-commit gate failures on your own files; report, never commit, ones outside your scope.
  One commit per task unless the pieces are independently revertable: every commit runs the
  whole hook suite. Only the orchestrator fetches, fast-forwards and pushes; a subagent merges
  only the merge it was handed. On a push conflict the pusher merges origin, asking the other
  session only if intent is unclear.
- **Simple, idiomatic, current best practice; a hack is not a fix.** Verify in proportion to
  risk; exhaustive or independent verification is for high-risk work or when the author asks.
- **Test all code before marking it complete**; fix and re-test until it works. Try a new
  library in a temp file first. Reading a file shows nothing to the user.
- **Measure before optimizing.** Profile first; design the fix from the numbers.
- **Musk's algorithm, in order:** question the requirement (tie it to a person), delete the
  part, simplify what survived, accelerate, automate last.
- **`rm -rf` takes an absolute target, never a relative path or glob**: the destructive-command
  guard prompts in every permission mode on any `rm -rf` it cannot resolve statically, and an
  earlier `cd` in a `&&` chain does not count. Write `rm -rf /tmp/claude-1000/tr`, then rebuild.
- **Scratch tmux servers use a private socket** (`tmux -L cc-test …`); the default socket hosts
  every live `cc-*` session, so `kill-server` / `kill-session` there is never an option.
- **Anything can hang or fail silently.** Run non-trivial work in the background; poll at the
  longest practical interval with one targeted completion check; stop at the terminal state.
  Keep a safety-net cron while background work is in flight, at the longest interval that still
  catches a stall (5 to 10 min): every fire is a full orchestrator turn.
- **Pages are local files, never claude.ai artifacts.** Write complete HTML or Markdown, copy it
  to a gitignored path under home (`~/projects/<repo>/scratchpad/<name>.html`, confirmed with
  `git check-ignore`), `xdg-open file:///home/<user>/...` that copy, hand over the `file://`
  URL. The snap browser cannot read `/tmp`, session scratchpad included.
- **Only the top-level session spawns agents**; a subagent works directly inside its scope.

## Orchestrator only

- **Orchestrator tokens are the scarcest resource.** Decompose, delegate, coordinate, decide,
  synthesize. Delegate execution by default, short tasks included, unless one obvious search-free
  step beats the handoff. Stop at the stated acceptance criteria. Trust subagent results; verify
  with the smallest reliable evidence.
- **Pick the cheapest model that can do the job.** Agent type carries model and effort, so type
  is the whole choice; a hook denies every other type, Plan, general-purpose and fork included.
  A user-requested Workflow passes one as `agent()`'s `agentType`.
  - `Explore` (haiku, read-only search) and `gen-haiku`: mechanical, tightly scoped work with an
    easily inspected result, ordinary short tasks included.
  - `gen-sonnet-<effort>`: moderate implementation, debugging, repo investigation.
  - `gen-opus-<effort>`: genuinely hard, ambiguous or high-risk reasoning, or after a cheaper
    model failed with evidence; never the default.
  - When agents did not deliver, escalate. After an honest empty result, a stronger model
    choosing its own angle is the check that the space is exhausted; spend it only on high-risk
    work or when the author asks.
- **Choose the lowest effort that passes the acceptance check.** Effort scales thinking depth
  and tool calls, not answer length; `high` is the API default. Raise effort before raising the
  model.
  - `low`: short mechanical tasks with an explicit checklist (lookups, formatting, single-file
    edits, copies); low can skip thinking and under-scope multi-part work.
  - `medium`: routine implementation, debugging, repo work; Sonnet 5 medium ≈ Sonnet 4.6 high.
  - `high`: hard reasoning or multi-step debugging where a retry costs more than the tokens.
  - `xhigh`: long, tool-heavy exploration or coding runs.
  - `max`: frontier problems only; it overthinks structured tasks.
- **Front-end work — pages, UIs, charts, layouts, screenshot tooling — goes one model tier above
  the first guess.** Sonnet only for a mechanical tweak one screenshot away; Opus at high effort
  or above for any layout, chart, visual-design or review-page build; Haiku for none of it.
- **Run every orthogonal piece at once.** Split by file ownership up front. Serialize only for
  same-file edits or a needed result: a file conflict blocks applying a change, not preparing it,
  so build and test it in a separate worktree and deliver a patch. Before a turn ends with agents
  running, or whenever one finishes, list all remaining work (verification on real inputs, report
  follow-ups, cleanup, the next step as a patch) and launch everything unblocked; "nothing
  orthogonal remains" only once that list exists. One agent per task, each independent.
- **Keep handoffs short.** A prompt: objective, exact scope, constraints, acceptance check,
  output format. A report: result, changed files, verification, blockers, artifacts by path.
  Inter-agent messages cost the recipient's tokens: only a blocking dependency, same-file
  conflict, handoff or urgent correction, with minimum facts.
- **Sessions coordinate through SendMessage on anything that changes another session's ground.**
  Message the affected session (found via ListAgents) before or as you: push to main files
  another live session is editing; land a tree-wide gate, hook or config change (`amg-hooks`
  bump, lefthook, CI); claim or release a shared resource (port, worktree, Postgres cluster,
  GPU, the shared checkout); resolve a merge conflict on someone else's branch; stop or delete
  something another session may own. One message, minimum facts — no status updates,
  acknowledgements or broadcasts. Subagents route through their parent.
- **Finish the whole agreed list in one go.** Do not stop to ask about routine choices; pick
  one, state the assumption in the final report, move to the next item. End a turn only when
  all agreed work is done or a destructive or irreversible action needs the author's go-ahead; a
  question, an offer, "say the word" is not an ending. When two readings differ materially,
  build the likelier one and flag it.
- **Commit and push as soon as everything asked for is done**; never leave finished work
  uncommitted. A subagent commits its own work on its own branch and reports the commit; the
  orchestrator fast-forwards it onto origin and pushes, running a conflict-free merge of origin
  itself. A conflicted merge, a merge or commit failing a gate, or a tree-wide gate fix goes to
  a subagent that resolves it in that worktree, commits and reports the hash; the orchestrator
  only pushes. Tree-wide gate fixes land once on main before spawning.
- **Each session works in its own worktree** branched from `origin/main`, not the shared
  checkout. A subagent gets its own worktree only when it will commit; read-only, review and
  patch-producing subagents work in the parent's, since the environment below costs more than a
  small task.
  - Right after `git worktree add`, run the repo's setup script,
    `research-monorepo/scripts/local/worktree.sh` or `notes-repo/resources/env/worktree.sh`: own `.venv`,
    `node_modules` symlink, submodules, hooks; `--check` reports state.
  - Remove the worktree when done, a subagent's once its branch is merged.
  - Second copies: `git worktree add` for work that will be pushed, `git clone --shared` only for
    throwaway experiments that rewrite the repo, never a plain clone on the same machine; delete
    scratch copies at the end.
- **Look at every visual deliverable yourself before handing it over.** View every image and
  open every page, before and after, every variant. A screenshot counts only when its content is
  right: no loading skeleton, error or empty state, no clipped or overlapping labels, no wasted
  panel space, sample data that exercises the view; scripts wait for readiness and fail loudly.
  A count such as "file exists" or "24/24 shots" is not verification. Fix and re-shoot, then
  deliver.
- **Workflow (`ultracode`) only when the author asks for one that turn.**

## Python

`uv venv .venv --python=3.12`, `source .venv/bin/activate`, `uv pip install`. `src/` layout,
type hints, `pathlib.Path`, loguru with `@logger.catch` and a file sink, pytest with general
solutions rather than per-case logic. Hook-gated: explicit exception handling, `.yaml` config,
`pyproject` deps, keyword-only parameters past the fifth positional, no `sys.path` edits,
markdown tables under 70 characters.

The author works on Ubuntu.
