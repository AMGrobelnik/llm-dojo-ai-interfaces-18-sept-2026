# A file-size ceiling derives from DEFAULT_MAX_FILE_SIZE_MB — no budget name and no byte-scale literal is bound to a hand-typed number

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

The budget is defined once, as `DEFAULT_MAX_FILE_SIZE_MB = 100` in
`aii_lib/src/aii_lib/remote/contracts.py:5`, under a comment that gives the
reason (git rejects a push carrying a file of 100 MB or more) and the
instruction — "downstream modules import this instead of redeclaring 100".
It was redeclared anyway, in two `aii_pipeline` signatures the existing
pytest could not see: `artifact_validation.py` typed `max_file_size_mb:
float = 100`, and `deploy.py` typed `max_file_size_bytes: int = 50 * 1024 *
1024`, half the canonical value, on a parameter a live caller relied on.
Three spellings of one number.

As an agent rule it ran 407 applies, 132 fails and 11 work-in-progress
leases, every verdict a grep typed by hand. Two of those verdicts say why
this is a program now:

- One WIP verdict recorded that the rule's own printed command, run
  literally, exited 0 — and only because a peer's uncommitted, unstaged
  edit had removed the violation from the working tree while the index and
  HEAD still carried it. The commit contained the defect the check had just
  cleared. So this hook reads the index (`git ls-files -s`, `git cat-file
  --batch`) and never the files on disk, except for a path argument with no
  index entry.
- The grep required a type annotation (`max_file_size[a-z_]*:\s*(int|float)
  \s*=`) and was scoped to `aii_pipeline/src` while the rule's own condition
  named `aii_lib/src` too. A bare `MAX_FILE_SIZE_MB = 100` in `aii_lib`
  matched neither half; 407 applies never saw it. The AST checker found it
  on its first run, and it is still there today.

The two defects the rule was written about have since been fixed. The one
it could not see has not.

## Mechanism

`check.py` parses each policed file with `ast` and walks every binding — a
parameter default (positional, positional-only or keyword-only), an
annotated assignment, a plain assignment, an attribute assignment. A value
that mentions the canonical name is never a finding, and neither is a value
that mentions any other name: only a provably re-typed number is reported.

| failure mode | mechanism |
|---|---|
| `max_file_size_mb: float = 100` | detector A |
| `MAX_FILE_SIZE_MB = 100`, no annotation | detector A |
| `= 50 * 1024 * 1024` under any name | detector B |
| the same text quoted in a docstring | not a binding |
| a default derived from a constant | not pure-numeric |

Detector A fires when the bound NAME fullmatches the budget family
(`(default_)?max_file_size[a-z0-9_]*`, case-insensitive) and the value is a
pure numeric expression. Detector B is name-independent: it fires on a pure
numeric MULTIPLICATION chain containing 1024, because a byte ceiling
spelled as arithmetic is the same defect wearing a different variable.
Requiring the multiplication keeps a bare `1024` — a buffer count, a page
size, a port — out.

`contracts.py` itself is excluded, or the ban would flag its own
definition. The canonical constant is resolved from the index once per run;
its absence is an infra exit, not a finding.

The complementary half is the existing pytest
`rule-agent-output-validation/test_max_file_size_has_one_source.py`, which
pins the `.get("max_file_size_mb", <default>)` call sites and the two
shipped YAMLs. Its regex structurally cannot see a signature default or a
module constant — neither has a `.get(` — so no logic is duplicated.

## Stock

**1 finding**, measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7499056a9a06ebc67e4ec315cd474d25` (the working tree was dirty; the
figure is from the index):

```
aii_lib/src/aii_lib/agent_backend/utils/agent_helpers.py:26: 'MAX_FILE_SIZE_MB' is bound to a hand-typed literal (100) instead of DEFAULT_MAX_FILE_SIZE_MB — a second spelling of one budget
```

Re-measured for this hook: the line the batch report found at HEAD
`619d5e085` is still present at today's HEAD, at the same file and the same
line 26. Its own comment reads `# Default file size limit (GitHub's 100MB
limit)` — the same rationale as `contracts.py:5`, which is what a second
spelling is. It is exported from `agent_backend/utils/__init__.py` and
consumed as a signature default at `agent_helpers.py:475`.

The hook ships `active` rather than as debt because it is file-scoped: it
sees only the staged files lefthook hands it, so this one line blocks
nothing until somebody edits that file. The fix is one import line, which
is why no debt file is shipped — it would outlive its usefulness at once.

Whole-tree runtime over the 426 tracked `.py` files under both roots:
0.40 / 0.39 / 0.39 s (median 0.39 s). Per file: 0.03 s.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: **1 finding**, the same `agent_helpers.py:26` line, whole-tree 0.39 s. The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | effect | guard |
|---|---|---|
| the constant is renamed | detector A blind | exit 2 |
| `contracts.py` moves | anchor unresolved | exit 2 |
| the packages move | population empties | exit 2 |
| the budget is renamed | detector A quiet | detector B |

A rename of `DEFAULT_MAX_FILE_SIZE_MB`, or a move of the module that
declares it, means no correct derivation "mentions the canonical name" any
more — the ban would then flag every compliant site, or, inverted, none.
The constant is therefore looked up in the index by
`^DEFAULT_MAX_FILE_SIZE_MB\s*=` at module level, and its absence exits 2
with `cannot run:` rather than reporting clean. Likewise the population
floor: fewer than 5 tracked `.py` files under `aii_pipeline/src` and
`aii_lib/src` (426 today) exits 2. A budget renamed outside the
`max_file_size*` family silences detector A, but detector B still fires on
any byte-scale literal, and a rename that touched the source module trips
the constant guard.

Outside a git checkout there is no index to read, so the hook prints
`skipped:` and exits 0. That is an environment it cannot run in, not a
tree that has moved.

## Residue

The rule's own scope included a judgment this program deliberately does not
make: whether a default that derives from *some* constant derives from the
*right* one. `agent_helpers.py:475` reads `max_size_mb: float =
MAX_FILE_SIZE_MB`, which mentions a name and is therefore not flagged —
proving which of two constants is canonical is judgment, and fixing the
single stock hit above collapses the case anyway.

Two further exclusions are deliberate. The four shipped YAML sites that
carry the same 100 are already pinned by the existing pytest, so this hook
stays out of config files. And a numeric literal passed at a CALL SITE
rather than bound to a name is not examined: the invariant is about where a
default lives, and a call that passes an explicit size is the caller making
a choice, not a second declaration of the budget.
