<!-- hook: toast-headline-curated -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# A toast headline is curated copy — a raw wire/exception `.message` never appears as the first argument of toast.*; the raw detail rides in `description`.

Measured 2026-08-28: the proposed grep returns nothing — ZERO toast
headlines are a raw `.message`, so the rule arrives at zero stock and is a
pure regression guard. The one outlier the proposal found,
`features/runs-list/use-dashboard.ts`'s
`toast.error(err.message || "Failed to delete run")` — a raw backend message
as the headline, via `||` no less — now reads
`toast.error("Failed to delete run", { description: err.message })`. The
house pattern is established across the 14 files that toast at all
(use-dashboard.ts, api-keys.tsx, files-view.tsx, run-review-view.tsx,
use-run-settings.ts, configure-page.tsx, use-run-files.ts, use-run-pane.ts,
share-button.tsx, …): a curated title first, the raw detail in
`description`; `lib/api/client.ts` even documents the shape in its
docstring. Distinct from rule-dashboard-copy-parity (backend block-reason
coverage) — this pins headline construction at the call site.

Type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: fe-a11y-ux)

## ADOPTED 2026-09-06 — as `rules-grep --tree`, because the stock is zero

`metadata.command` carries the proposal's regex unchanged; only the carrier
differs. `grep -rn` walks the DISK and would read a peer's untracked file,
so the adopted form is `rules-grep --tree`, which is `git grep` over tracked
files and blocks in BOTH lanes — the preferred shape, available here because
the whole-tree hit count is 0 (re-measured 2026-09-06). `--include` globs are
replaced by the four directory pathspecs, which cover `.ts` and `.tsx` alike.

Coordinates, re-measured the same day: the repaired call the census names
sits at `use-dashboard.ts:307`, not the `:303` the third filter verdict below
quotes — `grep -n 'toast.error' aii_frontend/features/runs-list/use-dashboard.ts`.
It still reads `toast.error("Failed to delete run", { description: err.message })`,
so only the address moved.

Proven to bite 2026-09-06, in a throwaway `git init` tree under the scratch
dir — never against the repo's own files:

| probe | exit |
|---|---|
| curated headline, `err.message` in description | 0 |
| `toast.error(err.message \|\| "Failed…")` | 1, line printed |
| `toast.success( response.data.message )` | 1, line printed |
| both removed | 0 |

Delete-check: The delete IS the end-state: raw-message headlines are gone (the one site
was fixed), and the rule holds the count at zero. Considered deleting
further — one shared error-toast helper — but 14 sites already agree on the
two-arg shape, so a helper adds indirection without deleting a concept.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Established house pattern at 14+ sites with a mechanizable check
(first toast.* arg must not be a raw .message expression); distinct from rule-
dashboard-copy-parity (backend-reason coverage, not headline curation). Weak-
medium value but cheap and enforces real UX copy discipline.
- KILL: Cosmetic copy convention; deciding whether a toast first arg is 'a raw
wire .message' needs semantic analysis a grep cannot do — false positives on
dynamic curated strings, false negatives via intermediates. One violating
site: fix it and let review hold the line; not worth a per-commit whole-tree
gate.
- KEEP: Live site verified (use-dashboard.ts:303 toast.error(err.message ||
...)). Grep for toast.*(x.message|x.detail as first arg is implementable and
bites today; aliasing escapes are acceptable false negatives, not vacuity.
oxlint lacks no-restricted-syntax, so cmd grep is the right mechanism.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds; "14 sites" is
14 FILES, and the site count is 44**.

The previous pass declined to check this, on the grounds that "14 sites
agree on the two-arg shape" is a claim about call ARITY and a grep counts
only calls. Checked properly since, by parsing each `toast.*(` call and
counting depth-0 commas with string and bracket awareness:

| scope | sites | files | 2-arg | 1-arg |
|---|---|---|---|---|
| all tracked ts/tsx | 48 | 15 | 40 | 8 |
| excluding stories + tests | 44 | 14 | 36 | 8 |

**14 is the file count under the natural exclusion, not the site count.**
The claim's substance survives — the two-arg shape is overwhelmingly the
house convention — but the number is off by a factor of three against its
own stated unit, and an implementation sizing itself against "14 sites"
would think it had covered the surface after a fifth of it.

The more useful figure the census omits: **8 one-arg call sites** are the
actual non-conformers. That is the population a rule would act on, and it
is a number the proposal never states.

Method note: the first parser reported 7 zero-arg calls, which is not a
plausible shape for a toast. The bug was setting the "saw content" flag
only in the final branch, so a call opening with a string literal set the
in-string flag and never tripped it. Any arity check written for this
rule needs that ordering right, or it will silently classify the most
common form — `toast.error("msg", { … })` — as taking no arguments.

## The enforcement carrier, and the TypeScript-AST port

The check is carried by the `lib/amg_hooks` dispatcher through `amg-hooks-env` — the live
lefthook line runs `{amg_hooks}/lib/amg_hooks/amg-hooks-grep --tree`, not the retired rule-engine's
bare `rules-grep`. The `rules-grep` naming in the ADOPTED section above predates
that migration and describes the same regex under its old carrier; the mechanism
today is `amg-hooks-env` + `amg-hooks-grep`, and the `--tree` frontmatter maps to the
dispatcher's TREE-mode, so the whole git index is judged unconditionally and any
committed stock blocks — no `$RULES_MODE` shell escape is needed and none is used.

**The TypeScript-AST port is written but INERT.** Re-verified 2026-09-14: no
set wires a dispatcher command (`tools/_dispatch_wiring.py`'s
`dispatcher_commands()` returns nothing for all four sets), so the ERE at
`research-monorepo/lefthook.yml:682` is the ENTIRE live predicate today and every
false positive below is still a real block. What the following paragraphs
describe is what the port will do at the cutover.

In that port the token grep is a line-level
prefilter — the SOLE candidate source, the live ERE
`toast\.(error|success|info|warning)\(\s*[A-Za-z_$][A-Za-z0-9_$.]*\.message`
VERBATIM, not broadened. `dispatch.py` then confirms each candidate against a real
parse (`lib/amg_hooks/tsast.py`): it locates the `toast.*` call and inspects its HEADLINE
(first) argument, reporting only when that argument is a raw wire `.message` and
leaving a curated string/template literal headline compliant. That drops the false
positives a flat ERE cannot tell apart — a `.message` token inside a string or a
comment, a wrong receiver (`footoast.error`), and a same-prefixed property
(`cfg.message_id`, which the boundary-less `\.message` tail falsely matches) — while
keeping the canonical `toast.error(err.message || "…")` shape, which `tsast`
flattens to a compound headline node, fail-closed. It is a pure false-positive
remover: every finding sits on a candidate line, so the finding set is a subset of
the live ERE's hits and `ADDED` is 0 by construction (measured 0/0 against the
migrated tree, whose whole-index hit count is already zero).
