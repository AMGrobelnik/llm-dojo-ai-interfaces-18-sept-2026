<!-- hook: agent-workspace-rail-one-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# The agent's write-containment rail is stamped once, from `options.cwd`, at the `build_options` chokepoint — no prompt module renders `get_workspace_prompt` itself; no turn ships without the rail.

**The door exists.** `build_options`
(`aii_lib/src/aii_lib/agent_backend/utils/agent_helpers.py`) renders the rail
from the same `workspace_dir` it writes to `cwd` and stamps it on
`AgentOptions.workspace_rail`. It stamps it AFTER `opts.update(overrides)`, so
unlike every other field a caller cannot replace or blank it — the one option
that is not a default. Each backend then folds it into its SYSTEM message:
`terminal_claude_agent` appends it to the `<system-prompt>` block
(`_options_to_repl` -> `ReplAgent._format_outgoing`, turn 0), and
`sdk_openhands_agent` passes it as `AgentContext.system_message_suffix`, a
SUFFIX so a step that supplies no persona still keeps OpenHands' own default
coding-agent prompt and gains the rail on top of it. `to_serializable_dict`
enumerates the dataclass fields, so it survives the RunPod dispatch round trip.

The system message, not the opening user prompt, is where it had to land. A
prepend onto `prompt_list[0]` would be byte-identical to the old placement,
but `prompt_list[0]` is the user's verbatim text on a fork-steering turn and
on a hot-resume respawn (`wrap_human_message`), where a prepended rail would
corrupt the human bubble the translator splits out — so that route has to skip
exactly those turns, which is the half of the H1 it cannot satisfy.

What the door replaced, measured before the change: `git grep -nE 'options =
build_options\(' -- aii_pipeline | wc -l` -> `16`, plus
`aii_server/dashboard/services/side_chat_runner.py:209` = 17 agent turns.
`rules-grep --tree 'get_workspace_prompt' -- aii_pipeline` -> EXIT=1, 13 lines:
the component, six imports, and six render sites, five of them written
`get_workspace_prompt(workspace_path) if workspace_path else ""` so an empty
argument silently dropped the rail. Nine of the 17 sites were handed a
rail-bearing prompt; the other eight carried no containment statement at all
(`_1_gen_hypo`, `_2_review_hypo`, `_4_gen_paper_text`, `_5_review_paper`,
`_6_upd_hypo`, `gen_plan_helpers`, `gen_strat_tasks`, `side_chat_runner`). All
six renders and the component
(`aii_pipeline/src/aii_pipeline/prompts/components/workspace.py`) are gone; the
same grep now exits 0.

**Equivalence, measured.** A probe rendered every affected prompt with fixed
inputs before and after the change and compared bytes. The rail text itself is
byte-identical (584 B for the same path) — the function body moved packages
unmodified. For all **8** renders, `before.replace(rail + sep, "", 1) == after`
holds exactly, with the rail occurring exactly once in each `before`, so the
only difference is the rail's excision and nothing else moved:

| render | before | after |
|---|---|---|
| research (agent_mode) | 4820 B | 4235 B |
| research (llm mode) | 4765 B | 4180 B |
| snippets header | 4404 B | 3819 B |
| viz data / concept | 4437 / 7127 B | 3851 / 6541 B |
| demo notebook | 7403 B | 6817 B |
| full paper / site | 7633 / 10063 B | 7047 / 9477 B |

Two behaviour changes, both the point of the rule rather than side effects:
the eight rail-less sites now carry the rail, and for the nine that had it the
rail moved from the top of the opening user prompt into the same turn's system
message. On `terminal_claude_agent` that is a few hundred bytes earlier in the
SAME submission (the driver emits `<system-prompt>` ahead of `<prompt>` on turn
0); on `sdk_openhands_agent` it becomes a real system message, present on every
turn instead of only the first.

The earlier in-tree verification pass noted that the rail-less turns were
exactly the structured-output ones (`output_format=...to_struct_output()`, no
`expected_files_field`) and asked whether that split was deliberate. Nothing in
the tree declared it so — no comment, no test — and a struct-out turn still has
`cwd` set with Write and Bash available, i.e. it is still an unconfined writer.
That is the counter-argument the H1 answers: the rail is a property of having a
workspace, not of producing files.

