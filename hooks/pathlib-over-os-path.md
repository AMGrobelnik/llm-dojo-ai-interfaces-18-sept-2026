<!-- hook: pathlib-over-os-path -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# File-system paths use `pathlib.Path` — not `os.path.join` / `exists` / `dirname` / `basename`

House rule (global CLAUDE.md, Python section): `pathlib.Path` for file ops.
One object carries the path, its parts and its I/O, so the four `os.path`
calls this bans collapse into `/`, `.exists()`, `.parent` and `.name` — and
a `Path` in a signature says what the argument is, where a `str` does not.

FAIL evidence: the added line the grep prints.

Fix when blocked, in order:

    os.path.join(a, b)   ->  Path(a) / b
    os.path.exists(p)    ->  Path(p).exists()
    os.path.dirname(p)   ->  Path(p).parent
    os.path.basename(p)  ->  Path(p).name

Scope: first-party `*.py` only. Any `.claude/` tree and test files are
excluded — a test that pins a legacy string path is testing what exists,
not choosing an idiom — as is whatever the consumer's `.amg-rules.yaml`
`exclude:` list adds (vendored and archived trees belong there).

Mode: ADDED LINES. Measured 2026-09-07: **34 occurrences in 14 files in
scope** (184 occurrences in 81 files tree-wide before the exclusions), so
the stock rides as an all-mode advisory and only new code is gated.

Delete-check: deletable only by dropping the house preference — until then
this is the difference between the convention being written down and being
followed.
