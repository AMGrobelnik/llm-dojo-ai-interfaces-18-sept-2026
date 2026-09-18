<!-- hook: loguru-is-the-logger -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Logging is loguru with the house format — `import logging` is not the logger here

House rule. The global CLAUDE.md's Python section prescribes "loguru with
`@logger.catch` and a file sink"; `@retry` on the flaky call is the same
stack's habit, not part of that line. The stdlib module needs a handler, a
formatter and a level set per module before it prints anything, and a script
that skips that setup logs into silence — which is the same failure
`rule-no-silent-except` exists to stop.

The house format, as the code that already uses it spells it — the five
modules under `archive/car-wallpapers/` carry these two lines exactly, and
`apps/notion/export.py:53-56` the same format string bound to a `LOG_FORMAT`
constant. Copy it rather than inventing a variant, so every script's output
lines up:

    GREEN,CYAN,END = "\033[92m","\033[96m","\033[0m"
    format=f"{GREEN}{{time:HH:mm:ss}}{END}|{{level:<7}}|{CYAN}{{function}}{END}| {{message}}"

with `@retry` on the flaky call, `@logger.catch` on the entry point (or
`logger.exception()` inside the handler), and a file sink so a background
run leaves a readable trace.

FAIL evidence: the added `import logging` / `from logging import` line the
grep prints.

Fix when blocked: `from loguru import logger`, add the sink with the format
above, and delete the stdlib setup. The one honest exception is code that
must hand a stdlib `Logger` to a third-party library that demands one —
route it through loguru's `InterceptHandler` rather than logging twice.

## The bridge carve-out

**That remedy used to trip the rule, which is why the rule now reads the
file.** Writing an `InterceptHandler` REQUIRES `import logging`, so the
module that owns the seam was reported for doing exactly what the paragraph
above tells a blocked author to do. Measured in research-monorepo on 2026-09-10:
3 of 8 findings were those modules —
`aii_lib/src/aii_lib/dbos_app/__init__.py` (`:35` feeding
`_LoguruInterceptHandler` at `:535`, and a function-local `:595` feeding a
`logging.Filter` on the third-party `dbos` logger) and
`aii_server/config/settings.py` (`:613`, `_DjangoHandler` at `:702`).
Permanent debt for complying.

`check.py` runs the same grep — it shells out to `rules-grep`, so both lanes are
unchanged — and then subtracts the hits in files whose own source says they
are the bridge:

| the file | verdict |
|---|---|
| subclasses a handler AND imports loguru | not reported |
| subclasses a handler, no loguru | reported |
| imports loguru, no handler subclass | reported |
| a comment claiming to be a bridge | reported |

**That subtraction only happens in the WHOLE-INDEX lane, so the first row is
unreachable at commit.** `check.py` takes each hit's path as the text before
the first `:`. Under `--tree` or `AMG_HOOKS_SWEEP=1` — which is how
`test_loguru_is_the_logger_bites.py` drives it — `rules-grep` prints
`path:line:text` and that read is right. The DEFAULT commit lane greps the
staged DIFF through `grep -nE`, so a hit reads `line:text`: the path is a
number, `is_loguru_bridge`'s `read_text` raises `OSError`, and its "unreadable:
judge it, do not excuse it" arm returns False. Nothing is ever subtracted at
commit, and a bridge module's own added line is reported like any other. This
is recorded rather than repaired here — the `dispatch.py` port judges paths
instead of grep output, and it carries the right behaviour into the cutover.

Both halves are required. A handler that does not reach loguru is a second
logging stack, which is the thing being banned; a module that merely imports
loguru next to some stdlib logging is the ordinary violation. And the
carve-out is deliberately NOT a marker comment: a marker is a silencer any
author can type, where a class definition is work the runtime checks. The
last row of that table is a test.

The unit is the FILE, not the line — a bridge module owns the seam, so its
stdlib manipulation belongs to it, which is how `dbos_app`'s function-local
import at `:595` is covered by the class at `:535`.

`test_loguru_is_the_logger_bites.py` pins all six shapes plus the pathspec, and
it drives the checker with `AMG_HOOKS_SWEEP=1` — the whole-index lane, the only one
where the carve-out can fire. Against the bare grep the two bridge fixtures
report `lib/dbos_app.py:4` and `:15`, exit 1; against `check.py`, exit 0.

Mode: ADDED LINES, and the pattern and pathspec now live in `check.py`
beside the exemption they belong with. In research-monorepo the whole-index stock
went **8 -> 5** on 2026-09-10, the five survivors all in
`claude_cred_manager` (`adopt.py:72`, `relogin.py:43`, `serve.py:19`,
`slots.py:47`, `usage.py:35`) — a package whose pyproject deliberately
excludes loguru to keep a standalone service's closure minimal, so those are
a real decision to revisit rather than an oversight.

In notes-repo, measured 2026-09-07: **6 occurrences in 6 files in
scope** (`apps/gmail/pull_attachments.py`, and `derive.py` / `pull.py` /
`readmes.py` / `sort_drive.py` / `timeline.py` under
`apps/google-takeout/`), 44 occurrences in 44 files tree-wide before the
exclusions. Six is small
enough to convert in one sitting; do that and flip this rule to
`rules-grep --tree`.

Delete-check: deletable by dropping loguru from the house stack — an owner
call. Until then two logging systems in one repo is the thing being deleted.
