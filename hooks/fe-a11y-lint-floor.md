<!-- hook: fe-a11y-lint-floor -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The a11y lint floor in aii_frontend/.oxlintrc.json only grows: the jsx_a11y plugin stays enabled and its ten pinned rules stay at error.

In full: the jsx_a11y plugin stays enabled and the ten pinned rules —
alt-text, anchor-is-valid, anchor-ambiguous-text, aria-props,
label-has-associated-control, html-has-lang, lang,
click-events-have-key-events, no-static-element-interactions,
no-noninteractive-tabindex — stay at error, and no override may relax them
outside test/story globs.

.oxlintrc.json:12 declares the plugin and lines 67,156-161,219-226 pin the
ten at "error". The real un-guard vector is the PLUGIN line: removing
"jsx_a11y" from `plugins` silences all 31 a11y rules at once (measured: 345
rules -> 314, zero a11y diagnostics on a violating probe) while
rule-oxlint-fe — which only runs the linter — stays green. The ten explicit
entries matter less than first claimed: nine are oxlint Correctness rules
that `categories.correctness: "error"` (line 15) keeps on regardless, so
deleting their lines changes nothing observable; exactly one,
`jsx_a11y/anchor-ambiguous-text` (line 67), is Restriction-category and
lives or dies by its explicit entry. The `no-noninteractive-tabindex`
allowlist (lines 156-161: tabpanel/region/group) WIDENS oxlint's default
(tabpanel only), so it is pinned as deliberate curation whose removal breaks
the build loudly, not silently. Category assignments are oxlint 1.62.0's and
can move between versions — which is why the checker pins all ten explicit
entries rather than trusting categories. Same accepted family as claimed
rule-tsconfig-strictness-floor, different config file and dimension.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **low** (proposer: fe-a11y-ux)

Proposed command (implemented at approval):

Mechanism (implemented 2026-08-26, `scripts/check_a11y_floor.py`):

    .venv/bin/python $RULE_DIR/scripts/check_a11y_floor.py

Arrives green: plugin enabled, all ten pinned at `error`, and none of the three
overrides relaxes an a11y rule.

**The floor is a MINIMUM, not an equality** — the rule's own statement is "only
grows", so enabling more `jsx_a11y` rules must not fail it. Probed.

**Overrides are checked, and that is the half a rules-key reader misses.** A
rule can be pinned at `error` top-level and switched off for a glob further
down, leaving the floor intact on paper while shipped files are exempt. Test
and story globs may relax them; nothing else may.

The config is JSONC — it carries `//` comments, so `json.loads` on the raw text
raises. Stripped first, or the check reads as a crash rather than a verdict.

Probed eight ways: a dropped rule, a downgrade to `warn`, a removed plugin and
an override switching one off for `app/**` all fire; the real config, an
override scoped to stories, additional a11y rules, and the `[error, options]`
array form do not.

## Widening the floor is available and free today — an owner call

Measured while building this: oxlint ships **31** `jsx_a11y` rules and this
config enables **10**. The other 21 were run against the whole tree and report
**0 warnings and 0 errors** — so adopting them costs nothing now and would add
21 gates.

Not done here, because this rule asks for a floor and widening it is a policy
choice about what future frontend code must satisfy, not a defect.

Worth recording alongside it: **no oxlint `jsx_a11y` rule covers an icon-only
button with no accessible name.** The killed `rule-icon-controls-named` (its
directory exists in neither `rules/` nor `rules-pending/` any more) carried a
filter verdict arguing that its scanner should be replaced by "oxlint jsx-a11y
rules that cover unnamed interactive controls". That is true of
`eslint-plugin-jsx-a11y`, which has `control-has-associated-label`; oxlint has
not implemented it, and the full 31-rule list contains no equivalent. The
closest, `anchor-has-content` and `heading-has-content`, are about anchors and
headings. So the "demote to config" option that verdict proposed did not exist
in this toolchain, and a future icon-name gate would need its own scanner.

Superseded proposal (prefix dropped so `ready.py` does not read it as owed):

    scripts/check_a11y_floor.py aii_frontend/.oxlintrc.json

Delete-check: Considered deleting via a category instead of a list — impossible: oxlint has
no a11y category, which is exactly why the explicit entries exist and why they
need a floor. If oxlint ever grows one, the rule becomes a one-line category
pin.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The ten jsx_a11y entries sit outside any oxlint category, so a deleted
line silently un-guards with no signal — same accepted floor-pin shape as
pending rule-tsconfig-strictness-floor. Low value but one-grep cheap and it
protects the substrate flow-axe-serious-zero and the other a11y rules assume.
- KEEP: The ten rules sit outside any oxlint category so a config trim
silently un-guards them; floor-pinning JSON keys is a trivial check and
matches the established tsconfig-strictness-floor pattern.
- KEEP: Ratchet on explicit config entries that sit outside any category
(deleting one line silently un-guards); JSON parse + pinned-list compare is
trivial and loud. Direct precedent: pending rule-tsconfig-strictness-floor.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Line numbers all hold: grep -n on .oxlintrc.json gives 12 `"jsx_a11y"`, 15
`"correctness": "error"`, 67 `"jsx_a11y/anchor-ambiguous-text"`, 156
`"jsx_a11y/no-noninteractive-tabindex": [` (options
`{"roles":["tabpanel","region","group"]}` through 161), 219-226 the eight-rule
block; parsing the JSON confirms exactly 10 explicit jsx_a11y entries,
matching the ten named. The CAUSAL claim is where it fails: deleting the
explicit entries does not un-guard nine of the ten — they stay on through
`categories.correctness` once the plugin is declared — so the silent un-guard
vector is the plugin line, not the rules list (details below).

Corrected statement of fact:
Nine of the ten pinned jsx_a11y rules are oxlint **Correctness** rules and
stay on via `categories.correctness: "error"` (line 15) once the plugin is declared — deleting their explicit
`rules` entries changes nothing observable, verified by probe (8 errors -> 7).
Exactly ONE rule depends on its explicit line: `jsx_a11y/anchor-ambiguous-
text` (line 67), which oxlint classifies as **Restriction** and therefore no
enabled category turns on. The real un-guard vector is `"jsx_a11y"` in
`plugins` (line 12): removing it silences all 31 a11y rules at once (345 rules
-> 314, zero a11y diagnostics on a violating probe) while rule-oxlint-fe stays
green — that is the property worth pinning. The `no-noninteractive-tabindex`
allowlist (lines 156-161, roles tabpanel/region/group) is worth pinning for a
different reason than stated: it WIDENS the default (oxlint's default allows
tabpanel only), so deleting it produces new errors rather than lost coverage —
pin it as a deliberate curation whose removal would break the build, not as a
guard that could vanish silently. Note the version dependency: these category
assignments are oxlint 1.62.0's; a rule asserting 'these are correctness-
category' should re-derive from `oxlint --rules` rather than hardcode.
