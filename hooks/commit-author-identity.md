<!-- hook: commit-author-identity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A commit lands under the configured identity: `git var` author and committer emails match `git config user.email`, and no unpushed commit in @{u}..HEAD carries a fixture-shaped author (t@t.t etc.).

A commit lands under the configured identity: at commit time `git var
GIT_AUTHOR_IDENT` and `GIT_COMMITTER_IDENT` carry the email `git config
user.email` says, and no unpushed commit in @{u}..HEAD carries a
fixture-shaped author (t@t.t, *@example.*, test@*).

Three commits authored t@t.t sit deep in origin/main's history — positions
777-779 from the tip at the 2026-08-28 re-measure (of 4383 commits: 4374
owner, 6 GitHub noreply, 3 t@t.t; `git log origin/main -50` counts 0 today)
— among them,
ironically, 'fix(tests): scrub inherited GIT_* at conftest import': the same
2026-08-22 GIT_* leak class that put a scratch 'init' commit (author 't
<t@t>') on main also let real, well-formed commits publish under a fixture
identity. Every ENFORCED commit rule (rule-conventional-commit, rule-commit-
subject-length, rule-commit-scopes, rule-commit-one-concern) inspects the
MESSAGE; nothing inspects authorship, so a leaked GIT_AUTHOR_EMAIL sails
through all four. `git var` reads the identity the pending commit will
actually use — env overrides included — so the check needs no hand-pinned
email: it compares git's effective identity against the repo's own config, and
the range scan catches any that already landed.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: incident-derived)

Mechanism (implemented 2026-08-26, `scripts/check_author_identity.sh`):

    bash $RULE_DIR/scripts/check_author_identity.sh

`git var` rather than a pinned address: it reports the identity the pending
commit will ACTUALLY use, environment overrides included, and holds it against
the repo's own `git config user.email`. A check written against a literal
email would need editing by anyone who ever legitimately commits here.

**The position drifts as commits land; the fact does not.** The proposal
was written when `git log origin/main -50` counted 3 fixture-authored
commits; the 2026-08-26 re-measure put them at positions 476-478 from the
tip (of 4082 commits: 4073 owner, 6 GitHub noreply — web-UI commits,
legitimate — and 3 `t@t.t`), and the 2026-08-28 audit at 777-779 of 4383.
Each claim was true when written; the opening now states the
position-independent fact so it cannot go stale the same way.

Scope is UNPUSHED commits (`@{u}..HEAD`), so this arrives green. Purging the
three needs a history rewrite and force-push, and origin/main is polled by
both the CI and image watchers, so a force-push orphans in-flight builds —
the rule's own delete-check reaches the same conclusion.

Probed seven ways. `GIT_AUTHOR_EMAIL=t@t.t`, a fixture committer, a plain
mismatched author and both halves overridden all fire; no override passes. In
a synthetic repository with an upstream, one unpushed `t@t.t` commit fires
while a clean range passes. The fixture pattern is anchored so the owner's own
address and `latest@…` are not caught by `^test@`.

Superseded proposal:

    bash "$RULE_DIR/scripts/check_author_identity.sh"  # git var GIT_AUTHOR_IDENT/GIT_COMMITTER_IDENT email == git config user.email; git log @{u}..HEAD --format=%ae free of fixture-shaped addresses

Delete-check: Root-cause deletion is proposal conftest-hermetic-env-pins (the scrub) — but
three t@t.t commits reached origin/main PAST the single defense, so this is
the independent second door on a different layer (git's effective identity,
not the test env). Purging the existing three would need a history rewrite and
force-push, not worth it; the gate stops the class going forward.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Survivor of the internal duplicate: verified 3 t@t.t commits in
origin/main's last 50, including the scrub fix itself — the contamination
class got PAST the single conftest defense, so a commit-time identity check is
genuine defense-in-depth, not redundancy with conftest-hermetic-env-pins.
Cheap git var check plus unpushed-range sweep.
- KEEP: Three t@t.t commits reached origin/main PAST the conftest scrub —
defense in depth at the commit gate is warranted, and the @{u}..HEAD fixture-
author sweep catches what an env-only check misses; absorbs commit-identity-
owner.
- KEEP: The surviving identity rule (absorbs commit-identity-owner): three
t@t.t commits reached origin/main PAST the conftest scrub, so a second,
independent gate at commit time is warranted. git var probe + @{u}..HEAD
author sweep are one-liners; handle the no-upstream case explicitly rather
than passing vacuously.
