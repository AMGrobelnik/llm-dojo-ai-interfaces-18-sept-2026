# An in-flight mutation of shipped config targets the layer that wins the overlay merge

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

`aii_config/` is layered. Every tracked `X.yaml` may have a gitignored
`X.private.yaml` sibling, and `load_config_with_overrides` deep-merges the
private sibling ON TOP, with `deep_merge` replacing same-named leaves
wholesale. Deploy paths ship both layers in one tar and rewrite bytes as they
go in — an exec-mode override, per-deploy image refs, an owner's compute
ceiling. A rewrite aimed at the PUBLIC layer of a file whose private sibling
re-declares the same key ships, logs, and is then discarded by the merge.

Two real regressions, three months apart, in the same twenty lines of
`aii_runpod/.../_remote/_deploy_flow.py`:

- `771f87d09^` targeted `harness/execute_env.yaml`, missing the `pipeline/`
  prefix that the tar loop's arcnames carry. The equality never matched, the
  file shipped unmodified, and a `logger.info` announced a rewrite that never
  happened.
- `bec784524^` corrected the arcname and thereby began rewriting the PUBLIC
  `pipeline/harness/execute_env.yaml`, while the private sibling shipped in
  the same tar carried its own `mode:` and out-ranked it on the pod.

`_redeploy.py` had the same job right the whole time, mutating the private
yamls with a comment saying why. The 2026-09-04 fix copied that twin. The
agent rule this hook replaces recorded 190 applications and 8 WIP verdicts,
every one of them a re-derivation of the same two mechanical questions:
which layer does this scope name, and does that name resolve.

## Mechanism

`check.py` parses each candidate python file and treats a scope (a function,
or module level) as a MUTATION scope only when it names a byte-rewriting
marker — `safe_dump`, `write_text`, `write_bytes`, `TarInfo`, `addfile`,
`mutators=`. For such a scope it collects every config-path string literal
the scope can see: its own literals, plus the values of module-level string
constants it references by name, so an arcname constant used inside a
function still resolves.

| failure mode | mechanism |
|---|---|
| wrong layer | private twin absent from the scope |
| dead arcname | path resolves to no config file |
| prose naming a file | literal must be all path chars |
| a read-only site | no rewrite marker in the scope |
| population collapse | two floors, exit 2 |

The wrong-layer test is "the private layer must be among the names", not
"the public layer must never appear". That keeps the shipped fallback green:
when no private sibling ships, the public file IS the winning layer, so a
scope naming both twins is correct.

The dead-arcname finding fires when a literal's basename matches a UNIQUE
file under the config root but the path itself resolves to nothing; the
message names the file it probably meant.

Prose is excluded twice: a literal counts only if it is entirely path
characters (an error message mentioning a yaml file is a sentence, not a
target), and docstrings and bare-expression strings are dropped outright.

**Disk independence is deliberate.** `*.private.yaml` is gitignored, so the
checker indexes only PUBLIC files and derives the twin BY NAME from
`CONFIG["overlay_suffix"]`. It never stats the private file, so CI, a fresh
clone and a developer box return one verdict.

**Everything is read from the INDEX.** The config index and the python
population come from `git ls-files`, the candidate prefilter from
`git grep --cached`, and file contents from `git cat-file --batch`, so
another agent's unstaged edit in the shared checkout can neither redden nor
green a commit. A path argument that is not in the index falls back to disk,
because a file written but not yet staged is the one a hand run cares about.
The prefilter result is intersected with this repository's own `ls-files`:
`git grep` follows `submodule.recurse`, which is set on the developer box,
and without the intersection the sweep reaches into vendored submodules —
123 of 224 candidates came from one of them when this was measured.

