# A registered handler that can spend money or provision a billable resource declares retries=0

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The ability worker wraps every handler in a blanket result-retry: the loop
re-invokes the handler on a transient-looking error, up to four runs at the
default `retries: int = 3`. The cost ledger books the call ONCE however many
times the handler ran, and a provisioning call is not idempotent, so a handler
that has already billed must never be re-invoked.

The re-invocation genuinely fired. `aii_fast_web_search` returned its failure
as `{"success": False, "error": f"serper: {type(e).__name__}: {e}"}`; a
`ReadTimeout` stringifies with "Read timed out", which is in the retry loop's
`_TRANSIENT_ERRORS`, so the whole free-first walk plus a second billed Serper
credit ran. `concept_fig_gen` puts `cost_usd` on its FAILURE dict on purpose,
so the caller books the spend even on failure — and the retry loop returns
only the LAST result, silently defeating exactly that fix.

A partial guard already exists in the runtime: the retry loop short-circuits
on a result carrying a key from `_RESOURCE_ID_KEYS`. It covers provisioned
resources keyed on `pod_id` and nothing else, so per-call metered spend stays
exposed. This hook extends that mechanism rather than inventing one, and reads
its key list.

The agent rule that preceded it recorded 45 applications, 18 blocks and **zero
evidence text** — 45 runs of the same grep with nothing written down.

## Mechanism

`check.py` enumerates the registered handlers by decorator and asks each one
whether it can spend, over the handler's intra-module CALL CLOSURE — the
handler plus every module-level function it transitively calls. Four signals,
a closed enumeration:

| signal | detects | mechanism |
|---|---|---|
| A | books external spend | a call in `spend_call_names` |
| B | returns money | a result key like `cost_usd` |
| C | provisions a resource | a runtime key + a create call |
| D | metered spend, no booking | a paid key env + a write |

Then the verdict:

| failure mode | mechanism |
|---|---|
| ships on the default retry | the decorator kwarg is read |
| `retries=3` written out | only the constant 0 satisfies |
| the decorator is aliased | import-alias map |
| an unrelated `main()` spends | closure-scoped, not file text |
| spend two helpers deep | the closure is transitive |
| a read-only catalog handler | GET-only, no write, not flagged |
| the decorator is renamed | vacuity guard, exit 2 |
| an unstaged edit decides it | content read from the index |

Signal C reads `_RESOURCE_ID_KEYS` out of the runtime's own retry module by
AST, from the index — the same list the retry loop short-circuits on — so the
checker and the runtime agree by construction, and adding a key to the runtime
widens the gate for free. `resource_keys_fallback` covers the module moving,
and `--explain` prints which source was used.

Signal D trades a false positive for coverage, deliberately: without it, a new
skill that charges an API and forgets to book the cost is invisible. Where the
judgment goes the other way, the answer is an in-source
`# spend-exempt: <why>` comment on the decorator — one line, written once at
the site, greppable, instead of an agent re-litigating "is this billable?" on
every commit.

The whole-tree pre-filter skips parsing any module whose text does not mention
the decorator name: 0.19 s with it, 1.1 s without, and the name comes from
`CONFIG`, so nothing is narrowed by hard-coding a path.

## Stock

**1 finding**, measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7` (re-confirmed unchanged at `eaf82761c`) in 0.19 s whole-tree (0.03 s scoped to one file). The census from
`--explain`: **31 registered handlers, 5 spend-capable**.

```text
retries=0  concept_fig_gen.py:700       core_concept_fig_gen   result key 'cost_usd'
retries=0  aii_or_call_llms.py:205      core_openrouter_call   result key 'cost_usd'
retries=0  aii_runpod_gen_pod.py:73     core_runpod_create_pod 'pod_id' after _rp('POST',…)
UNGUARDED  aii_runpod_gen_template.py:177 core_runpod_ensure_template
                                        RUNPOD_API_KEY + _rp('POST', …)
retries=0  aii_fast_web_search.py:551   core_web_search        result key 'cost_usd'
```

The finding is `.claude/skills/aii-runpod/scripts/aii_runpod_gen_template.py`
at line 168 (the decorator), signal D on a find-or-create the rule body argues
is not billable. Its fix is one `# spend-exempt: <why>` comment rather than a
per-endpoint "templates are free" judgment encoded in the checker.

The hook is relation-scoped and passes `{staged_files}`, so this stock blocks
only a commit that touches that one file; every other module is gated today.
That is why it ships `active` rather than as debt.

## Fragility

| refactor | effect | guard |
|---|---|---|
| the decorator is renamed | nothing found | exit 2 whole-tree |
| `_RESOURCE_ID_KEYS` moves | C narrows | fallback, `--explain` |
| spend moves to an import | missed | none — see below |
| a new paid provider | D misses it | A-C still apply |
| the marker becomes routine | silent waivers | greppable, countable |

The per-file mode cannot fire the rename guard — only the whole-tree run can —
so the adoption sweep has to be run periodically, or wired into CI.

The closure is intra-module by design, because the population is single-file
skill scripts. A handler split across modules would need one-hop import
following.

## Residue

"Spends money" in the general case. A handler that charges an API whose auth
variable is not in `paid_key_env`, books nothing, returns no cost key and
provisions no keyed resource is invisible. The residue is bounded and named,
and it is exactly that shape.

Also not implemented: the better end state the delete-check proposes — remove
the `retries` knob from the decorator and stop wrapping handlers, letting
callers own recovery with full context. That is an owner call. If taken, this
hook collapses to "no ability declares retries>0", a one-line variant of the
same script.

Signal D sits on the boundary of a separate pending rule about ledger booking.
If that one lands, D belongs there and this hook keeps A-C.
