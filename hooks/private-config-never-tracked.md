<!-- hook: private-config-never-tracked -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: condition had extra logic not mapped: 'git diff --cached --name-only --diff-filter=A | grep -q .' runs through lib/amg_hooks/amg-hooks-env: RULES_EXCLUDE
# No *.private.yaml and no .env is ever git-tracked, and .gitignore keeps both globs — the pointer belongs in git, the value in the gitignored file

.gitignore:185 carries the *.private.yaml glob, with its explanation and two
examples at :181-184, and .env/.env.* at :176-177 (the two value-less reference
files stay tracked via the !-negations at :178-179);
aii_config/free_router_keys.private.yaml holds real provider keys —
aii_lib/src/aii_lib/free_router/keys.py's load_free_tier_keys (:81-87) reads
them and apply_free_tier_keys (:90-105) copies each into an env var at :103;
CLAUDE.md states the convention ('the pointer is what belongs in git; the
value belongs in .env'). Verified clean 2026-09-05: `git ls-files -- '*.private
.yaml' '.env' '**/.env'` is empty and `grep -qx '\*\.private\.yaml' .gitignore`
holds, i.e. both halves of the proposed command pass on today's tree. Additive
to rule-gitleaks: gitleaks matches secret CONTENT patterns,
and an overlay carrying only template ids or account rosters (e.g.
server.private.yaml's tpl-XXXX per config_overrides.py:20-24) would pass a
content scan while still being private-by-convention. One tracked overlay
would then flow to the public export.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-shared)

Proposed command — **IMPLEMENTED 2026-09-07 as `$RULE_DIR/check.sh`**, invoked from
the frontmatter `command: bash $RULE_DIR/check.sh`. The one-liner it was promoted
with, kept for the record:

    test -z "$(git ls-files -- '*.private.yaml' '.env' '**/.env')" && grep -qx '\*\.private\.yaml' .gitignore

**Do NOT ask the glob question through a pipe.** The first implementation
tested each glob with `printf '%s\n' "$ignore" | grep -qx -- "$glob"` under
`set -o pipefail`, and that construction reports a glob MISSING while it is
present: `grep -q` exits at its first match and closes the read end, `printf`
still has bytes to write, SIGPIPE kills it with 141, and `pipefail` promotes
that to the pipeline's status. It cost two ci-local reds — 2026-09-09 on
`54e87efba911` naming BOTH globs, 2026-09-10 on `914b13dffe59` naming only
`*.private.yaml`, each against an index `.gitignore` that carried both lines.
Which glob loses is a scheduling accident, and that asymmetry is the tell: a
deleted line cannot name itself intermittently. Idle it lost the race 1 time in
10000 reads of the 12.8 kB consumer `.gitignore`; under the sweep's ~220
parallel commands it lost it in production, and past the 64 kB pipe buffer with
an early match it loses every time. The check now searches the variable in the
shell (`case $'\n'"$ignore"$'\n' in *$'\n'"$glob"$'\n'*`), which keeps
`grep -qx`'s whole-line semantics — `!.env`, `.envrc` and `sub/.env` still do
not count — with no second process to race, and quoting the expansion inside
the pattern keeps the `*` in the glob literal. A failure now also prints the
size and blob sha it judged, so the difference between "the line is gone" and
"the read was" is readable from a CI log without a reproduction.
`test_a_glob_that_is_present_is_never_reported_missing.py` pins all of it.

**That line asserts only the `*.private.yaml` glob, and the statement above
claims BOTH.** Deleting the `.env` line from `.gitignore` would have left the
gate green while the ignore that keeps the value out of git was gone — the
rule's H1 would then have overstated its own command, and that overstatement
propagates verbatim into the meta-rule table. `check.sh` asserts both globs,
and reads `.gitignore` from the INDEX rather than from disk: this gate re-reads
it on every commit, and in a shared checkout the file on disk belongs to
whoever edited it last, so a peer's unstaged deletion would have failed an
unrelated commit.


Delete-check: Cannot delete the dimension: moving all overlay content into .env was
implicitly rejected because overlays carry structured non-env config (nested
template ids, account lists) that deep-merges into tracked YAML. A one-line
git ls-files gate is cheaper than any restructuring.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Not covered by gitleaks — a tracked *.private.yaml carrying template
ids or non-secret structure trips no secret scanner, yet publishes the overlay
channel. One git ls-files pipe plus a .gitignore glob assert.
- KEEP: Public-export path makes this the highest-consequence file-hygiene
invariant in the repo; gitleaks checks content, not tracking of the globs, so
this is complementary. One git ls-files pipe, zero FP.
- KEEP: git ls-files check for the two globs + assert .gitignore carries them.
Trivial, deterministic, guards the public-export path. gitleaks checks
content, not tracking-status of these names — not redundant.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree. **Its
`.gitignore` coordinates are HISTORICAL and none resolves today** — that file
grows, so the glob has walked :182 (08-22) → :185 (2026-09-05), and the
statement above carries the live ones. The transcript is left as written.

What it found:
.gitignore:182 is `*.private.yaml` with the two examples on 180-181 — cite
fine. `git ls-files | grep -cE '\.private\.(yaml|md)$'` -> 0, clean as
claimed. aii_config/free_router_keys.private.yaml parses to 11 populated
provider fields (agnes, cloudflare, gemini, groq, ionet, mistral, nvidia_nim,
requesty, sealion, zai, cloudflare_account_id) — real keys, as claimed; but
keys.py:85-87 is the tail of `load_free_tier_keys` (read + return dict), while
the function that copies into env vars is `apply

Corrected statement of fact:
Tracked-state is clean and the gitleaks-additivity argument survives a real
scan — but the stated harm ('one tracked overlay would then flow to the public
export') is already guarded twice over. aii_public/sync.sh:124-128 runs `find
aii_config -name '*.private.yaml' -print -quit` on the staged export tree and
exits 1 with 'ERROR: *.private.yaml files leaked into the staged tree', and
research-monorepo/unit-tests/public-sync-invariants/test_invariants.py:481-486
pins that guard's presence while the test right after it pins that the guard's
directory still exists. On top of that, .gitignore makes tracking one require
an explicit `git add -f`. Also correct the example: aii_public/gitleaks.toml's
aii-runpod-template-ids rule matches the two LIVE ids literally (the values
are in that config, deliberately not repeated here), not a `tpl-` shape, so today's server.private.yaml is content-
covered — the uncovered case is a NEW id or a non-institutional roster, which is what
my scan actually demonstrated. Any rule here should be justified as covering
overlays outside aii_config/ (sync.sh's find is scoped to that one directory),
not as the only thing standing between an overlay and the public repo.
