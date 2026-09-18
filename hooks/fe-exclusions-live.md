<!-- hook: fe-exclusions-live -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every exclusion entry in aii_frontend lint/format/tsconfig configs names a path that exists and is genuinely generated

(Superseded 2026-08-26: 'lib/generated' is in NO config, and the missing
build-output dirs are correct. The backend.ts half was real and is CLOSED.
See IMPLEMENTED at the end.)

aii_frontend/.oxlintrc.json:331 ignores 'lib/generated' and .prettierignore
lists it too — the directory does not exist. tsconfig.json:35 includes
'dist/types/**/*.ts' with no dist/ in tree ('clean' script even rm -rf's it).
Worst: 'lib/types/backend.ts' is excluded from BOTH oxlint
(.oxlintrc.json:334) and oxfmt (.prettierignore) yet its header (backend.ts:4)
says 'HAND-MAINTAINED BE wire/tree types' — a live source file no lint gate
ever sees, left over from the retired Pydantic-to-TS codegen mirror. This is
the exact 'gate that is green and checking nothing' theme the rule-lint-gates-
actually-bite group pins for dead/typos allowlists, but nothing covers the FE
config exclusion lists.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: frontend-config)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_exclusions_live.py  # parses .oxlintrc.json ignorePatterns, .prettierignore, tsconfig include/exclude; fails on entries matching nothing in git ls-files, and on excluded .ts files lacking a .gen. name / generated-dir ancestry

Delete-check: Deletion is the immediate fix — the stale entries (lib/generated x2, dist x2)
should simply be removed, and backend.ts should be de-excluded and brought
under lint. But the dimension (exclusion lists exist and rot silently)
survives: _hey-api, openapi.json, next-env.d.ts are legitimately excluded, so
a liveness check is still needed to keep the list honest after the cleanup.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Live offenders including a file excluded from both lint and format
that still exists — an exclusion pointing at nothing (or worse, at something)
mis-shapes gates silently. Distinct surface from rule-gate-scopes-live.
- KEEP: A file excluded from BOTH lint and typecheck is a gate that is green
and checking nothing — the repo's documented worst class. Existence checks
over config entries are trivial; live offenders found.
- KEEP: Parse the three configs' exclusion entries, assert each path exists
(jq + test -e). Deterministic; the backend.ts double-exclusion is a real gate-
liveness gap. Loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -n` on aii_frontend/.oxlintrc.json returned `331: "lib/generated",` and
`334: "lib/types/backend.ts",` — both cited lines exact. `.prettierignore`
lists both too. `git ls-files aii_frontend/lib/generated` returned nothing and
`ls lib/` shows no `generated` entry (it was tracked once — `git log --all --
aii_frontend/lib/generated` returns 27fbeef8c and 4 others), so the entry is
dead. tsconfig.json line 35 is `"include": ["**/*.ts", "**/*.tsx",
".next/types/**/*.ts", "next-env.d.ts",

Corrected statement of fact:
Two of the three exclusions are genuinely dead (lib/generated in both
.oxlintrc.json:331 and .prettierignore; dist/types/**/*.ts in
tsconfig.json:35). The third is overstated: lib/types/backend.ts is excluded
from oxlint AND oxfmt as claimed, but the file's own line-1 `/* eslint-disable
*/` means un-ignoring it surfaces a single finding — that very comment — and
nothing else. The honest framing is 'stale codegen-era exclusions that no
longer name anything, plus a vestigial blanket disable on a now-hand-
maintained file', not 'a live source file hiding lint debt'.

RE-MEASURED 2026-08-24 — **stock is now ZERO**, and the named defect was
fixed earlier the same day.

Every exclusion entry in `.prettierignore` (19) and `.oxlintrc.json`'s
`ignorePatterns` (13) now matches something tracked, once build-output
names are set aside — `out`, `dist`, `.turbo`, `storybook-static`,
`coverage`, `*.tsbuildinfo` and friends are SUPPOSED to match nothing in
a clean tree, and a sweep that flags them is measuring the wrong thing.

The one genuine dead entry was `lib/generated`, excluded from BOTH tools
while absent from disk and from git. Removed in commit
`21d335221`. The hazard it left behind is worth restating, because it is
what makes this rule worth having rather than tidy: `.gitignore:16`
force-includes `aii_frontend/lib/**`, so anything recreated at
`lib/generated` would be TRACKED by git and invisible to both the linter
and the formatter — committed, never checked, and reported by nothing.

**So this is now a pure regression guard**, which strengthens it. Worth
noting the asymmetry that motivates it: the Python side already has
liveness guards for its allowlists —
`test_dead_allowlist_is_live.py` and `test_typos_allowlist_is_live.py`
assert that no entry has outlived its source and that none silences
nothing. The frontend has no equivalent, which is exactly the gap this
fills.

## IMPLEMENTED (2026-08-26) — the real hole is closed, two claims do not hold

`scripts/check_exclusions_live.py` judges **31** exclusion entries across
`.oxlintrc.json` and `.prettierignore`. Green.

**The `backend.ts` finding was real and is fixed here.** 380 lines headed
"HAND-MAINTAINED BE wire/tree types still consumed by the FE", exempted three
ways: oxlint `ignorePatterns`, `.prettierignore`, and in-file
`/* eslint-disable */` + `/* prettier-ignore */`. Measured: with the lint
exemption gone oxlint reports **0 warnings and 0 errors** on it, so that half
protected nothing and cost nothing to remove. Verified rather than assumed — a
planted violation in that file is now caught, and the sweep went 693 -> 694
files.

The FORMAT exemption stays, recorded with its reason: the type table is
hand-aligned and oxfmt would reflow all 380 lines, which is a style decision
and stays the owner's.

**Two of this body's other claims do not hold.** `lib/generated` appears in no
config — not `.oxlintrc.json`, not `.prettierignore`, not `tsconfig.json`. And
`dist/types/**/*.ts` in tsconfig's *include* is Next.js convention for build
output, not a dead path.

**The dead-entry direction is NOT checked, and this gate proved why on its
first CI run.** I shipped it testing disk existence; CI went red on
`5f13816bf`. `temp`, `next-env.d.ts` and `dev/components.html` exist in this
checkout and in NO fresh one, so the same check reported three dead entries
there and zero here — the exact local-versus-CI asymmetry
`rule-guards-ask-git-what-is-tracked` exists for, which I had built earlier the
same day. Build output is the same shape: `out`, `build`, `dist`, `.turbo`,
`storybook-static` are absent from a clean tree by definition.

Separating a dead entry from a transient one needs a maintained list of
transient names — the kind of list the four dockerignore incidents show nobody
updates. So only TRACKED files are judged, which git decides identically
everywhere.

The judgeable class is therefore narrow: an entry naming a TRACKED file that
does not declare itself generated. Probed both ways — planting a
hand-maintained tracked file in an exclusion is caught, and so is a recorded
exemption no config excludes any more.
