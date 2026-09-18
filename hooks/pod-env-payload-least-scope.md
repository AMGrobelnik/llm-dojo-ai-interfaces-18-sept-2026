<!-- hook: pod-env-payload-least-scope -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Pod launches ship least-scope env: every POD_ENV_ALLOWLIST key keeps a verified pod-side reader, and encode_env_full stays confined to the two server-pod deploy call sites

Pod launches ship least-scope env: every POD_ENV_ALLOWLIST key keeps a
verified pod-side reader (aii_pipeline / aii_lib / .claude/skills), and
encode_env_full stays confined to the two server-pod deploy call sites — no
pipeline/orchestrator/worker path ever receives the full .env.

aii_runpod/src/aii_runpod/deploy/env_payload.py:36-38 states the contract
('Env vars with a verified pod-side reader ... when adding a key, cite the
file that reads it') and the checker below enforces it. Measured 2026-08-28:
all 22 allowlist keys (env_payload.py:39-113) have >=1 reader in
aii_pipeline/aii_lib/.claude/skills (e.g. HF_TOKEN 9 files, EXA_API_KEY 3
files) — green, so the rule catches future scope creep, not a backlog. The
23rd key the proposal counted, DROPBOX_TOKEN, left the list on 2026-08-27
(e4d77354b, 'the pod env payload stops shipping a key nothing reads') — the
contract doing exactly what this rule pins. encode_env_full
(env_payload.py:116; whole .env incl. DJANGO_SECRET_KEY, EMAIL_HOST_*,
CLOUDFLARE_TUNNEL_TOKEN per its docstring) has exactly 2 call sites, both
server-pod deploys: _remote/_deploy_flow.py:296 and _remote/_redeploy.py:620;
every non-server path uses encode_env_allowlisted
(pod_infra/_worker_pod/_spawn.py:133, aii_server/dashboard/services/
runpod_provision.py:695, _deploy_flow.py:297). Existing
rule-pod-boot-handoff-parity pins only the AII_ENV_B64 variable-name handoff
and the CRED_MANAGER pair's presence (test_env_payload.py), not reader-
liveness or full-encoder confinement. KILLED-slug note: rule-env-keys-live
swept the untracked operator .env for any-reference liveness — different
artifact (tracked frozenset vs .env) and different failure mode (over-scoped
pod credentials vs dead keys); the mechanism here is a scoped reader-grep plus
a pinned call-site set, which that killed rule never had.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: access-parity)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/check_env_payload_scope.py  # (a) each POD_ENV_ALLOWLIST key referenced in aii_pipeline/ aii_lib/ .claude/skills/ outside env_payload.py; (b) grep call sites of encode_env_full == {_deploy_flow.py, _redeploy.py}

Proposed condition: `none — the check is a sub-second grep, run every time`


## IMPLEMENTED 2026-08-26 — `scripts/check_env_payload_scope.py`

    .venv/bin/python $RULE_DIR/scripts/check_env_payload_scope.py

Arrives green: 23 allowlist keys, every one with a pod-side mention, and both
`encode_env_full` call sites inside the two server-pod deploy modules. Cited
call-site lines drift — the redeploy site was `_redeploy.py:583` at proposal
time and is `:620` today — which is why the check finds callers by scanning
rather than by line.

**The reader corpus excludes `.claude/skills/amg-hooks/`** (since
2026-08-28). The verification below found that the three-tree scope includes
the rule engine's own tests, so a key mentioned solely in
`test_env_payload.py` would self-satisfy the check; the engine tree is not a
pod-side consumer and is left out of the mention grep. Re-run after the
change: 22 keys, all still backed outside the engine tree, exit 0.

**The reader check is a MENTION, not a proven read, and it says so.** It asserts
the key name appears somewhere under `aii_pipeline/`, `aii_lib/` or
`.claude/skills/` — the exact three trees the contract comment tells an author
to grep. A key mentioned only in a comment would pass. That is deliberate: the
cheap check catches the case worth catching, a key with NO pod-side trace at
all, without pretending to prove consumption.

**`POD_ENV_ALLOWLIST` is an `AnnAssign`**, not a plain assignment, so both
shapes are read. A checker handling only `ast.Assign` parses zero keys — and
zero keys would otherwise read as a clean sweep, which is what the floor exists
to stop. This is the second rule this session where that same shape mattered.

Verified it is not passing vacuously: the run takes 0.1 s, which looked too
fast, so it was instrumented — 1,941 pod-side files enumerated and read, 23 keys
parsed.

Probed six ways: an allowlist key with no pod-side trace, and an
`encode_env_full` call outside the two sanctioned modules, both fire; the real
allowlist, a plain-`Assign` declaration, a sanctioned caller, and a test calling
the full encoder all pass.

Delete-check: Deleting the allowlist means shipping the full .env to every pod — strictly
wider credential scope, so the dimension cannot be deleted; the allowlist IS
the deletion of unneeded scope. What CAN be deleted is any key whose reader
disappears, which is exactly what the check detects — the rule enforces that
reader-less keys leave the list.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Least-privilege config with the contract already written in
env_payload.py's own comment but unenforced; verified 23/23 keys have readers
today, so this locks a currently-clean high-stakes surface (full .env confined
to two call sites). No claimed rule covers the allowlist's reader-liveness or
encode_env_full confinement.
- KEEP: Least-privilege config contract stated in env_payload.py but
unenforced; reader-existence grep plus confining encode_env_full to its two
call sites is cheap, and the failure mode is a worker path silently receiving
the full .env.
- KEEP: Least-scope config at the deploy boundary; per-key reader grep +
encode_env_full call-site confinement are both closed and loud. Killed rule-
env-keys-live was repo-wide .env liveness — this is scope-confinement of what
ships to pods, a different mechanism and surface, stated explicitly as
required for a killed-adjacent dimension.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Structural claims all confirmed. AST-parsed POD_ENV_ALLOWLIST -> exactly 23
keys. Ran `git grep -lw <key> -- aii_pipeline aii_lib .claude/skills` for all
23: every key has >=1 reader, MISSING list empty — green today as claimed.
Contract docstring is verbatim but at env_payload.py:36-38, not 37-38: "Env
vars with a verified pod-side reader. One consumer note per entry — when
adding a key, cite the file that reads it".

Corrected statement of fact:
Fix the citations and drop the invented counts: the contract docstring is
env_payload.py:36-38 (not 37-38), HF_TOKEN has 10 reader files in the stated
scope (not 29), EXA_API_KEY has 3 (not 1). Everything load-bearing — 23 keys,
all with >=1 reader, encode_env_full confined to _deploy_flow.py:291 and
_redeploy.py:583, all three non-server paths on encode_env_allowlisted,
existing parity test covering neither dimension — re-measured and holds. One
mechanization caveat the body should carry, because the pending check script
(rules-pending/.../SKILL.md:30) excludes only env_payload.py from the reader
grep: the scope includes .claude/skills/, which contains the rule engine's OWN
tests, so a future key mentioned solely in test_env_payload.py would self-
satisfy the check. I measured this specifically — re-running the scan while
filtering out any path containing amg-hooks leaves all 23 keys still
backed by a real reader, so it is latent, not live. The grep should exclude
.claude/skills/amg-hooks/ as well as env_payload.py. No live defect
otherwise: this pins a currently-green invariant.
