# All Tips (Concise) — DRAFT

Tips for engineers/researchers working WITH AI agents, learned building
research-monorepo and the workflows around it. One tip ≈ one slide: a headline
plus the supporting details worth mentioning.

> **This file is the source; `agentic_coding_tips.pptx` beside it is a hand-built
> deck with no generator, so corrections here do NOT reach the slides.**
> Tips 3 and 13 were corrected on 2026-08-20 after being checked against the
> config they describe — the deck still carries the old numbers. Re-check
> against `../settings.json` and `../precommit-hooks/lefthook.yml` before
> presenting, and treat any measured figure in the deck as needing
> re-measurement rather than quotation.

---

## Setup

**1. Run agents in a VM and bypass permissions.**
Full autonomy is safe inside a disposable VM — the agent never stops to ask,
worst case you roll back. No VM? Use auto-accept-edits mode instead.

**2. Parallel terminal windows, one agent each — spatial memory is real.**
Tile sessions at fixed screen positions: monitor everything at a glance, and
each location mentally binds to its conversation, making context switches
between agents far cheaper.

**3. Tune your defaults once, in config.**
Pin the model + max effort (no silent model swaps), bake it into a shell
alias; one curated CLAUDE.md beats auto-memory. Multi-agent orchestration
(ultracode) is **off** here since 2026-08-29 — on by default it turned a
routine bug fix into a 14-agent review; a Workflow runs only when asked.
(If ever re-enabled it needs effort `xhigh` *exactly*, because `max` makes
it inert — a setting that reads as enabled and quietly does nothing.)

## Prompting

**4. Musk's Algorithm for every nontrivial change, in order.**
Question the requirement → delete the part → simplify → accelerate →
automate. Agents love to optimize and automate things that should have been
deleted.

**5. Make the agent ask: "what's the most common modern best-practice way?"**
Default to that — clean, elegant, idiomatic — plus minimal complexity: no
hacky quick fixes, no premature abstractions.

**6. Demand verified work, not plausible work.**
"Verify exhaustively before claiming done: run tests, check edge cases,
cross-confirm with independent methods." Agents ship plausible-looking
output by default.

**6b. Raise the tool budgets that silently cap verification.**
Claude Code allows **200 `WebSearch` calls per session** by default. A long
research session hits it, and the failure is quiet: the agent doesn't stop,
it just stops *checking* — verification degrades into assertion, undoing
tip 6. Raise it in `~/.claude/settings.json`:
`"env": {"CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION": "100000"}`. Takes
effect immediately, no restart. `WebFetch` is a separate path and is never
capped, so a known URL still works when search is exhausted — you only lose
the ability to *discover* URLs. Generally: when an agent starts hedging
("commonly cited as…") instead of confirming, suspect a spent budget
before you suspect the model.

**7. Power keywords: "meticulous", "exhaustive", "ultrathink".**
A few words reliably shift agent behavior: "meticulous" and "exhaustive"
raise the care and coverage bar; "ultrathink" literally triggers maximum
reasoning depth in Claude Code. Cheap to type, large effect.

**8. Lazy prompting is the default — typos and all.**
Don't polish prompts: short, misspelled prompts work just as well in most
cases and you move much faster. Only when the agent clearly misunderstood,
re-prompt with more information (spelling mistakes still fine).

**9. Test the limits of every new model.**
When a new model lands, probe until you find clearly-defined tasks it
*cannot* solve — that boundary tells you what you can safely delegate and
where you still need to supervise or decompose.

## Autonomy

