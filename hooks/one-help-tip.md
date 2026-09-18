<!-- hook: one-help-tip -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# The app has exactly one "?" help-tip primitive; the InfoTip/InfoTooltip twin is collapsed and the retired name never reappears

The twin is COLLAPSED and `InfoTip` is the survivor. Measured 2026-09-05 and
re-measured 2026-09-14 after the pathspec was widened:
`aii_frontend/components/ui/info-tooltip.tsx` does not exist, and
`git grep -nE 'InfoTooltip|ui/info-tooltip' -- 'aii_frontend/**.tsx'
'aii_frontend/**.ts'` returns nothing. The widening is what added the six
frontend root files the old `**/*.ext` spelling could not reach; none of them
names the retired twin, so the result is unchanged at zero.
`components/ui/info-tip.tsx` (136
lines) opens its docstring with "The app's ONE '?' help affordance" and now
earns it: **8** production modules import it and carry **14** `<InfoTip`
call sites —

| module family | files |
|---|---|
| `features/run-config/sections/` | 6 |
| `features/labs/views/models-view.tsx` | 1 |
| `features/human-feedback/fork-resume-help.tsx` | 1 |

The adjacent hover-explanation primitive, `components/ui/hover-tip.tsx`, is
a different affordance (hover, no "?" glyph) and is not in scope here; it has
27 production importers of its own. `components/ui/tooltip.tsx` is the Radix
wrapper both build on.

The state this rule was proposed on was the inverse: the file DECLARING itself
the one door had zero importers while the twin held every call site — a
migration started and never finished. The direction was an owner call because
the two differed in glyph (`CircleQuestionMark` vs `HelpCircle`) and in trigger
behaviour. It was decided by deleting the twin (`2b9683426`, 2026-08-29,
"feat(frontend): one hover-help style, and copy a newcomer can use"), which is
the direction the proposal's own command already assumed. `rule-fallow-fe`
could never have flagged either side — `info-tip.stories.tsx` imports the
component, and story-only usage defeats the dead-code gate — so a named rule is
what holds the collapsed end-state.

Type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: frontend-components)

## ADOPTED 2026-09-05 — the command is in the frontmatter, exactly as proposed

The proposal deferred approval until the migration/deletion decision was
executed. It has been, so the command is adopted verbatim in the direction the
owner took: assert the retired FILE absent, then ban the retired IDENTIFIER.

The file-absence half prints its own diagnostic. The earlier `test ! -f …` form
exited 1 SILENTLY while the file existed — the `&&` short-circuited before
`rules-grep`, so an early adoption would have blocked every commit with no
stdout and no hint why.

Condition: `aii_frontend/` staged. The ban half is the added-lines
`rules-grep` form, which only means anything in the commit lane (it is advisory
in a sweep), so gating on a staged frontend file costs one `git diff` and skips
the rule on every backend commit.

**Proven to bite, 2026-09-05**, in a throwaway `git init` tree under the
scratch dir — never against the repo's own files — with the real `rules-grep`
on `PATH` and `RULES_MODE=commit`:

| probe | result |
|---|---|
| clean tree | exit 0 |
| `info-tooltip.tsx` recreated | exit 1, `BLOCKED: …` |
| `InfoTooltip` import + JSX added | exit 1, both lines |

The identifier probe staged an added `import { InfoTooltip } from
"@/components/ui/info-tooltip"` plus a `<InfoTooltip …/>` usage, and the
command printed both.

Delete-check: This rule IS the deletion, already executed — `info-tooltip.tsx`
and its story are gone and the 14 remaining call sites, spread over 8
production modules, are all on `InfoTip`. The
rule now enforces that deleted end-state (retired file absent, retired
identifier never re-typed) instead of policing two variants forever. It cannot
itself be deleted without letting the twin regrow silently, which is exactly
how it arose: a four-way consolidation that `info-tip.tsx`'s docstring
narrates, undone by one paste.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Live inversion (the declared canonical primitive has zero importers;
the retired twin holds every call site) in a component that was already
consolidated four ways once — recurrence is proven. Migrate 7 files, delete
the twin, enforce.
- KILL: Do the migration (7 files) and delete the zero-importer 'canonical'
file — but a standing per-retired-filename grep rule doesn't scale as a genre.
The real gap is that fallow-fe failed to flag a zero-importer primitive; fix
that gate's liveness instead.
- KEEP: Verified: info-tip.tsx has zero importers, info-tooltip has 7. After
migrating and deleting the twin, a grep banning the retired module name is
trivial and loud. Textbook enforce-the-deleted-end-state.

## History — what the pre-collapse measurements said

Kept because the numbers are the argument for the rule, and every one of them
is now false in the good direction. Line references from these rounds resolve
against files that no longer exist; read them for the shape, not coordinates.

| date | finding |
|---|---|
| 2026-08-24 | `InfoTip` 0 importers, `InfoTooltip` 7 files |
| 2026-08-24 (audit) | re-measured: 15 usages across 8 files |
| 2026-08-28 | re-verified: twin still present |
| 2026-08-29 | `2b9683426` deletes the twin |
| 2026-09-05 | 0 references; `InfoTip` holds 8 files, 14 uses |

The 2026-08-24 "attempt the change" pass is the one worth keeping in full,
because it is why the collapse was cheap. `info-tooltip.tsx` was 94 lines with
7 production users; `info-tip.tsx` was 136 lines with 0. So "consolidate to one
help tip" was never a migration across 15 call sites — it was deleting one of
two near-duplicates and repointing the imports, and the direction that looked
obvious (delete the unused file) was the one that would have deleted the
intended destination. The single prop gap, `side` (placement), existed only on
`InfoTip`, so the surviving component was the strictly more capable one;
`info-tip.stories.tsx` still exercises all four sides.

That episode also retires a heuristic: a UI primitive existing only with a
story is not evidence of cruft, because `rule-ui-primitive-has-story` makes the
story mandatory.
