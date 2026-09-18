<!-- hook: deploy-image-refs-pinned -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: condition not mapped: 'ls aii_config/server/*.private.yaml >/dev/null 2>&1' runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every image ref in deploy config (tracked or private overlay) is an immutable 12-hex-SHA tag — never :latest

MEASURED 2026-08-28 — RED on exactly one ref, and it is machine-local.
`aii_config/server/server.private.yaml:56` pins the orchestrator template
image to `<author>/aii_pipeline:latest` (checker exit 1, re-run today)
while `execute_env.private.yaml` pins SHAs throughout. Both overlays are
gitignored, so the verdict rides on untracked per-machine state — a commit
gate cannot own it. And the consequence the proposal named does not occur on
the canonical path: `--redeploy` rewrites the shipped ref to the release SHA
(`_mutate_server_orchestrator_image` — called at `_redeploy.py:612`, defined
at `_common.py:228`; cites re-checked 2026-08-28), so the overlay's `:latest`
never reaches a pod from that flow. The audit's disposition is the second
lens' KILL: delete the vestigial overlay pin — an owner action, the file
being machine-local — after which this rule shrinks to asserting the yaml
image keys' absence.

## The original proposal (2026-08-22 measurements)

The immutability convention is stated at docker-bake.hcl:19-25 and the watcher
header, and execute_env.yaml:171-189 explains the image key lives in the
private overlay; the overlays on this machine split:
aii_config/pipeline/harness/execute_env.private.yaml pins
<author>/aii_pipeline:9b17bf654b5e throughout, while
aii_config/server/server.private.yaml:56 sets the orchestrator template image
to <author>/aii_pipeline:latest — so dashboard-provisioned orchestrator
pods track a floating pointer that only v* releases move, while the redeploy
path pins SHAs, leaving one deployment able to run two versions after a
release with no visible cause. (The verification below disproves that
consequence for the `--redeploy` path.)

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docker-deploy)

Command (checker implemented 2026-08-28 — red today on the overlay's `:latest`, which is the live split it exists to show):

    .venv/bin/python $RULE_DIR/scripts/check_image_refs_pinned.py  # every 'image:' under aii_config/ matching <author>/ must end :[0-9a-f]{12}

Condition: `ls aii_config/server/*.private.yaml >/dev/null 2>&1` — the overlay is machine-local, so the rule applies only where one exists.

Delete-check: Feasible and preferable if true: CLAUDE.md says --redeploy 'derives the image
refs from <sha>... no manual config pinning' — if the launcher genuinely
derives every ref, the yaml image keys are deletable and the rule shrinks to
asserting their absence. If the orchestrator template legitimately needs a
standing ref (fresh deploys), the rule enforces SHA form. Owner decides which
half applies.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: One overlay on this machine currently pins :latest while its sibling
pins a SHA — live drift on the immutability convention. Verify the launcher-
derives-refs claim at adoption; if true the config keys may shrink, but the
pin is needed either way.
- KILL: Wrong subject for a commit gate: the refs live in gitignored machine-
local overlays, so the check reads uncommittable per-machine state. And per
CLAUDE.md, --redeploy derives refs from the SHA anyway — verify that, delete
the vestigial overlay pins, and the dimension disappears without a rule.
- KEEP: Regex image refs in deploy config for ^[0-9a-f]{12}$ tags; skip-if-
absent for gitignored overlays. First verify the delete-check's claim that
--redeploy derives refs (if so, the tracked-config half may shrink).
Implementable, loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
The config split is real: `grep -rn "<author>/aii_" aii_config/` gives
server.private.yaml:56 `image: "<author>/aii_pipeline:latest"` against
execute_env.private.yaml:25,235,251,262,268,274 all pinned to `9b17bf654b5e`.
docker-bake.hcl:19-25 and execute_env.yaml:171-189 say what the proposal says.
BUT the stated consequence does not hold. `grep -rn
_mutate_server_orchestrator_image` shows it is called at
aii_runpod/.../deploy/_remote/_redeploy.py:574-575, inside the config tar
loop, and it

Corrected statement of fact:
Corrected fact: under the canonical `--redeploy` flow the on-disk `:latest` at
server.private.yaml:56 never reaches a pod — the shipped bytes are rewritten
to `<author>/aii_pipeline:<sha>` (_redeploy.py:574 -> _common.py:239-241) —
and `:latest` tracks the last redeploy anyway because redeploy pushes the `v*`
tag that moves it. So there is no 'two versions in one deployment' skew from
this. A LIVE defect does exist nearby, but it is a different one and the
proposal does not name it: the FRESH `--runpod` path ships every yaml verbatim
(_deploy_flow.py:266-281 — no orchestrator-image mutation at all), and worse,
its in-flight execute_env mode override is dead code — line 253 sets
`exec_env_arcname = "harness/execute_env.yaml"` while the loop computes `arc =
str(item.relative_to(config_dir))` = `pipeline/harness/execute_env.yaml`. I
ran that comparison in python: match=False. The branch still logs "Override
execute_env.mode -> ... in shipped harness/execute_env.yaml" (line 263-265)
and then ships the unmodified file, and _runpod.py:87-88 documents the
behavior that never happens ("deploy_and_run also rewrites the shipped
harness/execute_env.yaml so the orchestrator pod sees the same value"). One-
string fix, deploy-facing, no test covers it.

UPDATE 2026-08-28: the live defect the verification found nearby — the fresh
`--runpod` path's dead-code execute_env `mode` override (arcname mismatch) —
is FIXED and pinned by rule-deploy-config-single-source's
`test_the_shipped_execute_env_override_names_a_real_arcname.py`.

OWNER-GATED: the only red ref lives in gitignored machine-local config, and
`--redeploy` provably rewrites it out of the shipped bytes. The recommended
resolution is deleting the vestigial overlay pin rather than gating it —
deleting a machine-local pin is the owner's call.
