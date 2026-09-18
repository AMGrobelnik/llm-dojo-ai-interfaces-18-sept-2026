<!-- hook: check-merge-conflict -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# No conflict markers anywhere in the index

`git grep --cached` scans every tracked blob in the index — the whole
tree as it would be committed, not just this commit's added lines — for a
line opening with the 7-char `<<<<<<<` or `>>>>>>>` marker followed by a
space (the `(<{7}|>{7})` alternation). A marker anywhere in tracked
content blocks the commit, whether or not this commit introduced it.
Bare grep is instant (~10ms) vs ~2s uvx cold-start, and grepping index
blobs rather than looping over filenames sidesteps this repo's paths
with shell metachars (`foo (1).pdf`, Next.js route groups
`app/(app)/...`).

Fix when blocked: finish the conflict resolution — delete the
`<<<<<<<`/`=======`/`>>>>>>>` marker lines and keep the intended content,
then re-stage.

Delete-check: cannot delete — conflict markers are a merge byproduct git
itself will happily commit; only a gate catches them.

History: until 2026-08-22 the check scanned only ADDED lines, reading the
`git diff --cached` text for `+<<<<<<<`, and an earlier spelling avoided
regex alternation because the bash subshell it forced broke lefthook's sh
parser with a "( unexpected" error. Both descriptions outlived the
widening to the whole index; the paragraphs above describe the command as
it runs today.
