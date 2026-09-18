# Importing the staged root conftest under a hook-shaped environment leaves the process hermetic: no GIT_* survives and every module-scope setdefault pin holds

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 1s | active |

`tree` here means one file that has to be EXECUTED. There is no changed-lines
relation for a behavioural probe: the subject is `conftest.py` as a whole, and
the only way to know what importing it does is to import it. The glob keeps the
command off commits that touch neither `conftest.py` nor `tests/`.

## Why

git exports `GIT_DIR` and `GIT_INDEX_FILE` into every hook process, and for a
pathspec commit it points them at a temporary index. The rule engine runs the
test suite inside the commit-msg hook, so on 2026-08-22 a test subprocess
inherited both and operated on the parent repo instead of the throwaway one it
had just built: it committed a test's scratch index onto `main` as `init` by
`t <t@t>`, and the same inheritance had twelve rule-tree modules red inside the
hook while green standalone (a tmp-repo `git add` exits 128 against the locked
temporary index; `git ls-files` answers from the wrong index).

The fix was one unguarded `for` loop at module scope in `conftest.py` that
deletes every `GIT_*` key at import. Beside it sit `os.environ.setdefault`
pins that keep the unit suite off real daemons and paid providers —
`CRED_MANAGER_ENABLED=0` after a developer box reached the live credential
manager on `127.0.0.1:8021` mid-test and nine tests failed only there, and
`AII_WEB_APP_MODE=1` because CI has no private overlay and every
`dashboard.models` import raises without it. Nothing proved either still
worked, and a grep for the loop proves nothing about behaviour: the loop can
be present and still run after something that has already read `GIT_*`.

An earlier reading of the rule claimed that moving the scrub into
`pytest_configure` would re-open the hole. A throwaway probe disproved it —
the order is module import, then `pytest_configure`, then collection, then
test-module import — so both placements are early enough. What must hold is
the behaviour, which is what this hook measures.

## Mechanism

`check.py` materialises the INDEX copy of `conftest.py` into a temporary
directory and imports it there in a subprocess started with a hook-shaped
environment (`GIT_DIR`, `GIT_INDEX_FILE`, `GIT_AUTHOR_EMAIL`,
`GIT_AUTHOR_NAME`, and nothing else but `PATH`). The subprocess prints the
surviving `GIT_*` names and the post-import value of every pin.

Reading the index matters here: a hook runs while other people edit the same
checkout, so the working-tree file may hold an unstaged edit that is not part
of this commit. `git show :conftest.py` is what the commit contains. A
conftest that is untracked — newly written and not yet staged when someone
runs the checker by hand — falls back to the file on disk.

| failure mode | how it is caught |
|---|---|
| scrub deleted | `GIT_*` names survive the import |
| scrub narrowed | the names it forgot survive |
| scrub runs too late | same, if the reader is in this file |
| named pin deleted | absent from the AST walk |
| named pin default flipped | compared to `expected_pins` |
| any pin overridden later | runtime value differs from its literal |
| a new pin goes unguarded | AST finds it; no edit here needed |

The pin set comes from the AST, not from a name list, so a pin added tomorrow
is held to its own declared literal with no change to the checker; a test
pins that property. The two pins in `CONFIG["expected_pins"]` are additionally
compared against a semantic value, because an AST read alone cannot tell a
deliberate default from a quiet flip.

## Stock

0 findings against `/home/<user>/projects/research-monorepo` at HEAD
`eaf82761cddc`. The live `conftest.py` declares five module-scope pins —
`AII_WEB_APP_MODE` `'1'` at :73, `CRED_MANAGER_ENABLED` `'0'` at :74,
`AII_ABILITY_CLIENT_ENABLED` `'0'` at :77,
`AII_FREE_ROUTER_DISCOVERY_ENABLED` `'0'` at :81 and
`AII_MODEL_ROSTER_DISCOVERY_ENABLED` `'0'` at :91 — plus the scrub loop at
:105-106. All five hold their literals after the import and no `GIT_*` name
survives.

Whole-tree runtime 0.04 s, median of three runs (0.04 / 0.04 / 0.04), rounded
up to the 1 s floor in the table. The probe runs under the system `python3`
(`/usr/bin/python3`, 3.12.3) — verified at this HEAD, where the module scope
of `conftest.py` imports only `os`. That is why the lefthook `run:` line says
`python3` and not `.venv/bin/python`: this hook has no venv dependency, and it
keeps working on a checkout whose virtualenv is missing or half-built.

17 bites tests, 2.9 s.

## Fragility

| refactor | effect | guard |
|---|---|---|
| `conftest.py` renamed | subject gone | exit 2 |
| pins moved to `pytest_configure` | no pins found | exit 2 |
| conftest imports repo code | import fails | exit 2 |
| a git call added before the scrub | `GIT_*` lives | exit 1 |
| a pin's value becomes computed | not a pin | none |

A rename exits 2 only while `tests/` is still tracked; a checkout with neither
a root conftest nor a test tree is a repo this hook does not apply to, and it
prints `skipped:` and exits 0. So does a working directory that is not a git
checkout.

The third row is the one worth knowing before editing `conftest.py`. The probe
imports the staged bytes from a temporary directory with nothing else of the
repo importable, which is what makes the verdict independent of the working
tree. A conftest whose module scope reaches into `aii_lib` or any other repo
package therefore fails to import, and the hook reports `cannot run:` with the
`ImportError` in the message. That is deliberate: loud, on the commit that
introduces it, rather than a probe that quietly starts measuring a different
file. The fix at that point is either to keep the new import inside a function
(where the rest of this conftest already keeps `psycopg`, `aii_lib` and
`django`) or to give the probe an exported index to import from.

Moving the pins into `pytest_configure` would still be correct behaviour, per
the ordering measurement above, but the module-scope AST walk would find none
and exit 2 — loud rather than silent, and the fix is a one-line change to
which nodes the walk visits.

## Residue

The rule was an agent verdict over the whole question "is the test environment
hermetic". The program is narrower on purpose.

- A pin whose value is computed rather than a string literal is not recognised
  as a pin and is not checked. There is no declared literal to compare a
  runtime value against.
- Whether the *right* default was chosen is out of scope for every pin except
  the two named in `CONFIG["expected_pins"]`. Any other pin is held only to
  its own declaration, which catches an override but not a bad decision.
- Hermeticity beyond `GIT_*` and these pins — sockets, API keys, ambient
  config — is not measured here. `rule-tests-offline-guard` covered that and
  was retired in the 2026-08-28 audit; nothing replaced it.
- Anything a per-directory `conftest.py` or a fixture does later in the
  session is invisible to a probe that imports the root file alone.
