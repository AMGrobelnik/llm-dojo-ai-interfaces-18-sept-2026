# A route carries the admission and access gates its siblings carry

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

Three route families in the dashboard API provision work: they take a user's
request and start a pipeline or a pod. Two of them hold a per-user admission
lock, refuse while intake is quiesced, and check the active-run limit. The
third, `resume_run`, does none of it. The rule was written for that outlier
and says plainly that it "exists so the count stays at one while it is fixed,
and at zero after".

The related failure is quieter: a route that turns the API auth off
(`auth=None`, `aii_optional_auth`) and then leans on a user-level check the
decorator has just disabled, or one that adopts the admission lock and
forgets the quiesce check beside it.

## Mechanism

The judgment is eliminated rather than approximated. "Does this route
provision work?" is answered by CALL CLOSURE over the whole package —
reaching `_launch_pipeline`, `RunPodAPI`, `create_pod` or
`start_workflow_async` — which resolves to exactly `{start_run, fork_run,
resume_run}` and is stable at closure depths 3 through 6. "Which gates should
it carry?" is not a list in the script: it is DERIVED from what a strict
majority of that population already carries, which is the rule's own title.

| failure mode | mechanism |
|---|---|
| a run-scoped route with no access gate | closure must reach one |
| auth override plus a run id | must reach a per-object gate |
| a new provisioning route, ungated | derived parity, majority rule |
| lock adopted, quiesce forgotten | some-but-not-all of the three |
| a module that does not parse | reported at line 1, never skipped |

Closure is what makes the delegation trap a non-issue: `start_run` holds the
lock inline and delegates quiesce and the limit check to
`runs_helpers.prep_request` two hops away, so a body-only scan invents a
second outlier. A test pins that.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**1 finding** — the outlier the rule tracks. Whole-tree runtime 0.14 s
(three runs, all 0.14 s); 42 routes, 3 provisioning, 21 run-id-scoped.

```
aii_server/dashboard/api/run_resume.py:383: resume_run provisions work
(reaches ['RunPodAPI']) but carries none of ['check_active_runs_limit',
'get_user_admission_lock', 'quiesce_intake_error'], which fork_run/start_run
— the other provisioning routes — all carry.
```

The hook is glob-scoped to the API package and takes the staged files, so the
finding bites when `run_resume.py` is edited, which is the moment its owner is
in that file anyway. Closing the gap deletes the debt line; nothing in the
checker changes, because the count comes from the tree.

## Fragility

| refactor | effect | guard |
|---|---|---|
| the api package moves | no files | exit 2 |
| the route decorator changes | 0 routes | exit 2 |
| provisioning names change | no population | exit 2, needs two |
| `run_id` renamed | check A empty | exit 2 |
| gates move to a decorator | closure still finds them | partial |
| gates removed from the pair | majority flips to 0 | not guarded |

The last two are the residual fragility. A gate that becomes purely
declarative drops the majority to zero and the parity limb then requires
nothing; so does "fixing" the stock by stripping the gates off `fork_run` and
`start_run` instead of adding them to `resume_run`. A floor requiring at
least one gate on any provisioning route would close it, and was not added
because it would hard-code the policy this hook deliberately derives.

## Residue

Whether a first-of-its-kind endpoint OUGHT to carry a gate no sibling has:
the program can only enforce agreement with an existing population, so the
first route of a new kind is ungated by construction, exactly as the first
provisioning route was. The rule's "with no comment defending the asymmetry"
escape hatch is gone — no comment is read, so a route that admits
unconditionally on purpose needs a CONFIG entry or a code change.

A throttle decorator was evaluated as a fourth signal and dropped: measured,
`guided_intake` and `guided_followups` carry one for cost throttling without
provisioning anything, so folding it in yields two false positives.

The access-gate limb overlaps the unit-test group
`aii/unit-tests/rule-server-run-access-gate`, with two differences in this
hook's favour: it selects handlers by the `run_id` PARAMETER rather than by a
literal path template, and it follows delegation through the closure. The
auth-override, parity and half-adoption limbs are covered nowhere else.
