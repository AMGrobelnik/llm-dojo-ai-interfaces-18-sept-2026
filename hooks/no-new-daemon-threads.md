<!-- hook: no-new-daemon-threads -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# aii_server gains no new threading.Thread call sites

Measured: 14 daemon-thread starts already run inside the single-worker web
process, three of them copy-pasted reconciler scaffolds with a double-start
race in two, while DBOS's installed scheduler listens to zero queues. The
migration (audit R10) is an open owner decision; this rule stops the
pattern growing while it is decided.

(Measured 2026-08-22 at 14; previously recorded as 17 — that figure counted
every `.start()` line in aii_server, still 17 today, three of which start
the ability-server's `multiprocessing.Process` workers rather than threads.)

At commit this flags ADDED `threading.Thread` lines in aii_server — ANY
thread, daemon or not, web process or ability worker; the motivating census
below is narrower (daemon loops in the web process), the gate is not. A
genuinely necessary new thread (a process-local cache warmup) is what the
waiver is for — waive with the justification, which documents the
exception in history.

Fix when blocked: `aii_server._bg_thread.run_in_background` — the single
door every background thread in `aii_server` now starts through — for a
genuinely necessary new thread; `@DBOS.scheduled` for recurring work; a
queue workflow for one-shots; the existing sweeper/reaper modules as
references for what NOT to copy.

Delete-check: mostly deletable upstream — the scheduler migration removes
the reason threads exist; this rule is the interim ratchet.

Stock (2026-08-22): 18 whole-tree hits across 8 server modules — a real
design backlog (each needs its own offload decision), not flippable.

RE-MEASURED 2026-08-24 — **in the right range; the exact figure depends
on a scoping this body references but does not spell out.**

Counting `daemon=True` across `aii_server` gives **15** occurrences, of
which **13** have a `Thread(` within three lines above. The stated figure
is 14, for starts "inside the single-worker web process" — a narrower
population than "anywhere under `aii_server`", since
`agent_abilities/worker.py` and parts of `credentials.py` run in ability
worker processes rather than the web process.

So 13/15 unscoped brackets the scoped 14, and nothing here suggests the
count has moved. What would make it re-checkable without this reasoning
is naming the process boundary — the body already shows the author cared
about exactly that, since it records a prior correction from 17 to 14
where the larger figure "counted" the wrong population.

## 2026-09-15 — the AST port dropped the ratchet; `debt.txt` restores it

The AST port onto the one-pass dispatcher (`dispatch.py`) kept the whole-tree
scan but not the waiver: it flags every `threading.Thread` site the population
holds, unconditionally, on every commit — including the 18-hit stock above.
That is a hard block, not "this rule stops the pattern growing while it is
decided". A `debt.txt` beside `dispatch.py`, mirroring the shrinking-debt
mechanism `server-yaml-closed-schema` already uses (`_read_debt`, `_rule_dir`),
restores the ratchet: a module keyed in the list is silenced up to a pinned
site COUNT (not just presence, so a listed module cannot grow new threads
unnoticed), an unlisted module still blocks, and an entry pinned above a
module's real count blocks too, as stale, so the list can only shrink.

Measured 2026-09-15 against `aii_server/*.py` in the real tree: 9
`threading.Thread` sites across 6 modules, all 9 pinned. Checked against the
README's own prescribed fixes (`@DBOS.scheduled`, a queue workflow) and found
that neither can serve any of the 9 — each is exactly the case the waiver
sentence above names, "a process-local cache warmup":

| module | n | why not DBOS |
|---|---|---|
| `dashboard/apps.py` | 2 | pre-`init_dbos()`; own-process warmup |
| `.../_compute_catalogue.py` | 1 | pre-`init_dbos()` |
| `.../_openrouter_catalog.py` | 1 | pre-`init_dbos()` |
| `.../_roster/_cache.py` | 1 | pre-`init_dbos()` |
| `agent_abilities/credentials.py` | 2 | cache warmup + poll loop |
| `aii_server.py` | 2 | CLI process; is the ASGI server |

The first four start inside `DashboardConfig.ready()` *before* `init_dbos()`
runs later in that same `ready()` — DBOS is not launched yet at the point
these threads start, so a DBOS workflow is structurally impossible there.
`apps.py:130-134` already carries the owner's own reasoning for why it stays a
thread even once DBOS exists: it warms *this process's* memory, while a
scheduled task would warm whichever executor happened to win the tick.
`credentials.py`'s two threads are request-time credential/usage cache
warmup and a tmux-scraping poll loop gated by a stop `Event` — process-local
state again. `aii_server.py`'s two run in the CLI/launcher `__main__`
process; the second *is* the ASGI server (`uvicorn.run(...)` inside a
thread), which no workflow can replace.

The list shrinks one line at a time as each site moves onto the scheduler
migration the delete-check above already names; it is empty exactly when that
migration is done.

## 2026-09-16 — every pinned site closed through the single door; `debt.txt` is empty

All 9 sites pinned above moved onto `aii_server._bg_thread.run_in_background`,
the one function every background thread in `aii_server` now starts through
instead of calling `threading.Thread` directly. `debt.txt` lists no modules
any more: the ratchet has fully shrunk, not been turned off, so a bare
`threading.Thread(...)` call site anywhere in `aii_server` blocks the commit
again, exactly as it did before the first waiver was ever pinned.
