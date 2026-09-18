<!-- hook: docker-context-no-credentials -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every credential-bearing file present on disk (.env at any depth, aii_config *.private.yaml, cookies.txt, .mcp.json) is excluded from every role build context, re-include rules notwithstanding

Both Docker Hub repos are public (aii-image-watcher.sh:98-99 relies on it for
anonymous probes), so anything the context admits is published. The trap is
documented but pinned only in one narrow shape:
Dockerfile.server.dockerignore:255-258 explains that a '!' re-include of a
skill ROOT would out-rank '**/.env' and bake a live Dropbox refresh token, and
test_skill_local_env_never_enters_the_image pins exactly that amg-dropbox path
and nothing else. The role ignore files are hand-mirrored and drift
independently (diff of server vs pipeline ignores shows disjoint editing), and
the global .dockerignore:143-150 mirrors the .env family 'for a bare docker
build' by hand. A future '!' re-include elsewhere, or a pattern missed in one
of the three files, has no guard; this evaluates the real on-disk files
against the real matchers instead of policing pattern text.

Mechanism (implemented 2026-08-26, `scripts/check_credential_reachability.py`):

    .venv/bin/python $RULE_DIR/scripts/check_credential_reachability.py

**Measured, and the reassuring half first: ZERO actual credentials are
admitted.** Everything that genuinely holds values — the root `.env`, the
seven `aii_config` overlays, `cookies.txt` and the skills' own `.env` files —
is excluded by both role matchers today.

39 files match the credential-shaped names and 21 are admitted, but none of
those 21 carries a value: 16 are `.mcp.json` under
`.claude/plugins/marketplaces/` (vendored third-party manifests whose secrets
are `${ENV_VAR}` references), 4 are `.env.template`/`.env.example`, and 1 is a
root `*.private.yaml` scratch bundle whose five secret-shaped keys all hold
PROSE — 7 to 19 words each, describing credential state — and which `gitleaks`
passes clean. Flagging all 21 would leave the guard permanently red on files
that carry nothing, which is how a guard teaches its reader to ignore it, so
templates and the vendored tree are exempt by path shape, stated in the script
rather than hidden.

**It arrives RED on exactly one file** — `run_OQqS4CxS0UNl_reuse.private.yaml`,
admitted by both matchers. The fix is to widen the ignore patterns to cover a
root-level `*.private.yaml`, which is the owner-gated dockerignore change
already on the list; excluding more is additive and cannot break a build, but
it is a change to what the published images are built from, so it is stated
rather than made. Note the file is prose-only and gitleaks-clean, so nothing
is leaking today — this is hygiene, not an incident.

It must walk the FILESYSTEM, not git: every file it cares about is gitignored
by design, so a git-based listing returns an empty set and reports a clean
sweep. That is the legitimate exception to
`rule-guards-ask-git-what-is-tracked` — a docker build context IS the
filesystem.

A clean result and a broken walk both look like zero findings, so the check
needs a way to tell them apart. `main()` already requires `<repo>/.env` to
exist before it scans at all, so the walk is proven intact iff `.env` shows up
among the candidates that walk actually returns; it bails "the walk broke"
only when it does not. This sentinel is deterministic and holds regardless of
how many other credential-shaped files happen to sit in a given checkout — a
fresh git worktree and the main checkout have wildly different candidate
counts, so a fixed count floor was both machine- and checkout-dependent and
tripped on every commit from a worktree.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: docker-deploy)

Proposed command (implemented at approval):

    .venv/bin/python $RULE_DIR/scripts/check_credential_reachability.py  # bounded find for .env/*.private.yaml/cookies.txt/.mcp.json, assert every role matcher excludes each, assert both rm -f .env strips present

Delete-check: Cannot delete the dimension: the pod genuinely needs runtime env injection
(AII_ENV_B64) and the images genuinely need parts of .claude/skills, so
exclusion rules with re-includes will keep existing. Both role Dockerfiles
also keep the defense-in-depth 'rm -f /research-monorepo/.env'
(Dockerfile.server:440, Dockerfile.pipeline:154); the script asserts that line
stays too.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Both Hub repos are public, so context admission equals publication;
the re-include out-ranking trap is documented in only one narrow place.
Credential hygiene with a mechanical context-evaluation check.
- KEEP: Both Hub repos are public, so context admission equals publication.
Evaluating exclusion with real dockerignore semantics (including re-include
out-ranking) is exactly the check humans get wrong; bounded file list, high
consequence.
- KEEP: Same dockerignore-semantics matcher applied to a pinned credential-
file pattern list, including '!' re-include out-ranking — the exact documented
trap. Both Hub repos are public, so a context admission is a publication. High
value, deterministic, loud.
