<!-- hook: pipeline-config-files-enumerated -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every tracked public yaml under aii_config/pipeline/ is enumerated in PIPELINE_CONFIG_FILES or BACKEND_CONFIG_FILES — no config file that ships but never loads

The loader reads a fixed enumeration (pipeline_config.py:97-111:
pipeline.yaml, io/sinks.yaml,
harness/{agent_backend,llm_helper_backend,execute_env}.yaml) while the deploy
tar ships EVERY *.yaml under the dir (_deploy_flow.py:267-270, redeploy
likewise). A yaml added without touching the tuples ships to every pod and is
never read — the run behaves as if the file didn't exist, with zero errors
anywhere. Exactly five files match five entries today; the check keeps the
add-a-file path honest in both directions (a tuple entry whose file was
deleted also fails).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: config-yaml)

Proposed command (implemented at approval):

    .venv/bin/python $RULE_DIR/scripts/check_pipeline_files_enumerated.py  # git ls-files aii_config/pipeline (minus *.private*.yaml) == the union of the two tuples in pipeline_config.py, both directions

Delete-check: Deletion is feasible: derive the load set by globbing the layer dir (harness/*
merges under its stem key, everything else at root — the only two semantics
that exist), which removes the enumeration entirely; ordering can be pinned by
sorting with pipeline.yaml first. If that lands, the rule flips to enforcing
no re-introduced hand list. Until then the parity check is cheap and closes
the silent-never-loaded gap.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Ship-set (glob) vs load-set (hand enumeration) drift means a config
file that ships but never loads — silent by construction. Keep the parity
check now; the glob-the-loader deletion is a behavior change needing its own
decision.
- KEEP: A yaml that ships but never loads is config that silently does nothing
— confusing at exactly deploy time. Glob-vs-tuple parity is a trivial check;
the glob-derived-loader deletion is even better and the rule then pins it.
- KEEP: Compare tracked aii_config/pipeline/*.yaml glob against the loader
tuples (imported via python -c). Deterministic set comparison; a shipped-but-
never-loaded yaml fails loudly. Prefer the glob-derivation deletion later.
