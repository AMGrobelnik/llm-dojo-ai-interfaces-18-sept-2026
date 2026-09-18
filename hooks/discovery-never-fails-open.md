<!-- hook: discovery-never-fails-open -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A guard's discovery step never converts its own failure into a clean result

In full: no `except`/`catch` in a test module or its helpers may have
`return` of a falsy/empty value as its whole body — it re-raises, fails
the test, or narrows to the one expected status.

Distinct mechanism from an empty population: here the discovery ERRORS and the
error is spelled "nothing found". Measured with an AST scan over `git ls-files
'*test_*.py'` for `ExceptHandler` whose sole statement returns an empty/falsy
literal: `except handlers in TEST modules whose sole action is 'return
<empty/False>': 7` — `test_every_relative_import_resolves.py:99 except
SyntaxError: return []`, `test_dbos_app.py:55 except OSError: return False`,
`test_ability_discovery_prefilter.py:52 except SyntaxError: return False`,
`test_bff_endpoints.py:42 except OSError: return False`,
`test_staff_owner_resolution.py:42 except Exception: return False`,
`test_staff_run_access.py:45 except Exception: return False`,
`test_claude_project_slug.py:99 except ImportError: return None`. The last two
are the skip predicate `_has_dashboard_app()`; `sed -n '40,54p' rule-server-
run-access-gate/test_staff_run_access.py` shows `try: from django.apps import
apps; return apps.is_installed("dashboard") / except Exception: return False`,
immediately followed by `pytest.skip(..., allow_module_level=True)` — so ANY
Django breakage, not just a genuinely absent app, silently deletes the whole
cross-user access-gate module from the run. Frontend, same shape, one site:
`cd aii_frontend && git grep -n -A3 "} catch" -- '*.test.ts'` gives
`lib/__tests__/viewport-height-unit.guard.test.ts:51: } catch {` / `52- return
[] // grep exits 1 when nothing matches`. The comment anticipates exit 1 only;
the catch is unconditional, so a renamed `app`/`features`/`components`
directory (grep exit 2) reports zero offenders and the dvh guard passes having
scanned nothing.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: guard-effectiveness)

Command (BUILT — `scripts/no_fail_open_discovery.py`), no condition:

    python3 $RULE_DIR/scripts/no_fail_open_discovery.py

**Two live offenders were fixed to make this approvable**, and they were the
ones that mattered: `_has_dashboard_app()` in `test_staff_owner_resolution.py`
and `test_staff_run_access.py` caught broad `Exception` and returned False,
which module-level-skips the file. So any unexpected Django error — not just an
absent app — silently removed the STAFF RUN-ACCESS tests from the suite while
the run stayed green. Both now catch only `ImproperlyConfigured` and
`AppRegistryNotReady` (and `ImportError` for an absent Django); anything else
propagates.

**Narrowed handlers PASS, and that is the rule's own escape clause** — "it
re-raises, fails the test, or narrows to the one expected status". Reading
every falsy-returning handler as a defect reports 9 where there are 2: the
other 7 are `except OSError` around a filesystem probe, `except ImportError`
around an optional dependency, `except subprocess.CalledProcessError` around a
git ref that may legitimately be absent. A gate that flags those loses its
audience.

Python only. The frontend guard tests are TypeScript and their `catch` shape is
not covered — a gap, stated rather than exempted.

Verified to bite: restoring one broad handler fails naming file and line;
narrowed handlers keep passing. 47 tests in the access-gate group pass after
the narrowing.

Proposed condition: `none — whole-tree cmd, runs unconditionally`

