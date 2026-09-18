<!-- hook: http-detail-no-exception-text -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# A user-facing API error `detail` is curated copy — it never interpolates a caught exception; the exception goes to the log, and the response says what happened and what to do next.

RE-MEASURED 2026-08-28: the census grep below returns ZERO hits across the
three package trees — all 8 recorded sites are fixed (run_config/__init__.py's
`f"Failed to save config: {e}"` no longer exists). The rule is now a
zero-stock regression guard, and per rules-grep doctrine the `--tree` form is
safe: it ships in the frontmatter above and blocks in both modes. The census
below is the record of what it guards against, not a list of live defects.

## Original census (2026-08-24 — all 8 sites since fixed)

Ran `git grep -nE '"detail": *f"[^"]*\{ *(e|exc|err|ex|error)[]}!.[]' --
'aii_server/**/*.py' 'aii_lib/**/*.py' 'aii_pipeline/**/*.py'` → exactly 8
hits, zero false positives: `files/_run.py:576` and `:644` (`f"Failed to save
file: {e}"`, `f"Failed to delete file: {e}"`, both status=500),
`files/_staging.py:201` and `:274` (same pair), `run_config/__init__.py:568`
(`f"Failed to save config: {e}"`), `runs_helpers.py:453/470/588` (`f"Failed to
stage workflow input: {e}"`, `f"Failed to start pipeline: {e}"`, `f"Failed to
start runpod run: {e}"`). These reach the user verbatim: `lib/api/install-
error-interceptor.ts` wraps the thrown body's `detail` into `Error.message`,
and `toast.error("Failed to start pipeline", {description: err.message})`
(use-dashboard.ts:386) renders it. The four file sites catch `OSError`, whose
`str()` carries the absolute server path — `[Errno 13] Permission denied:
'/data/.../user_uploads/x.py'` — into a product toast. Two house-doctrine
statements say the opposite, and I read both:
`run_start_failures.display_title`'s docstring (`sed -n '241,251p'`) — "Known
failure classes get actionable copy; the fallback stays generic so an
unrecognized provider error never leaks raw text into the sidebar title (the
detail column keeps it for operators)"; and the global handler at
`dashboard/api/__init__.py:96-108`, which logs the full traceback and returns
`{"detail": "Internal Server Error"}`. Strongest evidence: ONE module
contradicts itself 297 lines apart — `run_config/__init__.py:269-271` does it
right (`logger.error(f"...: {e}")` + `{"detail": "Failed to parse config"}`)
while `:568` pastes `{e}` into the body. No comment at any of the 8 sites
declares the interpolation deliberate (read all four surrounding blocks). Ran
`git grep -nE '"detail": *\($'` and inspected all 6 multi-line details — every
one is curated, actionable copy naming a next step (`"...cannot revive a local
tmux session. Relaunch it locally instead."`), so the single-line grep is the
complete violation set. Distinct from rule-error-envelope (ENFORCED), which
pins the envelope SHAPE `create_response(request, {"detail": str},
status=4xx/5xx)` and says nothing about the string's content; distinct from
rule-no-silent-except (these sites DO log) and from rule-loguru-diagnose-off
(log sinks, not response bodies).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: error-taxonomy-ux)

Proposed command (implemented at approval):

    rules-grep --tree '"detail": *f"[^"]*\{ *(e|exc|err|ex|error)[]}!.[]' -- 'aii_server/**/*.py' 'aii_lib/**/*.py' 'aii_pipeline/**/*.py'   # superseded — the 8 stock sites are converted and the command now lives in the frontmatter (with [{] for \{ so the value stays valid YAML)

