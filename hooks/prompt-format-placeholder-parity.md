<!-- hook: prompt-format-placeholder-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every .format() call on a prompt template supplies exactly the placeholders the template declares — no missing (runtime KeyError mid-run), no extras (silent drift)

Four modules use the late-substitution .format idiom: snippets.py:43-45
documents the '{file_max_size} placeholder survives each module's later
.format()' contract consumed by dataset/experiment/evaluation u_prompts (e.g.
experiment/u_prompt.py:83); HEADER templates with 5-10 placeholders live at
_3_gen_demo_art/u_prompt_code.py:28 and _4_gen_full_paper/u_prompt.py. A live
drift instance exists today: u_prompt_code.py:200-212 supplies artifact_name=
but HEADER (line 28) has no {artifact_name} placeholder — str.format swallows
extras silently, and the inverse (a placeholder added without the kwarg)
raises KeyError only when that pipeline step runs in production. Verified
feasible: an AST script scoping templates per-module flags exactly this one
instance and nothing else across all 73 files.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: prompts)

Proposed command (superseded by the frontmatter above, kept as the proposal's
own text — the script it names was never written):

    python3 scripts/check_format_placeholders.py aii_pipeline/src/aii_pipeline/prompts

Delete-check: Partially deletable: the two HEADER.format templates could become f-string
PROMPT() functions (the house default per rule-prompt-module-shape), shrinking
the surface. The TODO-list templates cannot — late per-item substitution
across modules is the point of snippets.py's shared
FILE_SIZE_CHECK_TODO_PREFIX. Rule stays for the residual idiom; migration of
the HEADER blocks is worth doing alongside adoption.

Filter verdicts (3-lens adversarial, kept 2/3):
- KILL: Subsumed: rendering every registered arg combination catches missing
placeholders (KeyError) and unresolved {placeholder} residue dynamically,
which is strictly stronger than the static parity for the failure modes that
matter. [merge->rule-prompt-render-registry]
- KEEP: A missing placeholder is a KeyError mid-run (expensive, late); an
extra one is silent drift. Four modules, bounded surface, AST-checkable.
Prefer shrinking the surface by converting HEADER templates to PROMPT()
functions per the house shape.
- KEEP: AST: resolve template constants, parse {placeholders} via
string.Formatter, compare against .format() kwargs at each call site. Four
modules, statically resolvable; catches both KeyError-in-prod and silently-
ignored extras (which render checks cannot). Implementable.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds; the named
instance was real and is now FIXED, and the stock is zero.**

The live drift reproduced exactly. `HEADER` in
`_3_gen_demo_art/u_prompt_code.py` spans lines 28-117 and declares ten
placeholders; `_build_header` passed eleven kwargs, the extra being
`artifact_name`. Fixed in `56289c19d` — the kwarg went, and with it the
parameter it orphaned plus two in-module call sites. `artifact_name` is
still used where it belongs, by the per-item `item.format` whose todo
templates really do carry `{artifact_name}`.

Re-swept every prompt module afterwards: **2 `TEMPLATE.format()` sites, 0
mismatches.** So this becomes a regression guard rather than a cleanup.

## The check MUST use `string.Formatter`, not a regex

This is the whole implementation, and getting it wrong produces a
confident false alarm. A regex like `\{([a-z_]\w*)\}` reports four
"missing placeholders" — `figure`, `hyperref`, `plain`, `url` — in
`_4_gen_full_paper/u_prompt.py`. Those are LaTeX: the source contains
`\\begin{{figure}}`, `\\usepackage{{hyperref}}`, doubled braces, which is
the correct `str.format` escape for a literal brace. The regex matches the
INNER `{figure}` of `{{figure}}`.

Read naively that is a live `KeyError` in full-paper generation, which is
exactly the failure this rule exists to catch — so the false positive
looks indistinguishable from the true positive.
`string.Formatter().parse()` understands `{{ }}` and reports zero.

Two further constraints for the implementation, both hit while measuring:
a call using `**kwargs` cannot be checked statically and must be skipped
rather than guessed at; and the template's placeholders must come from
its FULL extent — sampling a twenty-line window of a ninety-line HEADER
reported six extras where there was one.

## IMPLEMENTED (2026-08-26) — `scripts/check_format_parity.py`

Green on the live tree: **2 judged calls, 0 findings**, matching the 2026-08-24
re-sweep above exactly. The `string.Formatter` mandate is honoured, and it
earns its keep beyond the doubled-brace case: `{{{x}}}` is a literal brace
around a real placeholder, which every lookaround regex I tried skipped.

`**kwargs` is REPORTED as unjudged rather than skipped. Silence would be a hole
exactly where a caller is most likely assembling arguments dynamically.

**Of 8 raw `.format(` hits, only 2 are judgeable, and the script says so.**

| shape | n | why |
|---|---|---|
| module `HEADER` constant | 2 | judged |
| prose inside a comment | 1 | not a call |
| loop var over a local | 2 | needs dataflow |
| loop var over imported text | 2 | template not in this AST |

The last row was found the honest way — the checker reported two findings
against correct code. `PROMPTS` there is built from `get_read_skills(...)` plus
constants imported from `snippets.py`, which is where `{file_max_size}` is
actually declared; reading only the literals written inline made a
correctly-supplied kwarg look like an extra. An impure source is now left
unjudged instead of guessed at.

A malformed template is a finding, not a traceback: `Formatter().parse` raises
the same `ValueError` `str.format` would, and an uncaught one reads as a broken
checker rather than a broken template.

**But it is parsed only where a `.format()` call actually reaches it.** A first
cut validated every string constant in each module up front, which reported
`out_schema.py:278` — a JSON schema whose braces are literal, formatted by
nothing. A string only has to be a valid format string if something formats it.

**The floor yields to findings.** `_MIN_CALLS` exists so a CLEAN result cannot
be vacuous; guarding the report itself lets a corpus that both shrinks below the
floor and breaks report "cannot run" and discard what it found. Surfaced in an
earlier cut of this script, where a malformed template made its whole file
unjudgeable and drove the count to zero — that particular path is gone now, but
the general one stands. The same shape was latent in
29 other pending mechanisms and is fixed across all of them — but only where
the floor sits AFTER the scan; 16 pre-scan floors are genuine cannot-run guards
and were deliberately left alone, since nothing has been found yet when they
fire and `not problems` there is a `NameError`.
