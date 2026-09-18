# A failure response leaves the API in one envelope shape

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The frontend's error interceptor is built against one response shape: a 4xx
or 5xx whose body carries a `detail` key, produced by `create_response`. A
failure that arrives some other way — a different constructor, a payload
without `detail`, a 200 carrying an `ok: false` flag, or an exception raised
where the siblings return — reaches the client as something the interceptor
does not recognise, so the user sees a generic message instead of the one the
endpoint wrote.

This was the most-exercised of the converted rules: 188 applies and 92 fails.
It is also the only one with recorded evidence, five identical passes reading
"no error path added or altered; the sweep's hits are pre-existing and
correct". That sentence is the specification: find the failure sites, tell a
failure from a download, and know that the outlier still carries the right
key. All three are in the checker.

The body's own numbers have moved since it was last swept, which is the
argument for a program that prints its counts on every run: 76 helper sites
are now 77, and the four `JsonResponse` outliers are down to one.

## Mechanism

`ast`, not grep, and for a reason the body records: the outliers are
multi-line calls — `return JsonResponse(` with the dict on the next line — so
a pattern requiring the constructor and the key on ONE line matches none of
them and reports the file clean.

| failure mode | mechanism |
|---|---|
| a failure built another way | any 4xx/5xx call must be the helper |
| the payload has no `detail` | dict-literal keys; extras are fine |
| a 200 with an outcome flag | `ok`/`success`/`error`/`failed` keys |
| a raise where siblings return | majority of handlers return, today |
| a module that does not parse | reported at line 1, never skipped |

The constructor is deliberately not enumerated — the STATUS is the signal —
so a failure built with Django, Ninja, DRF or a hand-rolled class is caught
identically. A response with no status kwarg is never a failure site, which
is what keeps the file-download path in `files/_run.py` out of the finding
list, exactly as the recorded evidence says it should be.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**3 findings**, whole-tree runtime 0.08 s (three runs, all 0.08 s); 78
failure sites, 77 helper calls, 25 return against 2 raise handlers.

| file | line | finding |
|---|---|---|
| `run_resume.py` | 399 | `JsonResponse(status=409)` |
| `contact.py` | 74 | raises where siblings return |
| `race_parked.py` | 138 | raises where siblings return |

The first is the outlier the body tracks, now down from four to one. The two
raisers are the whole raise population and both carry an in-code
justification — `race_parked.py:125` says it is raised "rather than returned
as a second success schema". They are recorded as debt rather than silenced:
no comment escape hatch was added, because a magic comment is the sort of
thing an agent rule could read and a program should not have to.

## Fragility

| refactor | effect | guard |
|---|---|---|
| the api package moves | no files | exit 2 |
| failures stop carrying a status | no population | exit 2 |
| `create_response` renamed | every site looks bad | exit 2 |
| the route decorator changes | no handlers | exit 2 |
| the envelope key changes | 77 findings at once | not guarded |

The last row is deliberate: that IS the change the rule exists to make
visible, and it is a one-line CONFIG edit.

## Residue

Whether a refusal is semantically a 409 or a 400 — any 4xx or 5xx satisfies
the shape check. Whether a raise is deliberate: the two documented raisers
are flagged, and the rule's "pass everything else" leniency is gone. Failure
responses whose payload is a variable rather than a dict literal are skipped
by the payload limbs; there are none today, and the constructor limb still
applies to them.

`http-detail-no-exception-text` governs the CONTENT of `detail` — it must not
interpolate a caught exception — and composes with this one, which governs
the shape: that key must exist here, and that hook says what may go in it.