Delete-check: The delete IS the end-state and it is bigger than dropping `{e}`: five of the
eight try/except blocks add no status or branch value over the framework's own
handler. `@api.exception_handler(Exception)` (dashboard/api/__init__.py:96)
already logs the traceback and returns `{"detail": "Internal Server Error"}`
with status 500, so `_run.py:576`, `_run.py:644`, `_staging.py:201`,
`_staging.py:274` and `run_config:568` can delete their handler entirely and
inherit it. The three `runs_helpers` sites do branch (they fall back to other
start modes), so they keep the try and lose only the interpolation, matching
`run_config:269-271`'s shape in the same file. Residue after deletion: zero,
which is what the rule then holds.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
$ git grep -nE '"detail": *f"[^"]*\{ *(e|exc|err|ex|error)[]}!.[]' --
'aii_server/**/*.py' 'aii_lib/**/*.py' 'aii_pipeline/**/*.py'
files/_run.py:576, files/_run.py:644, files/_staging.py:201,
files/_staging.py:274, run_config/__init__.py:568, runs_helpers.py:453,
runs_helpers.py:470, runs_helpers.py:588 = exactly 8 hits, at exactly the 8
claimed file:line pairs, zero false positives. Widened the pattern to catch
forms the proposal did not test — `str(e)`, `detail=f"...{e}"`,
`HttpError(4xx, f"...{e}")` — over all *.py excluding .claude/ and tests/: the
only additional hits are three aii_pipeline `end_task(..., detail=f"Agent
failed: {err}")` calls (_research/claude.py:80, _4_gen_full_paper.py:201,
gen_py_demo.py:206), which are internal task-journal fields, not HTTP bodies.
So the 8 are the complete server-side violation set. Exception types confirmed
by reading all four file sites: each is `except OSError as e:` preceded by
`logger.exception(...)` then the 500 with `{e}` in the body — so an OSError
str, which carries the absolute server path, reaches the response verbatim. No
comment at any of the 8 sites declares it deliberate (read all surrounding
blocks). House doctrine, both read and both say the opposite:
aii_server/dashboard/api/__init__.py:96-110 —
`@api.exception_handler(Exception) def _capture_traceback` →
`logger.exception(...)` then `create_response(request, {"detail": "Internal
Server Error"}, status=500)`.
aii_server/dashboard/services/run_start_failures.py:241-248 `display_title`
docstring — verbatim: 'Known failure classes get actionable copy; the fallback
stays generic so an unrecognized provider error never leaks raw text into the
sidebar title (the detail column keeps it for operators).' Self-contradiction
confirmed inside ONE module: run_config/__init__.py:269-271 `except Exception
as e: logger.error(...); create_response(request, {"detail": "Failed to parse
config"}, status=500)` vs :567-568 `except Exception as e:
create_response(request, {"detail": f"Failed to save config: {e}"},
status=500)` — 297 lines apart, exactly as claimed (and the second does not
even log). Multi-line completeness check reproduced: `git grep -nE '"detail":
*\($' -- '*.py'` → 6 hits (api/__init__.py:612, files/_staging.py:213,
run_fork.py:469, run_resume.py:313, run_resume.py:356, runs_helpers.py:122).
Read all six; every one is curated actionable copy naming a next step, e.g.
run_resume.py:313-317 '…is a local run — resume provisions a RunPod
orchestrator and cannot revive a local tmux session. Relaunch it locally
instead.' and runs_helpers.py:122-126 'System update in progress — new runs
are paused. Please try again in a few minutes.' Frontend propagation
confirmed: lib/api/install-error-interceptor.ts header comment lines 5-13 —
'For Django Ninja that body is shaped {detail: "..."} … This interceptor wraps
the thrown value into a real Error whose .message is the BE's detail
(preferred)'; and features/runs-list/use-dashboard.ts:386 `toast.error("Failed
to start pipeline", { description: err.message })`. Both exact. Dedupe: rule-
error-envelope [ENFORCED] pins the SHAPE `create_response(request, {"detail":
str}, status=4xx/5xx)` and is silent on the string's content — these 8 sites
all satisfy it. rule-toast-headline-curated [PENDING] (claimed_r3.txt:350)
governs the FE toast's first argument (the headline), and all 8 of these land
in the `description` slot instead, so that rule cannot see them. Not a dedupe
hit.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Eight confirmed sites interpolating a caught exception into a user-
facing `detail`. rule-error-envelope pins the envelope SHAPE, not its content;
this is credential/internal-text hygiene on the API boundary with a clean
grep.
- KEEP: Ban-grep reproduces exactly at eight located sites and is probe-
testable; the population (API detail literals) is large and assertable. rule-
error-envelope pins the response shape, not whether curated copy or a caught
exception fills it — a real credential/internal-path hygiene gap.
- KEEP: No collapse closes it — the delete-check's move (drop 5 of 8
try/excepts that add no status or branch value) removes today's sites but not
the reflex to interpolate `{e}` into the next handler. Dedupe checked against
PENDING rule-toast-headline-curated: I read that rule; it is scoped to
`toast.*` first-argument construction in aii_frontend and its own delete-check
…
