---
description: Self-paced 1-minute loop — keep working on the highest-priority item, max quality, stop the cron when genuinely blocked on user input
---

/loop 1m

**Schedule via `CronCreate` with `*/1 * * * *` (recurring) — NOT `ScheduleWakeup` (one-shot, silently breaks 1m cadence). `CronList` to verify on resume.**

ULTRATHINK and APPLY MAXIMUM QUALITY BAR for the rest of this conversation:

- **Modern best practice by default.** For every decision (code, architecture, tooling, naming, structure), ask first: "what is the MOST COMMON MODERN BEST-PRACTICE — clean, elegant, idiomatic — way?" Pick that, not the first thing that came to mind.
- **Exhaustive verification.** For every claim, fix, and piece of code: run tests, search the codebase, check edge cases, cross-confirm via multiple independent methods. Ship verified work, never plausible-looking work.
- **Ultrathink before acting.** For nontrivial tasks, think very hard about the plan, edge cases, and trade-offs before writing code. State the plan in one short paragraph, then implement.
- **Root-cause only.** No `# noqa`, no `# type: ignore`, no `--no-verify`, no `_typos.toml` / allowlist patches, no hook excludes. Fix the underlying smell.
- **Simplicity & minimal complexity.** No hacky quick fixes. No premature abstractions. No half-finished implementations. The simplest thing that correctly solves the problem.
- **No backwards compatibility or legacy cruft.** Unless the user explicitly asks for it, don't keep deprecated APIs, fallback paths, shims, renamed re-exports, or `// removed` comments — delete unused code outright.
- **Musk's Algorithm per tick — in this exact order.** Before adding code: (1) make the requirement less dumb — is it actually needed, tied to a specific person?, (2) delete the part / process — try to remove it entirely, expect to add ~10% back, (3) simplify what survives, (4) accelerate cycle time, (5) automate last. Never optimize or automate something that should have been deleted. See the global CLAUDE.md `!!!` bang for the canonical statement.
- **Substance over polish.** Each cron tick lands a bug fix, real refactor, dead-code deletion, or verification run. Bundle docstring fixes into their underlying code change — no standalone `docs:` commits. If the obvious deletions are done, pick the next architectural step or report "no substantial work this iteration — paused"; do NOT chain docstring sweeps to look productive.
- **Don't rush commits.** A tick doesn't need to end in a commit. Large refactors that span many files / can break things should stay uncommitted across many ticks until the whole change is verified — investigation, partial work, planning, and audits are all valid tick outcomes. Better to land one carefully-staged commit than three half-baked ones.
- **Highest priority only — never fillers.** Each tick: identify the single highest-priority pending item (real architectural work, bug fix, or production-affecting refactor), and work on THAT. Do NOT fall back to mechanical lower-priority cleanup (formatting, allowlist hygiene, dead-method audits past the obvious ones, more docstring polish) as filler when the top item is hard. If the top item genuinely requires user input — a design decision you can't make alone, validation that needs the user's environment / creds, or a scope clarification — STOP and ask in the response, then PAUSE the loop ("paused — needs user input on X"). Do not keep ticking on lower priorities to look busy.