**10. Multitask a single agent — just keep typing.**
You don't need subagents to multitask: send the next task while the agent
is mid-task (as long as the current one isn't huge) and a good agent queues
it and picks it up when the current task — or its current step — ends. One
conversation, several tasks in flight.

**11. Make the agent supervise itself: loops + safety-net crons.**
End prompts for ongoing work with `/loop 1m` or "set up a recurring
monitor". Each fire verifies *real progress* (logs, diffs, tests — not "a
process exists") and fixes what broke. Crons run in addition to event
watchers, which silently die. Pausing when blocked beats filler busywork.

**12. Background everything, checkpoint everything.**
Anything >30 s runs in the background with log polling — a hung foreground
call blocks the agent forever. And every long job must resume from its last
checkpoint, or overnight autonomy is a lottery.

## Code with agents

**13. Pre-commit hooks built for agent-speed commits.**
lefthook over pre-commit (no stash dance racing concurrent agents), native
binaries and parallel hooks, and secret scanning whose patterns match the
providers you actually use (`sk-` doesn't catch `sk-or-` or `hf_`).
Measured on the 43-hook stack (35 of them pre-commit) over a 246-file
commit: **17.9 s wall clock, of which one hook was 17.9 s.** That is the
whole argument for running them in parallel — the total is the slowest
hook, not the sum, so 43 hooks cost what the worst one costs. Keep the
slow one honest and the stack stays cheap.

**14. Git discipline when multiple agents share a repo.**
Ban destructive working-tree git (stash, reset --hard, restore, clean) —
another agent's uncommitted work has no recovery; "undo" = write the prior
content back. Stage files by name, never `git add -A`.

**15. Skip worktrees — run parallel agents on the same checkout.**
Worktrees mean rebasing/merging every agent's branch back together. Instead
run all agents on one repo and prompt them to stay out of each other's
files — no merge overhead, and the hooks/git discipline below make it safe.

**16. Give the agent a real verification surface.**
Storybook + vitest browser mode lets it verify UI without auth or dashboard
driving; E2E runs against the real dev server, not mocks; new libraries get
probed in a temp script first (agents hallucinate APIs). And audit for
silently-skipped tests — a green suite once hid 9 of 11 test files skipping
at module level for months.

**17. Review agent code with adversarial, multi-lens audits.**
Findings only ship if a second agent instructed to *refute* them fails
(20 of 57 died that way). Use several lenses (per-subsystem, logic,
cross-subsystem). Biggest decay mode: migration residue — budget a cleanup
pass after every big agent-driven change.

## LLM reliability

**18. Never trust an LLM judge you haven't sanity-checked.**
Check extensively first: self-consistency on repeated identical
comparisons (23–42% for budget models), position bias (66–69% first-option
preference — always shuffle A/B), tier ≠ quality (Sonnet beat Opus), and
only the extremes rank reliably. Counterintuitive: more reasoning effort
made judging *worse* — use low effort + more independent judges. Prefer
pairwise tournaments over "is this good?" rating loops.

**19. Retry by re-prompting with the exact failure.**
Not "try again" — feed back the missing field, the keys that did appear,
the file that wasn't written; converges in 1–2 rounds. Validate reality,
not just schema (files the model claims to have written must exist), and
surface every retry to the human — silent retry loops look like hangs.

## Skills

**20. Everything should be a skill.**
Skills are a strict superset of MCP servers, prompt files, and one-off
scripts — markdown + optional scripts the agent reads on demand. Almost
nothing needs an MCP server; a skill is easier to set up, version, and
transfer between machines, projects, and even different agent harnesses.

**21. The description is the trigger.**
Say exactly when to use the skill — what it does plus the exact
phrases/situations people type; the most common failure is a skill that
never triggers. Make skills run with and without their backing
infrastructure, and emit full/mini/preview output variants so the agent
reads a preview while code reads the full data.

## Research outputs

**22. Presentation craft.**
Anchor abstractions in spatial before/after visuals; three concrete
examples for any generality claim; motivate as What / Why / Why-Now.

**23. Human-in-the-loop image generation that scales.**
Folder hierarchy figure/batch/variant with a prompt + log file per image —
the human arrow-flips one batch in a viewer, every image traces to its
prompt, batch letters never reused. Fire batches in parallel and retry only
failures. Explore at 1K, re-render only winners at 4K.

**24. Figures-as-code with exact-number specs.**
For data figures, LLMs write plotting code from specs carrying the real
numbers ("K=3 (0.765)", never "compare metrics") — auditable and revisable.
Reserve diffusion-style generation for illustrative art.

**25. Papers with agents.**
Critic-in-the-loop (separate reviewer pass → revise) beats single-shot;
contribution explicit by page 2–3; BibTeX batch-fetched from Semantic
Scholar by DOI/ArXiv ID — never from LLM memory; and LaTeX compiles as four
separate commands (pdflatex exits non-zero on warnings, so `&&`-chaining
skips bibtex and leaves `??` citations).