**Known remaining debt, one parameter.** `snippets.build_artifact_header` still
takes an INERT `workspace_path`. Dropping it requires dropping the four
forwards in `prompts/steps/_3_invention_loop/_3_gen_art/{dataset,evaluation,
experiment,proof}/u_prompt.py` and the four call sites in
`steps/_3_invention_loop/executors/{dataset,evaluation,experiment,proof}.py`,
which were in another session's in-flight commit when this landed. The
parameter renders nothing; it is a signature the executors still pass to.

The gate is `rules-grep --tree`, so it blocks in BOTH commit and sweep mode:
the renderer's name may appear in package source only in its own module, and
`build_options` must stamp it at four-space indent (any `if` around it indents
further and fails the anchored match). Verified to bite: a
`_PLANTED = get_workspace_prompt("/w")` appended to `snippets.py` -> exit 1
naming the line; wrapping the stamp in `if True:` -> exit 1 with "the
chokepoint no longer stamps the rail"; both reverted, sha256 of both files
identical before and after, clean tree exit 0 in `RULES_MODE=all` and
`RULES_MODE=commit`.

Delete-check: Yes — and this rule IS the deleted end-state, so what remains is
guarding it. The dimension deleted was per-prompt rendering: six call sites,
one component module and the `workspace_path` plumbing through five prompt
signatures. A step cannot omit a block it never renders. The rule survives
because the deletion is not self-enforcing: nothing stops a new prompt module
from importing the renderer again, which is exactly what the ban-grep costs one
`git grep` to prevent.

PORTED 2026-09-14 onto the one-pass AST dispatcher: `run.sh` and its
standalone `amg-hooks-grep`/`git grep` command are removed, `agent-workspace-rail-
one-door` is removed from `research-monorepo/lefthook.yml`, and
`research-monorepo-ast-checks` (the shared dispatcher command) now discovers and
runs `dispatch.py` in the same pass as every other AST-confirmed hook.
`SCOPE` is `"tree"`, matching the retired `--tree` / `--cached` reads: there
is one lane, and a committed violation blocks a later unrelated commit the
same as any other tree-mode hook.

The ban half keeps `amg-hooks-grep`'s literal-substring candidate
(`get_workspace_prompt`) as a line-level prefilter and adds a Python `ast`
confirmation the bare regex never had: a candidate survives only if its line
carries a real `Import`/`ImportFrom` alias, `Name` or `Attribute` node named
`get_workspace_prompt`, so a comment or docstring naming the renderer (or an
unrelated identifier that merely contains the text as a substring) is
dropped rather than counted, the same predicate `httpx-only` already carries
for its own banned-import ban. The chokepoint half — does `agent_helpers.py`
still carry the exact four-space-anchored stamp line — has no
comment/string ambiguity an AST walk could resolve without loosening the
live anchor (a re-indented stamp under a new `if` must still fail), so it
stays a direct literal check over the same `Services`-supplied INDEX text.

Measured 2026-09-14 against the real research-monorepo index (`AMG_HOOKS_SWEEP=1`): the
ban half's candidate population is 0 across the five package trees (`git
grep -nE 'get_workspace_prompt' -- 'aii_lib/src/*.py' 'aii_pipeline/src/*.py'
'aii_server/*.py' 'aii_runpod/src/*.py' 'aii_launcher/src/*.py'
':!aii_lib/src/aii_lib/agent_backend/utils/agent_helpers.py'` -> exit 1, no
hits), 0 AST findings, ADDED 0; `agent_helpers.py:275` still stamps
`    opts["workspace_rail"] = get_workspace_prompt(str(workspace_dir))`
verbatim, so the chokepoint check is clean too. The live `amg-hooks-grep --tree`
run over the same pathspec agrees (exit 0), and the dispatcher run over the
whole tree agrees: `agent-workspace-rail-one-door=0`.
