# Every persistent file write in the credential package goes through its store module — no bare write_text/write_bytes/json.dump/open-for-write elsewhere in the package

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

`claude_cred_manager/src/claude_cred_manager/store.py` pins `_FILE_MODE = 0o600`
at line 24 and declares `write_json_0600` and `atomic_write_json` as the shared
persistence primitive for every state file the package owns — `credentials.json`,
`slots.json`, `owner.json`. `write_credentials` does more than write: it
quarantines a displaced blob and clears both backoff markers.

A bare `json.dump` or `Path(p).write_text` next to that lands a refresh token at
the umask default of 0644, non-atomically, and skips the quarantine — three
regressions from one convenient line, in the one package where the file being
written is a live credential.

The rule this replaces proposed a text grep
(`\.write_text\(|json\.dump\(|os\.open\(|open\([^)]*["']w`). Measured against the
package, that grep misses three real spellings — `write_bytes`, `import json as
j`, and `from json import dump as d` — and it cannot tell `sys.stdout.write` or
`json.dumps` from a file write. The checker is an AST walk instead.

## Mechanism

`check.py` reads each target from the git index, parses it, and walks every
`ast.Call`. The door file is exempt; it is where the primitives live.

| write spelling | how it is seen |
|---|---|
| `Path(p).write_text(s)` | attribute name in CONFIG |
| `Path(p).write_bytes(b)` | same list |
| `json.dump(o, f)` | `import json [as j]` tracked |
| `from json import dump as d` | the bound name tracked |
| `os.open(p, ...)` | attribute call on `os` |
| `open(p, "w")` | mode literal at argument 1 |
| `Path(p).open("w")` | mode literal at argument 0 |
| `sys.stdout.write(s)` | not matched |
| `json.dumps(o)` | not matched |

The two mode slots differ and confusing them is a silent miss: the builtin takes
the path as its first argument, so the mode is argument 1, while `path.open(mode)`
has the path as the attribute's own value, so the mode is argument 0. Reading
slot 1 for both made the pathlib spelling invisible; both slots are pinned by
tests. A mode letter in `wax` makes the call a write, which covers every `+`
variant through the letter it also carries.

Content comes from the index (`git ls-files -s` for the population and the blob
shas, one `git cat-file --batch` for the content), never the working tree, so an
unstaged edit by another agent in the same checkout cannot change the verdict. A
path argument that is not in the index is read from disk, which is what a human
gets when checking a file they have written but not staged.

The mechanism is generic: the package root, the door file, the door primitives,
the enumerated write APIs, the write-ish mode letters and the population floor
are all in one `CONFIG` dict, and nothing below it names this project. The
defaults are research-monorepo's `claude_cred_manager`. The hook nevertheless stays in
the `general` set, because that is where the migration placed the folder and hook
names must stay unique across sets; a consumer that vendors the set without the
package is handled by the skip below rather than by moving the folder.

## Stock

0 findings, measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7499` (dirty working tree, which is why the checker reads the index).
Whole-tree runtime 0.05 s, median of three runs (0.05 / 0.05 / 0.05); the
file-mode run over two staged paths is 0.03 s.

Population: 14 tracked modules under
`claude_cred_manager/src/claude_cred_manager`. Confirmed a second way with
`git grep --cached` for the write spellings over the package excluding the door:
no match. The only write-shaped calls anywhere in the package are `store.py:37`
(`os.open`) and `store.py:39` (`json.dump`), both inside the door. The old rule
body's note that `__main__.py:44` writes JSON to stdout is stale; that call no
longer matches, and it would not be a finding in any case.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: **0 findings**, whole-tree 0.05 s. The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | guard |
|---|---|
| `store.py` renamed or moved | exit 2 |
| a door primitive renamed | exit 2 |
| the package drops below 5 modules | exit 2 |
| the package is absent entirely | `skipped:`, exit 0 |
| a new write API enters the language | none |

Renaming the door, or either primitive, breaks the exemption in the direction
that matters: either every module becomes a finding, or a relocated door is
scanned as an ordinary module while the real writes go unchecked. The checker
therefore reads the door file from the index and requires it to still define each
name in `door_primitives`, exiting 2 with `cannot run:` when it does not. The
planned collapse to a single primitive will trip this deliberately — a one-line
CONFIG edit, made loudly rather than discovered later.

A package that has shrunk below the floor of 5 modules (measured 14) is a move in
flight, and passing on the remains would be a green light that means nothing, so
that is exit 2 as well. A package with no tracked modules at all is a different
case: a repo that vendors this set and has no credential package must not be
blocked, so the checker prints `skipped:` and exits 0. That leaves one hole —
moving the package wholesale to another path reads as absent and goes green. It
is the price of a `general`-set hook whose population is optional.

A write API this enumeration does not list, or a local helper that wraps `open`
and is called from elsewhere in the package, is not seen. That is inherent to a
closed enumeration; the set is the original rule's own, plus the three spellings
the conversion added, and it is stated in the module docstring.

## Residue

The old rule asked an agent to judge intent. The program judges spelling, and
four things it deliberately does not do:

- A mode held in a variable (`open(p, mode)`) is not classifiable statically and
  is treated as not proven to be a write. The check stays free of false positives
  at the cost of that spelling.
- `shutil.copy`, `os.rename`, `tempfile.NamedTemporaryFile(delete=False)` and a
  subprocess that writes a file are outside the enumerated set, as they were
  under the original rule.
- Whether a particular write *ought* to be atomic and 0600 is not asked. Every
  write in this package goes through the door; the check does not grade
  exceptions.
- The door's own body is not checked. It is exempt by path, and the guard proves
  only that it still defines the primitives, not that they still do what their
  names claim — that belongs to the `rule-claude-creds-*` unit-test groups,
  which pin lifecycle semantics and do not overlap with write-site discipline.
