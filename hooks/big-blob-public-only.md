<!-- hook: big-blob-public-only -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: condition not mapped: 'git diff --cached --name-only --diff-filter=A | grep -q .' runs through lib/amg_hooks/amg-hooks-env: RULES_EXCLUDE
# A newly-added file over 2 MB lands only under aii_frontend/public/ — the product-asset surface — so bulk data can never again creep into permanent history below the 100 MB per-file gate.

.git measures 4.4 GB, and every giant blob stranded in history sat comfortably
below the enforced rule-check-added-large-files 100 MB gate while outside
public/: 69.3 MB .claude/skills/owid-
datasets/_setup/checkpoints/checkpoint_0157.json, 48.4 MB
llm_judge_messages.json (tracked at TWO history paths), 37.4 MB
aii_pipeline/.../topics.json, 34.3 MB
datasets/full_stanfordnlp_imdb_plain_text_train.json, 33.6 MB
temp/data_imdb.json — all since deleted from the tree (research artifacts
moved to ../research-monorepo-artifacts, .gitignore:327-331) yet permanent in the
pack. The clean end-state is already achieved and measurable: today only 4
tracked files exceed 1 MB outside aii_frontend/public/gallery (largest 8.6 MB
logo_4096.png, itself under public/; then uv.lock at 1.27 MB with headroom),
and the last 200 commits added ZERO files over 2 MB outside public/. Not a
near-duplicate of enforced rule-check-added-large-files (per-file 100 MB, no
path predicate): that gate measurably admitted every one of the blobs above;
this one pins the 50x-tighter path-scoped policy the cleanup established.
Gallery churn itself is separately governed by pending rule-gallery-covers-
immutable.

Proposed type: **cmd-check** · scope: **staged-only** · value: **high** (proposer: git-repo-hygiene)

Proposed command — **IMPLEMENTED 2026-09-07 as `$RULE_DIR/check.sh`**, invoked from
the frontmatter `command: bash $RULE_DIR/check.sh`. The one-liner it was promoted
with, kept for the record:

    bad=0; while IFS= read -r -d '' f; do case "$f" in aii_frontend/public/*) continue;; esac; s=$(git cat-file -s ":$f" 2>/dev/null || echo 0); if [ "$s" -gt 2097152 ]; then echo "$f ($s bytes) — >2MB outside aii_frontend/public/"; bad=1; fi; done < <(git diff --cached --diff-filter=A --name-only -z); [ "$bad" -eq 0 ]

**That command could not fail until 2026-09-06, and the shape is worth
recognising because it looks completely correct.** The previous spelling piped
the file list INTO the `while`, which puts the loop in a subshell, so its
`exit 1` ended the subshell and not the command; a trailing `; exit 0` then
overrode whatever survived. Measured with a 3 MB synthetic blob staged outside
`public/`: it printed `… (3145728 bytes) — >2MB outside aii_frontend/public/`
and returned **0**. A gate that reports the violation and passes is worse than
no gate, since the output looks like proof it is working.

Both halves are fixed: the list arrives by process substitution so the loop
runs in THIS shell and a `bad` flag survives it, and the command's exit status
is that flag rather than a constant. Bash is guaranteed — `rules.py` runs every
command with `executable="/bin/bash"` — so `< <(…)` is safe here, and `read -d`
was already a bashism. Re-measured on the same blob: exit **1** with the
violation printed, exit **0** once unstaged, and exit **0** for a 3 MB file
staged UNDER `aii_frontend/public/`, so the carve-out the rule exists for still
works.

Both fixes above are what `$RULE_DIR/check.sh` ships, with the loop body and the
2 MB threshold unchanged; it additionally appends the consumer's `exclude:`
pathspecs to the staged listing, and prints where bulk data belongs
(`../research-monorepo-artifacts`) rather than only the offending path.

Proposed condition: `git diff --cached --diff-filter=A --name-only | grep -q . # applies only when the commit adds files`

Delete-check: The deletion already happened — bulk data moved out of the checkout
(.gitignore:327) — and this rule enforces exactly that deleted end-state.
Deleting the existing 100 MB hook instead and lowering its maxkb would gate
ALL paths including legitimate public/ assets (gallery covers run to 5.9 MB),
so the path-scoped rule is the minimal surviving form.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Killed sibling rule-no-bulk-data-in-packages was a whole-tree package-
dir census; this is a genuinely different mechanism — a staged-only size gate
(2MB, any path outside public/) tightening the enforced 100MB hook, which
every historical giant blob (69MB, 48MB) sailed under. 4.4GB of .git is the
measured cost. The killed dimension returns with a different, cheaper, add-
time mechanism — …
- KEEP: 4.4GB .git with every stranded giant blob sitting under the 100MB
enforced gate — a 2MB add-time gate outside public/ is the missing tier.
Killed rule-no-bulk-data-in-packages was whole-tree directory policing; this
is a staged-only size gate on new adds — genuinely different mechanism, and it
must stay staged-only to avoid re-litigating history.
- KEEP: Killed rule-no-bulk-data-in-packages returns here with a genuinely
different mechanism — staged-only size threshold at add time (2MB, path-
scoped) instead of tree-scanning package dirs — and the killed slug's failure
mode (what counts as 'bulk data dir') doesn't apply to a byte count.
Complements, not duplicates, enforced 100MB rule-check-added-large-files.
Needs a documented allowlist …

RE-MEASURED 2026-08-24 — **holds: 0 files over 2 MB added outside
`public/` across the last 200 commits.** Checked by walking each commit's
added files and asking `git cat-file -s` for the blob size, so it counts
what actually entered the tree rather than what is there now.

One caveat on the phrasing rather than the finding. "The last 200
commits" is a RELATIVE window, and this repo's commit volume is bursty —
115 commits landed on 2026-08-24 alone, so a 200-commit window can be
mostly one day's work. The measurement is unaffected here (documentation
commits add no large blobs), but a relative window is worth avoiding
where the population matters. "The last 200 commits that add a file"
would be stable at no extra cost.
