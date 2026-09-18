---
description: Raise the quality bar — modern best practices, exhaustive verification, deep thinking, root-cause fixes
---

**Maximum quality bar — apply for the rest of this conversation.**

- **Modern best practice by default.** For every decision (code, architecture, tooling, naming, structure), ask first: "what is the MOST COMMON MODERN BEST-PRACTICE — clean, elegant, idiomatic — way?" Pick that, not the first thing that came to mind.
- **Exhaustive verification.** For every claim, fix, and piece of code: run tests, search the codebase, check edge cases, cross-confirm via multiple independent methods. Ship verified work, never plausible-looking work.
- **Ultrathink before acting.** For nontrivial tasks, think very hard about the plan, edge cases, and trade-offs before writing code. State the plan in one short paragraph, then implement.
- **Root-cause only.** No `# noqa`, no `# type: ignore`, no `--no-verify`, no `_typos.toml` / allowlist patches, no hook excludes. Fix the underlying smell.
- **Simplicity & minimal complexity.** No hacky quick fixes. No premature abstractions. No half-finished implementations. The simplest thing that correctly solves the problem.
