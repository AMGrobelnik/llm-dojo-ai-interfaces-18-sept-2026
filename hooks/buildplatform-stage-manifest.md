<!-- hook: buildplatform-stage-manifest -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Each build stage's platform pin matches a declared manifest

Each build stage's platform pin matches a declared manifest:
arch-independent-output stages stay on $BUILDPLATFORM, and arch-dependent
ones (mathlib_warmup, tex, builder, lean, frontend_prod_deps) never gain
it. The check parses FROM lines against the manifest only — the pinned
tool-binary aliases (uv_bin, bun_bin) are themselves manifest entries and
so keep their pins, but a `COPY --from` naming an external image directly
inside a $BUILDPLATFORM stage is NOT inspected; that discipline is the
manifest's recorded rationale, not something the script verifies.

Both recorded build-outage classes are this invariant breaking.
Dockerfile.base:38-43: the upstream installer executing an amd64 Bun binary
under QEMU crashed 175 consecutive builds with nothing published (fixed by
pinning the claude stage to $BUILDPLATFORM). Dockerfile.server:136-140: a bare
COPY --from of an external image resolved for the TARGET platform, landing an
amd64 uv in an arm64 stage — '/bin/uv: line 1: ELF: not found', 'Measured, not
guessed'. The doctrine ('only works for stages whose OUTPUT is arch-
independent... tex and mathlib_warmup cannot follow it') lives in CLAUDE.md
prose and comments only; a well-meaning 'speed up the build' edit adding
$BUILDPLATFORM to mathlib_warmup would ship an aarch64-built cache into the
amd64 image with a green build.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docker-deploy)

Proposed command (implemented at approval):

    .venv/bin/python $RULE_DIR/scripts/check_stage_platforms.py --manifest $RULE_DIR/stage_platforms.yaml  # parse FROM/--platform across Dockerfile.*, diff against manifest

Delete-check: Cannot delete — the host is aarch64 and the sole published arch is amd64, so
the native/emulated split is forced by hardware. The manifest
($RULE_DIR/stage_platforms.yaml) makes the classification explicit; an
unclassified new stage fails until it is placed on one side.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Both recorded build-outage classes (175 consecutive failed builds;
cross-arch COPY) are this invariant breaking, and the native/emulated split is
forced by hardware. Manifest maintenance is justified by outage cost.
- KEEP: Both recorded build-outage classes (175 consecutive failed builds; the
bare COPY of an arch-wrong binary) are this invariant breaking, and the
aarch64-host/amd64-target split is permanent. The manifest is small, stable,
and machine-checkable against the Dockerfiles.
- KEEP: Parse FROM/--platform per stage against a checked-in manifest;
unlisted new stages fail (no vacuity). Two recorded build-outage classes are
exactly this invariant. Implementable.
