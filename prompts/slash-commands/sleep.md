---
description: Autonomous overnight/away build — keep working the agreed task to completion under a recurring safety-net cron, treating each fire as the author asking in person. Stop only when truly nothing is left.
---

**The author is going to sleep (or stepping away). Keep working the task we just agreed on, autonomously, to completion.** This command is task-agnostic — the *what* is whatever we settled on in this conversation; the *how* is everything below.

## Set up the safety-net cron FIRST (before doing any of the work)

Create a **recurring** cron via `CronCreate` (NOT `ScheduleWakeup` — that is one-shot and silently breaks the cadence). Verify with `CronList`.

- **Interval by how fast the work changes:** ~1–2 min for fast-moving edit/test loops, up to ~10 min for slow multi-hour jobs (builds, training, long runs). Default `*/5 * * * *` when unsure.
- The cron runs **IN ADDITION** to any event watchers (Monitor, background-task notifications, SSH streams) — those can silently die or miss the event, so the cron is the independent backstop.
- **Only ever `CronDelete` it when the work is TRULY done** — i.e. if the author asked "anything left?" in person you'd answer "no, nothing" with full conviction. Otherwise keep it running and keep working.

### Cron prompt template (fill in the agreed deliverables, keep the protocol verbatim)

> SAFETY-NET (autonomous build for the author, who is away). Treat this fire as the author asking in person — do NOT stop until everything below is truly DONE. For each item: re-verify it ACTUALLY advanced (not just that a process/file exists), fix/resume anything broken (everything should be checkpoint/resumable), keep fixes synced EVERYWHERE they live (remote host AND local repo). Background all long commands + poll their logs. Maintain the task list.
> Deliverables: <1..N concrete, verifiable items — each with its own done-check, e.g. "tests green", "bash -n / shellcheck clean", "build rc=0 sentinel in <log>", "run progressed past substep X">.
> Constraints: do NOT git commit/push unless the author asks. Do NOT bypass git hooks (no `--no-verify` / `--no-gpg-sign` / hooksPath). Apply root-cause fixes only — no `# noqa` / `# type: ignore` / allowlist silencing. No secret VALUES in logs (first 8 chars + length OK). Do NOT run destructive working-tree git commands. Do NOT touch unrelated live runs/pods/other agents' WIP.
> Only `CronDelete` this job when ALL deliverables are verified complete AND nothing is left for me to do.

## On every fire (including the first)

1. **Re-verify real progress** — confirm each deliverable actually moved forward (read the log tail, re-run the test, diff the file), not merely that a process is alive or a file exists.
2. **Fix or resume anything broken** — crashes, hung jobs, failed builds. Everything should be checkpoint/resumable; resume from the last good point, don't restart from scratch.
3. **Keep fixes synced everywhere** — if the same fix lives in more than one place (remote host + local repo, multiple services), apply it in all of them.
4. **Background + poll** — assume any task/script/command can hang or fail silently. Run anything non-trivial in the background (`Bash run_in_background: true`, `Agent run_in_background: true`, or `&` + log redirect) and poll/Monitor; never block the main thread on an opaque foreground call.
5. **Advance the next item** — once everything verified is still healthy, pick up the next highest-priority unfinished piece and push it forward.

## Standing constraints (apply the whole time)

- **Quality bar:** modern best-practice, clean/idiomatic; simplicity and minimal complexity; ultrathink before nontrivial changes; exhaustive verification (run tests, check edge cases, cross-confirm) — ship verified work, never plausible-looking work.
- **Root-cause only:** no `# noqa`, `# type: ignore`, `--no-verify`, allowlist/`_typos.toml` patches, or hook excludes to silence a warning — fix the underlying smell. Allowlist entries are last-resort, only for genuine false positives / real domain terms.
- **Git safety:** commit/push only when the author explicitly asks. Never bypass git hooks. Never run destructive working-tree git commands (`git stash` any form, `git checkout/restore <file>`, `git reset --hard`, `git clean -fd`) — other agents may be working concurrently. To undo your own edit, write the prior content back with Edit.
- **Secrets:** never print full secret values (first 8 chars + length is fine).
- **Scope:** don't touch unrelated live runs, pods, or other agents' uncommitted work.
- **Task list:** keep `TaskCreate`/`TaskUpdate` current so progress is legible on resume.

## Stopping

Keep the cron running until every deliverable is verified done and there is genuinely nothing left to do. When that's true, `CronDelete` the job and leave a short summary of what landed and how it was verified. Until then, each fire = the author talking to you; keep going.
