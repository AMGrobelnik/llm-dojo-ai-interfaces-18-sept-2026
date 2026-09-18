<!-- hook: builder-prewarm-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every workspace package installed editable in a role Dockerfile's final stage is pre-warmed in its builder stage (stub COPY, matching extras) or named on the pinned no-prewarm list with its reason

The point: a new final-stage `-e` cannot silently move its closure's
resolution into the per-commit layer.

The exact regression this catches is documented and was expensive: before
aii_pipeline was pre-warmed in Dockerfile.server's builder, its closure
resolved in the final stage at 'Prepared 37 packages in 3m 43s' on EVERY
commit, under QEMU, landing in a layer that then re-pushed
(Dockerfile.server:44-54, CLAUDE.md '265 s -> ~50 s'). Current parity is
deliberate and only comment-pinned: server builder installs aii_lib[ability-
server]+aii_runpod+aii_pipeline (Dockerfile.server:66-74) vs final's six -e
(line 483), with the delta {aii_server, aii_launcher, claude_cred_manager}
justified at lines 60-65; pipeline builder (Dockerfile.pipeline:34-42) vs
final (line 150), delta {aii_launcher} (declares no deps). A seventh -e added
at line 483 without a stub restores the slow path with a green build — nothing
fails, the layer just gets 3+ min and megabytes heavier per commit. Also
checks the extra matches (ability-server/agent-runtime) between the two
invocations, since an extras drift leaks part of the closure downstream the
same way.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: docker-layer-economics)

Mechanism (implemented 2026-08-26, `scripts/check_builder_prewarm_parity.py`
plus its pinned `scripts/prewarm_exceptions.yaml`):

    .venv/bin/python $RULE_DIR/scripts/check_builder_prewarm_parity.py \
        --manifest $RULE_DIR/scripts/prewarm_exceptions.yaml

Arrives green. Measured: server builder 3 editable installs, final 6, delta 3
— all pinned; pipeline builder 3, final 4, delta 1 — pinned.

**Only `--system` installs count, and missing that reports four phantoms.**
These files run eight `uv pip install` commands: four with `--system` into the
image's own site-packages, and four with `--python=<path>` into a venv, three
of them the ability-client venv which has its own pre-warming in the hoisted
block. The unscoped version reported `aii_lib[ability-client]` as un-warmed in
both files, which is wrong — it is installed elsewhere.

The manifest pins the deliberate exceptions with a FACT per package rather
than a preference, each verified by reading its pyproject: `aii_launcher`
declares 0 dependencies, `claude_cred_manager` 5 and `aii_server` 9, all
already covered by `aii_lib[ability-server]`'s 17 — and `aii_server` is the one
package with a flat `where = ["."]` layout, so its stub cannot be one mkdir +
touch. It is checked in BOTH directions, so an exemption cannot outlive the
arrangement that earned it.

Extras are part of the identity: `aii_lib[ability-server]` and
`aii_lib[dashboard]` resolve different closures, so the comparison key keeps
them. Probed four ways — a new unpinned `-e`, a stale pinned entry, and a
builder/final extras mismatch all fire; the current tree does not.

Superseded proposal:

    $RULE_DIR/scripts/check_builder_prewarm_parity.py  # per role Dockerfile: parse builder-stage and final-stage `uv pip install ... -e` sets incl. extras; assert final − builder ⊆ pinned exceptions {server: aii_server,aii_launcher,claude_cred_manager; pipeline: aii_launcher} and extras agree on the intersection

Proposed condition: `git diff --cached --name-only -- 'Dockerfile.*' | grep -q .`

Delete-check: Cannot delete the pre-warm: it exists precisely because the final stage sits
below the source COPYs, so its installs re-run per commit — the 3m43s
measurement is the cost of the deleted state. The exception list is the
deletable part: shrinking it (e.g. stub-pre-warming aii_server despite its
flat layout) only tightens the rule.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Incident-backed (3m43s per-commit QEMU resolution until the prewarm
landed) and regression-shaped: a NEW final-stage -e silently reintroduces the
cost with no build failure. Enforced rule-docker-image-guards pins named
guards, not the prewarm-parity derivation; this is a genuine closed-world
extension worth its own check. Could live as a test in that group — acceptable
either way, keep the …
- KEEP: Pins a measured 3m43s-per-commit-under-QEMU regression class that
returns silently with any new final-stage -e install; Dockerfile parse is
contained and the no-prewarm allowlist keeps false positives out.
- KEEP: Documented 3m43s-per-commit regression class; Dockerfile parse pairing
final-stage -e installs to builder-stage prewarm blocks (or pinned no-prewarm
list) is closed-world — a NEW editable install cannot escape because detection
keys on the -e lines themselves.
