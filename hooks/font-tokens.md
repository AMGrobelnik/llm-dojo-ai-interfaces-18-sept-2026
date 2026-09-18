<!-- hook: font-tokens -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Fonts come from the three registered tokens (--font-sans / --font-mono / --font-serif), no fourth family

The app registers three families and maps them to --font-sans /
--font-mono / --font-serif; nothing stopped a call site naming its own,
and several did — echarts fell through to its OWN default (Microsoft
YaHei on Windows) in every chart, and `fontFamily: "monospace"` put the
same model ids in two different mono faces in one view. The rule is not
about the families, it is about the absence of anything that says no.
A THRESHOLD, not a ratchet, and no allowlist: an allowlist would
recreate the exemption the gate exists to remove. Checks every tracked
aii_frontend ts/tsx/css/mjs file, every run — check.sh walks `git ls-files`
in BOTH modes (flipped 2026-08-22, owner directive: whole-surface, not the
staged list), so a pre-existing violation blocks any commit. Sizes are deliberately NOT enforced — see the
script's docstring (`scripts/lint/check_font_tokens.py`). ~40 ms.

Fix when blocked: reference the token (`var(--font-sans)` /
`var(--font-mono)` / `var(--font-serif)`, or the corresponding Tailwind
class) instead of naming a family literal.

Delete-check: tool-enforced, cannot delete — the dimension (which font
a call site uses) must exist, and history shows call sites drift the
moment nothing says no.
