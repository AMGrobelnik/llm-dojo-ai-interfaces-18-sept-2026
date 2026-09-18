<!-- hook: doc-paths-resolve -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every repo path named in tracked markdown resolves to a file that exists

Stock today: **0** — re-measured 2026-08-28, `scripts/check_doc_paths.py`
examines 417 path-shaped tokens across tracked markdown and exits 0, so the
rule arrives GREEN. At implementation (2026-08-26) it examined 352 tokens
and found 16 stale references — fourteen `src/`-layout near-misses and two
moved test modules, all fixed in the same change (see IMPLEMENTED at the
end). None of the 16 were among the ten refs the proposal below was built
on: nine of those were repointed by commit `4d4da6f34` on 2026-08-22, four
days before the checker first ran, and the tenth was fixed with the
2026-08-24 re-measurement.

One repair on 2026-08-28: the "rules ABOUT stale paths" carve-out was a
fixed three-name list exempting only the resolver rules themselves, and
the first OTHER rule to quote a dead path as evidence —
`rule-config-models-closed-schema`, in a sentence whose own words are
"which does not exist" — turned the gate red. The carve-out is now
generic: a line that itself declares the path absent is quoting history,
not claiming presence (`DECLARES_ABSENCE` in the script). The fixed list
stays for the resolver rules' own bodies, whose evidence lines do not all
carry such wording.

**The pair decision is taken:** this rule and `rule-comment-paths-resolve`
were a near-identical pair — same resolver idea, each shipping its own
script and the same false-positive analysis — and at most one was to
survive. The 2026-08-28 audit killed the sibling (it exists in neither
tree now); this rule, which carries the richer exclusion set, is the
survivor and stands alone. The 2026-08-24 re-measurement below argued both
were kill candidates at the time; that predates the checker, whose
implementation found a fresh 16-defect stock, and is kept as history.

**Dependency note (2026-08-28 audit):** ENFORCED `rule-comment-drift`
already mechanizes one slice of this invariant family — its sweep
`scripts/stale_test_paths.py` in rule-comment-drift's own directory (prose naming dead test paths),
run whole-tree on every verification — and its body points here. If this
rule is approved and widened to source comments and docstrings, it should
ABSORB that sweep rather than rebuild it; until then the sweep stays with
`rule-comment-drift`. (`rule-comment-paths-resolve`, the near-duplicate
this body weighs itself against, was killed in the same audit.)

## History — the ten stale refs the proposal was built on (since fixed)

