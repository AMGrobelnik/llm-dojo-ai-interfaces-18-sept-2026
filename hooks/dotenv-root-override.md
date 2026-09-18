<!-- hook: dotenv-root-override -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every load_dotenv of the repo-root .env passes override=True so a rotated key in .env beats a stale shell export

aii_lib/src/aii_lib/config.py:27-31 states the invariant and complies
('override stale shell env vars so rotating a key in .env takes effect');
aii_server/config/settings.py:23 and
aii_pipeline/src/aii_pipeline/_cli/setup.py:75 comply. LIVE VIOLATION:
aii_launcher/src/aii_launcher/deploy.py:315 calls load_dotenv(PROJECT_ROOT /
".env") with no override — so `aii_launcher --redeploy` (a production action)
resolves RUNPOD_API_KEY from whatever the launching shell still exports,
exactly the stale-key class config.py documents.
scripts/debug/redeploy_finished_run.py:28-30 shows the intended single-door
pattern (import aii_lib.config for the side effect).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-shared)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_dotenv_override.py

This block named `check_dotenv_override.sh` until 2026-08-26 while the file on
disk, and the frontmatter, were both `.py` — the proposal was for a shell
one-liner and the implementation went to Python. That single stale character
sequence kept the rule in BLOCKED with a working mechanism sitting beside it,
because `ready.py` treats EVERY `$RULE_DIR/<path>` occurrence in a rule body as
a claim that the file exists and `missing` outranks `has_cmd`. Verified: the
mechanism runs clean (exit 0) and the frontmatter command was correct all
along. → exit 1 with the offending sites

Proposed condition: `git diff --cached --name-only -z -- '*.py' | grep -zq . || [ "$RULES_MODE" = all ]`

Delete-check: Partially deletable: the launcher could drop its own load_dotenv and `import
aii_lib.config` for the side effect (it already depends on aii_lib),
collapsing to one door. Django settings.py must self-load before heavier
imports, and claude_cred_manager deliberately never loads the repo .env
(config.py:123-130), so at least two legitimate sites remain — the rule
enforces the flag on whatever sites survive.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Live violation (launcher's override-less load_dotenv beats a rotated
key with a stale shell export). Fix by importing aii_lib.config where
possible, then enforce override=True at the remaining doors. Absorbs rule-
dotenv-no-handrolled-parser — same one-door-for-.env invariant.
- KEEP: Live violation verified (deploy.py:315 lacks override=True) with a
real symptom class (rotated key loses to stale shell export). Fix by importing
aii_lib.config where possible, then a one-line grep pin. Absorbs rule-dotenv-
no-handrolled-parser.
- KEEP: Grep load_dotenv call sites for override=True (or the import-
aii_lib.config idiom). I verified the live violation: deploy.py:315 calls
load_dotenv without override. Trivial, loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
aii_lib/src/aii_lib/config.py lines 27-31 are exactly the three-line comment
plus `load_dotenv(_project_root / '.env', override=True)` — cite exact.
aii_server/config/settings.py:23 exact.
aii_pipeline/src/aii_pipeline/_cli/setup.py:75 is `from dotenv import
load_dotenv`; the compliant call is line 78.
aii_launcher/src/aii_launcher/deploy.py:315 is exactly
`load_dotenv(PROJECT_ROOT / '.env')`, no override, no comment claiming intent
— the violation is real. But I reproduced the consequence and i

Corrected statement of fact:
The missing `override=True` at deploy.py:315 is live, but the named victim is
wrong. --redeploy self-heals: aii_lib.config is imported transitively (via
aii_pipeline.utils.pipeline_config at deploy.py:95) before redeploy_runpod
runs, restoring the .env value. The paths where a stale exported key genuinely
survives into a client call are --resume
(aii_launcher/src/aii_launcher/_deploy/_runpod.py:105 ->
`resume_stream(api_key=...)`) and --stop-runpod-all (_deploy/_teardown.py:294
-> `RunPodAPI(api_key)`), neither of which imports aii_lib.config; plus an
exported-but-EMPTY var makes all four sites print 'RUNPOD_API_KEY not set'
while .env holds the key. Scoping caveat for the rule text: twelve
.claude/skills/* scripts load the repo-root .env deliberately WITHOUT
override, each carrying the comment 'load_dotenv never overrides an existing
var, so the repo-root … wins' — a blanket rule must exclude .claude/skills/.
Fix is one kwarg but lands on a production CLI with no test behind it.


BUILT AS AST, NOT GREP — a correction to this proposal, measured. The proposed
mechanism was `git grep 'load_dotenv(' | grep -v 'override=True'`. Run against
the tree it reports THREE sites of which ONE is real: the other two are a
trailing `# noqa` comment that mentions `load_dotenv()` and a docstring
discussing `load_dotenv(..., override=True)`. A gate built that way exits 1 on
a clean tree forever. Only a call node is a call.

ADOPTION (2026-08-25): the one real site is FIXED. `aii_launcher/src/aii_launcher/deploy.py`
now passes `override=True`, matching `aii_lib/src/aii_lib/config.py` and the reason it
states. That entry point is the sharpest case — it reads `RUNPOD_API_KEY` a few
lines below and spends real money, so a shell holding yesterday's key deployed
against the wrong account while `.env` looked correct.

Checked before changing behaviour, because `override=True` also means an inline
`VAR=x aii_launcher` stops working: no such invocation is documented anywhere
in the repo, and the only other env that function reads is set explicitly after
the load.

Verified against history: on the tree before the fix the gate exits 1 naming
`deploy.py:315` and nothing else; today it exits 0 over 2 calls.