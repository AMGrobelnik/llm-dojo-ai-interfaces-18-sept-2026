<!-- hook: httpx-only -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# httpx is the only HTTP client in new code

Measured 2026-08-22: httpx is imported in 26 first-party files; requests in 3, aiohttp in 4, urllib.request in 2 — 10 banned import lines across 9 files. (The three banned figures are import LINES and still hold; the previous "36 httpx files" reproduces under no scope, then or now — it was 31 files / 42 lines the day it was written.) Four clients means four timeout idioms, four
retry wrappers, four mock styles — every reader pays for all four.
`urllib.parse` is fine (parsing, not transport); the ban is on
`requests`, `aiohttp`, and `urllib.request` imports.

Scope: the six package-source trees. Skill scripts under .claude/skills/
are self-contained CLIs with their own venvs and stay free — widening the
scope to them is an owner decision.

At commit this checks only ADDED lines, so the existing stock never blocks
you; `rules.py all` reports the stock drift for planned cleanup.

Fix when blocked: use httpx (sync and async APIs are near-identical to
requests/aiohttp). If an upstream SDK genuinely forces another client,
waive with the SDK named in the reason — repeated waivers here are the
signal to revisit the rule, not to keep waiving.

Delete-check: HTTP must exist, so the dimension cannot be deleted — only
pinned. The stock cleanup (9 files, 10 import lines) would let this rule guard a clean 1.

Stock (2026-08-22): 10 whole-tree hits — and the aiohttp-vs-httpx
direction itself is still an open owner call; stays added-lines.

RE-MEASURED 2026-08-24 — **exact on every figure, including the split.**

| quantity | body | today |
|---|---|---|
| files importing `httpx` | 26 | 26 |
| `requests` | 3 | 3 files (4 lines) |
| `aiohttp` | 4 | 4 files (4 lines) |
| `urllib.request` | 2 | 2 files (2 lines) |
| banned import LINES | 10 | 10 |
| banned import FILES | 9 | 9 |

Worth stating because the body's phrasing is easy to misread: "requests in 3,
aiohttp in 4, urllib.request in 2 — 10 banned import lines across 9 files"
counts FILES in the first three figures and LINES in the total. They reconcile
exactly (3+4+2 = 9 files; `requests` contributes 4 lines from 3 files, giving
10). Both readings were checked rather than assumed.

Measured with the rule's own pathspec. A looser sweep over all of `*.py`
reports 59 lines in 31 files, which is 3x the real figure — the difference is
entirely `tests/` and `aii_pipeline/**/archive/**`, both of which the rule
excludes on purpose. Anyone re-measuring this should copy the pathspec out of
the `command:` rather than re-deriving it.

The whole-tree direction remains an owner decision; this only confirms the
census the decision would be made against.

REPLACED 2026-09-10 — **the grep is now an AST check, and the stock is 8.**

A text grep cannot tell an import from a line of PROMPT that quotes one, and
2 of the 10 findings above were exactly that. Both are string literals that no
"use httpx" could ever fix, and both had been permanent debt since adoption:

| finding | what the line really is |
|---|---|
| `u_prompt_code.py:64` | one line of a Colab prompt |
| `_config.py:138` | a stdlib-only script for the pod |

In full, with the sentence each one is part of:

- `aii_pipeline/src/aii_pipeline/prompts/steps/_4_gen_paper_repo/`
  `_3_gen_demo_art/u_prompt_code.py:64` — `import urllib.request` inside the
  triple-quoted prompt that tells the agent how a generated notebook should
  load its demo data from GitHub. The pipeline imports nothing of the sort;
  the notebook it describes does.
- `aii_lib/src/aii_lib/claude_oauth/_accounts_health/_config.py:138` — the
  same line inside `POD_PROBE_SCRIPT`, a raw string carrying a program sent
  over one SSH round-trip and run by the POD's interpreter, where by
  construction only the stdlib exists.

`check.py` runs `rules-grep` for the candidates — the pattern, the
pathspec and `.amg-hooks-exclude` all stay where they were — and then asks `ast`
whether the candidate line is a real `Import`/`ImportFrom` of `requests`,
`aiohttp` or `urllib.request`. Depth is not the question: the walk is
`ast.walk` over the whole module, so the function-local pair at
`workflows/summarize.py:376-377` is still a finding, as it should be — a late
import is the same dependency arriving later.

| whole-tree stock | lines |
|---|---|
| before (grep only) | 10 |
| after (grep + parse) | 8 |
| dropped, both string literals | 2 |

Lanes are unchanged: a commit judges only the lines it ADDS, and
`--tree` / `AMG_HOOKS_SWEEP=1` judges the whole index, which is how the stock above
is counted. One implementation note, because it is the reason the script
calls `rules-grep --tree` in both lanes: rules-grep's own commit lane pipes the
diff's added lines through a single `grep -n`, so it prints `<n>:<text>`
where `n` counts within that stream and the path is gone. Measured on a
two-file fixture, the old lane printed `1:import requests` for a line that
sits at `aii_lib/a.py:12`. So the matching stays rules-grep's and the script
narrows the result to what `git diff --cached -U0` adds, keyed on
`(path, line)` — a hunk header's `+start` and `git grep --cached -n` are both
index line numbers and agree exactly. The commit lane now names the file it
is blocking you on, which it never did.

The judged snapshot is the INDEX, read with one `git cat-file --batch` over
`:<path>`. There is no fallback to the file on disk: in a shared checkout a
peer's unstaged edit would otherwise decide your verdict.

Vacuity bails, since the parse is now the only thing standing between a hit
and silence:

| condition | verdict |
|---|---|
| blob missing, or will not parse | the hit is REPORTED |
| `rules-grep` not on PATH | exit 2, `cannot run:` |
| pathspec matches no tracked file | exit 2, `cannot run:` |

`test_httpx_only_bites.py` pins all of it — 14 tests, including the two
string-literal shapes above and the unparseable-file case, which is the one
that would otherwise turn every syntax error into a hole in the ban.