All from the tests-into-rule-engine migration:
CLAUDE.md:184 names tests/lint/test_module_lines_gate.py, CLAUDE.md:294 and
scripts/local/watchers/README.md:173,340,359 name
tests/lint/test_watcher_scripts_match_installed.py, CLAUDE.md:556 names
tests/aii_lib/test_autologin_magic_link.py,
scripts/local/watchers/README.md:66,70,107,294 name four more moved tests —
every one now lives under .claude/skills/amg-hooks/research-monorepo/unit-tests/
(verified by git ls-files basename match). Plus COMMIT_CHECKLIST.md:97 names
aii_lib/run/messages.py, a src/-layout near-miss for
aii_lib/src/aii_lib/run/messages.py. rumdl's MD057 (relative-link-target-
exists) was deliberately disabled as 'too brittle' (rule-rumdl SKILL.md), so
nothing checks doc→file references today. This is defect class #9 from history
(subjects move, references don't) surfacing in prose.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: docs-comments)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_doc_paths.py  # git ls-files '*.md' minus .agents/ and .claude/skills vendored bundles; extract backticked path tokens + relative link targets; resolve against doc dir AND repo root; skip globs/URLs/placeholders; on miss, print file:line plus the basename's new home from git ls-files; allowlist aii_public/README.md deploy-target links

Delete-check: Cannot delete the dimension: cross-referencing files in prose IS this repo's
documented style ('explains itself in prose on purpose'). Stripping path refs
from docs would destroy the navigation value the prose exists for. The
brittleness that killed MD057 is handled by scoping (dual-root resolution,
glob/placeholder skips, one named allowlist) instead of disabling.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: 10 live stale refs from one migration prove the class; prose path-
referencing is this repo's documented style so the dimension cannot be
deleted. Absorbs rule-comment-paths-resolve — one resolver check scans
markdown and source comments/docstrings together.
- KEEP: Ten live stale refs, all pointing agents at files that moved — in a
repo whose documented style is prose cross-reference. Path-extraction plus
existence check is cheap; needs a small allowlist for deliberately-historical
names (CLAUDE.md intentionally names removed files like publish-images.yml).
- KEEP: Implementable with a deliberate-past-tense allowlist: extract
backticked path-like tokens, resolve, allowlist deliberately-referenced
removed files (CLAUDE.md itself names publish-images.yml as removed). 10 live
stale refs prove value; allowlist maintenance is real but failures are loud,
not vacuous.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
All 10 cited doc refs were repointed by commit 4d4da6f34 "docs(tests): repoint
stale test paths to their rules-tree homes" (2026-08-22 02:46:39 +0200, i.e.
before HEAD 1ea0c0e63 at 13:33). Live readings: CLAUDE.md:294 now reads
`.claude/skills/amg-hooks/research-monorepo/unit-tests/rule-lint-gates-actually-
bite/test_module_lines_gate.py`; CLAUDE.md:294-ish watcher ref reads
`.../rule-watchers-installed-and-
current/test_watcher_scripts_match_installed.py`; CLAUDE.md:556 reads
`.../rule-claude-creds

Corrected statement of fact:
Corrected count: 0 of the 10 cited refs are live — all were fixed ~11 h before
this check. Of the surviving four in my scan, three are not defects:
`aii_config/dbos.private.yaml` is a gitignored private-overlay filename inside
a yaml example block; JOURNEYS.md's `tests/e2e/helpers/mock-run.ts` is
relative to aii_frontend/ and resolves there; and COMMIT_CHECKLIST.md:97's
`aii_lib/run/messages.py` is the repo-wide logical-module-path shorthand, used
the same way in ~40 other places (.env.template:9/15/18, pyproject.toml,
aii_frontend/lib/types/backend.ts:32, aii_runpod/.../env_payload.py:44-102),
so a resolver rule would have to allowlist that idiom wholesale or fire ~40
times. Exactly ONE genuine live stale ref exists and the proposal did not cite
it: aii_lib/src/aii_lib/abilities/BENCHMARK.md:90 gives a copy-pasteable
command naming
`.claude/skills/aii_fast_web_research/scripts/aii_fast_web_search.py`; `git
ls-files` puts that script at `.claude/skills/aii-web-
tools/scripts/aii_fast_web_search.py`, and `aii_fast_web_research` exists
nowhere in the tree. The MD057 half of the why is accurate: rule-
rumdl/SKILL.md:23 lists "MD057 relative-link-target-exists (too brittle: ...)"
among disabled rules — and its stated reason (aii_public/README.md links to
files that exist only in the deploy-target repo) is the same false-positive
class this rule would inherit.

## Re-measured 2026-08-24 — the one real defect is now FIXED

The single genuine live offender both this rule and its sibling
`rule-comment-paths-resolve` were built on has been repaired: `aii_lib/src/aii_lib/
abilities/BENCHMARK.md:90` gave a copy-pasteable command naming
`.claude/skills/aii_fast_web_research/scripts/aii_fast_web_search.py`, a
skill that is `aii-web-tools` now. Commit `e23fef84b` repointed it.

An independent sweep over every repo-rooted path mentioned in tracked
markdown and in source comments, resolved against `git ls-files`, now
returns **zero** dead references. The two remaining sweep hits are correct
prose and must not be "fixed": `tests/e2e/.auth/admin.json` is a Playwright
storage-state file the setup spec CREATES at runtime, and
`aii_lib/src/aii_lib/config.yaml` is named by a comment whose whole point is
that it never existed.

So both proposals now have a stock of ZERO and no cited defect left. That is
the owner's call to make, not this note's, but the honest summary is that
these two are kill candidates rather than merge candidates: consolidating
them into one rule with a two-row instance table would produce a single rule
guarding a class with no members and a high false-positive rate.

**Why the false-positive rate is the deciding factor.** Measuring this at
all took four corrections, and without every one of them the sweep reports
66 and 24 instead of 2 and 1 — a 30x false-positive rate:

- a `\b` prefix drops the leading dot, so `.claude/...` never resolves;
- the extension alternation must put `tsx` before `ts`, or `app/page.tsx`
  truncates to `app/page.ts` and looks dead;
- run-directory artifacts (`_2_gen_viz/gen_viz_results.json`) and gitignored
  `*.private.yaml` overlays are not repo paths;
- a path whose first segment is not a real top-level entry is prose.

That is on top of the ~40-occurrence logical-module-path idiom and the
synthetic example paths both verifications already recorded. A checker that
needs five separate exclusions to reach zero findings is one that will be
waived the first time it fires.

SECOND VERIFICATION (2026-08-24) — **9 of the 10 named refs are already
fixed; the 10th is fixed here. And the resolution ROOT SET is measured.**

Checked each named offender individually. Every `tests/…` reference the
migration stranded — in `CLAUDE.md` and `scripts/local/watchers/README.md` —
now resolves; those were repaired by later work. The survivor was
`COMMIT_CHECKLIST.md:97` naming `aii_lib/run/messages.py`, a src-layout
near-miss for `aii_lib/src/aii_lib/run/messages.py` (`aii_lib/run/` does not
exist at all). Corrected.

**The useful new datum is how much the root set does.** This proposal's
delete-check says the brittleness that killed MD057 is "handled by scoping
(dual-root resolution…)", which is right but understates how much scoping
decides. Sweeping backticked path-shaped tokens across tracked `*.md`:

| resolution attempted | unresolved |
|---|---|
| repo root only | 335 |
| + package roots + own dir | 278 |
| + the token's PARENT dir | 49 |

Repo-root-only reports **335 findings and is ~99% noise**. The single
biggest win is the parent dir, because a rule's SKILL.md names its siblings
as `rule-<name>/test_x.py` — relative to the unit-tests directory, not to its
own. Miss that and every one of the 162 enforced rule bodies looks broken.

The residual 49 are mostly not references at all, and they show what the
checker must still exclude by kind rather than by root: illustrative
placeholders (`_foo/_part.py`, `data_out/x.json`, `./pack.py`), generated
artifacts never tracked (`coverage/coverage-final.json`), container-absolute
paths (`/research-monorepo/aii_data/…`), and design docs written against a package
src root (`pod_infra/worker_pod.py` in `aii_runpod/PROVISIONER_DESIGN.md`).
Adding `aii_runpod/src/` removes that last group, which is the point: the
root list is per-package and has to be derived, not guessed.

So the rule is worth having and the mechanism is real, but "extract path
tokens and check they exist" is the easy half. Budget the work for the root
set — that is where 286 of the 335 apparent findings dissolve.

## IMPLEMENTED (2026-08-26) — 16, not 10, and all of them fixed

`scripts/check_doc_paths.py` walks tracked markdown. It examined **352**
path-shaped tokens and found **16** stale references — a population
disjoint from the 10 this body opened with, all of which were already
fixed before the checker first ran (nine by `4d4da6f34` on 2026-08-22, the
tenth on 2026-08-24). All 16 are corrected in the same change, so the rule
arrives GREEN and guards the next migration rather than carrying a
backlog.

Fourteen were `src/`-layout near-misses (`aii_lib/config.py` naming what is
really `aii_lib/src/aii_lib/config.py`); two named test modules that moved into
the rule engine.

### Why MD057 was right to be disabled, and what makes this one usable

A naive "every path-shaped token must resolve" sweep reports **119** findings
here and nearly all are noise. The exclusions each remove a measured class:

| excluded | n | why it is not a defect |
|---|---|---|
| doc-relative | 88 | skill-relative `scripts/x.py` |
| ellipsis elision | 6 | `aii_lib/…/tmux.py` is prose |
| basename exists nowhere | 15 | an invented example |
| rules ABOUT stale paths | 3 | they quote them as evidence |

The doc-relative class is the big one and the reason MD057 felt brittle: a
skill naming its own `scripts/cf.py` is correct, not broken.

**A finding requires the basename to exist somewhere**, so the report says
"this moved, and here is where to" rather than "this is wrong". A path whose
basename exists nowhere is left alone — a deliberate false NEGATIVE, taken to
hold the false-positive rate at zero.

The last exclusion is the self-reference trap: checked without it, this rule
reports its own body, and the "fix" would be deleting its evidence.
