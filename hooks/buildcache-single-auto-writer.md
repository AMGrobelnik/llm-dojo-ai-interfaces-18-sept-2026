<!-- hook: buildcache-single-auto-writer -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The registry buildcache keeps exactly one automatic writer

In full: aii-builder-keepalive.sh exports cache-to for every bake
target, and the other three build surfaces carry none — the image
watcher passes cache-from only, docker-bake.hcl defines no cache-to,
and build_push_image.sh no longer exports at all.

Placement argument worth pinning: the export lives on the keepalive because
it is off the critical path (twice daily), not because it is cheap —
measured from the keepalive's own log it ranges 2.2-7958.5 s per run
(median ~36 s per target; ~65 s warm; ~1500-1600 s on a cold cache, per
CLAUDE.md's 2026-08-25 idle-box re-measurement — the '~65 s vs up to
1069 s' this file used to quote was a warm-cache point against a stale
ceiling), so a watcher gaining cache-to would tax every per-commit ship by
up to that much. Verified in this tree: aii-builder-keepalive.sh:5-6
declares itself 'the ONLY writer' and lines 292-295 carry the four
cache-to sets (``tex`` joined 2026-09-07 with the aii_tex image); `grep -c cache-to` returns 0 for
executable lines in aii-image-watcher.sh, docker-bake.hcl and
build_push_image.sh. A regression in either direction is silent: a
watcher gaining cache-to taxes every ship; a keepalive losing its cache-to
re-creates the four-day stale-cache window that ended in an image that
would not push. Comments were the only enforcement until this rule shipped
its checker.

(Those positions have already moved three times — the keepalive's sets were
cited at 269-271, corrected to 219-221 when that went stale, read 269-271
again, and are 292-295 today. That churn is the ordinary cost of pinning
positions in prose, and it is why the checker asserts a PROPERTY of each
file rather than a line number. It used to locate the opt-in guard by
grepping for its `if [[ "${PUSH_CACHE:-0}"` opener and scanning to the
matching `fi`, so that block could move without the gate going quietly
blind; with the flag deleted on 2026-09-08 the assertion is simply that
build_push_image.sh carries no executable cache-to.)

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: docker-layer-economics)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    bash $RULE_DIR/scripts/check_single_cache_writer.sh  # assert: no executable 'cache-to' in aii-image-watcher.sh, docker-bake.hcl or build_push_image.sh; keepalive has cache-to for base+server+pipeline+tex

All four clauses were proven to bite in a throwaway copy of the four files
rather than inferred from a clean exit: a cache-to added to the watcher, one
added to docker-bake.hcl, one added to build_push_image.sh, and
`server.cache-to` removed from the keepalive each exit 1 and name the file.
Re-proven the same way on 2026-09-08 after the build_push_image.sh clause
stopped being positional. When that clause was positional the probe took two
attempts — the first inserted a line ahead of the guard, which left the
exports still inside it and proved nothing; a probe that fails to reproduce
the defect looks exactly like a gate that works.

It counts only EXECUTABLE occurrences, skipping comment lines. All four files
discuss cache-to in prose — the keepalive's own header explains the placement
at length — so counting raw grep hits would report the explanation as if it
were the mechanism, and the keepalive would appear to export from its header.

Proposed condition: `git diff --cached --name-only -- 'scripts/local/' 'docker-bake.hcl' | grep -q .`

Delete-check: The dimension is itself a deletion pin (cache-to deleted from every surface
but one). The further deletion this entry proposed has happened — the
PUSH_CACHE manual writer was retired on 2026-09-08, leaving literally one
writer — so the rule is now the tightened form: 'executable cache-to exists
only in the keepalive'.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Pins a measured, incident-backed placement decision (65s on the
keepalive vs up to 1069s per-commit; the 2-day deploy outage chain) that lives
only in CLAUDE.md prose. Sibling of pending rule-latest-moves-on-release-only
(single-writer discipline for a different registry artifact) — same accepted
shape, different artifact, no dupe.
- KILL: Same files, same grep targets, same cache-topology dimension as ref-
families-agree — the writer-placement clauses (keepalive-only cache-to,
watcher exports nothing, bake defines none) belong as assertions inside that
one rule. [merge->buildcache-ref-families-agree]
- KEEP: Distinct invariant from ref-families-agree (writer cardinality vs ref
agreement) with a measured placement argument (65s off-critical-path vs 1069s
on-watcher); house precedent for writer-cardinality rules is pending rule-
latest-moves-on-release-only. Four greps, each loud.

(Two rules the verdicts above cite as live siblings are gone — killed in
the 2026-08-28 audit, rules-pending/KILLED-2026-08-28-audit.md:
rule-latest-moves-on-release-only restated enforced
rule-image-watcher-release-guards, and
rule-buildcache-ref-families-agree's premise is already enforced by
test_buildcache_readers_use_the_written_family.py. The `[merge->…]`
target therefore no longer exists; this rule stands alone on writer
cardinality.)

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Structural claims all verified exactly. aii-builder-keepalive.sh:5-6 reads '#
Keepalive for the persistent buildx builder cache, and the ONLY writer of the
/ # registry buildcache.' Lines 219-221 carry base/server/pipeline cache-to.
`grep -c cache-to scripts/local/watchers/aii-image-watcher.sh docker-bake.hcl`
-> 0 and 0. Repo-wide `grep -rn PUSH_CACHE` found it in executable source only
in build_push_image.sh, which is the evidence the 2026-09-08 deletion acted
on: one guarded export, one caller, no consumer.

Corrected statement of fact:
Half the invariant is already live-enforced, not comment-only: rules/aii/unit-
tests/rule-image-watcher-release-guards/test_image_watcher_contract.py (lines
200, 228, 256) asserts the keepalive keeps a mode=max cache-to for every
docker-bake.hcl target, and it passes today (8/8). The genuinely uncovered
direction is the negative one — nothing asserts that aii-image-watcher.sh and
docker-bake.hcl stay cache-to-free, nor that build_push_image.sh stays
cache-to-free. Scope the rule to that. Drop '~65s vs up to
1069s' as the placement argument: measured from the keepalive's own log the
export is 2.2-7958.5s (median ~36s per target, p90 in the thousands), so 65s
is a cherry-picked point and CLAUDE.md's 1069s ceiling is stale. The placement
argument stands on 'off the critical path, twice daily' alone. Note the
invariant currently HOLDS: the buildcache-amd64 tags for all three repos that
existed then were rewritten 2026-08-22T02:37-02:39Z; aii_tex is the fourth and
post-dates that reading.
