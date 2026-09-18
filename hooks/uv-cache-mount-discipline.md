<!-- hook: uv-cache-mount-discipline -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# In each role Dockerfile's final stage, every package-installing uv invocation carries the shared id=uv-aii cache mount, and the cache-clearing rm -rf /root/.cache/uv never carries any mount

Both halves have a measured incident. A single mount-less uv call cost 39.4 s
of PyPI round-trip on EVERY build, unnoticed until measured
(Dockerfile.server:566-572 records the history; the discover_abilities step
was 235-319 s bimodal for the same reason per CLAUDE.md). The rm side is
documented as a standing trap in both files (Dockerfile.server:586-589,
Dockerfile.pipeline:188-191): attaching a mount to it would aim the wipe at
the shared cache and destroy what makes builds fast. Scoped to final stages
deliberately — parallel build stages (e.g. frontend_python_deps,
Dockerfile.server:150-153) omit the mount arguably on purpose, since
sharing=locked would serialize stages that currently run concurrently.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docker-deploy)

Mechanism (implemented 2026-08-26, `scripts/check_uv_cache_mounts.py`):

    .venv/bin/python $RULE_DIR/scripts/check_uv_cache_mounts.py

All three role Dockerfiles are scanned, as proposed. One deliberate deviation:
the proposal required a mount for `uv pip install|uv venv`, and requiring it
for `uv venv` would be **wrong**. `Dockerfile.server:327` creates a venv with
`--system-site-packages` and carries no mount, correctly — creating a venv
downloads nothing. Only forms that can FETCH are required to cache:
`uv pip install`, `uv sync`, `uv tool install`, `uvx`, and `uv venv --seed`.
Under the proposal as written, that correct line would be the checker's first
reported defect.

Two parsing details, both measured rather than assumed. RUN blocks are joined
across backslash continuations first — every mount in these files sits on a
continuation line, so a line-oriented reader sees all five installs as
unmounted. And counts are per RUN BLOCK, not per matching line: the pipeline's
two adjacent install steps are separate blocks, which is why the count is 5
rather than the 4 a line-grep suggests.

Measured: 5 package-installing blocks, all mounted; 2 cache-clearing blocks,
neither mounted. `Dockerfile.base`'s final stage has no uv invocation and is
scanned anyway, so the first one added there is not the one nobody checks.
Bite-probed with six mutations — dropped mount, mount on the wipe, privatised
cache id and `uv venv --seed` fire; a plain unmounted `uv venv` and a
builder-stage edit correctly do not.

Delete-check: Cannot delete — BuildKit cache mounts are per-RUN by design, so the shape must
be repeated at each install site; the rule pins the one correct shape at each.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Both halves incident-backed (mount-less call cost 39.4s every build;
rm-under-mount empties the shared cache). Per-RUN repetition is forced by
BuildKit, so a shape check at each site is the only closure.
- KEEP: Both halves incident-backed (39.4s per build unnoticed; the
discover_abilities bimodality). BuildKit forces per-RUN repetition, so a
shape-check at each site is the only closure. Grep over Dockerfiles, near-zero
cost.
- KEEP: Parse RUN lines: uv install → require id=uv-aii mount; rm -rf
/root/.cache/uv → require no mount on that RUN. Both halves incident-backed
and greppable. Loud.
