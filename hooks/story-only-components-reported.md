<!-- hook: story-only-components-reported -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A component reachable only from its own story is reported

Status 2026-08-28 — **SUPERSEDED, see `## Resolved 2026-09-03` at the end.**
`check.py` exits 1 on the tracked tree, naming the same three components it has
named since 2026-08-25 (re-run today). Approving the rule as written therefore
blocks every commit until the owner wires or deletes them — see the APPROVAL
BLOCKER and TRIAGED sections at the end.

`fallow` cannot flag these, and the reason is structural rather than a
misconfiguration. It treats every `.stories.tsx` as an ENTRY POINT — its
own output says "311 entry points detected (307 plugin, 3 manual entry, 1
package.json)" against **68** tracked story files. A component imported
only by its own story is therefore reachable from an entry point, and
live.

Measured: `fallow dead-code` reports "✓ No issues found (0.11s)" on a tree
containing three such components.

| component | lines |
|---|---|
| `features/human-feedback/module-pill.tsx` | 155 |
| `components/ui/info-tip.tsx` | 136 |
| `features/human-feedback/action-mode-picker.tsx` | 68 |

359 lines that no gate reports.

## The interaction that makes this permanent

`rule-ui-primitive-has-story` makes a story MANDATORY for a UI primitive.
So a primitive acquires immunity to dead-code detection at the moment it
complies with the other rule. The two are individually reasonable and
together leave a hole neither owns.

That is also why the fix is not "stop treating stories as entry points" —
Storybook genuinely needs them, and fallow would then report all 68.

## What this rule does NOT claim

