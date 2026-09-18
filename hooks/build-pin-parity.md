<!-- hook: build-pin-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A toolchain pinned at multiple build sites carries one version everywhere: uv image tag, Lean toolchain, lean-interact, bun and python base tags

ghcr.io/astral-sh/uv:0.6.14 appears at Dockerfile.base:133,
Dockerfile.pipeline:31, Dockerfile.server:42 and :141 — four sites a bump must
hit together. Sharper: leanprover/lean4:v4.14.0 at Dockerfile.server:91 (elan
install) must equal lean_version='v4.14.0' at :115 (TempRequireProject), and
lean-interact==0.10.5 at Dockerfile.server:110 must equal .claude/skills/aii-
lean/scripts/server_requirements.txt:5 — the ~5 GB Mathlib cache is built by
one side and consumed by the other (COPY at Dockerfile.server:328), and a one-
sided bump ships a cache the runtime version won't use, resurfacing the pod-
boot cold Mathlib download that 'exceeds RunPod's container health window and
triggers a SIGTERM crash-loop' (Dockerfile.server:96-100). The failure would
look nothing like its cause and no current test compares any of these pairs.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: docker-deploy)

Mechanism (implemented 2026-08-26, `scripts/check_pin_parity.py`, 30 ms):

    .venv/bin/python $RULE_DIR/scripts/check_pin_parity.py

Python rather than the proposed bash, because measuring the tree changed the
comparison in two ways that a `grep | sort -u` cannot express.

**"One version everywhere" is wrong for `python`.** It ships as BOTH
`3.12-slim-bookworm` (4 references) and `3.12-alpine` (2), and that split is
deliberate — the alpine stages are the small frontend toolchain images. A
whole-tag comparison false-fails on it, which is what the first attempt did.
That family compares the leading numeric version and lets the variant differ;
a probe bumping one site to `3.13-alpine` still fires, so the tolerance does
not cost the check anything.

**An anchored `FROM <image>` grep under-reads by two thirds.** `FROM
--platform=$BUILDPLATFORM oven/bun:1-alpine` puts a flag between the keyword
and the image, so `grep 'FROM oven/bun:'` finds ONE bun site where there are
three — the same shape of error as the backslash-continuation miss recorded in
`rule-copy-exclude-parity`. Stage aliases are collected first so an internal
`FROM lean AS …` is not counted as an external pin.

Measured: 5 families across 19 references — `python` 6, `debian` 4, `uv` 4,
`bun` 3, `aii-base` 2 — plus the 2 cross-form pairs, all consistent today.
Bite-probed with five mutations: a one-site uv bump, a Lean toolchain bumped
without `lean_version`, `lean-interact` bumped in the requirements file only,
and a `3.12`→`3.13` drift all fire; the control — a variant change at the same
version — correctly does not.

Delete-check: Partial deletion is possible and preferable for the uv/bun/python family:
single-source them as bake variables injected as ARGs into all three
Dockerfiles, then the rule shrinks to asserting no literal pin bypasses the
ARG. The lean-interact pair cannot be ARG'd away — server_requirements.txt is
a runtime-shared file — so cross-file parity stays needed regardless.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Four uv sites plus Lean/lean-interact pairs that must move together;
single-source the uv/bun/python family via bake ARGs where possible (partial
deletion), parity-check the remainder — a split Lean pin fails at runtime
only.
- KEEP: Four uv sites plus a Lean-toolchain/lean_version pair that must move
together; a partial bump produces confusing build-time divergence. Literal
parity extraction from three Dockerfiles is cheap; prefer the ARG single-
sourcing deletion where possible.
- KEEP: Regex-extract each pinned family (uv tag, lean toolchain, lean-
interact, bun, python base) across Dockerfiles + pyproject, assert one value
per family. Prefer the partial deletion (bake ARGs) where noted, then the
check shrinks. Deterministic, loud.
