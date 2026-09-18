<!-- hook: redeploy-one-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# A redeploy is launched through scripts/local/redeploy_detached.sh — no tracked file instructs running bare `aii_launcher --redeploy`.

Why one door: a redeploy runs for the best part of an hour (the resume
sweep alone took 66 min for nine in-flight runs), and on 2026-08-26 one
launched with a bare `setsid … &` died ~24 s in with no traceback and no
error — identified only by its stale lock. The wrapper is the launch
procedure that survives: own session (verified `sid == pid`, not claimed),
stdin closed, FILE output (never a pipe whose dead reader delivers
SIGPIPE), plus the status file `aii-redeploy-watchdog.sh` alarms on.
CLAUDE.md already says "use the wrapper, not `aii_launcher --redeploy
<sha>` directly" — but two shipped surfaces PRINTED the bare command as
next-step guidance, teaching every reader the undetached path at exactly
the moment they are about to deploy.

Pattern design — an instruction is a NON-BACKTICKED occurrence:

- every legitimate prose mention of the bare command backticks it (house
  style), so the ERE's leading ``(^|[^`])`` group skips them all;
- `:!.claude/skills/amg-hooks` — rule bodies and unit-test
  docstrings that merely mention the flag are out of scope by the task's
  own carve (and this rule's own frontmatter carries the string);
- `:!scripts/local/redeploy_detached.sh` — the one door may spell the
  command it wraps; today its exec line is `"$CMD" --redeploy "$SHA"` and
  does not even contain the literal, so the exclude is defensive.

Measured hit list (2026-08-28). At authoring, BEFORE the concurrent fix:
3 instruction sites — `aii_launcher/src/aii_launcher/deploy.py:292`
(`print(f"   next: aii_launcher --redeploy {sha}")`), `deploy.py:307`
(the retired `--gh` branch's `then:` hint — a third site the pattern
surfaced beyond the two known ones), and
`.lefthook/pre-push/release-tag-guard.sh:33` (`echo "Run 'aii_launcher
--redeploy' …"`). Re-measured LATE the same session, after the concurrent
fix reached the working tree: **0 hits, exit 0** — deploy.py:292/:307 now
print `scripts/local/redeploy_detached.sh {sha}` and the guard now echoes
`Run 'scripts/local/redeploy_detached.sh <sha>'`; both files are still
uncommitted (`M` in git status), so re-measure at approval — the rule may
read red again only if that fix fails to land.

Legitimate mentions verified UNMATCHED (all backticked): CLAUDE.md:75
(itself the warning to use the wrapper), CLAUDE.md:342,
aii_runpod/ACCOUNT_MIGRATION.md:258, deploy.py:142 (a commit-message
string), deploy.py:237 (docstring), aii_runpod/…/_redeploy.py:723 (a
recovery log line explaining what a re-run does — judged a mention, not an
instruction: the reader's canonical re-run instruction is CLAUDE.md's,
which names the wrapper), scripts/local/watchers/aii-image-watcher.sh:24,
redeploy_detached.sh:3, and the engine tree's docstrings via the exclude.

Probes, both ways (2026-08-28, via the engine's own `rules-grep --tree`):

- RED, scratch git repo: planted `To ship, run aii_launcher --redeploy
  abc123` (doc.md:1) and `echo "next: aii_launcher --redeploy $sha"`
  (hint.sh:1) both matched, exit 1 — while a planted CLAUDE.md-style
  backticked line and a double-backtick docstring in the same repo did
  not print;
- GREEN, real tree with the rule's exact command: 0 hits, exit 0 (3 hits
  under the same command before the concurrent fix — the pattern found
  both known sites plus deploy.py:307).

Proposed type: **cmd-check** · scope: **whole-tree (`--tree`, blocks both
lanes)** · value: **high** (proposer: owner-tasked, 2026-08-28; incident
2026-08-26)

### AST port (2026-09-14)

Mechanism: `dispatch.py` keeps the ERE as a cheap per-line PREFILTER over the
same `.` pathspec (minus the two excludes) and adds a confirm step behind it,
routed by extension since the population is not one language:

| extension | reader | drops |
|---|---|---|
| `*.md` | `lib/amg_hooks/mdast.py` | a hit inside a fenced block or an inline code span |
| `*.py` | `tokenize` (stdlib) | a hit inside a `#` comment (docstrings are NOT dropped) |
| `*.sh` | `lib/amg_hooks/shast.py` | a hit inside a `#` comment |
| everything else | none | nothing — the live grep's verdict stands unconfirmed |

The last row is a documented gap, not a silent one: nothing in `lib/amg_hooks`
reads YAML, JSON, Dockerfiles or plain text structurally, and this rule's own
measurement below finds zero real hits in that population, so a fifth reader
is not warranted. A `.md`/`.py`/`.sh` file that fails to parse gets the same
"report everything" treatment as an unconfirmed extension — see `dispatch.py`
for the fail-closed detail. No confirm step ever ADDS a line, so findings stay
a subset of the grep's candidates.

Measured against the consumer index 2026-09-14, whole-tree: 2057 files in the
population (`.` minus both excludes), 0 candidates, 0 findings, 0 dropped, 0
added — matching the re-measurement above, exit 0.

PORTED 2026-09-14 onto the one-pass AST dispatcher: the standalone `amg-hooks-grep`
line is removed from `research-monorepo/lefthook.yml`, and `research-monorepo-ast-checks`
(the shared dispatcher command) now discovers and runs this hook's
`dispatch.py` in the same pass as every other AST-confirmed hook. `SCOPE` is
`"tree"`, matching the retired `--tree`: there is one lane, and a committed
instruction blocks a later unrelated commit the same as any other tree-mode
hook.

Delete-check: the deeper deletion is making the launcher itself refuse an
undetached `--redeploy` (e.g. requiring the session-leader check or an env
var only the wrapper sets, with an explicit override) — that would retire
the doc-hint dimension outright and is an owner call on the launcher's
interface; until then this text gate keeps shipped surfaces from teaching
the path that dies on hangup.
