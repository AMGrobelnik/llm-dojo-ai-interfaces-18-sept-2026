<!-- hook: nightly-red -->

| stage | scope | budget | status |
|---|---|---|---|
| commit-msg | tree | 90s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MSG_FILE, RULES_ENGINE_DIR
# While the nightly full suite is red, each failure is one worktree's job and blocks its commits until fixed

The commit gate runs only the unit groups a commit's paths trigger
(`lib/amg_hooks/run_groups.py`): 127 groups, one pytest process, the ones
whose `paths.txt` matched. A change that breaks a test in a group it did not
trigger lands green and stays green — nothing ran the full suite anywhere
after the local CI watcher was retired (research-monorepo 29901d218, 2026-09-16).

`.github/workflows/nightly.yml` in the consumer runs everything on
GitHub-hosted runners every night (python unit suite, frontend unit +
storybook, hermetic e2e, the whole-tree hook sweep, secret scan) and
publishes one file, `failures.json`, on the branch `nightly-status`. This
hook reads it at every commit:

- **Units.** `python:<test file>`, `fe-unit:<test file>`,
  `fe-storybook:<story file>`, `e2e:<spec file>`, `hooks:<hook name>`, or
  `<lane>:*` when a lane failed without naming a test (a build, a lint).
- **Claims.** `<git common dir>/amg-hooks-nightly/claims.json`, shared by
  every worktree of the clone, so parallel sessions never fix the same
  failure twice. A committer holding no claim takes ONE free unit; the rest
  wait for the next committer. Claims expire after 8 h
  (`AMG_NIGHTLY_CLAIM_TTL_S`) so a dead session holds nothing forever, and
  every claim is keyed to the nightly run id, so a new night drops them all.
- **Re-judged in the snapshot.** python and vitest units are rerun against
  the index being committed: passing releases the claim and the commit goes
  through; failing blocks it with the ids and the reproduce command. Free
  units are rerun too, so a failure main already fixed is never claimed.
- **Trailers** for what cannot rerun locally (`hooks:*`, `e2e:*`, `<lane>:*`):
  `Nightly-Fixed: <unit>` releases it; `Nightly-Waive: <unit> - <reason>`
  marks a false positive. Both stay in history (`git log --grep Nightly-`).
- **Never blocks on the network.** The status branch is fetched inline at
  most every 10 min with a 15 s timeout; a failed fetch is one warning line
  and the last fetched copy is judged. No status branch at all = pass.

`python3 lib/amg_hooks/nightly_red.py status` prints the red units and who
owns each. Merges skip this stage (lefthook `commit-msg: skip: merge`), so a
fix lands through ordinary commits, never through a merge.

Fix when blocked: run the reproduce line printed, fix the failure in this
commit (or a prior one on the branch), commit again. If the unit is not
yours to fix, do not touch it — the message says whose it is.