It does not say the three are deletable — the CHECKER reports, it does not
judge. (The TRIAGED 2026-08-28 section at the end does read the history and
does point at deletion; that is a reading of the tree, not something this
mechanism asserts.) A primitive may be parked
deliberately, and `info-tip.tsx` is the LARGER of a near-duplicate pair
(136 lines against `info-tooltip.tsx`'s 94, which has 7 real consumers) —
so the unused one is the more elaborate, which is worth understanding
before removing.

The claim is narrower and, I think, uncontroversial: **nothing currently
puts the question in front of anyone.** A component can sit unused
indefinitely while every gate reports green.

## Driven both ways

- Real tree: exit 1, naming the three above.
- Throwaway repo, component imported by a story AND a page: exit 0.
- Same repo with the page deleted: exit 1, naming the component.

The middle case is the one that matters — it proves the check
distinguishes "has a story" from "has only a story", which is the whole
distinction.

Detection note: the check matches an IMPORT (`from "…/stem"`), not a
mention of the name. `module-pill.tsx` is referenced by a comment in
`module-select.ts` ("Split out of ``module-pill.tsx``"); a name-match
would count that as a consumer and miss the finding.

Delete-check: deletable if `fallow` ever grows a notion of "reachable
only from a story", or if the three are resolved and the class stops
recurring. Until then this is the only thing that reports them.

## Scope: stories only. The test-only case is NOT the same, measured.

The obvious extension — "also report modules imported only by their
test" — was checked and does not hold. Across 185 tracked test files,
8 modules have no production importer, and every one is legitimate:

| module | why it is fine |
|---|---|
| 7 under `tests/e2e/` | helpers and page objects |
| `lib/api/hey-api-client.ts` | declared entry in `.fallowrc.json` |

Test infrastructure is SUPPOSED to be imported only by tests; a page
object with a production consumer would be the surprising thing. And the
one production module is explicitly listed as a fallow entry point, with
a comment saying why.

So the asymmetry is real and worth stating: a component reachable only
from its STORY is a component nothing ships, while a module reachable
only from TESTS is usually a module tests are meant to own. Widening this
rule to tests would produce eight findings and eight correct rebuttals,
which is how a rule earns a reputation for crying wolf.


APPROVAL BLOCKER (measured 2026-08-25) — **this rule exits 1 on today's tree,
so approving it blocks every commit until the three are resolved.** Found by
running every pending rule's command under a replica of the engine's
environment; `rule-pending-tree-approval-ready` checks the loader contract and
metadata, not whether a command exits 0.

The three are confirmed unreachable from app code: each is imported only by its
own `.stories.tsx`, and `git log -S` shows none was EVER imported from anywhere
else. So the report is accurate — this is not a detector artefact.

**Deleting them is not the safe call, and the dates are why.** All three are
recent, and `module-pill.tsx` was modified on 2026-08-24:

| component | added | last touched |
|---|---|---|
| `action-mode-picker.tsx` | 2026-08-14 | 2026-08-14 |
| `info-tip.tsx` | 2026-08-21 | 2026-08-21 |
| `module-pill.tsx` | 2026-08-21 | **2026-08-24** |

A component edited yesterday is in-flight work, not a corpse. Removing 359
lines of someone's unlanded UI to make a gate green would be the gate
dictating the roadmap.

**CORRECTED 2026-08-25 — that inference does not survive reading WHAT the edit
was, and it points the other way.** `module-pill.tsx`'s 2026-08-24 commit is
`0b0d0d2d7 fix(frontend): touch floors in CSS pixels`, part of a cross-cutting
responsive sweep over the whole frontend. A sweep touches every component it
matches whether or not anything imports it, so the edit is evidence that
maintenance is being spent ON unreachable code — the cost this rule exists to
surface — and not evidence that someone is mid-way through wiring it up. Recency
of a file and intent behind a file are different measurements, and only the
second one supports "in-flight".

The conclusion below still stands, on the other three arguments the section
makes; what is retired is the strongest-sounding of them. The date table is
kept because it is accurate — it just does not mean what this paragraph
originally read into it. This is the same failure mode the rule's own scope
note warns about elsewhere: a name-match or a timestamp standing in for
checking the thing itself.

So the decision is the OWNER'S, and it is a genuine fork:

- **Blocking**, as written — then wire or delete the three first, and the rule
  keeps a fourth from appearing.
- **Advisory** — exit 0 and print the report. Approvable today, but then
  nothing stops the next one, and the hole this rule documents stays open.

Either is defensible. What is not defensible is approving it as-is without
knowing it fires immediately.

## Triage of 2026-08-27 — SUPERSEDED by the 2026-08-28 triage below

**This section's conclusion is retired.** Its import-level confirmation
still holds, but its verdict — components built ahead of a caller, wire
them up rather than remove them — was an inference from recency, and
reading the git history on 2026-08-28 reverses it: each of the three lost
its only consumer to a commit that replaced it with a sibling. The live
recommendation is the TRIAGED section below; this one is kept for the
record, the same way the CORRECTED note above marks its own disproved
inference in place.

Each was confirmed by import, not by grep: the ONLY `from "…/<name>"` in the
tracked frontend is the component's own `.stories.tsx`. A looser search
suggests `module-select.ts` imports `module-pill`, and it does not — that is a
prose mention in a comment ("Split out of ``module-pill.tsx``"), and the real
dependency runs the other way.

| component | exports | last touched |
|---|---|---|
| `components/ui/info-tip` | `InfoTip` | 6d |
| `human-feedback/action-mode-picker` | `ActionModePicker` | 13d |
| `features/human-feedback/module-pill` | `ModulePill` | 3d |

**None is stale, and that was read as the finding.** All three were authored
or edited within the last two weeks, by the composer and human-feedback work
still in flight, and this section concluded they were components built ahead
of the caller that would use them — wire them up rather than remove them,
with the author deciding which. That verdict did not survive reading WHAT
orphaned them (below): recency measured maintenance being spent on
replaced code, not work in progress — the same recency-as-intent mistake the
CORRECTED 2026-08-25 note already retracts once above.

## TRIAGED 2026-08-28 — all three are orphans of a replacement, not work in progress

The checker still names the same three. Their git history says what they are:

| component | orphaned by | replaced by |
|---|---|---|
| action-mode-picker.tsx | d65993ace | send-mode-pill.tsx |
| module-pill.tsx | c868c7784 | send-mode-pill.tsx |
| info-tip.tsx | 45d6fcc8f | info-tooltip, hover-tip |

`d65993ace` is "Chat/Fork is the pill, not the select"; `c868c7784` resumes a
stopped run from Chat; `45d6fcc8f` landed `info-tip.tsx` already orphaned.

None is a component awaiting its feature: each lost its only consumer to a
commit that replaced it with a sibling, and `module-pill.tsx` was even
maintained after it was orphaned — twice: `0b0d0d2d7`, a touch-floor CSS fix
on 2026-08-24, and `bbe1f4441` on 2026-08-28, a composer-pill sizing sweep
that restyled it to match `send-mode-pill.tsx`, the very component that
replaced it. Deleting a UI component and its story is the owner's call; the
evidence points the same way for all three, and the rule stays red until it is
made.

## Resolved 2026-09-03 — all three settled, the checker exits 0

`check.py` returns 0 on the tracked tree. The blocker the APPROVAL BLOCKER
and TRIAGED sections describe is cleared, so the rule can be approved
without it firing on arrival.

`info-tip.tsx` resolved itself the other way and needed nothing done here:
it acquired eight production importers — `fork-resume-help`,
`labs/views/models-view`, and six under `run-config/sections/` — so by
2026-09-03 the checker named only two.

The other two were deleted, exactly as the TRIAGED 2026-08-28 reading
concluded — each lost its only consumer to a commit that replaced it with a
sibling, and neither was ever imported from anywhere else:

| deleted | lines | evidence |
|---|---|---|
| `action-mode-picker.tsx` | 76 | orphaned by `d65993ace` |
| `action-mode-picker.stories.tsx` | 106 | its only importer |
| `module-pill.tsx` | 155 | never wired, `c868c7784` |
| `module-pill.stories.tsx` | 129 | its only importer |

466 lines. `send-mode-pill.tsx` is what both were replaced by, and it is
live in `feedback-input.tsx` today.

Per component, re-confirmed before deleting rather than taken from the
triage:

- `ActionModePicker` — added by `3a90db076`, wired by `037229402`, and
  unwired by `d65993ace` ("Chat/Fork is the pill, not the select"), whose
  diff removes both the import and the JSX from `feedback-input.tsx`.
  `git log -S ActionModePicker` lists exactly those commits plus the
  rename sweep, so no other call site ever existed.
- `ModulePill` — `git log -S ModulePill` returns ONE commit, `c868c7784`,
  the one that added it. It never had a production importer at all; its
  two later commits (`0b0d0d2d7`, `bbe1f4441`) are cross-cutting styling
  sweeps, which is the "maintenance spent on replaced code" the CORRECTED
  2026-08-25 note above already identifies.

Nothing downstream was left dangling: `Segmented`, `action-mode.ts`,
`hexA`, `ActiveSpinner` and `COMPOSER_PILL_CLASS` each keep other
production consumers. The ONE exception is recorded rather than acted on —
`module-select.ts` (110 lines, "Split out of ``module-pill.tsx``") now has
no production importer, only `__tests__/module-select.test.ts`. That is
the test-only shape this rule's scope section deliberately excludes, so no
gate reports it; removing it is a separate owner call.

`check.py` was fixed in the same pass. It enumerated with `git ls-files`
and then read every path, so a file deleted in the working tree but not
yet staged raised `FileNotFoundError` — an uncaught traceback and exit 1,
not the documented exit 2. Tracked paths absent from the working tree are
now dropped up front, which is also the correct semantics: the sweep
examines the tree, and a deleted file is not in it. Driven three ways in a
throwaway repo — component plus page, exit 0; page removed from disk only,
exit 1 naming the component; page unindexed as well, exit 1.

Verified after the deletion: `fallow dead-code` clean (308 entry points),
`oxlint` 0 errors over 690 files, `tsgo --noEmit` clean, `vitest`
(`unit`) 145 files / 1969 tests, `vitest` (`storybook`) 65 files / 190
tests. The unit count is unchanged from before the deletion; the storybook
project drops the two stories that went with the components.

The `PENDING owner approval —` prefix and the "exits 1 on today's tree"
clause were dropped from the description, because neither was true any more,
and the `git mv` into `rules/general/frontend/` followed on 2026-09-03. Both
halves had to happen together: `rule-pending-tree-approval-ready` requires
that prefix on everything under `rules-pending/` and forbids it on everything
under `rules/`, so a description edited ahead of the mv names this rule until
the mv lands, and a mv without the edit names it afterwards.
