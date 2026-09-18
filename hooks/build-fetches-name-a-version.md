<!-- hook: build-fetches-name-a-version -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every NEW artifact the image build downloads names an explicit version and is content-verified; the four existing moving-pointer fetches are recorded with the cost of pinning each.

A moving pointer is `releases/latest`, `${BASE}/latest`, a raw `master`
branch script, or `setup_NN.x`; the target shape is the
pinned-release-plus-sha256sum block Dockerfile.server already uses for
cloudflared.

Dockerfile.base's own header already reached this conclusion and set the
ordering — verbatim, lines 19-27: "Base images are pinned by TAG, not digest,
and that is deliberate. A digest pin would freeze the smallest part of what
this build pulls while the ``claude.ai/install.sh`` pipe, eza's
``releases/latest`` URL and three unpinned apt sources ... keep floating — so
it buys no reproducibility. ... If this image ever has to be reproducible, pin
those fetches first; the FROM lines are the last step, not the first." This
rule is that first step (and deliberately NOT the FROM-digest half, which that
comment declines on purpose). A comment-stripped scan I ran — `for f in
Dockerfile.base Dockerfile.server Dockerfile.pipeline; do grep -nE
'^[^#]*(curl|wget)' "$f" | grep -vE '^[0-9]+:\s*#' | sed 's/`#[^`]*`//g' |
grep -nE 'releases/latest|/latest"|/master/|/main/|setup_[0-9]+\.x'; done` —
returns exactly four hits and zero prose false positives: `Dockerfile.base:62
VERSION="$(curl -fsSL "${BASE}/latest")"` (Claude CLI version resolved at
build time — the binary IS sha256-checked against the manifest, so this is
integrity without reproducibility), `Dockerfile.base:96 curl -fsSL
"https://github.com/eza-community/eza/releases/latest/download/${EZA_ASSET}"`
(no version, no checksum), `Dockerfile.server:90 curl -sSf
https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh`
(installer script off a live branch; only the `--default-toolchain
leanprover/lean4:v4.14.0` argument is pinned), and `Dockerfile.server:290 curl
-fsSL https://deb.nodesource.com/setup_20.x | bash -`. The standard is already
written down one file over, at Dockerfile.server:247-250: "Pinned release +
checksum (not releases/latest): the image build must be reproducible and the
binary content-verified ... Bump deliberately: update both the version and the
sha256 together" — applied at exactly one of five download sites. Distinct
from the pending rule-build-pin-parity, which checks that versions ALREADY
pinned at several sites agree; these four have no version to disagree about.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: release-reproducibility)

Proposed command (implemented at approval):

    bash scripts/check_build_fetches_pinned.sh  # SUPERSEDED — built as scripts/check_build_fetches_pinned.py  # comment-stripped scan of Dockerfile.{base,server,pipeline} (strips leading # and the inline `# ... ` backtick form Dockerfile.base uses) for a fetch whose target resolves a moving pointer: releases/latest | "${VAR}/latest" | raw.githubusercontent.com/*/{master,main}/ | deb.nodesource.com/setup_NN.x. exit 1 listing each unless the same RUN pins a literal version AND verifies it with `sha256sum -c`

Proposed condition (SUPERSEDED — the frontmatter ships `[ "$RULES_MODE" =
all ] || git diff --cached --name-only -- "Dockerfile*" | grep -q .`,
which also runs in all-mode where this one would skip): `[ "$RULES_MODE" =
commit ] || exit 1; git diff --cached --name-only -- 'Dockerfile.base'
'Dockerfile.server' 'Dockerfile.pipeline' | grep -q .`

