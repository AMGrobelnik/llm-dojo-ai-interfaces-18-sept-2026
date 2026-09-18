<!-- hook: private-template-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The tracked agent_backend.private.template.yaml stays disjoint from its public sibling AND covers every key path the machine's real private overlay uses

Both halves are stated invariants: the template says 'Keys here must NOT also
appear in the public agent_backend.yaml'
(agent_backend.private.template.yaml:4-6) and the public file says private
values 'NEVER appear here — not even as empty placeholders'
(agent_backend.yaml:13-18). Disjointness holds today (measured: intersection
empty). (Superseded 2026-08-26: the finding is real but the DIAGNOSIS is backwards —
cred_manager.enabled is declared in the PUBLIC sibling, so adding it to the
template would enshrine a disjointness violation. See IMPLEMENTED at the end.)

Completeness is BROKEN today: the local agent_backend.private.yaml
carries cred_manager.enabled, absent from the template — a fresh machine
following the template silently runs without that dimension, the same
discover-only-when-it-dies bootstrap failure CLAUDE.md's worktree section
documents for missing overlays.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: config-yaml)

Proposed command (implemented at approval):

    .venv/bin/python $RULE_DIR/scripts/check_private_template_parity.py  # (a) template leaf paths ∩ public leaf paths == ∅; (b) if the gitignored agent_backend.private.yaml exists on disk, its leaf paths ⊆ template's (values never read); (b) auto-skips where absent (CI)

Delete-check: Deleting the template would leave the private file's shape documented nowhere
machine-readable — agent_backend lands in PipelineConfig as an untyped dict
(pipeline_config.py:225), so the <REQUIRED> sentinel mechanism cannot cover
it. The real deletion play is typing the agent_backend block so pydantic owns
the shape; until that refactor, the template is the only bootstrap surface and
parity is the honest check.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Both halves are stated invariants (disjointness in both files' prose)
and the private overlay's shape is machine-readable nowhere else — it lands in
an untyped dict. Credential-adjacent config hygiene.
- KEEP: Disjointness half is repo-state, cheap, and guards a stated both-sides
invariant on credential-adjacent config. The coverage half reads the machine-
local overlay — make it skip-if-absent so worktrees and CI don't false-fail.
Combined cost is small for a real drift channel.
- KEEP: Disjointness half (template key-paths ∩ public key-paths = ∅) is pure
commit content — deterministic yaml key-set math. The coverage-of-real-overlay
half reads a gitignored local file: run skip-if-absent. Both implementable,
failures loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
The two quotes are verbatim and the line anchors are right:
agent_backend.private.template.yaml:4-6 says 'Keys here must NOT also appear
in the public ``agent_backend.yaml`` — public defaults and private secrets are
strictly disjoint'; agent_backend.yaml:13-18 says private values '... NEVER
appear here — not even as empty placeholders'. I computed leaf-path sets for
all three files with yaml.safe_load: public=20 leaves, template=4, private=5.
Results: `template ∩ public = []` (the disjointness t

Corrected statement of fact:
Disjointness does NOT hold today — the proposal measured template∩public
(empty) and reported it as the invariant, but the invariant is stated over the
private FILE, and private∩public = {cred_manager.enabled}. The completeness
observation (private carries a key the template lacks) is factually correct,
but its consequence is wrong: the public file declares cred_manager.enabled:
false explicitly at agent_backend.yaml:95-96, and the private file's own
comment at :61-64 documents the override as an intentional per-host runtime
toggle. Broader: overriding a public default from a private sibling is this
repo's normal practice (execute_env overlaps 32 of 33 public keys;
pipeline.private.yaml fills the documented `<REQUIRED>` sentinels), so the
'strictly disjoint' prose is the outlier. The live defect is that prose: the
template's lines 4-6 and agent_backend.yaml's 13-18 assert an invariant the
repo — including agent_backend's own private file — does not follow. Fix by
narrowing the statement to 'secrets/PII must never appear in the public file'
(which does hold) rather than 'keys must be disjoint'.

## SIX OVERLAYS HAVE NO TEMPLATE AT ALL (measured 2026-08-26)

This rule asks whether the one template that exists is complete. Measured
against the tree, that is one seventh of the surface:

| overlay | template | tracked docs naming it |
|---|---|---|
| `agent_backend.private.yaml` | yes | 4 |
| `server.private.yaml` | no | 5 |
| `execute_env.private.yaml` | no | 3 |
| `pipeline.private.yaml` | no | 2 |
| `free_router_keys.private.yaml` | no | 1 |
| `sinks.private.yaml` | no | **0** |
| `llm_helper_backend.private.yaml` | no | **0** |

CLAUDE.md's worktree section says a checkout without these "dies in pydantic
with `Unfilled required config keys` (`init.run_dir`,
`gen_paper_repo.github.commit_author_{name,email}`)". Both of those keys live in
`pipeline.private.yaml` — which has no template. So the file whose absence
produces the documented bootstrap failure is the one with nothing describing its
shape, and two further overlays are named in no tracked document at all.

This does not widen the rule's statement, and is recorded rather than acted on
for a reason: whether each overlay SHOULD have a template is a judgement per
file. `free_router_keys` is pure credentials, where a template lists key names
and nothing else; `sinks` may be genuinely optional. Deciding that is the
owner's, and writing six templates from the local copies would also mean
deciding what in them is structure and what is a secret.

What the measurement does settle is the scope question this rule leaves open.
Its value is not "keep one template honest" — it is that six of seven overlays
have no machine-readable shape, and the existing gap the body already names
(`cred_manager.enabled` missing from the one template) is the smallest instance
of it.

## IMPLEMENTED (2026-08-26) — the finding is real, the diagnosis was backwards

`scripts/check_private_template_parity.py` compares on LEAF paths. A naive
path-set intersection reports `terminal_claude_agent` as an overlap; that is the
container both files nest under, not a duplicated setting, and counting it
reports a violation of an invariant that holds.

**This body says completeness is broken because the overlay carries
`cred_manager.enabled` and the template does not. Measured, the key is declared
in the PUBLIC sibling** — `agent_backend.yaml:95`, `enabled: false`, commented
"DEFAULT OFF" — and this machine's overlay sets it `true`. So the two remedies
the body implies are both wrong:

- adding it to the template enshrines a DISJOINTNESS violation, which the
  template's own header forbids;
- removing it from the overlay turns the credential manager off on this machine.

The key is genuinely per-machine, which the same header explicitly allows
("secret / PII / per-machine values"). So the two sentences in that header
disagree for exactly one key. Resolving it — relax "must not appear in public"
for per-machine toggles, or move the toggle to an env var — is an owner call
between two stated invariants, not a parity repair. It sits in
`KNOWN_CONFLICTS` with that evidence, checked the other way so it cannot outlive
its cause.

**In CI it reports cannot-run.** The overlay is gitignored, so a worktree has
none and the completeness half reads nothing; the floor refuses to certify what
it did not read. Verified in a `git archive HEAD` tree and recorded in
`_MAY_NOT_RUN`.

Measured 2026-08-26: 1 template, 6 template keys, 8 overlay keys, 0 leaf-level
disjointness violations, 1 recorded conflict.
