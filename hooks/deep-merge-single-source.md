<!-- hook: deep-merge-single-source -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Exactly one deep-merge implementation exists in the workspace: aii_lib.utils.config_overrides.deep_merge — PipelineConfig._deep_merge is deleted and its callers import the canonical one

Config merge semantics decide WHICH VALUE WINS. Two copies of them is history
defect class #1 (twin implementations drift: 584f91167, 69279ba42) — if one
copy's list/dict handling ever changes, the pipeline loader and every other
overlay consumer silently resolve the same YAML to different configs, and
nothing fails loudly enough to notice.

The canonical door is `aii_lib/src/aii_lib/utils/config_overrides.py:40`,
pinned by `rule-lib-config-merge-paths` and already imported by the pipeline
loader for `load_config_with_overrides` — so the import direction predates
this rule.

`claude_cred_manager/src/claude_cred_manager/config.py` keeps its own copy by
a documented service-isolation decision (separate deploy unit, not a workspace
member per `pyproject [tool.uv.workspace]`). The exemption is structural, not
an allowlist entry: that path is simply absent from the command's pathspec, so
it cannot be forgotten into scope.

## Why the command excludes the canonical file rather than counting to one

A count-to-one check (`[ "$(grep -rl …)" = <the one path> ]`) passes only while
the answer is *exactly* that string, so it also fails when the canonical file
moves — a rename that keeps the invariant would read as a violation. Naming
the ONE legal definition as a pathspec exclusion and banning every other match
says the same thing and degrades correctly: a new twin anywhere under the five
package roots is a hit, wherever it is put. `--tree` because the stock is clean
(hit count 0), so a pre-existing violation blocks instead of riding as an
advisory.

## LANDED 2026-09-04

**Deleted:** `PipelineConfig._deep_merge`
(`aii_pipeline/src/aii_pipeline/utils/pipeline_config.py`, the staticmethod at
:522 plus its self-recursive call). Both call sites in `from_yaml` — the
`harness/<name>.yaml` per-top-key merge and the `pipeline.yaml` + `io/*.yaml`
root merge — now call the canonical `deep_merge`, added to the function-local
`from aii_lib.utils.config_overrides import …` already present in that method.
`rule-pipeline-config-load-bind`'s `test_config_overrides_policy.py` built its
overlay through the twin and was repointed at the canonical import.

**Measured before deleting, because "byte-equivalent semantics" was a claim,
not a measurement.** The two bodies differ textually — the twin guards
`key in result and isinstance(result[key], dict)` where the canonical writes
`isinstance(out.get(k), dict)` — but `dict.get` returns `None` for an absent
key and `isinstance(None, dict)` is False, so the two predicates are the same
predicate; the rest (shallow copy of base, replace-otherwise, new dict per
level) is identical. Confirmed empirically at 200,140 comparisons, 0
differences, checking result value, dict KEY ORDER at every level, exception
behaviour, and non-mutation of both inputs:

| population | cases | differences |
|---|---|---|
| pairs the real loader passes | 113 | 0 |
| adversarial, hand-written | 27 | 0 |
| randomized nested-tree fuzz | 200,000 | 0 |

The adversarial set covers None / list / scalar overriding a dict and the
reverse, an empty dict either side, three-level nesting, a `Mapping` that is
not a `dict`, non-`str` keys, a key the base lacks, a key the overlay lacks,
and an overlay that reorders the base's keys.

The 113 real pairs were captured by wrapping the staticmethod while running
`PipelineConfig.from_yaml` over canonical `aii_config/pipeline/`, over a
per-preset overlay dir built the way `_bootstrap._default_preset_overlay`
builds one (`frontend/config.yaml` + each of the four presets, sparsed with
`deep_diff`), over raw `frontend/config.yaml`, and over a `harness/` +
`io/sinks.yaml` overlay that exercises the other call site.

**Proved the collapse changed nothing observable:** the fully-resolved
`PipelineConfig.model_dump(mode="json")` for all seven scenarios, dumped
before and after, `cmp`-identical (28,777 / 25,829 / 28,775 / 25,837 / 25,853
/ 25,885 / 25,830 bytes; directory sha256
`d02d128f2d3ee9356392cbd5497100409e0968d55ac4eaa7b9571f5ef58d0757` both
sides). The dumps are non-degenerate — each overlay scenario differs from
canonical by 2-64 lines — so the equality is evidence, not two empty runs.

Delete-check: Deletion WAS the rule: PipelineConfig._deep_merge is gone and the command
enforces the deleted end-state (every definition except the canonical one is a hit).
