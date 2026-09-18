<!-- hook: env-single-door -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Server-only process.env reads live only in lib/env.ts; app code sees env only as NEXT_PUBLIC_ values or props

lib/env.ts:9-18 states the contract verbatim and admits it is unenforced: 'the
contract is kept by convention (read in Server Components, pass down as props)
rather than enforced at build time' — a hard server-only guard is impossible
(breaks next.config.ts import and the jsdom suite, as the docstring
documents). The failure mode is silent: a client component reading
DJANGO_UPSTREAM or CONTACT_EMAIL compiles to the fallback default in the
bundle with no error. Current tree complies exactly (measured: server-only
reads exist only at lib/env.ts:30,40; everything else is NEXT_PUBLIC_ in
lib/api/http-common.ts:19,34 or NODE_ENV checks) — pin it before it drifts.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: frontend-config)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_env_reads.py  # scans tracked aii_frontend *.ts/*.tsx for process.env.<NAME> where NAME is not NEXT_PUBLIC_* / NODE_ENV / CI, allowing only lib/env.ts and *.config.{ts,mjs}

Condition: `git diff --cached --name-only -- 'aii_frontend/**/*.ts' 'aii_frontend/**/*.tsx' | grep -q .`

Two scope decisions the proposal did not settle, both made against the tree
rather than by preference:

- **The bracket form counts.** `process.env["CONTACT_EMAIL"]` reads exactly
  what `process.env.CONTACT_EMAIL` reads, and a gate matching only the dotted
  spelling would be trivially side-stepped without anyone meaning to.
- **Tests are out of scope.** `lib/__tests__/render-message.test.ts` sets
  `process.env.TZ` to pin a timezone. That is a test controlling its own
  environment, not app code reading deployment config, and TZ is neither
  NEXT_PUBLIC_ nor in the allow-set — so scanning tests would report it as a
  violation on the first run. Same exclusion every other gate here applies.

The scan is also line-aware about prose: a comment mentioning
`process.env.DJANGO_UPSTREAM` — and `lib/env.ts` discusses these names at
length — is not a read of it.

Proven to bite in a throwaway tree rather than inferred from the clean exit
this repo currently gives it: a component reading `DJANGO_UPSTREAM` and one
reading `process.env["CONTACT_EMAIL"]` are both named, while `NEXT_PUBLIC_*`,
`NODE_ENV`, `CI`, the door itself, a test file, and a comment naming the
variable all stay silent.

Delete-check: Cannot delete the dimension: DJANGO_UPSTREAM and CONTACT_EMAIL must come from
the environment (deployment-specific, and the domain is deliberately kept out
of tracked files per the aii-private-domain gitleaks rule). The single-door
module already IS the collapsed design; the rule keeps the door single.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The contract is stated in lib/env.ts and admits it is unenforced; a
build-time guard is impossible per its own docstring, so a grep banning
process.env outside lib/env.ts is the available instrument.
- KEEP: The contract is stated in lib/env.ts and admitted unenforced; a grep
for process.env outside env.ts/next.config.ts (NEXT_PUBLIC_ exempted) is cheap
with a short exception list. Prevents server-only config leaking into client
bundles by accident.
- KEEP: Grep process.env outside lib/env.ts + next.config.ts + NEXT_PUBLIC_
prefixed reads. The docstring's 'unenforceable at build time' concern doesn't
apply to a source grep at commit. Clean.


CORRECTED 2026-08-25: the gate no longer treats a missing `lib/env.ts` as
"could not run". A tree with no door AND server-only reads scattered through
app code is the exact state this rule exists to report, so bailing went silent
on it. Verified by probe: given a component reading `DJANGO_UPSTREAM` and no
door at all, it now exits 1 and names the read, with the hint adapted to
"create the door" rather than "import from it".

Third instance of that shape among this session's gates — the query-key and
admission-record checkers had it too — so it is a habit rather than a slip.
When a gate and its remedy are written in the same sitting, every tree you test
against already contains the remedy, and "require the remedy to exist" never
fails in front of you. It only fails on the tree that has the defect.