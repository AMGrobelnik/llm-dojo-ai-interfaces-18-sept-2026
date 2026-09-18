<!-- hook: workflow-agents-name-their-type -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_REPO
# Every `agent()` call in a tracked workflow script names its agent type — a bare call runs on the session model and bypasses the opus pin

The incident is in the global CLAUDE.md ("SUBAGENTS RUN ON OPUS, NEVER ON
THE SESSION MODEL"), measured 2026-08-28: a ~50-agent workflow ran on the
session model because every `agent()` call was bare. The pin
(`~/.claude/agents/{general-purpose,Plan}.md`, `model: opus`) binds only
when that agent TYPE is invoked; the Workflow tool's default subagent
inherits whatever the session runs. Nothing in the run announces which one
you got.

The directive fixes future SESSIONS. It does not fix the SCRIPTS: a
workflow template checked into a skill is the copy the next run starts
from. Measured 2026-09-03, the tree carried exactly one — `.claude/skills/
amg-handbook-forge/scripts/delta_gate.template.js` — with three bare
`agent()` calls (lines 62, 69, 112; two ideation arms and the judge panel),
i.e. the shape that produced the incident, still tracked. All three now
pass `agentType: 'general-purpose'`, and this rule keeps them that way.

Mechanism: `check.py` enumerates tracked `.js` under `.claude/` (plus
`.claude/workflows/**`) through git, finds each `agent(` call, balances its
parentheses with strings and comments skipped — prompt templates are full
of `(` — and requires `agentType:` or `model:` inside the call's argument
text. Exit 1 lists `path:line` per bare call. Whole-tree in both modes; the
population is small (1 file today) and the check is milliseconds.

Probes, both ways (2026-09-03, via the script itself pointed at a scratch
repo): `probe/hit.js` — one bare call whose prompt contains `(hi)` and a
`${name}` interpolation → reported at line 2, exit 1; `probe/miss.js` —
`agentType`, an explicit `model`, a differently-named function, and
`agent(` inside a comment → nothing reported, exit 0. Then the live tree
after the fix → exit 0, and the live tree with the fix reverted in a copy →
three lines reported.

Nearest existing rules: none names the Workflow tool. `rule-skills-declare-
what-exists` checks skill contracts, not the model a workflow's agents run
on. The pending `rule-no-actions-invocations` bans GitHub Actions calls in
scripts — same shape (a tracked script carrying a forbidden invocation),
different invocation.

Delete-check: delete when the Workflow tool's bare `agent()` binds to the
pinned agent type by default (an upstream change), or when no workflow
script is tracked in this repo.
