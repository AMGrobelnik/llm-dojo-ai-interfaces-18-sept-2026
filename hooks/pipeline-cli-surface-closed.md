<!-- hook: pipeline-cli-surface-closed -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_REPO
# The pipeline subprocess parser's flag set stays exactly {--run-id, --run-dir, --fork-from-workflow, --fork-target-module, --fork-id, --aii-user} — config values travel in YAML, never as CLI args

The config-in-yaml discipline is stated three times and enforced
mechanically nowhere:
args.py:3-24 ('prompt, config, uploads, execute-mode, resume coordination etc.
all live in <run_dir>/.workflow_input.json ... NOT in CLI args. No
--resume-*/--prompt CLI flags exist on this parser'),
pipeline_config.py:163-167 ('there is no --prompt CLI flag'), and user-level
Rule 6 — which the ENFORCED agent rule rule-config-in-yaml ('New
configuration is a .yaml key, not a CLI flag or env var') pins by judgment
alone. OVERLAP, disclosed: this proposal is that agent rule's cmd-check
promotion at its hottest seam — the agent rule judges any staged diff, this
pin deterministically closes the one parser where a flag would reopen the
channel. A convenience flag added during
debugging would create a second config channel that bypasses validation, the
config snapshot, and fork/resume semantics — the exact split-brain the
docstrings exist to prevent. The whitelist is tiny and changes only with
deliberate protocol work, so the pin is nearly free.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: config-yaml)

Proposed command — **IMPLEMENTED 2026-09-07 as `$RULE_DIR/check.sh`**, invoked from
the frontmatter `command: bash $RULE_DIR/check.sh`. The one-liner it was promoted
with, kept for the record:

    .venv/bin/python -c "from aii_pipeline._cli.args import setup_argparser; got={o for a in setup_argparser()._actions for o in a.option_strings}; want={'-h','--help','--run-id','--run-dir','--fork-from-workflow','--fork-target-module','--fork-id','--aii-user'}; assert got==want, got^want"

`$RULE_DIR/check.sh` keeps the introspection and the set equality (both
directions — a REMOVED flag breaks the dashboard's spawn contract as silently
as an added one reopens the config channel) and drops the hard-coded
interpreter. `.venv/bin/python` is a path relative to whatever cwd the runner
happens to have and does not exist in every consumer, so the script resolves
`$RULES_REPO/.venv/bin/python` and falls back to `python3`. An interpreter that
cannot import the module exits **2** — infrastructure: loud, never blocking,
because a half-built venv must not wedge every commit — and prints the
interpreter path with it, since that failure otherwise reads like a parser
change rather than a missing venv.


The pinned set still matches the live parser — re-run 2026-08-28: the
introspection command reports the sets equal.

Delete-check: The parser itself cannot be deleted (the dashboard spawns the subprocess
through it) and is already minimal — six flags, all identity/coordination,
zero config values. The rule enforces that already-minimal end-state rather
than policing variation.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Mechanical pin of a hot seam the agent-verified config-in-yaml rule
cannot guarantee; the discipline is stated three times and enforced nowhere,
and a new flag is exactly how config sneaks out of YAML.
- KEEP: The config-in-yaml discipline is stated three times and enforced
nowhere; the parser is the one place a --prompt flag would quietly reintroduce
config-via-argv. Pinning a six-flag set is a one-assertion AST check.
- KEEP: python -c introspection of the argparse parser, assert flag set equals
the pinned six. Deterministic, loud, pins a thrice-stated never-enforced
discipline.
