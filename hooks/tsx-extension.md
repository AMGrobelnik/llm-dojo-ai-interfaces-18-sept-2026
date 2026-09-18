<!-- hook: tsx-extension -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# JSX lives in .tsx; a .ts file exports no components

The measured convention (104 of the 105 in-repo modules the 145 unit tests import are .ts — the lone exception is `features/run-views/_shared/render-message.tsx`, whose pure helpers two lib tests import on purpose; and zero .ts files anywhere in aii_frontend match the JSX pattern, tests and dev included. Re-measured 2026-08-22; previously stated as 78 modules, all .ts, with 4 stray .ts files carrying JSX in tests/dev): logic in `.ts` so Fast
Refresh works and tests import no component tree; anything returning JSX is
`.tsx`. This check runs `--tree`: it flags JSX-looking returns
(`return <Cap...` / `=> <Cap...`) anywhere in the non-test `.ts` stock,
every commit — flipped 2026-08-22 with the stock measured at zero hits,
so the first hit ever is the regression.

Fix when blocked: rename the file to `.tsx`, or move the JSX into a sibling
`.tsx` and keep the logic where it is. If the match is a false positive
(a generic like `=> <T>(...)`), waive with that stated — repeated false
positives mean the pattern here needs tightening, not more waivers.

Delete-check: the dimension could be deleted the OTHER way (all-.tsx
everywhere) — a valid owner call; until made, this pins the measured
majority convention (96% adherence).

RE-MEASURED 2026-08-24 — the stray count is **still exactly 4**, and they
are still the same kind of file:

    aii_frontend/dev/prod-component-dashboard.ts
    aii_frontend/features/human-feedback/__tests__/side-chat-toast.test.ts
    aii_frontend/lib/api/__tests__/api-error.test.ts
    aii_frontend/lib/api/__tests__/client.test.ts

Detection note, because the obvious pattern does not work. Searching `.ts`
files for an opening `<Tag` matches TypeScript GENERICS — `Map<string>`,
`Promise<Result>` — and reports 123 of them, which is nonsense. A JSX
CLOSING tag (`</Foo>`) is the discriminator: generics never produce one.

RE-MEASURED 2026-08-26 — **still exactly 4, the same four files**, and the
rule's `--tree` stock is still zero hits.

But the closing-tag discriminator has a SECOND false-positive class the note
above does not mention, and it costs two phantom strays. A grep for `</[A-Za-z]`
reports **6**; the two extras are prose, not code:

    constants/message-types.ts:452   `"terminal</arg_value>…"` in a docstring
    tests/e2e/tab-switching.spec.ts:60  ``<h1>Run details</h1>`` in a `//` comment

Both are documentation ABOUT markup. So the discriminator is a JSX closing tag
**outside a comment** — skip lines whose first non-space characters are `//`,
`*` or `/*` and the count returns to 4. Worth knowing before concluding the
stray set has grown: this tree explains itself in prose on purpose, so any
pattern that matches markup will also match writing about markup.

## Ported onto tsast (opening-tag ERE + `has_jsx`) — a README/live drift reconciled

`dispatch.py` keeps a per-line grep only as a candidate PREFILTER and confirms
each candidate against a real TypeScript parse (`tsast` `FileFacts.has_jsx`),
so the grep would no longer have to be a correct JSX detector — the parser
would be.

**That port is written but INERT, and the ERE is still the whole check.**
Re-verified 2026-09-14: no set wires a dispatcher command
(`tools/_dispatch_wiring.py`'s `dispatcher_commands()` returns nothing for all
four sets), so what runs at commit is the bare
`{amg_hooks}/lib/amg_hooks/amg-hooks-grep --tree '(return|=>)[[:space:]]*<[A-Z]'` line at
`research-monorepo/lefthook.yml:685` and nothing else. The prefilter is the live
predicate, not a prefilter, until a set adds that command.

**The drift this port found and reconciles.** The two Detection notes above
document detection by a JSX **closing** tag, `</[A-Za-z]` **outside a comment**
(skip lines opening with `//`, `*`, `/*`), reached after arguing that the
"obvious" bare opening pattern `<Tag` reports 123 generics and is "nonsense".
But the **shipped / live** amg-hooks-grep line in `research-monorepo/lefthook.yml` never used a
closing tag — it uses an **opening**-tag ERE:

- README's documented detection ERE (drifted):
  **`</[A-Za-z]`** (a JSX closing tag, outside a comment)
- Live lefthook amg-hooks-grep ERE (what actually ships):
  **`(return|=>)[[:space:]]*<[A-Z]`** (a `return` / `=>` then `<` then a capital)

They detect different things (closing vs opening tags). The live ERE avoids the
123 generics not with a closing tag but by **anchoring on `return` / `=>`** and a
capitalised component name — `return <Cap...` / `=> <Cap...`, exactly the main
statement above. The port's `_CANDIDATE` is that live ERE **verbatim** (the one
translation is POSIX `[[:space:]]` → Python `\s`), so it is the sole candidate
source and findings ⊆ candidates.

**What `has_jsx` supersedes.** The AST confirmation does structurally what both
README heuristics were approximating: a candidate line is a real finding only when
the `.ts` file **genuinely parses as containing JSX**. A `.ts` file is parsed with
the TS grammar first, so a generic arrow (`=> <T>(x)`) and an old-style
type-assertion cast (`return <Foo>bar`) parse cleanly there and report
`has_jsx = false` — dropped, with no closing-tag discriminator needed. A comment
or string that merely spells `</Foo>` yields no JSX node, so the "outside a
comment" line-skip is unnecessary too. This is fewer false positives than the flat
grep, never more: the only lines reported are candidate lines in a file the parser
confirms is JSX (or a file that parses under neither grammar, reported fail-closed
so a syntax error is never a hole in the ban).

Because `has_jsx` is a FILE fact, a `.ts` file that holds any JSX reports on every
one of its candidate lines, and a file that holds none reports on none. The
non-test `.ts` stock is still zero candidates today, so the port's finding count
over the live tree is 0 and `ADDED` over the live ERE is 0; the generic/cast drop
and the JSX catch are exercised by the bites cases in
`test_tsx_extension_bites.py`.
