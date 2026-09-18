# A test module declares exactly one genre, as a registered pytest marker

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

Converted from the retired rule engine's `general/tests/rule-test-genre-declared`,
which the migration left in this same slug as a README-only stub. That tree is
gone — nothing under `general/tests/` exists in this repo — so the path is
provenance, not somewhere to look. These files replace it: the rule asked for a
docstring sentence, this hook reads a marker.

## Why

Four genres, because each needs a different response when the module is red.
`behaviour` — the code broke. `pin` — an edit changed a pinned fact, and someone
must say whether that was intended. `parity` — a seam drifted, and the real fix
is one source of truth rather than a better test. `monitor` — this machine is
unhealthy; page someone. A module readable as two of those, or as none, gives no
machine-readable answer to "what do I do about this?"

The rule's own delete-check said markers "could mechanize this later ... until
the owner picks marker names, the docstring sentence is the cheapest closing of
the dimension". Measured over the real population at `3f1060fa7` (703 modules),
the docstring is no longer the cheaper option in either direction:

| property | modules | % |
|---|---|---|
| docstring of 40 characters or more | 702 | 99.9 |
| genre word in the first 200 chars | 179 | 25 |
| genre word anywhere in the docstring | 391 | 56 |
| module-level `pytestmark` | 598 | 85 |
| ... exactly `pytest.mark.unit` | 590 | 84 |

Two facts settle it. A docstring rule needs about 523 prose edits that nothing
can automate, while a marker rule edits a line that already exists in 85% of
modules. And the single most-matched genre word is the verb `pins` (91 of the
179), which no regex separates from the genre label — the group `Genre:` lines
hedge the same way at group level ("behaviour, mostly", "PIN-heavy"). Prose
hedges; a marker cannot. The marker also pays back: `pytest -m parity` selects,
a docstring sentence does not.

## Mechanism

`check.py` parses each in-scope module from the index and reads the module-level
`pytestmark` binding (`Assign` and `AnnAssign`), unwrapping list and tuple
values, `pytest.mark.X(...)` call forms and `.with_args(...)`.

| failure mode | mechanism |
|---|---|
| declares no genre | no module-level `pytestmark` |
| binding names no genre | marker set disjoint from the four |
| readable as two genres | more than one genre on the binding |
| genre not registered | nearest-config walk, `markers =` block |

The fourth is why the check has two halves. The repo-root `pytest.ini` carries
`filterwarnings = error::pytest.PytestUnknownMarkWarning` and registers `unit`,
`behaviour`, `integration` and `speed_check` — ONE of the four genres, not none
(`behaviour`, `pytest.ini:32`, re-read 2026-09-14). Adding `pytest.mark.pin`,
`.parity` or `.monitor` to a module today therefore still does not degrade
gracefully; it makes that module error. The registration half is usage-driven: it reports a
genre only where a module in scope actually declares it, so zero adoption
reports nothing, and the first module to declare a genre must register it in
the same commit.

Scope is `file` for the genre half and `relation` for the registration half,
which is the word in the header table because it is the wider of the two: from a
changed test module the checker resolves the config that governs it by walking
up to the nearest `pytest.ini` / `pyproject.toml` / `tox.ini` / `setup.cfg`. All
909 modules resolve to the repo-root `pytest.ini` today; the walk is what keeps
that correct after the ini moves or the tests move under another one.

The walk applies pytest's own rule for what counts as a config, because a
matching NAME is not one: `pytest.ini` always is, while `pyproject.toml`,
`tox.ini` and `setup.cfg` count only when they carry `[tool.pytest.ini_options]`,
`[pytest]` or `[tool:pytest]`. Two of those names are ordinary files with other
jobs — a packaging `pyproject.toml`, a lint `setup.cfg` — and pytest walks past
one that holds no pytest section (`_pytest/config/findpaths.py`,
`load_config_dict_from_file` returning `None`).

A bare `pyproject.toml` is not quite invisible to pytest, and the exception
proves the point rather than weakening it: when NOTHING up the tree carries a
section, `locate_config` falls back to the nearest one it passed and reports it
as the `configfile` — with an empty settings dict. It anchors the rootdir and
registers nothing. So it is never the file a genre is missing from.

