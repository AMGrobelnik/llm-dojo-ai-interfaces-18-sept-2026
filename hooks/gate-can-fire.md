# A hook command's gate can actually fire

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 1s | debt |

## Why

A gate that cannot fire is not a gate. The retiring rule engine kept a ledger
of every run, and it settles what that costs. Two of its user-flow rules gated
in the CONDITION on `RULES_APP_URL`, a variable no lane sets: over **3,132
runs** each recorded **2,507 skips, zero applications, zero blocks**. Two
sibling rules gated on the same variable inside the COMMAND, with
`[ -n "$RULES_APP_URL" ]` and an early exit 0, and were recorded **PASS 2,001
times** — every one of those green ticks having run no browser at all.

The pair that skips is dead weight; the pair that passes is worse, because a
report of green includes it. Neither can be told apart from a healthy hook by
looking at the run record, which is the whole reason this is a program and not
a review item.

Both idioms survived the migration into `<set>/lefthook.yml` with the shape
intact inside their `run.sh`, so the population moved and the mechanism did
not. The two flow commands are recorded as debt here rather than fixed,
because the fix is deleting them — see
`docs/decisions/retired-hooks.md`, where the verdicts on
`rule-flow-run-lifecycle` and `rule-flow-redeploy-resume` say where that
intent goes instead.

This hook was converted from an `aii/user-flows/` rule, but nothing in the
mechanism is project-specific: it reads whatever sets exist under the hooks
root, so it ships in `general`.

## Mechanism

`check.py` reads every `run:` line in every `<set>/lefthook.yml`, resolves each
to the files it delegates to (`{amg_hooks}/…`, `$AMG_HOOKS/…`, `$RULE_DIR/…`), and looks in
that text for an early exit whose test fails when an environment variable is
unset. Each such variable is then resolved against every assignment site in
both the hooks repo and the consumer. A variable nothing sets is a finding: the
exit code says which kind.

| failure mode | mechanism |
|---|---|
| exits non-zero when `$V` is unset | DEAD GATE |
| exits 0 when `$V` is unset | VACUOUS PASS |
| the gate sits in a delegate script | run line resolved |
| `${V:-}`, the `set -u` spelling | read as gateable |
| `${V:-commit}`, non-empty default | not gateable |
| `-z` or `!=`, true when unset | not a blocking test |
| unset variable used as a filter | needs an exit idiom |
| a yaml `env:` block sets it | counted as a setter |
| `V="${W:-}"` forwards the question | chain resolved |
| `PATH`, `CI`, `GIT_DIR` and kin | runner-provided list |
| a gate quoted in Python prose | docstrings dropped |

Two of those rows are load-bearing rather than refinements, and each has its
own test. **Following the delegate script**: both dead commands keep the gate
inside `run.sh`, so a checker that reads only the `run:` string finds nothing —
the first version of this program found the two vacuous commands and missed
the two dead ones. **The exit idiom is what separates a gate from a filter**:
`RULES_EXCLUDE` is also set nowhere and is referenced by five live commands,
and is correctly silent, because unset there means "exclude nothing" and the
command still runs.

The docstring row is not hypothetical: it is this hook reporting ITSELF. Run
over a build that included it, the check flagged `general/lefthook.yml` for the
command `gate-can-fire`, because its own `check.py` quotes
`[ -n "$RULES_APP_URL" ] || exit 0` in the docstring that explains what it
looks for, and a shell scanner reads that sentence as shell. A `.py` delegate
now has its docstring lines blanked before the scan; ordinary string literals
are kept, so a gate a Python delegate genuinely hands to a shell still counts.
Both directions are tests. The sibling `toolchain-pinned` hook records the same
lesson from the other side — English prose read as binary names — and its fix
is the same one: parse Python as Python.

The passthrough row is the one that would have made this check go green while
the gate it exists to catch stayed dead: `lib/amg_hooks/amg-hooks-env` contains
`RULES_APP_URL="${AMG_HOOKS_APP_URL:-}"`, which sets nothing of its own — it forwards
the question — so the chain is resolved rather than counted.

`--explain` lists every gate variable with where it is set, and every debt
entry. `--emit-debt` prints today's findings in the CONFIG `debt` key's form.

## Stock

Re-measured 2026-09-14 against `/home/<user>/projects/research-monorepo`:
**265 hook commands over 4 sets, 512 delegate scripts followed, 3 early-exit
env gates over 2 gate variables, 1 of the two set somewhere, 2 recorded debt,
0 findings shipped.** Whole-tree runtime **roughly 1–2.5 s** across eleven
runs, with more run-to-run spread than the single-digit-percent variance
elsewhere in this doc — this box runs other CPU-heavy jobs (image builds,
CI) that contend for it, so the wall clock swings with what else is running,
not with the tree. The
first measurement, at `44642bb4f`, read 256 commands and 454 delegates at
0.46 s; it was 0.28 s before the Python delegates were parsed rather than
scanned as text, so that correctness is what the walk costs. Both counts grow
with every hook added, so re-run `--explain` rather than quoting these — what
must not happen is a DROP over the same tree, which would mean the run-line
parser stopped seeing commands.

The two debt entries, both VACUOUS PASS:

```text
research-monorepo/flow-share-link/RULES_APP_URL
research-monorepo/flow-byo-openrouter-key/RULES_APP_URL
```

They are debt rather than findings because the remedy is to delete the two
commands, not to set the variable, and that deletion is an owner call recorded
in the decisions file. The hook therefore ships `debt` with those two excluded
and `fail_text` pointing here; empty the CONFIG `debt` set and it reports them
again. The third gate resolves `$REPO`, which a scanned script does set, so it
is not a finding — the discrimination the whole check rests on.

## Fragility

| refactor | effect | guard |
|---|---|---|
| lefthook.yml indent moves | nothing parsed | commands floor |
| run lines stop delegating | gate unseen | scripts counted |
| a gate phrased another way | walks past | one CONFIG regex |
| the hook folder moves depth | wrong root | `AMG_HOOKS_ROOT` |
| a set folder is added | scanned | discovery, no list |
| a setter shape not listed | false finding | assign shapes |
| a gate named in prose | false finding | docstrings dropped |

The commands floor is the one that matters: below 20 parsed commands the check
exits 2 rather than reporting a clean tree it never read. That is the same
failure this hook exists to catch, applied to itself.

The assign-shapes row fails in the unsafe direction — a setter written in a
shape the CONFIG list does not know reads as "nothing sets it". The seven shapes
cover shell, yaml, three Python spellings and a CLI flag, and `--explain`
prints the resolved setter for every variable so a wrong answer is visible
rather than silent.

## Residue

The flows themselves are not attempted, and that is the verdict rather than a
limitation. Driving a redeploy takes about an hour and a live browser walk
spends money; neither belongs on a commit. Their invariants already have
headless coverage — 23 modules and 147 test functions behind the redeploy
steps, 39 modules and 282 behind the lifecycle steps — and the decisions file
says where the remaining prose goes.

Also dropped: the converter's `--history` mode, which read the rule engine's
own `history.jsonl` to surface a rule that never applies for some reason the
static half cannot see. It found one such rule and read it correctly as
legitimately narrow rather than dead. The ledger dies with the engine, so the
mode has no population here.

Not judged: whether a gate that CAN fire is aimed at the right population. A
command wired to a glob that matches nothing is invisible to this check.
