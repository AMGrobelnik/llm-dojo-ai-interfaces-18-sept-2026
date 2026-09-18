<!-- hook: copy-exclude-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every --exclude=<pkg> on a role Dockerfile's catch-all source COPY has a later per-package COPY of that pkg in the same stage, so no package can be silently dropped from an image

Dockerfile.server:424-435 pairs 7 excludes with 7 package COPYs by hand;
Dockerfile.pipeline:141-149 pairs 5 with 5. The split exists for push cost
(per-package layers took the per-commit push from 604 MB to 35 MB per
CLAUDE.md), but its hazard is unguarded: adding --exclude=<pkg> to shrink the
catch-all without adding the matching COPY removes the package from the image
with a fully green build — the first symptom is an import error on a deployed
pod. The sibling test test_docker_heavy_layers_sit_above_source.py pins layer
ORDER and the public/ exclusion only, not exclude/COPY completeness.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docker-deploy)

Proposed command (implemented at approval):

    .venv/bin/python $RULE_DIR/scripts/check_exclude_copy_parity.py Dockerfile.server Dockerfile.pipeline  # parse catch-all COPY --exclude list, require a subsequent 'COPY <name>/' (aii_frontend counts via its --exclude=public form)

Delete-check: The split cannot be deleted — it is the measured push-cost fix, and collapsing
back to one COPY re-pushes ~1.2 GB per commit. Parity checking is the residual
cost of keeping it.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The exclude/COPY split is the measured push-cost fix and cannot be
collapsed; an --exclude without its later per-package COPY silently ships an
image missing a package. Mechanical Dockerfile parse.
- KEEP: An --exclude without its paired later COPY silently ships an image
missing a package — invisible until runtime import failure on the pod.
Dockerfile parse of exclude/COPY pairs is deterministic and cheap; the layer
split itself is a measured 604→35 MB win that cannot be reverted.
- KEEP: Parse Dockerfile COPY lines per stage: every --exclude=<pkg> must have
a later per-package COPY of <pkg> in the same stage. Line-parsing with stage
tracking is implementable; a dropped package fails loudly instead of silently
vanishing from the image.