Naming such a file is not a harmless near-miss, which is why the qualification
is in the walk rather than in prose. The finding's only fix is to add a pytest
section to it, and that MOVES pytest's rootdir to that directory: `confcutdir`
follows rootdir, so every `conftest.py` above it stops loading. In a vendored
tree — a submodule whose tests are collected by its consumer, which is the shape
this hook's own repository has — the dropped conftest is the consumer's, the one
pinning the hermetic test environment. The advice would be worse than the debt.

Every commit runs whole-tree: the fragment ignores `{staged_files}` and judges
every tracked test module, so a pre-existing undeclared genre now blocks a
commit exactly as a newly added one does.

Reads are index reads. Enumeration is non-recursing on both the live `check.py`
(`amg-hooks-ls-files`, `lib/amg_hooks/amg-hooks-ls-files`) and the ported `dispatch.py`
(`svc.tracked()`) — both honour `RULES_EXCLUDE`, and neither recurses into a
vendored submodule: its own test population is that submodule's own concern,
judged by its own gate, not this consumer's.

## Stock

Re-measured 2026-09-15 in `/home/<user>/projects/research-monorepo`, whole-tree,
index reads, `check.py` and `dispatch.py` enumerating identically (no
recursion): **971 findings over 982 tracked test modules** — 715 "pytestmark
names no genre", 256 "no module-level pytestmark", 0 registration findings (the
registration half is usage-driven and nothing declares a genre yet). 260 of the
findings are under `.claude/skills/amg-hooks/`, 711 under `tests/unit/`
— the population now spans both, not the single `.claude` row of earlier
measurements. The 2026-09-14 figure (907 over 909) was taken with the
standalone `check.py` still recursing into vendored submodules, and the
population also grew in the interim, so the two numbers are not directly
comparable.

There is no narrower per-commit scope any more: the checker judges the whole
tracked population on every commit, and the retrofit sequence below is how the
stock gets to 0 before this blocks on a real repo.

**Retrofit sequence.** The order matters, and only one order avoids turning the
suite red:

1. Register `pin`, `parity` and `monitor` in the root `pytest.ini`; `behaviour`
   is already there. Nothing declares them yet, so this commit changes no test
   outcome.
2. Seed the markers. Re-measured 2026-09-14, 706 of the 909 modules are
   mechanically derivable from the `Genre:` line their group's `README.md`
   already carries — 109 of the 110 unit-test groups carry one, and no group
   has a `SKILL.md` any more. The rest are hook and tool tests that need a
   human read. The edit is one line per module.
3. Tighten the scope — drop the new-or-touched filter — once the census is 0.

Step 1 before step 2 is the whole point of the registration half. Doing it the
other way makes every seeded module error on an unregistered mark.

## Fragility

| refactor | effect | guard |
|---|---|---|
| tests renamed `*_test.py` | population empties | exit 2 floor |
| `pytest.ini` moves or nests | none | nearest-config walk |
| markers move to `pyproject` | none | one textual reader |
| a packaging `pyproject` appears | none | section qualification |
| a genre is renamed | one CONFIG tuple | `CONFIG["genres"]` |

The vacuity floor is `AMG_MIN_TEST_MODULES`, default 10, the same on both
`check.py` and `dispatch.py`: neither recurses into a vendored submodule, so a
consumer's own tracked-test count (notes-repo: 16) must clear it unaided. It
catches "the tree moved and this check now sees nothing", not growth. A
whole-tree run below it exits 2, which blocks — meaning fix the hook
now.

The `markers =` block is read textually and identically for ini and toml,
because pyproject keeps the same strings under `[tool.pytest.ini_options]`. One
reader for both cannot disagree with itself; a toml parser plus an ini parser
can.

## Residue

The rule asked the docstring to EXPLAIN the genre. This checker requires only
the label. That is the deliberate half to drop: the explanation is what the 523
unautomatable prose edits would have cost, and the label is the part with a
machine consumer.

An untouched existing module is debt, not a block, so the census clears by
retrofit rather than by attrition. That is a scoping choice made to let the gate
ship before the retrofit; step 3 above is where it is reversed.

Editing a config to REMOVE a genre it registers is not caught at commit time —
the glob covers test modules, not configs, so no test module is staged and the
hook does not run. The whole-tree sweep catches it. Widening the glob to the
four config names would close this, at the cost of a whole-tree registration
pass whenever a `pyproject.toml` is touched.

`rule-group-manifest-current` checks the `Genre:` line on the group `SKILL.md`
files and is the group-level twin of this check. It is the source step 2 seeds
from; it is not replaced here.