Scope is relational. A changed `*.py` is resolved from the file itself, so
only that file's scopes are reported. A changed path inside `aii_config/`
inverts the relation ("which code names this yaml?"), which the yaml cannot
answer, so that case falls back to the python sweep rather than checking
nothing.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7499056a9a06ebc67e4ec315cd474d25`: **1 finding**, 102 of 762 tracked
`*.py` surviving the prefilter and getting parsed, against 18 public config
yamls.
That finding, `runpod_provision.py` `_encode_config_dir()`, is listed in
`CONFIG["recorded_debt"]` so the hook ships green; the redesign is the owner's
call and the entry goes when the site changes. Whole-tree runtime 0.27 s (median of 0.30 / 0.27 / 0.27); a
single-file relation run is 0.03 s.

The finding, verbatim:

```
aii_server/dashboard/services/runpod_provision.py:146: in-flight mutation in _encode_config_dir() targets the PUBLIC layer 'pipeline/harness/execute_env.yaml'; the loader deep-merges 'pipeline/harness/execute_env.private.yaml' on top, so a key the private sibling re-declares out-ranks this rewrite. Target the private layer and fall back to public only when it is absent.
```

`_encode_config_dir` is the dashboard's fresh-RunPod launch path. It ships
every yaml under `aii_config/` including the private sibling, and
re-serializes the PUBLIC `execute_env.yaml` with `_apply_compute_floors`,
`apply_cap_to_execute_env` and `_apply_compute_tiers` applied. The public
file declares `runpod.compute_profiles: {}` while the private overlay
declares the real profiles, and `deep_merge` replaces same-named leaves
wholesale — so on a deployment carrying that overlay the owner's USD/hr
ceiling is trimmed from a dict the merge then discards.

**The fix is behavioural, not mechanical.** This is a compute-ceiling path,
money-adjacent, and repointing the rewrite at the private layer changes what
a fresh launch enforces. It is reported, not fixed, and it was not verified
end to end on a pod.

The hook still ships as `active` because it is relation-scoped: it reports
only what a changed file relates to, so this line blocks nothing but a
commit that touches `runpod_provision.py` itself. Verified — the checker run
against one unrelated staged path,
`aii_lib/src/aii_lib/dbos_app/schema_bootstrap.py`, exits 0 with no output.

Both historical regressions were re-run read-only via
`git show <rev>:<path>` into a temporary fixture and reproduce at their exact
lines: `_deploy_flow.py:258` for the public-layer shape of `bec784524^`, and
`_deploy_flow.py:253` for the dead arcname of `771f87d09^`. Both sources are
embedded in the bites test, padded so the reported line numbers are the
historical ones, so the test needs no consumer checkout. The checker is
silent on today's `_deploy_flow.py`.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: **1 finding**, the same `runpod_provision.py:146` line, whole-tree 0.25 s. The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | effect | guard |
|---|---|---|
| config root renamed | nothing resolves | skip, or exit 2 |
| overlay suffix moves | twins misderive | index collapses |
| new rewrite idiom | that scope unseen | marker list |
| whole population goes | nothing to check | two floors |
| tar drops the private layer | invariant inverts | none |

The config root disappearing from a checkout is an environment fact, not a
regression, so it prints `skipped:` and exits 0. A root that survives but
holds fewer than 5 public yamls, or a tree with fewer than 10 tracked `*.py`
mentioning a yaml suffix, is a walk that has gone blind: `cannot run:` and
exit 2.

The last row is the honest residue. If the tar filter stopped shipping
`*.private.yaml`, the public layer would become the winning layer everywhere
and this hook would report the opposite of the truth. Nothing checks that,
because the checker deliberately never looks at the private files.

## Residue

What the agent rule judged and the program does not:

- Whether the mutated KEY is actually re-declared by the private sibling.
  That needs the gitignored file. The program treats "the convention permits
  an overlay" as sufficient — stricter, and machine-independent.
- Targets computed at runtime: f-strings, `Path` arithmetic, values that
  arrive as arguments. Only literals and module-level string constants
  resolve.
- Whether the tar filter still ships the private layer at all.
- The python floor guards the whole-tree sweep only. A relation run on named
  paths judges those paths, and a collapsed tree cannot make it vacuous.

The old rule's condition also fired on `aii_launcher/src/`, where the
exec-mode override enters. The hook's glob is wider than that — every `*.py`
plus the config tree — so the launcher is covered by the population rather
than by a hand-maintained path list.
