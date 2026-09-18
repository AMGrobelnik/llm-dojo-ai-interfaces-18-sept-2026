# The published platform set stays exactly linux/amd64 on every build surface

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The repo publishes one architecture. `ARCHES=(amd64)` in the image watcher
since 2026-08-04; the watcher log holds 934 `*-arm64` tags, every one of them
predating that line, and the last arm64 push is
`aii_pipeline:32e866abf40e-arm64` at 2026-08-04 20:56:07. That was a whole
architecture built and pushed that nothing pulled — RunPod hosts are amd64.

The bake default followed in `69499519d` ("default PLATFORMS to amd64 — the
only arch anything pulls"), after `95f14d4e9` found that `--rebuild --local`
"built BOTH arches while announcing one". The build host is aarch64, so the
arm64 half was a native build with no consumer while the amd64 half — the one
that ships — ran under emulation.

A quiet re-add is expensive and silent. It doubles the emulated build and the
push bytes on a home uplink where Docker Hub's blob-session limit already
bites, and the keepalive derives the arch it warms by parsing the watcher's
`ARCHES` line, so drift there also desynchronizes the only automatic writer of
the registry buildcache.

The decision is written down three times — the watcher pin, the bake default,
the launcher's explicit `PLATFORMS` env — and an independent re-measurement of
the original rule found the third copy missing from its own statement, free to
drift. That is what makes this a set, not a literal.

## Mechanism

Three layers, because no one of them catches what the others do.

| failure mode | layer |
|---|---|
| a pin deleted or widened | 1: the pin set |
| a retired-arch token on a known surface | 2: strict scan |
| a brand-new build surface adds the arch | 3: content sweep |
| a pin file renamed or deleted | exit 2 |
| the sweep sees nothing | exit 2 |

**Layer 1 — the pin set.** The three literals that declare the platform set
(`ARCHES=(amd64)`, the bake `PLATFORMS` default, the launcher's `PLATFORMS`
env) must still be present and unwidened. Paths are unavoidable here, so each
is guarded: a pin file that has vanished is exit 2, never a pass. Because the
three are one decision written three times, all three are verified whenever
any build surface is named — that is the relation, and it is why the scope is
`relation` rather than `file`.

**Layer 2 — strict surfaces.** On the five known build surfaces (the three
pin files plus the two bake callers that deliberately inherit the default) no
`arm64`/`aarch64` token may appear in live code at all. Blunt on purpose and
cheap: on those files any live mention is either the retired arch returning or
prose that belongs in a comment. This layer runs per file, on the files under
judgment.

**Layer 3 — the declaration sweep.** Every `linux/<arch>` literal and every
`ARCHES=(...)` array in a tracked non-doc file must name an allowed arch. The
population is discovered by CONTENT — `git grep --cached -lI` over the index —
so a fourth build surface is covered the day it is written, with no edit to
the checker. With no path arguments it sweeps the whole tree; with path
arguments it reads exactly those files. The bites test
`test_a_brand_new_build_surface_is_covered_with_no_checker_edit` pins that
generality with a `ci/publish.yml` that appears nowhere in CONFIG.

**The split.** Layers 1 and 2 are addressed by path, so they are per-file work
that lefthook's `{staged_files}` narrows for free; layer 3 has no fixed
population at all, so it is a whole-tree sweep by nature and degrades to the
named files when the hook passes them. Keeping `{staged_files}` on the
fragment buys the common case; a bare whole-tree run costs 0.3 s and is the
form layer 3 was designed for.

**Prose is not a declaration.** Both the bake comment and `deploy.py`'s module
docstring narrate the retirement. Comments are stripped, and python docstring
spans are masked via `ast` — masking only docstrings, rather than every string
literal, cannot hide a real code token. A `#` inside quotes or glued to code
is not a comment: `${var#suffix}` keeps everything after it, which
`test_a_hash_glued_to_code_is_not_a_comment` pins.

**A multi-arch builder stage is legitimate.** `Dockerfile.base` maps
`TARGETARCH` case arms on a host that is genuinely aarch64. Layer 3 reads only
`linux/<arch>` literals against an architecture vocabulary, so a case arm is
not a declaration, and `Dockerfile.base` is outside the strict list for that
reason.

All content is read from the INDEX (`git ls-files -s` plus one
`git cat-file --batch`), never the working tree: this checkout is shared and
another agent's unstaged edit is not what the commit contains. A path named on
the command line that the index does not hold falls back to disk, so a human
checking a file just written is not met with silence.

## Stock

**0 findings.** Measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7499056a9a06ebc67e4ec315cd474d25` on 2026-09-08, reading the index.

Whole-tree runtime: 0.27 s median of three (0.24 / 0.27 / 0.28), six git
subprocesses. A per-file run as lefthook invokes it costs 0.02 s.

The layer-3 population is 8 files matched by content, 5 of which declare a
platform. Every declaration is `amd64`:

- `aii_launcher/src/aii_launcher/deploy.py:265`, `:282`, `:390`
- `docker-bake.hcl:47`
- `scripts/local/build_push_image.sh:122`
- `scripts/local/verify_image_private_imports.py:99`
- `scripts/local/watchers/aii-image-watcher.sh:33`

The fourth of those is a surface the original rule's fixed three-file list
never covered. The three matched files that declare nothing are
`Dockerfile.base` (a comment plus `TARGETARCH` case arms),
`aii_lib/.../_browser_login/_helpers.py` (docstrings about chromium arch
layouts) and `aii_pipeline/.../_bundles/_registry.py` (one docstring).

The population is read from the shared index, so it moves: a run minutes
earlier saw 9 files, the extra one being `aii_pipeline/.../bundles.py`, staged
by another agent between the two runs. The floor of 3 declaring files is what
makes that movement safe to tolerate.

Historical reproduction, as evidence the check bites on the real regression:
`docker-bake.hcl` from `69499519d^` — the last commit that published both
architectures — fires all three layers at once, `docker-bake.hcl:1: pin gone
or changed`, `:32: retired arch back on a publishing surface` and
`:32: publishes platform 'arm64'`. That file is embedded verbatim in the bites
test, so the test needs no consumer checkout.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: **0 findings**, whole-tree 0.21 s. The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | effect | guard |
|---|---|---|
| a pin file renamed | layer 1 blind | exit 2 names it |
| a build surface deleted | layers 1-2 blind | exit 2 names it |
| the tree stops declaring | layer 3 blind | floor of 3 |
| `git grep` unavailable | no population | exit 2 |
| the hook vendored elsewhere | nothing to check | `skipped:` |

A pin whose path moves is re-pointed in `CONFIG["pins"]`, not deleted. Adding
an architecture is the deliberate two-sided edit this exists to force: widen
`CONFIG["allowed_arches"]` in the same commit that adds the consumer, and the
pins follow.

Narrowing `CONFIG["retired_arch_tokens"]` or widening
`CONFIG["sweep_excludes"]` both make a layer stop biting without any test
failing, which is why each carries a comment in the dict saying so.

## Residue

The rule as an agent judgement covered a little more than the program does,
deliberately:

- A platform set assembled at runtime from variables
  (`PLATFORMS="linux/$a,linux/$b"`) names no literal, so layer 3 cannot see
  it. The strict layer over the five known surfaces is the backstop, and the
  min-declaring floor makes a wholesale disappearance loud.
- A tool that publishes an image while naming no platform literal at all is
  outside every layer.
- `*.md` and `.claude/` are excluded from the sweep by directory convention,
  so a build surface hidden in markdown is missed. It is prose by definition.
- Whether an architecture is worth publishing is not judged here. The check
  only holds the three pins and every declaration in the tree to one answer.

Scope note: this stays in the `research-monorepo` set. The pins, the paths and the
measurement are all specific to this repo's build layout.

Distinct from the pending `buildplatform-stage-manifest`, which pins per-stage
`$BUILDPLATFORM` usage inside Dockerfiles — a different question from the
published platform matrix.
