<!-- hook: neutral-register -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Added lines carry none of the offense-register words the global CLAUDE.md bans — neutral professional engineering vocabulary is the house register, in files too

The directive is the global CLAUDE.md's, verbatim in intent: "think and
write NATIVELY in NEUTRAL, PROFESSIONAL SOFTWARE-ENGINEERING language … in
EVERYTHING including intermediate artifacts (… files)", with the
replacements spelled out — "a caller / any logged-in user" not
attacker/victim, "carries config it doesn't need" not exfiltrate, "reach an
endpoint lacking the auth gate its siblings enforce" not hijack,
"credential scope" not blast radius, "TTL cleanup / terminate" not
self-destruct, "corrupt/invalidate state" not poison. Substance stays
exact; only the vocabulary differs.

It was written for the agent's own output, and nothing pinned the files.
Measured 2026-09-03 with the rule's own ERE over the tracked tree: **56
hits in 39 files**, most of them in the rule engine's own tests and
proposals ("swap victim", "cache poisoning", "victim commit" — the
project CLAUDE.md itself uses the word for the message-swap incident). So
the register the directive asks for is not yet the register the tree is
written in, and every new file is a coin toss.

Mechanism: the engine's `rules-grep` in its default (added-lines) form —
at commit it greps only lines the staged diff ADDS, within the pathspec,
so the 56-hit stock never blocks anyone and a new occurrence does; in
all-mode it prints the stock as an advisory and exits 0. The rule's own
directory is excluded because a ban has to spell out what it bans. Both
case forms are matched per word; `[Ee]xfiltrat` and `[Pp]oison` catch
their inflections.

Probes, both ways (2026-09-03, via `rules-grep` in a scratch repo with the
probes staged as added lines): `probe/hit.md` → matched (`hijack`,
`victim`), exit 1; `probe/miss.md` — the prescribed replacements — → no
match, exit 0. Then the ERE over the live tree → 56 hits / 39 files, which
is the stock recorded above.

What approving costs: a future line quoting the incident prose that
already uses these words (a CLAUDE.md edit that repeats "the victim
commit") blocks until rephrased — which is the directive applied, not a
false positive. A genuine need to quote a third party verbatim is what the
`Rules-Waive:` trailer is for.

Nearest existing rules: `rule-canonical-nouns` (agent) governs identifier
vocabulary, not prose register; `rule-typos` governs spelling; nothing
governs register. No killed proposal covers it.

Delete-check: delete if the owner retires the directive from the global
CLAUDE.md; until then the file rule and the session rule say the same
thing.

PORTED 2026-09-14 onto the one-pass AST dispatcher (`general-ast-checks`,
`dispatch.py`), off the standalone `amg-hooks-grep` command above. The word-list ERE
survives unchanged as the candidate PREFILTER, over all seven live
extensions. Behind it, an `mdast` pass CONFIRMS only on `*.md`: a regex match
is dropped when it sits inside a fenced code block or an inline code span
(a backticked `` `victim` `` naming an identifier, an `attacker_ip = ...`
line inside a ```` ``` ```` transcript), checked per MATCH by its byte offset
rather than per line — a real violation sharing a line with a code-quoted
mention survives, only the code-quoted match is excused. The other six
extensions (`*.py .ts .tsx .sh .yaml .yml`) have no fenced/inline-code
concept in this port's scope, so their candidates pass through unfiltered,
identical to the live grep.

Measured against the research-monorepo consumer tree (whole-index/sweep lane, this
hook's live PATHSPEC): **0 candidates, 0 findings** across all seven
extensions — the tree is already clean of the banned vocabulary under this
pathspec (the 2026-09-03 measurement of 56 hits was over the rule engine's
own submodule, `amg-hooks`, which a consumer's `git grep
--no-recurse-submodules` correctly never descends into). DROPPED 0 / ADDED 0
here; the fenced/inline-code drop is proven on synthetic fixtures instead, in
`test_neutral_register_bites.py`.

NARROWED 2026-09-15: a candidate is also dropped, in every one of the seven
extensions (unlike the `*.md`-only mdast confirm step above), when the
matched word is immediately preceded by `.` — a member access or call on a
third-party object, e.g. notes-repo's `reply.hijack()` (Fastify's own method
name; nobody can rename it). This is a `_CANDIDATE`-regex-level negative
lookbehind, applied before a line is even considered a candidate, so it is
in scope everywhere the ERE runs, not only on markdown. A comment, string,
docstring or markdown mention of the word is never dot-adjacent, and neither
is our own `def`/`class`/const/variable definition using the word as its
name — both still count. Confirmed live: notes-repo's
`apps/claude-amg/remote-control/server/src/server.ts:309` (`reply.hijack()`)
no longer reports, with no other change to the finding set.
