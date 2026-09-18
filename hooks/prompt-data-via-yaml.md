# Structured data reaches a prompt through one serializer

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

Steps in this pipeline read each other's output. When one prompt renders a
model as JSON and the next renders the same model as a Python repr, key
order, quoting and null rendering all fork, and the model sees two dialects
for one thing. The repo funnels every such rendering through
`to_prompt_yaml`, and this hook keeps that door single.

It was the most-evaluated rule of its batch — 238 applies, 40 fails, 278
evaluations of a question `ast` answers in 0.15 s. That ratio is the argument
for conversion on its own.

## Mechanism

`ast`, over two trees with two different questions. Under `prompts/` any
banned serializer call is a finding. Under `steps/` a serializer is only a
finding when its value reaches string text, which is what separates a prompt
from a JSON file being written to disk.

| failure mode | mechanism |
|---|---|
| `json.dumps` in a prompt module | dotted name in the banned table |
| `repr(x)` interpolated | banned bare name |
| `pprint.pformat` | a third dialect the grep never named |
| `model_dump_json()` | attribute table; invisible to `json\.` |
| `str({...})` over a literal | first arg is a dict/list/set literal |
| prose describing the ban | `ast`: comments are not calls |
| a tree renamed | per-tree floor, exit 2 |
| the door itself renamed | door-user floor, exit 2 |

The converted rule covers MORE than the grep its body proposed: that grep
scanned `prompts/` only, because a plain pattern cannot tell a `json.dumps`
that builds prompt text from one that writes a file. The `steps/` mode closes
four shapes — an f-string, `%` or `+` with a string literal, `.format()` or
`.join()`, and an assignment whose name an f-string in the same function
reads — and correctly exempts `repo_info.py:309`, which dumps into a
`write_text`.

The vacuity floors close a real hole in the proposed command: `! grep -rnE …
<dir>` on a renamed directory exits 2, which `!` inverts to 0, so a moved
tree reads as a clean bill.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**0 findings** across both trees — 78 tracked modules under `prompts/`, 56
under `steps/`, 17 naming the door. Whole-tree runtime 0.17 s (0.16 / 0.16 /
0.17), parsing all 134 modules.

Proved to bite on the real files: seeded with the live trees, rewriting
`to_prompt_yaml(` to `json.dumps(` in one prompt module reports both call
sites with the right message, and restoring it returns the run to 0.

## Fragility

| refactor | effect | guard |
|---|---|---|
| either tree renamed | scan sees nothing | per-tree floor, exit 2 |
| `to_prompt_yaml` renamed | nothing to funnel | door floor, exit 2 |
| a sixth dialect appears | it is not banned | not guarded; one line |
| serializing moves outside | out of scope | the trees are the rule |

The ban list is an enumeration, and a positive form — "only the door may
produce prompt-bound strings" — is not statically decidable. Adding a
serializer is one CONFIG line.

## Residue

The hook bans DIALECTS, not misuse: passing an already-serialized string
through the door still passes, and so does hand-writing YAML with an
f-string. Both are outside what any of the 278 agent evaluations could have
caught either. In `steps/` the interpolation analysis is intra-function on
purpose — a value assigned in one function and interpolated in another is
missed, because widening it across functions re-introduces the false positive
on the file-writing path.

CONFIG names two `aii_pipeline` trees, which is the project-specific part;
the invariant and the mechanism are not.
