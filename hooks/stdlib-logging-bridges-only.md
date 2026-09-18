<!-- hook: stdlib-logging-bridges-only -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# In the five aii_* packages, stdlib logging appears only at the two framework bridge files — application logging is loguru

Re-measured 2026-09-10: **228** loguru-importing files (aii_lib 100,
aii_server 64, aii_pipeline 47, aii_runpod 17; `aii_launcher`, the fifth
package, imports it nowhere — 6 Python files, zero loguru and zero
`import logging`) against stdlib `logging` in exactly **two** aii_* files,
both legitimate framework seams:

| file | line | what it is |
|---|---|---|
| `dbos_app/__init__.py` | 35 | import for the bridge below |
| `dbos_app/__init__.py` | 535 | `_LoguruInterceptHandler` |
| `dbos_app/__init__.py` | 595 | function-local, for the filter |
| `dbos_app/__init__.py` | 597 | `_DropIntentionalCancel(Filter)` |
| `config/settings.py` | 613 | import for the bridge below |
| `config/settings.py` | 702 | `_DjangoHandler` |

`dbos_app`'s first import feeds the handler that forwards DBOS's stdlib
records into loguru; its second, function-local one feeds a `logging.Filter`
that drops one noisy record off the stdlib `dbos` logger — stdlib
manipulation rather than a bridge INTO loguru, on the same file.
`settings.py` is the Django LOGGING wiring. **Three import statements, two
files** — the count this README has always carried, re-verified today; only
the line citations had drifted (`:473` -> `:535`, `:533` -> `:595`,
`:535` -> `:597`, `:610` -> `:613`), which is what happens to a citation
against a file that keeps growing. The invariant holds today by discipline
only; a third stdlib import would silently fork the logging stack.

Both files are ALSO the carve-out the sibling `loguru-is-the-logger` derives
rather than lists: each subclasses a stdlib handler and imports loguru, which
is what that hook reads off the source instead of naming these paths. So the
two rules agree on the same two files without either one enumerating them.

Only the five packages named in the title are in scope, and `aii_accounts` is
not one of them: it is a console script declared at
`aii_lib/pyproject.toml:234` (its `[project.scripts]` table) pointing at
`aii_lib.claude_oauth.accounts_health:main`, so it owns no package tree of
its own. Its 38 modules live under `aii_lib` and are already counted in that
100 — 24 of them import loguru and none imports stdlib `logging`.

`claude_cred_manager` (5 stdlib files — adopt.py:72, relogin.py:43,
serve.py:19, slots.py:47, usage.py:35 — with `basicConfig` at serve.py:275) is
exempt by design: its pyproject deliberately excludes aii_lib and loguru to
keep the standalone service's closure minimal, and the pathspec below never
reaches it.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: cross-cutting)

Proposed command — **IMPLEMENTED 2026-09-07 as `$RULE_DIR/check.sh`**, invoked from
the frontmatter `command: bash $RULE_DIR/check.sh`. The one-liner it was promoted
with, kept for the record:

    rules-grep --tree '^(import logging$|from logging import)' -- 'aii_lib/**/*.py' 'aii_server/**/*.py' 'aii_pipeline/**/*.py' 'aii_launcher/**/*.py' 'aii_runpod/**/*.py' ':!aii_lib/src/aii_lib/dbos_app/__init__.py' ':!aii_server/config/settings.py' ':!**/tests/**'

**That ERE is narrower than the statement it enforces, and `$RULE_DIR/check.sh`
widens it.** `^(import logging$|from logging import)` misses `import logging as
log`, `import logging.config`, `from logging.handlers import …`, and any
INDENTED function-local import — and the last one is not hypothetical: the
excluded bridge file has exactly that shape at `dbos_app/__init__.py:595`, so
the `^` anchor was never once exercised against a real occurrence. An agent
verifying the statement catches all four, so the conversion is lossless only
with `'^[[:space:]]*(import|from) logging([.,[:space:]]|$)'`. Verified
2026-09-07: that pattern matches all three stdlib imports in the two bridge
files (`:35`, `:595`, `settings.py:613`) and nothing else in the five packages.
`':!**/tests/**'` is dropped — the statement carves out the two bridge files and
nothing else, and the sweep is clean without it. The failure text says what to
do instead: application logging is loguru.


Delete-check: Considered deleting the variation by converting claude_cred_manager to loguru
— rejected: that adds a dependency to a package whose minimal closure is a
documented decision (own deploy unit, outside the uv workspace). The two
bridge files cannot be deleted (DBOS and Django emit stdlib records). So the
dimension is pinned at its current exact boundary rather than collapsed.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Winner of the logging pair: names the exactly-two legitimate bridge
files and reasons the claude_cred_manager exemption. Cheap grep keeping a
second logging system from growing back.
- KEEP: Canonical of the loguru pair (absorbs rule-loguru-only-shared-src):
the two-bridge end-state is precise and grep-cheap, and a second logging
system regrowing is exactly the silent divergence the bridges exist to
prevent.
- KEEP: Survivor absorbing rule-loguru-only-shared-src: grep `import logging`
in the five aii_* packages, allowlist exactly the two bridge files.
Deterministic, loud, guards against a second logging system regrowing.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Counts CONFIRM exactly. Per-package `grep -rln 'from loguru\|import loguru'
--include='*.py'`: aii_lib 89, aii_server 54, aii_pipeline 39, aii_runpod 17 =
199, and aii_launcher 0. `grep -rn 'import logging'` across aii_lib/src,
aii_server, aii_pipeline/src, aii_runpod/src, aii_launcher/src returns exactly
3 hits in 2 files: dbos_app/__init__.py:35 and :533,
aii_server/config/settings.py:592. claude_cred_manager: 5 files (slots.py:34,
serve.py:19, adopt.py:72, relogin.py:43, usage.py:35) and `gre

Corrected statement of fact:
Every count holds; two line citations are off. _LoguruInterceptHandler is at
dbos_app/__init__.py:473 (import at :35), and claude_cred_manager's
basicConfig is serve.py:275. 'Both legitimate bridges' also undercounts the
file: dbos_app/__init__.py additionally subclasses logging.Filter at :534-537
to drop 'Asyncio task cancelled for workflow or step' records off the stdlib
'dbos' logger — stdlib-logging manipulation, not a bridge into loguru. The
two-file total is unaffected.

Re-checked 2026-09-10: every count in that verification still holds and
every line citation in it has moved again — `_LoguruInterceptHandler` is at
`:535`, the `logging.Filter` subclass at `:597`, `settings.py` at `:613`,
`slots.py` at `:47`; only `serve.py:275` has stayed put. **Read the table at
the top, not the citations below it**: this section is kept for the reasoning
it records, and its line numbers are historical by now. The check runs clean
on today's tree, exit **0**.
