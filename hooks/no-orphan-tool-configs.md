<!-- hook: no-orphan-tool-configs -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tool config file or section in the tree belongs to a tool actually present in the toolchain

Three orphans from two separate tool migrations survive today:
aii_frontend/.prettierignore exists while prettier appears in NO package.json
dep, script, or lefthook entry (README.md:287: 'oxlint + oxfmt … replaced
eslint + prettier'); aii_pipeline/pyproject.toml:76 [tool.black] and :80
[tool.isort] configure formatters absent from lefthook.yml and ci.yml
(ruff/ruff-format is the house toolchain). Orphan configs are worse than
clutter — they invite an agent to 'fix' formatting with the retired tool and
produce diffs the real formatter rejects.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: simplification-deletions)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_orphan_tool_configs.py  # map: .prettierrc*/.prettierignore→prettier in package.json; [tool.black]/[tool.isort]/[tool.flake8]/[tool.mypy]→tool in lefthook.yml or ci.yml


## IMPLEMENTED 2026-08-26 — and only HALF the delete-check was carried out

    .venv/bin/python $RULE_DIR/scripts/check_orphan_tool_configs.py

`[tool.black]` and `[tool.isort]` are deleted from `aii_pipeline/pyproject.toml`
— they configured formatters nothing invokes, while ruff and ruff-format are
the house toolchain. The file still parses, and `ruff check` / `ruff format
--check` are clean over its 179 files. Arrives green at 4 surfaces, 0 orphans.

**`.prettierignore` was NOT deleted, and deleting it would have broken the
commit gate.** The verification above already established that oxfmt reads it;
I confirmed independently before touching anything — the shipped binary carries
both `.prettierignore` and `.oxfmtrc.json` as strings, and `.oxfmtrc.json`
declares no ignore patterns, so it is the ONLY ignore source for the enforced
`rule-oxfmt-fe`. Removing it would pull `lib/api/_hey-api`, `lib/types/
backend.ts`, `dev/components.html` and `temp/` back into scope, and `backend.ts`
fails oxfmt the moment it is unignored.

I nearly deleted it anyway. My own grep found prettier in no `package.json`,
hook or CI step — which is true, and is precisely the reasoning the correction
names: **absence of the namesake is not evidence of orphanhood when a different
tool reads the file.** So the checker maps a config to the tool that READS it,
never to the tool it is named after.

A consumer counts wherever it appears — dependency, script, hook, CI step, or
rule command. That last one matters: `rule-oxfmt-fe` is what runs oxfmt, and a
hooks-only search would call the whole frontend format config an orphan.

**A pyproject cannot vouch for its own section**, which the probes caught: with
`pyproject.toml` in the consumer corpus, `[tool.black]` matched the word
"black" in its own heading and every dead section read as live. The file under
test is excluded from its own corpus.

Probed five ways: a dead `[tool.black]`, a dead `[tool.isort]` in a
sub-pyproject, and a `.prettierignore` with no oxfmt anywhere all fire; a
`[tool.black]` a hook invokes, and `.prettierignore` with oxfmt present, do not.

Delete-check: Deletion is the action: rm .prettierignore, drop the [tool.black]/[tool.isort]
sections now. The rule earns its keep because recurrence is evidenced — two
independent migrations each left residue. Script keeps a small map of known
config filenames/sections → toolchain-presence probes (package.json deps,
lefthook.yml, pyproject tool sections), so a future tool swap that forgets its
config fails at commit.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Two independent tool migrations each left orphans, so recurrence is
evidenced. Delete the three orphans at adoption; the rule sweeps for configs
no toolchain member reads. Absorbs rule-pyproject-dead-sections.
- KEEP: Two independent tool migrations each left orphans, so recurrence is
evidenced. Delete the three now; the residual check (config file/section names
a tool present in the toolchain) is a small mapping over a short list. Absorbs
rule-pyproject-dead-sections.
- KEEP: Pinned table of known config artifacts → toolchain-presence signal
(.prettierignore→prettier in package.json/lefthook; [tool.X]→X anywhere in
deps/hooks). Vacuous only for novel unknown configs, but two independent
migrations left orphans, so the known-class check earns its keep. Absorbs
rule-pyproject-dead-sections. Orphan .prettierignore verified live.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
The .prettierignore half is wrong, and I proved it two ways. (1) Empirical: in
a scratch dir I wrote `.prettierignore` containing `ignored`, plus
`ignored/x.ts` and `kept/y.ts` both mis-formatted, then ran the repo's own
binary `aii_frontend/node_modules/.bin/oxfmt --check .` -> 'kept/y.ts (0ms)
... Finished in 33ms on 1 files' — the ignored file was skipped. (2) `strings
node_modules/@oxfmt/binding-linux-arm64-gnu/oxfmt.linux-arm64-gnu.node | grep
-o '.prettierignore|.gitignore|.oxfmtrc.json'`

Corrected statement of fact:
aii_frontend/.prettierignore is NOT an orphan — oxfmt reads it (proven by
probe: the ignored file was skipped, the kept one checked), it is the only
ignore source since .oxfmtrc.json declares no ignorePatterns, and the live
rule general/frontend/rule-oxfmt-fe runs `oxfmt --check` from that directory.
The rule's own delete-check action ('rm .prettierignore') would put
lib/generated, lib/api/_hey-api, lib/types/backend.ts, dev/components.html and
temp/ back into the commit gate's scope and break it — backend.ts fails oxfmt
the moment it is unignored. Note the repo already knows this: rules-
pending/aii/frontend/rule-fe-exclusions-live/SKILL.md:11 states oxfmt consumes
.prettierignore, and rules-pending/KILLED-2026-08-22.md:106 killed a sibling
rule partly on this proposal's false 'orphan status verified: prettier appears
0 times in package.json' — absence from package.json is not evidence of
orphanhood when a different tool reads the file. The genuine live defect is
the other half: [tool.black] (aii_pipeline/pyproject.toml:76-78) and
[tool.isort] (:80-82) configure formatters no hook, CI job or rule invokes,
while ruff+ruff-format with lint rule 'I' is the house toolchain — 6 dead
config lines worth deleting.
