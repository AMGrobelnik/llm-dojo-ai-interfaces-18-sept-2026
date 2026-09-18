<!-- hook: test-basenames-unique -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:engine-git
# Every test module basename in this repo is unique.

Re-measured 2026-09-14 at `f4c55cb`: 932 tracked test modules across 277
directories
(707 of them in the 110 `research-monorepo/unit-tests` groups, 219 beside the hook
each one pins, 6 under `tools/`), ZERO duplicate basenames,
ZERO `__init__.py` in any of those directories, and no import-mode override
anywhere
(pytest.ini, pyproject, conftest) — so pytest's default prepend mode makes a
duplicate basename a collection error. The census moves every week (this
body has said 488, 497, 543, 554 and 656 before) and is given only to size the
population; the invariant is the zero, which is why the statement no longer
carries a count. The commit gate runs ONE command per set,
`python3 lib/amg_hooks/run_groups.py <set>/unit-tests {staged_files}`
(`research-monorepo/lefthook.yml:694`), and there is no longer any per-group
command at all — so a cross-group collision can never surface at commit: it
lands on main and breaks CI's full-tree collection later: exit 1 with
`--continue-on-collection-errors` in pytest.ini addopts, 2 without, so the
flag keeps the run from aborting mid-collection but does not hide the error.
This pins the invariant before the first collision, and unique names are
also what lets a group `README.md` and an incident docstring cite a test
unambiguously. (The `SKILL.md` manifests the historical notes below quote are
gone — every group carries a `README.md` instead.)

Type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: tests-quality)

## ADOPTED 2026-09-06 — the census asks git, not the filesystem

`metadata.command` carries the check, with no condition: it is one
`git ls-files` over the rule tree and holds every commit, not only the ones
that touch a test.

One change against the proposal, and it is the difference between a guard and
a coin flip. The proposed `find … -printf '%f\n'` walks the DISK, so an
untracked scratch module in a peer's working tree — two or three existed
in this checkout while this was written — would decide this rule's verdict; that is exactly what
`rule-guards-ask-git-what-is-tracked` forbids. The adopted form pipes
`git ls-files` through `awk -F/` and prints the colliding basenames rather
than exiting 1 in silence.

Proven to bite 2026-09-06, in a throwaway `git init` tree under the scratch
dir — never against the repo's own files:

| probe | exit |
|---|---|
| two rule dirs, unique basenames | 0 |
| second renamed to collide, tracked | 1, names `test_alpha.py` |
| same collision left untracked | 0, a scratch file is no verdict |
| collision removed | 0 |

Delete-check: Deletable in principle by setting --import-mode=importlib (removes the module-
name collision mechanically), but that only fixes pytest — ambiguous basenames
would still break the filename-as-citation convention the whole tree leans on.
The one-liner check is cheaper than the semantic argument; keep the rule.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: No __init__.py anywhere in 98 dirs plus pytest prepend mode makes a
duplicate basename a collection error that surfaces only in full-suite CI, not
the per-group commit gate. Cheap uniqueness check; importlib-mode alone leaves
human ambiguity.
- KEEP: With no __init__.py and default import mode, a duplicate basename is a
collection error that only surfaces when both groups happen to run together.
Uniqueness over 488 basenames is a one-liner; keeps names unambiguous for
humans and conditions too.
- KEEP: basename | sort | uniq -d over the rule tree. Trivial; a collision is
a real pytest prepend-mode collection error. Loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`find rules -name '__init__.py' | wc -l` -> 0. `grep -rn 'importmode|import-
mode|consider_namespace' pytest.ini pyproject.toml */pyproject.toml
conftest.py tests/conftest.py` -> no output. `grep -h '^ command:'
research-monorepo/unit-tests/*/SKILL.md | sort | uniq -c` -> a single line, `98
command: ".venv/bin/pytest -q -p no:cacheprovider $RULE_DIR"` — 98/98
identical, confirmed. pytest.ini:21 addopts does contain --continue-on-
collection-errors. Duplicate basenames today across rules tree + tests + a

Corrected statement of fact:
Every mechanism claim holds and I reproduced the collection error itself. Two
numbers are stale: 497 test_*.py in the rules tree (496 under aii/unit-tests),
not 488; and 99 dirs hold test files, not 98 — 98 is the count of dirs with a
SKILL.md, and rule-server-resume-guards is the one with a test and no rule.
One nuance on '--continue-on-collection-errors softens it further': measured
exit codes are 1 with the flag and 2 without, so CI still goes red either way
— the flag only prevents the run from aborting mid-collection, it does not
hide the error. No collision exists today, so there is nothing live to fix;
this is purely a pre-emptive pin.
