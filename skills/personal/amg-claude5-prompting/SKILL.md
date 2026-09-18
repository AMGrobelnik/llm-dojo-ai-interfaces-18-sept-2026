---
name: amg-claude5-prompting
description: "Captures how to prompt and drive the Claude 5 model family (Fable 5.1 orchestrator, Opus 5 / Sonnet 5 / Haiku 4.5 subagents) from lessons a research-monorepo orchestrator session learned the hard way: the model-and-effort ladder, handoff and report shape, CLAUDE.md/agent-definition token-audit heuristics, and concrete failure modes with the exact wording that fixed each. Use whenever a request asks to write or tune an orchestrator's CLAUDE.md or system prompt, write or fix a subagent definition file, pick a model or effort level for a task, draft a subagent handoff or report format, or diagnose why an agent stalled, over-asked, or under-delivered. Triggers: CLAUDE.md, effort level, model tier, orchestrator instructions, subagent definition, gen-sonnet/gen-opus/gen-haiku agent files, handoff prompt, agent stopped waiting on a monitor, task notification, prompting Claude 5 / Opus 5 / Sonnet 5 / Haiku 4.5 / Fable. NOT for: benchmarking or pricing models against each other (use amg-llm-bench), compressing an existing prompt file's character count (use amg-prompt-optim), or building a new skill's structure from scratch (use anthropic-skill-creator)."
---

# amg-claude5-prompting

Lessons from running a Fable 5.1 orchestrator over Opus 5 / Sonnet 5 /
Haiku 4.5 subagents for many hours in this repo, plus this repo's own
`~/.claude/CLAUDE.md` and `~/.claude/agents/gen-*.md`. Every claim below
is something that was observed, not a guess about how the models
"should" behave — use the incident to judge whether it applies to your
situation, don't just copy the wording blind.

## When to use

- Editing `~/.claude/CLAUDE.md`, a project `CLAUDE.md`, or any
  orchestrator system prompt.
- Writing or fixing a subagent definition (`~/.claude/agents/*.md`).
- Picking a model and effort level for a task, or writing the handoff.
- A subagent stalled, over-asked, under-delivered, or a wording change
  to an instruction file didn't change behavior.
- NOT for ranking models by published benchmarks (`amg-llm-bench`), for
  shrinking a prompt's character count with no behavior question
  (`amg-prompt-optim`), or for a skill's own structure (`anthropic-skill-creator`).

## Model and effort ladder

Model is the whole choice of capability; effort is the whole choice of
how hard that model thinks. Raise effort before raising the model.

| Tier | Use for |
|---|---|
| Haiku / Explore | mechanical, tightly scoped, easy to check |
| Sonnet | routine implementation, debugging, repo work |
| Opus | hard, ambiguous, high-risk, or after Sonnet failed |

Never Opus by default — only for genuinely hard/ambiguous/high-risk
work, or after a cheaper model failed *with evidence*. After an honest
empty result, escalating to a stronger model choosing its own angle is
the check that the search space is exhausted — reserve it for
high-risk work or when explicitly asked, not every empty result.

Front-end work (pages, UIs, charts, layouts, screenshot tooling) goes
one tier above the first guess: Haiku never, Sonnet only for a
mechanical one-screenshot tweak, Opus at high+ for any real layout,
chart, visual-design or review-page build. This category is
consistently underestimated by a naive first guess.

| Effort | Use for |
|---|---|
| low | short mechanical, explicit checklist; can skip thinking |
| medium | routine impl/debug; Sonnet 5 medium ≈ Sonnet 4.6 high |
| high | hard reasoning, multi-step debug; API default |
| xhigh | long, tool-heavy exploration or coding runs |
| max | frontier problems only; overthinks structured tasks |

`low` effort can under-scope multi-part work by skipping the thinking
that would have caught the second and third parts of the ask.

## Writing a handoff

A prompt that gets the right result on the first try states, in order:
objective, exact scope (what's in, what's out, what another agent
already owns), constraints, the acceptance check, and the output
format. Terse command-style prompts to a *fresh* agent (no shared
context) produce shallow, generic work — brief it like a colleague who
just walked in: what you're trying to accomplish, what you've already
ruled out, enough surrounding context to make judgment calls. A fork
inherits full context, so its prompt is a directive, not a briefing.

A report back states: result, changed files (absolute paths), how it
was verified, blockers, artifacts by path — never a log or diff dump;
the orchestrator's tokens are the scarce resource, not the subagent's.

## Writing a subagent definition

Every `gen-*.md` in this repo ends with the same paragraph, added after
one incident (below) exposed its absence:

> Run long commands in the foreground with a timeout (up to 600000 ms)
> or poll them in a foreground loop; never end your turn to wait for a
> background task, since every stop costs the orchestrator a turn.
> When a git hook fails, grep its log for the failing gate
> (`grep -E '🥊|exit status'`) before reading anything else.

Applied to all eleven `gen-{haiku,sonnet,opus}-*` files; the read-only
`Explore` agent was left alone since it never runs commands that could
background-stall. A third proposed fix — routing skill invocations
through the subagent that needs them rather than the orchestrator, so
the ~12k-token skill body doesn't ride along in every orchestrator
context window after each compaction — was identified but is a habit,
not a sentence that fits an agent definition file; apply it by
delegating the skill-shaped task instead of invoking the skill
yourself as orchestrator.