Delete-check: Genuinely partial-deletable, and the rule should enforce the deleted end-state
for the easy one: the eza stage is self-described "modern ls replacement (SSH
convenience)" (Dockerfile.base:85) and `git grep -rn eza -- .
':!Dockerfile.base'` finds no user anywhere in the tree — only three prose
mentions in the two role Dockerfiles' header comments. Delete the stage
instead of pinning it and one floating fetch disappears rather than being
policed. The remaining three (Claude CLI version, elan installer, NodeSource
setup script) are load-bearing and can only be pinned; the Claude one
additionally needs a bump owner, which is the honest cost to put in front of
the owner.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
$ sed -n '19,27p' Dockerfile.base # Base images are pinned by TAG, not digest,
and that is deliberate. A digest # pin would freeze the smallest part of what
this build pulls while the # ``claude.ai/install.sh`` pipe, eza's
``releases/latest`` URL and three # unpinned apt sources (including the gh
repo, which only ever carries the # newest version) keep floating — so it buys
no reproducibility. ... # If this image ever has to be reproducible, pin #
those fetches first; the FROM lines are the last step, not the first.
(verbatim at the cited lines — and it declines the FROM-digest half only, so
it is NOT a comment declaring THESE fetches deliberate) $ for f in
Dockerfile.base Dockerfile.server Dockerfile.pipeline; do grep -nE
'(curl|wget)' "$f" | grep -vE '^[0-9]+:[[:space:]]*#'; done base:62 &&
VERSION="$(curl -fsSL "${BASE}/latest")" base:96 && curl -fsSL
"https://github.com/eza-community/eza/releases/latest/download/${EZA_ASSET}"
server:90 RUN curl -sSf
https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh |
CARGO_HOME=/root/.elan sh -s -- -y --default-toolchain
leanprover/lean4:v4.14.0 server:290 && curl -fsSL
https://deb.nodesource.com/setup_20.x | bash - (all four moving-pointer sites
confirmed at the exact cited lines; Dockerfile.pipeline has ZERO curl/wget) $
sed -n '66,78p' Dockerfile.base && { [[ ${MANIFEST} =~
\"${CLAUDE_PLATFORM}\"[^}]*\"checksum\"...([a-f0-9]{64})\" ]] ... && echo
"${CHECKSUM} ${DEST}" | sha256sum -c - (confirms the proposal's own caveat:
the Claude binary IS content-verified; only its VERSION floats) $ sed -n
'96,98p' Dockerfile.base -> eza: piped straight into `tar -xz`, no checksum,
no version $ sed -n '247,250p' Dockerfile.server # Pinned release + checksum
(not releases/latest): the image build must be # reproducible and the binary
content-verified — digest cross-checked # against the GitHub release asset
digest AND an independent local hash. # Bump deliberately: update both the
version and the sha256 together. (the house standard exists verbatim, applied
at server:263 only) $ grep -rn "releases/latest\|setup_20\|elan-
init\|nodesource" --include=*.py --include=*.sh --include=*.md
.claude/skills/amg-hooks tests/ (no output — no existing test or rule
guards this) $ sed -n '1,20p' .claude/skills/amg-hooks/rules-
pending/aii/*/rule-build-pin-parity/SKILL.md => that rule compares uv:0.6.14
across 4 sites, lean4:v4.14.0 vs lean_version, lean-interact==0.10.5 vs
server_requirements.txt — all PARITY among existing pins. Confirms the
proposal's distinction: these four sites have no version to disagree about.

Corrected statement of fact:
Every citation reproduces verbatim at the exact lines given, and the
distinction from rule-build-pin-parity is correct (I read that rule's
SKILL.md: it is parity among existing pins, nothing about unpinned fetches).
Two scope notes for implementation rather than errors. (a) The proposed scan
pattern misses a fifth unpinned source that Dockerfile.base's own header names
— the gh apt repo keyring at base:121 plus the unpinned apt sources generally
— so 'four hits' is an undercount of the problem, not an overcount. (b)
Dockerfile.pipeline has zero curl/wget, so the rule bites only two files
today. Also flag the tension the rule must answer: pinning eza's
releases/latest and nodesource setup_20.x creates exactly the unserviced bump
obligation that same header uses to decline digest pins (no
renovate/dependabot here), so the rule should require version+sha256 with a
stated bump owner, or it will be waived the first time it fires.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Moving build inputs (releases/latest, ${BASE}/latest, raw master
scripts, setup_NN.x) make an image unreproducible and change silently under a
rebuild; Dockerfile.server's pinned+sha256sum cloudflared is the in-tree shape
to match. Claimed rules cover pin PARITY (rule-build-pin-parity) and git deps
(rule-git-deps-immutable-rev), not fetched artifacts.
- KEEP: Textbook ban-grep over Dockerfiles: releases/latest, ${BASE}/latest,
raw master script URLs, setup_NN.x — probe-testable, and the Dockerfile count
is the floor. Distinct from rule-build-pin-parity (one version across sites),
rule-git-deps-immutable-rev (git deps) and rule-image-installs-lock-
constrained (Python resolution); this governs artifacts curled into the image.
- KILL: 'Pin the dep' is the lens's first named keep=false case, and that is
literally the whole deliverable here. The delete-check also finds the eza
stage self-described optional and removable. Note the base images are tag-
pinned-not-digest-pinned by an explicit documented decision at
Dockerfile.base:19-27, so the rule would have to carve that out — a sign the
judgment …

OWNER-GATED (RETIRED 2026-08-26): an earlier draft made green require
pinning the four live fetches (eza releases/latest, the elan installer off
master, nodesource setup_20.x, the Claude CLI latest). The shipped checker
takes the other path — the four are RECORDED with the cost of pinning each
(below) and it exits 0 today, biting only on a NEW unpinned fetch. Pinning
any of the four stays an owner decision, taken outside this gate.

## IMPLEMENTED (2026-08-26) — four moving pointers, recorded not reported

`scripts/check_build_fetches_pinned.py` reads every fetch line in the three
tracked Dockerfiles. Four resolve a moving pointer:

| where | what it fetches |
|---|---|
| `Dockerfile.base` | Claude CLI via `${BASE}/latest` |
| `Dockerfile.base` | eza via `releases/latest` |
| `Dockerfile.server` | elan-init.sh off a `master` branch |
| `Dockerfile.server` | NodeSource `setup_20.x` |

**They are recorded, not reported, and the ordering is the owner's own.**
`Dockerfile.base`'s header argues it directly: pinning the FROM lines "would
freeze the smallest part of what this build pulls while the claude.ai
install.sh pipe, eza's releases/latest URL and three unpinned apt sources keep
floating — so it buys no reproducibility. If this image ever has to be
reproducible, pin those fetches first."

Each carries what pinning would cost. Freezing the Claude CLI freezes agent
behaviour across every image. Pinning elan risks a Lean-toolchain mismatch
against the mathlib cache, which CLAUDE.md prices at a ~1500 s rebuild. Those
are build and product decisions, not gate failures — so the gate stays green
and catches the NEXT unpinned fetch instead of re-litigating these four.

`Dockerfile.server`'s cloudflared block is the target shape and is already
there: `ARG CLOUDFLARED_VERSION` plus `sha256sum -c -`, with a comment saying
to bump both together.

Checked the other way: an accepted entry no fetch line matches any more is
reported, so the list cannot outlive its reason. Probed five ways —
`releases/latest`, a `master` script and a rolling installer are each caught,
a pinned-and-verified fetch passes, and a COMMENT quoting one of those shapes
is not counted, which matters because both this rule and Dockerfile.base quote
them while arguing against them.

Verified in a `git archive` checkout as well as locally: exit 0 in both, since
Dockerfiles are tracked and the check reads nothing off disk.
