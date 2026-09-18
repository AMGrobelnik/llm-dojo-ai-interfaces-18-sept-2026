<!-- hook: tests-reap-their-children -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

# A test that starts a `subprocess.Popen` must reap it on every path

A test that shells out and never reaps the child it started leaves a zombie,
or a live process outliving the test run — worse under a parallel/CI runner,
where the leak compounds. Three conservative, AST-proven shapes, in test
files only (`test_*.py`, `*_test.py`, `conftest.py`):

  (a) **unreaped handle** — `proc = subprocess.Popen(...)` (not a `with`
      block, whose `__exit__` waits for free) with no `.wait()` /
      `.communicate()` on `proc` anywhere in the enclosing function;
  (b) **kill without wait** — `.kill()` / `.terminate()` / `os.killpg(...)`
      with no `.wait()` / `.communicate()` call AFTER it (by line number) in
      the same function;
  (c) **unhandled communicate timeout** — `.communicate(timeout=...)` whose
      nearest enclosing `try` does not catch `subprocess.TimeoutExpired` (a
      bare `except:` or a broad `except Exception:` / `except BaseException:`
      counts, since either would actually catch it).

Fix, in order:

    proc = subprocess.Popen(...)          ->  with subprocess.Popen(...) as proc:
    ...no reap...                         ->  proc.wait() / proc.communicate()
    proc.kill()                           ->  proc.kill(); proc.wait()
    proc.communicate(timeout=T)           ->  try: proc.communicate(timeout=T)
                                               except subprocess.TimeoutExpired:
                                                   proc.kill(); proc.communicate()

Only what the AST proves blocks. A receiver this hook cannot trace to a plain
`Name` or a dotted `Attribute` chain of only names (a call result, a
subscript, a comprehension target) is skipped entirely, on both the
assignment and the reap side — never guessed at, never a false positive.
Reap correlation is by name within one function's whole AST subtree (nested
`def`s included), not by control flow, except for the "after the kill, by
line number" rule in (b): coarse enough to miss a leak on one branch when
another branch of the same function reaps a like-named handle, but it can
never invent a finding.

Every run sweeps the whole tracked tree, through the shared, non-recursing
`svc.tracked()` listing (honours `RULES_EXCLUDE`; no `--recurse-submodules` —
a vendored submodule's own tests are that submodule's own concern), and
reports the full debt list, floored at `AMG_MIN_REAP_TEST_MODULES` (default
10) so a renamed convention or a moved checkout reads as "cannot run", not
"clean". There is no narrower per-commit scope: the stock below now blocks a
commit exactly as a newly introduced leak does.

## Stock

Measured 2026-09-14, whole-tree, index reads:

- `aii-hooks-reap` (this repo): **0 findings** out of 1008 tracked test
  modules — the 19 findings in 11 modules previously listed here, all under
  its own `research-monorepo/unit-tests/` set, are fixed (reaped properly, not
  suppressed).
- `research-monorepo` and `notes-repo`: each now scans only its OWN tracked test
  population (no `--recurse-submodules`) — the vendored
  `.claude/skills/amg-hooks` / `resources/skills/amg/amg-hooks`
  copy's own tests are that submodule's own concern and are judged by ITS
  commits, not the consumer's.

There is no narrower per-commit scope any more: the checker blocks on the
whole stock measured above.

Delete-check: deletable only by dropping the house rule that a test reaps
every process it starts — until then this is the difference between that
rule being written down and being followed.
