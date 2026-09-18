<!-- hook: dsn-structural-redacted -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Postgres DSNs are composed with URL.create (never f-strings) and logged only through the password-masked form — hide_password=False stays inside the composer

aii_lib/src/aii_lib/dbos_app/__init__.py:119-127 records the incident: an
f-string DSN turned password 'p@ss' into a corrupted host, and
POSTGRES_PASSWORD is a human-set .env secret where '@' is plausible — 'this
was the lone hand-assembled DSN in the repo'. __init__.py:340-352
(_redact_dsn) states redaction is load-bearing, not cosmetic: init_dbos logs
both URLs every boot into entrypoint.log, which run_server.sh mirrors onto the
shared network volume readable by every pod. The only legitimate
hide_password=False is the composer's return at :155. Whole-tree grep confirms
zero other sites today — pin before the next hand-assembled DSN appears.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-shared)

Proposed command — **IMPLEMENTED 2026-09-07 as `$RULE_DIR/check.sh`**, invoked from
the frontmatter `command: bash $RULE_DIR/check.sh`. The one-liner it was promoted
with, kept for the record:

    rules-grep "hide_password=False|f[\"'][^\"']*postgres(ql)?(\+psycopg)?://" -- '**/*.py' ':!aii_lib/src/aii_lib/dbos_app/__init__.py' ':!.claude/skills/amg-hooks/rules/**'

The apostrophe is spelled into the bracket by shell quoting (the pattern is
double-quoted, so `\"` is the escaped double quote and `'` sits literal),
NOT as `\x27`: `rules-grep` runs `git grep -nE`, and git grep's ERE engine
treats `\x27` inside a bracket expression as the literal characters
backslash-x-2-7. Probed 2026-08-28 with two fixture files: under the old
`\x27` spelling, `f"postgresql…"` matched but `f'postgresql…'` did NOT, so
a single-quoted f-string DSN escaped the gate. (GNU `grep -E` matches both,
which is how that spelling looked tested.) Under this spelling both probes
match, the whole-tree sweep minus the composer and the rules tree is clean
(verified 2026-08-28), and minus only the composer it finds exactly the
deliberate fixture `test_dsn_redaction.py:22` — the false positive the
exclusion below exists for.

The rules-tree exclusion is load-bearing before any `--tree` adoption:
`research-monorepo/unit-tests/dbos-bootstrap/test_dsn_redaction.py:22`
composes an f-string DSN as a deliberate fixture — invisible while the
check reads added lines only, a standing block the moment it sweeps the
whole tree (the engine's preferred form).

**IMPLEMENTED 2026-09-07 as `$RULE_DIR/check.sh`**, invoked from the frontmatter
`command: bash $RULE_DIR/check.sh`, and STRICTER than the line above in one
place. That pattern bans one composition shape — an f-string — so
`"postgresql://" + user`, `"postgres://%s" % host`, `.format(…)` and
`"".join([…])` all passed it while violating the statement, and an agent
reading the statement catches every one. Measured 2026-09-07 across the three
package dirs: the scheme literal appears NOWHERE, not even in the composer,
which builds the URL structurally with `URL.create` and never spells a scheme
string. So the check bans the literal outright outside the composer — strictest,
zero hits today, and it closes every string-building shape at once instead of
enumerating them. `hide_password=False` is matched with optional spaces around
the `=`.

**What a grep still cannot see, stated rather than implied:** a DSN assembled
from a scheme held in a VARIABLE (`f"{scheme}://{user}:{pw}@{host}"`) carries no
literal and no pattern here matches it. That shape has never appeared in this
repo and the composer is the only place a DSN is built, but it is the residue
of mechanizing this rule and it belongs on the record rather than in a claim of
total coverage.

The rules-tree exclusion the paragraph above calls load-bearing is no longer
needed: the deliberate f-string fixture at
`research-monorepo/unit-tests/dbos-bootstrap/test_dsn_redaction.py:22` sits outside
the three package pathspecs, so `--tree` never reaches it.


Proposed condition: `git diff --cached --name-only -z -- '*.py' | grep -zq . || [ "$RULES_MODE" = all ]`

Delete-check: The hand-assembly dimension was already deleted (the incident fix collapsed
every DSN onto URL.create in one module); DSN logging itself cannot be deleted
— the boot line exists because two silent no-log branches once cost a full
investigation (:311-321). The rule locks the deleted end-state.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Incident-backed (f-string DSN corrupted by '@' in a human-set
password) and the masked-logging half is credential hygiene stated only in
prose. Hand-assembly already deleted; enforce the end-state.
- KEEP: Incident-backed (corrupted host from '@' in password) and secret-
logging adjacent. Narrow greps (f-string DSN shapes, hide_password=False
outside the composer) at near-zero cost.
- KEEP: Grep for postgres:// f-string composition and hide_password=False
outside the composer module. Incident-backed, literal-ban shape, loud.
