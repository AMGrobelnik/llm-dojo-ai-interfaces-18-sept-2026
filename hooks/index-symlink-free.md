<!-- hook: index-symlink-free -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: condition not mapped: 'git diff --cached --name-only --diff-filter=A | grep -q .' runs through lib/amg_hooks/amg-hooks-env: RULES_EXCLUDE
# The git index contains no symlink entries (mode 120000) — committing one embeds an absolute local path or a hook-breaking self-referential loop into history.

The index is symlink-free today (git ls-files -s mode-120000 count = 0);
symlinks in this repo are working-tree wiring into the main checkout or
runtime debris, and two documented producers make the pin worth holding.
(1) .gitignore:377-380
records .claude/skills/.ability_client_venv, 'in some worktrees a self-
referential symlink, which breaks every pre-push hook that stats the tree.
Never belongs in a commit.' (2) The repo's own worktree-deploy procedure
(CLAUDE.md 'Deploying from a WORKTREE') has agents run ln -sf against
/home/<user>/projects/research-monorepo for .env and seven aii_config/*.private.yaml
overlays — symlinks embedding absolute owner paths, kept out of the index
today only by ignore globs, i.e. one git add -f (or one new un-ignored symlink
path) from history. Distinct from KILLED rule-worktree-overlays-symlinked,
which REQUIRED those working-tree symlinks to exist in worktrees — opposite
direction, different object (working tree vs index), different mechanism
(index mode scan); the killed dimension does not return here.

Re-measured 2026-09-06: the index still carries zero mode-120000 entries, and
so does HEAD (febb5a63f), whose mode histogram is {100644: 3261, 100755: 102} — no
120000 bucket at all (it read {100644: 3210, 100755: 103} on 09-05). The zero
is the load-bearing figure; the other two buckets drift with every commit, and
the index's own totals drift further still with whatever happens to be staged.
The .gitignore citations drift the same way as that file grows, so this block
has now walked four addresses: 337-340 when first proposed, 358-361 at the
08-22 verification below, 370-373 on 08-28, and **377-380 since 09-05**
(comment at 377-379, path at 380), which is where they still sit today. The
'kept out of the index today only by ignore globs' claim rests on `.env` at
.gitignore:176 and `*.private.yaml` at :185, all four re-measured 2026-09-06
and unmoved.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: git-repo-hygiene)

Proposed command — **IMPLEMENTED 2026-09-07 as `$RULE_DIR/check.sh`**, invoked from
the frontmatter `command: bash $RULE_DIR/check.sh`. The one-liner it was promoted
with, kept for the record:

    test -z "$(git ls-files -s | awk '$1 == 120000 {print $4; exit}')" || { git ls-files -s | awk '$1==120000{print "symlink in index: " $4}'; exit 1; }

What the script adds over that line: it reads `git ls-files -s` once instead of
twice, splits on the TAB rather than on whitespace (`git ls-files -s` prints
`<mode> <object> <stage>\t<path>`, so a path containing a space put the wrong
field in `$4`), appends the consumer's `exclude:` pathspecs the way every other
tree-walking check does, and prints the fix — keep the link in the working tree,
`git rm --cached` it out of the index — rather than only the path.


Delete-check: Nothing to delete — the invariant already holds at zero and the check is one
pipeline over git ls-files -s. The producers themselves cannot be deleted: the
worktree overlay symlinks are load-bearing dev wiring and the venv link is
created by the ability server at runtime; keeping them out of the INDEX is the
only enforceable end-state.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Holds at zero with two documented producers that would embed an
absolute local path or a hook-breaking self-referential loop into history;
killed rule-worktree-overlays-symlinked was the opposite concern (working-tree
wiring), not index entries. One-pipeline check, cheap insurance against a
nasty class.
- KEEP: Zero-state pin against two documented live producers (worktree wiring,
self-referential venv symlink that breaks pre-push); one git ls-files
pipeline, effectively free insurance against embedding absolute local paths in
history.
- KEEP: One-pipeline check over git ls-files -s at a current count of zero,
with two documented producers making the ratchet worth holding. Distinct from
killed rule-worktree-overlays-symlinked (working-tree wiring, killed) — this
polices the INDEX, a different mechanism and failure mode.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Headline confirmed: `git ls-files -s | awk '$1=="120000"' | wc -l` -> 0, and
the full mode histogram is {100644: 2710, 100755: 81} with no 120000 bucket at
all. Producer (1) quote is verbatim but the cited line numbers are wrong:
`grep -n ability_client_venv .gitignore` puts it at .gitignore:358-361, not
337-340 — lines 358-360 are the comment "Created by the ability server next to
the skills; in

Corrected statement of fact (2026-08-22 coordinates throughout — every
`.gitignore` line number below is superseded by the re-measurement above):
Substance holds unchanged; only the citation is off. Replace
".gitignore:337-340" with ".gitignore:358-361" (comment at 358-360, path at
361), and add the two supporting citations the body currently asserts without
pointing at: .env is ignored by .gitignore:173 and the seven overlays by
.gitignore:182 (`*.private.yaml`), which is what "kept out of the index today
only by ignore globs" rests on. No live defect: the index carries zero
symlinks right now, so this is a green-state pin, not a backlog item.