Delete-check: Yes — deletion is the primary fix and the rule should accept nothing less at 5
of the 8 sites. Drop the try/except entirely and let the error propagate: a
`SyntaxError` while parsing the tree, an `OSError` opening a settings file, or
an unexpected Django failure are all things a guard should go RED on, not
shrug at. Where one specific non-error status is genuinely expected, narrow to
it — `viewport-height-unit.guard.test.ts` should check `err.status === 1`
(grep's no-match) and rethrow anything else, which removes the fail-open path
rather than policing it.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
MY OWN AST SCAN (not theirs): over `git ls-files '*test_*.py'`, ExceptHandler
whose body is exactly one Return of an empty/falsy value -> 'except handlers
in TEST modules whose sole action is return <empty/False>: 8' rules-
pending/.../rule-relative-imports-
resolve/test_every_relative_import_resolves.py except SyntaxError: return []
(except at :99) rules/.../rule-dbos-bootstrap/test_dbos_app.py except OSError:
return False (except at :55) rules/.../rule-docker-image-
guards/test_ability_discovery_prefilter.py except SyntaxError: return False
(except at :52) rules/.../rule-free-router-endpoint-
selection/test_free_router_timeout.py except AllProvidersFailedError: return
(except at :249) <- MINE, not theirs rules/.../rule-server-bff-
endpoints/test_bff_endpoints.py except OSError: return False (except at :42)
rules/.../rule-server-run-access-gate/test_staff_owner_resolution.py except
Exception: return False (except at :42) rules/.../rule-server-run-access-
gate/test_staff_run_access.py except Exception: return False (except at :45)
rules/.../rule-session-bucket-continuity/test_claude_project_slug.py except
ImportError: return None (except at :99) All 7 of their citations verified at
the EXACT line numbers claimed. My 8th is a bare `return` inside a test body,
which their filter evidently (and reasonably) excluded. THE SKIP PREDICATE —
confirmed, and worse than described: $ sed -n '38,58p' .../rule-server-run-
access-gate/test_staff_run_access.py -> `def _has_dashboard_app(): try: from
django.apps import apps; return apps.is_installed("dashboard") / except
Exception: return False` immediately followed by `if not _has_dashboard_app():
pytest.skip(..., allow_module_level=True)`. Bare `except Exception`, so any
Django breakage reads as 'app absent'. $ timeout 300 .venv/bin/pytest -n 0 -p
no:cacheprovider .../test_staff_run_access.py -> '13 passed' So 13 live cross-
user access-gate tests are what that one handler can silently delete from the
run. FRONTEND SITE — exact: $ cd aii_frontend && git grep -n -A3 '} catch' --
'*.test.ts' -> lib/__tests__/viewport-height-unit.guard.test.ts:51: '} catch
{' / :52: 'return [] // grep exits 1 when nothing matches' (the ONLY match in
the frontend test tree) $ node -e
"execFileSync('grep',[...,'nonexistent_dir'])" -> 'grep missing-dir status:
2'; same call against a real dir with no match -> 'grep no-match status: 1'
The comment anticipates 1; the catch is unconditional and swallows 2
identically, so a renamed app/features/components dir reports zero offenders
and the dvh guard passes having scanned nothing. Confirmed empirically, not
reasoned. DEDUPE CHECKED AGAINST THE ONE RULE THAT COULD KILL THIS — rule-no-
silent-except [ENFORCED]. I read its checker rather than its statement:
general/hooks/no-silent-except/check.py:35 `if "/tests/" in f or
f.startswith((".claude/", "scripts/", "tests/")): continue` Every site above
lives under a `.claude/skills/` submodule, i.e. explicitly OUT of scope.
Additionally its trivial-detector matches only `pass`, `continue` and returns
of `None` or an `ast.Constant` (check.py:47-53), so `return []` — an
`ast.List` — would not flag even if the scope were widened. No collision.
(Line anchors re-read 2026-09-14; they were :22 and :36-38 when this was
written, and the checker lives in a hook folder, not the retired engine's
`rule-` tree.)

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Verified the gap: no-silent-except/check.py:35 explicitly skips
tests/, .claude/ and scripts/, so the 8 test-helper handlers whose whole body
is `return <empty>` are uncovered — and a discovery step that swallows its own
failure reports a clean sweep over nothing.
- KEEP: I re-ran an AST scan for except handlers whose whole body returns an
empty value in test modules — deterministic, and the handler count is a large
non-empty floor. Genuinely distinct from rule-no-silent-except, which a
`return []` carrying an explanatory comment satisfies while the guard still
reports clean.
- KILL: Same dimension as sweep-population-floor (a guard that passes having
checked nothing), and the smaller half: 8 handlers, with the delete-check
calling deletion the primary fix at 5 of them. Also crowds ENFORCED rule-no-
silent-except, whose checker I read — it already scans every tracked module
and fails a handler that only returns a default with no logger, re-raise, or …