## Writing instruction files (CLAUDE.md audit heuristics)

A real token-inefficiency audit of this repo's own `CLAUDE.md` found
six paying rules, ranked biggest cost first: per-subagent worktrees for
every task including two-line fixes, routing every conflict-free merge
through a subagent, one commit per file group instead of per task,
mandatory escalation after any empty result, a 1-10 min safety cron,
and viewing every image yourself. Five became rule changes in one pass
(worktree-only-if-committing, orchestrator-runs-clean-merges,
one-commit-per-task, escalate-only-when-high-risk, 5-10 min cron
floor); the sixth (image viewing) was kept on request even though it
is the most expensive, because the author asked for it explicitly — not
every expensive rule is a bug.

Heuristics that held up under a real compression pass:

- **State each rule once.** A second phrasing of the same rule is pure
  cost.
- **Attach a "why" only where it blocks a tempting shortcut.** Kept:
  the `rm -rf` static-resolution reason, the shared-venv reason, the
  `low` skips-thinking / `max` overthinks calibration — each stops a
  plausible wrong move. Dropped: narrative justifications that only
  explain organizational intent ("so instructions and results pass
  through one layer") without blocking anything a reader would
  otherwise do.
- **Point at a mechanism instead of restating a procedure.** A script
  or hook name is cheaper than describing what it does.
- **Don't restate what a hook already enforces.**
- **Role-gate sections.** Split "every agent" from "orchestrator only"
  and state in the preamble which one to skip, keyed off something
  the reader already has (how their own system prompt introduces
  them) rather than a separate lookup.
- **Closed vocabularies compress.** Named effort levels
  (low/medium/high/xhigh/max) and named model tiers carry more per
  word than adjectives ("try harder", "a bigger model").
- **Wordiness is often shape, not redundant content.** One pass could
  not hit a stated 55-65% size target and said so rather than quietly
  missing it: at 1584 words, every remaining word was a rule, a
  number, a command, a path, or a mandated justification — nothing
  left to cut without dropping content. What actually shrank the file
  (1584 to 1404 words) was converting five-line run-on paragraphs
  (the model ladder, the effort ladder, worktree setup) into
  sub-bullet lists with one lead-in clause each, same information,
  fewer connective words.

## Failure modes observed, and the wording that fixed each

| Failure | Fix |
|---|---|
| stops to wait on a bg job | foreground timeout/poll sentence |
| reads whole hook log | grep gate marker first |
| turn ends on a question | "not an ending" rule |
| vague wording ignored | imperative + concrete alt |

**Subagents end their turn to "wait."** A fixer subagent (branch
`fix/notional-tokens`) fixing a two-line wire-format bug ended its turn
eight separate times with variants of "I'll wait for the monitor
notification rather than polling" — each stop fired a task
notification and cost the orchestrator a full turn to notice and
resume it, for a task that should have taken one. No subagent
definition told it otherwise. The fix was the one added sentence
above, not a longer explanation: tell it exactly what to do instead
(foreground with a timeout, or a foreground poll loop) rather than
only what not to do.

**Orchestrators end turns with a question, an offer, or "say the
word."** Across a long session this recurred constantly on legitimately
destructive or ambiguous calls (deleting a branch, tearing down a paid
deployment, pushing to a shared `main`) — those are correctly gated,
but the same phrasing crept into routine choices too. The fix layered
two rules: turns end only on genuinely destructive/irreversible actions
or on completion, plus "do not stop to ask about routine choices; pick
one, state the assumption in the final report, move to the next item."
Naming the exception (destructive/irreversible) kept the legitimate
"say the word" cases intact while killing the routine ones.

**Wording that reads as ambiguous gets reinterpreted, not followed.**
The author rejected "Make routine calls yourself" outright ("I don't like
this make routine calls yourself thing") because it read as "do the
work yourself" — directly contradicting the delegate-by-default rule
two bullets above it in the same file. Replacing it with "Do not stop
to ask about routine choices; pick one, state the assumption in the
final report, move to the next item" paired an imperative negative
with a concrete positive action, and the ambiguity was gone. Lesson:
an instruction that could be read two ways will be, and a short
imperative beats a compressed idiom every time token count is not the
only goal.

## Verification wording

A count is not verification: "24/24 shots" or "the file exists" was
flagged and rewritten because neither says the content is right.
Require content criteria instead — no loading skeleton, no error or
empty state, no clipped or overlapping labels, no wasted panel space,
sample data that actually exercises the view — and look at every
image or page yourself, before and after, every variant, rather than
trusting a subagent's textual summary of what it saw.

## Environment notes carried alongside these lessons

- In bypass-permissions mode, do file reads/edits through Bash (cat,
  sed, grep, heredocs); reserve the Read tool for images, since Bash
  cannot render them.
- A safety-net cron and every subagent stop are each a full
  orchestrator turn — keep cron intervals at 5-10 min (the longest
  interval that still catches a stall) and prefer a foreground wait
  with a timeout over a chain of short cron pokes.
