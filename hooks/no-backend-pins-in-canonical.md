<!-- hook: no-backend-pins-in-canonical -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# Canonical pipeline.yaml carries no per-step agent_backend_name pins — the harness active: is the single backend selector, so flipping it switches a whole run

9 of 15 agent blocks in aii_config/pipeline/pipeline.yaml (lines
160,172,238,247,256,264,292,302,363 at the time) pin agent_backend_name:
terminal_claude_agent — every one equal to the harness active:
(agent_backend.yaml:50). The pins are why agent_backend.yaml carries a 13-line
'!! FLIPPING THIS LINE ALONE DOES NOT SWITCH A WHOLE RUN !!' hazard block
(lines 38-50): _normalize_agent_blocks honours a step pin OVER active
(pipeline_config.py:461), so a CLI/overlay user who edits only active: gets a
mixed run with no warning. Deleting the pins is behavior-preserving today (the
loader stamps active into every block) and removes the hazard plus the warning
prose. The dashboard is unaffected — it fans the choice out per step in USER
overlays, not canonical.

Type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: config-yaml)

LANDED 2026-09-04: the nine pins are stripped (resolved config proved
byte-identical before and after — `PipelineConfig.from_yaml` dumped and
diffed), the hazard comment in agent_backend.yaml is replaced by one that
states the now-true invariant, and the grep above is the command.

Delete-check: Deletion IS the rule: strip the nine redundant pins (and then the hazard
comment), and the grep enforces the deleted end-state so they never creep
back. frontend/config.yaml's per-step pins stay — that file IS the dashboard's
explicit fan-out seed, a different and deliberate mechanism.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Nine redundant pins are why a 12-line hazard comment exists; strip
them (deletion), delete the comment, enforce the pin-free end-state so
flipping the harness active: switches whole runs again.
- KEEP: Nine redundant pins that turn the documented single selector into a
lie requiring a 12-line hazard comment. Strip them, delete the comment, grep
pins the deleted end-state — pure Musk step 2 with a free guard.
- KEEP: After stripping the nine redundant pins: yq/grep pipeline.yaml for
agent_backend_name = fail. Trivial literal ban enforcing the deleted end-
state; also deletes the 12-line hazard comment.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **the substance is exact.
Two line references are off by one.**

Parsed `pipeline.yaml` rather than grepping it, so the denominator is real:

| claim | measured |
|---|---|
| agent blocks | 15 |
| of them pinned | 9 |
| pin lines 160,172,238,247,256,264,282,292,353 | all 9 exact |
| every pin equals the harness `active:` | yes |

The mechanism reference is the sharpest part and it lands precisely.
`_normalize_agent_blocks` is defined at `pipeline_config.py:436`, and **line
461 is** `abn = blk.setdefault("agent_backend_name", active_agent_backend)` —
`setdefault` is exactly what makes a step pin win over `active`, since it only
fills the key when absent. So the cited line is not merely inside the function,
it is the single statement that creates the hazard.

The hazard block in `agent_backend.yaml` corroborates the count from the other
side: its own text says the canonical file "pins `agent_backend_name:
terminal_claude_agent` on NINE steps".

Two drifts, both cosmetic:

- `active:` is at **agent_backend.yaml:50**, not 51.
- The hazard block is described as "12-line (lines 38-50)". Lines 38-50 span
  **13** lines, so one of the two numbers is wrong; the range is the useful
  half and matches the `!!` banner starting at 38.

Neither affects the argument. The delete-first move — remove the nine pins,
which is behaviour-preserving today because the loader stamps `active` into
every block — stands unchanged, and so does the reason it is worth doing: the
pins are the only thing making that 13-line warning necessary.
