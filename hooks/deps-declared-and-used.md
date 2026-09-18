<!-- hook: deps-declared-and-used -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# Every package-source import resolves to a dependency declared where it runs

An import that resolves only because some *other* distribution happens to
require the module is a latent ImportError: it fires the day that provider
drops the edge, on the machine furthest from the person who can read the
traceback. This rule says the declaration lives where the import lives.

Narrowed 2026-08-28 (audit): the original proposal was bidirectional —
declared→imported and imported→declared. The unused half is DROPPED: the
TRAP section below measured its truthful stock at close to zero once
runtime-contract, binary-invoked and string-loaded dependencies are
excluded, so this rule keeps only the DECLARED half. That half is free of
the unused half's three hazards, and dropping it removes the per-package
allowlist the generated-code closure would have needed.

## Green as of 2026-09-05 — the stock was DECLARED, not ignored

The body used to end here with "the command below does not arrive green".
It does now. Measured with deptry 0.25.1, DEP002 off, each package's own
source root scanned, on a `git archive` of `b07138d18` (before) and on
the working tree after. Counts are IMPORT SITES, deptry's unit; the module
count differs and is given wherever it matters:

| package | before | after | dominated by (sites) |
|---|---|---|---|
| aii_lib | 27 | 0 | sqlalchemy 25, in 16 modules |
| aii_pipeline | 323 | 0 | aii_lib 267, dbos 46 |
| aii_server | 301 | 0 | aii_lib 208, dbos 28 |
| aii_launcher | 38 | 0 | aii_lib 20, aii_runpod 8 |
| aii_runpod | 31 | 0 | loguru 20, httpx 5 |
| claude_cred_manager | 0 | 0 | — |
| **total** | **720** | **0** | all DEP003 |

Every one of the 720 was DEP003 ("imported but it is a transitive
dependency") — not one DEP001, i.e. every module was reachable, and the
gap was purely that nothing named it. They collapse to **28 declarations**
across five `pyproject.toml` files: 8 first-party sibling edges and 20
third-party ones, and `uv lock` moved no package. Two rules together fix
every specifier, leaving nothing to taste:

- 14 of the 20 name a distribution the workspace ALREADY declares
  somewhere, so `rule-shared-dep-floors-agree` settles them — the new
  entry repeats the existing specifier verbatim (`dbos~=2.20.0` x4,
  `httpx>=0.28.0` x2, `pyyaml>=6.0` x2, and one each of
  `psycopg>=3.1`, `pydantic[email]>=2.11.0`, `loguru>=0.7.0`,
  `tenacity>=8.0.0`, `python-dotenv>=1.1.0`,
  `opentelemetry-api>=1.20.0`). Two of those were learned the hard way:
  the first draft floored psycopg at the locked `>=3.3.4` and pydantic at
  `>=2.13.4`, and that rule failed until both were lowered to the floors
  aii_server and aii_lib already carried.
- The other 6 edges are 4 distributions the workspace had never declared
  at all (0 declarations at `b07138d18`), so there is nothing to agree
  with and the floor is the locked version: `sqlalchemy>=2.0.49` x3,
  `typing-extensions>=4.15.0`, `asgiref>=3.11.1`, `cryptography>=50.0.0`.
 The only lock additions are deptry itself
and its two new transitives (`requirements-parser`, `tomli`).

Owner decision, taken rather than deferred: **declare, do not ignore.** A
`[tool.deptry] ignore` would have silenced the finding while leaving the
latent ImportError exactly where it was.

Three shapes the declarations take, and why each is spelled that way:

- **First-party siblings — plain names, resolved by the workspace.**
  `aii_pipeline` now lists `aii-lib`; so do `aii_server` and
  `aii_launcher`, which additionally list `aii-pipeline`. The spelling is
  copied from `aii_runpod/pyproject.toml:10`, which has declared
  `aii-lib` this way all along: a bare name, no per-member
  `[tool.uv.sources]`, because the workspace root already pins it
  (`pyproject.toml:39`, `aii_lib = { workspace = true }`).
- **`aii_runpod` is an EXTRA, never a base dependency.** The public/OSS
  export does not ship that directory, so a base dependency would break
  it. Every import of it is function-local and RunPod-only, and
  `aii_launcher/src/aii_launcher/deploy.py:69` already probes for it and
  fails with an actionable message. `aii_pipeline`, `aii_server` and
  `aii_launcher` each gained `runpod = ["aii-runpod"]`, the same name and
  spelling as the workspace root's own extra (`pyproject.toml:26`).
  deptry reads `[project.optional-dependencies]` as declared, so this
  satisfies the rule without pretending the package is always present.
- **Third-party transitive-only imports — declared at the locked
  version.** loguru, dbos, SQLAlchemy, httpx, PyYAML, tenacity, psycopg,
  asgiref, cryptography, pydantic, python-dotenv, typing-extensions,
  opentelemetry-api. Two carry extra reasoning: `pydantic[email]` in
  `aii_server`, because `dashboard/api/contact.py:29` imports `EmailStr`
  and that raises at class-definition time without email-validator —
  which reaches the venv today only via `fastmcp-slim -> pydantic[email]`,
  three packages from anything that asked for it; and `dbos~=2.20.0`, the
  load-bearing ceiling from `aii_lib`, REPEATED verbatim in all four
  siblings. The first attempt spelled those `dbos>=2.20.0` on the
  reasoning that the siblings import only public dbos API, all now depend
  on `aii_lib`, and a resolver intersects the two. The full suite said
  otherwise: `rule-private-api-deps-are-capped` failed both of its tests,
  because it requires a ceiling on EVERY declaration of a privately
  imported distribution — the image builds resolve from these files, not
  from `uv.lock`, and dbos 2.30.0 deleting
  `dbos._core.execute_workflow_by_id` crash-looped the server pod on
  2026-08-24. Four places to bump is exactly what that guard trades for
  not repeating that outage; the reasoning-about-intersection version is
  the kind of argument the guard exists to refuse.

The "name collision on PyPI" note that kept `aii_lib` out of
`aii_pipeline`'s list is retired, and the rewritten comment there records
why: all four names are unregistered on PyPI (404 for `aii-lib`,
`aii-pipeline`, `aii-server`, `aii-runpod`, checked 2026-09-05), the
workspace source means `uv lock` never reaches an index at all — the lock
now reads `{ name = "aii-lib", editable = "aii_lib" }` inside
`aii-pipeline`'s `requires-dist` — and the images install every editable
in ONE `uv pip install` (`Dockerfile.pipeline:42,158`,
`Dockerfile.server:74,483`) where the local project satisfies the name.

**deptry is now a real dependency of this repo**, `deptry>=0.25.1` in the
root `[dependency-groups] dev`. The command invokes `.venv/bin/deptry`, a
native binary, matching every other hook in `lefthook.yml` — never `uvx`.
The whole six-package sweep costs **0.14 s**, so it is cheap enough to run
on any commit its condition matches.

## Six invocations, run concurrently — and why it cannot be one

The six are SIX because the statement is "declared where it RUNS": each
source root is judged against its own `pyproject.toml`. deptry 0.25 does
accept several ROOTs in one call — `deptry src worker` — but exactly one
`--config`, so a single invocation would union six source trees against
one dependency list. An import declared by any one member would then pass
for all six, which is the latent ImportError this hook exists to catch.
Merging them is not an optimisation available here at any price.

What was available was the six WAITS. `check.sh` backgrounds all six,
reaps them, and replays each buffer in package order, so the win is the
serial sum collapsing to the slowest single run (`aii_server`, 0.17 s):

| form | runs (s) | median |
|---|---|---|
| serial `for` loop | 0.529 0.532 0.531 0.537 0.518 | **0.531** |
| concurrent | 0.145 0.142 0.134 0.149 0.136 | **0.142** |

Measured 2026-09-14, five runs each, interleaved, in the research-monorepo
working tree; deptry 0.25.1, warm.

Two properties the buffering buys, both verified byte-for-byte against
the serial form. The report is ORDERED — files are replayed in package
order once every child is reaped, so no two writers interleave and the
output does not depend on which package finished first. And it is on the
same STREAM: deptry writes everything, "Scanning N files..." included, to
stderr, so the replay goes to stderr and stdout stays empty exactly as
before. ANSI is unaffected — deptry colours unconditionally unless
`--no-ansi`, so a buffer file and a pipe carry the same bytes.

Exit stays non-zero iff any deptry is non-zero. The one deliberate
difference: the serial form's `|| exit 1` stopped at the FIRST failing
package, so a tree with two offenders took two commits to see both. All
six always run now. Injecting `import seaborn` into `aii_lib` and into
`claude_cred_manager` at once, the serial form printed `aii_lib` alone
(275 B) and the concurrent one printed both plus the four clean packages
(858 B) — with the serial 275 B a byte-exact PREFIX of it. A violation in
the last package alone is byte-identical between the two forms, as is a
clean tree.

**This is 0.39 s of a hook the gate timer reports at ~6 s.** The rest is
`snapshot.py exec`: 49 commands share one snapshot of the index and the
first to arrive builds it (1.2 s, 183 MB) while the others wait on
`flock`, so every snapshot-using command carries that floor. Nothing here
can move it, and the snapshot is not optional for this hook — deptry
reads `.py` files off disk, so without it the check judges whatever
another agent has unstaged in the shared checkout.

Proof the gate bites, not merely that it is green: deleting the single
line `"loguru>=0.7.0",` from a scratch copy of `aii_runpod/pyproject.toml`
and pointing `--config` at it turns 0 findings into 20 DEP003 and exit 0
into exit 1. Restoring it returns exit 0.

## The `runpod` extras broke the PUBLIC export, and that is now gated

Caught in review, and the one genuinely dangerous thing here. The three
new `runpod = ["aii-runpod"]` entries SHIP in the public/OSS export —
`aii_public/allowlist.txt:9,13,21` take `aii_pipeline/`, `aii_launcher/`
and `aii_server/pyproject.toml` wholesale — while `aii_runpod/` and
`uv.lock` do not. `aii_public/sync.sh` stripped the `aii-runpod` path
source and extra from the ROOT manifest only, and that is not enough:
**uv locks a workspace UNIVERSALLY, across every member's every extra,
whether or not anyone requests it.**

Measured 2026-09-05 on a public-shaped copy (`rm -rf aii_runpod uv.lock`,
then sync.sh's seds), `uv lock` with network:

| tree | result |
|---|---|
| `b07138d18`, before this change | Resolved 418 packages |
| staged, root-only strip | **fails, unsatisfiable** |
| staged, plus the member strip | Resolved 421 packages |

The failure reads `aii-runpod was not found in the package registry and
aii-launcher[runpod] depends on aii-runpod ... your workspace's
requirements are unsatisfiable` — the public repo would not install at
all. `rule-public-sync-invariants` stayed green throughout, because it
asserted only the root sed.

`sync.sh` now strips the entry from the three member manifests too, and
that group gained `test_public_export_strips_the_runpod_extra.py`, which
pins both halves with no network: sync.sh must carry a member-manifest
strip, and applying its seds to copies of every allowlisted
`pyproject.toml` must leave no `aii-runpod` token anywhere. The member
strip is line-wise rather than the root's section-wise delete, because a
member's `runpod` sits in a section that also holds `dev` and
`dashboard`, which must survive.

## Two invocation traps, both measured

Scan each package's `src/` (aii_server has none and scans its package
dir): pointed at the package DIRECTORY from the repo root, deptry does not
treat the package's own modules as first-party and reports the package to
itself — measured 2026-08-28, aii_pipeline inflated from that day's 345 to
800, 455 of them `aii_pipeline` importing `aii_pipeline`. That is why the
command derives `d` per package rather than passing `$p` directly.

And deptry reads `[project.optional-dependencies]` as declared, so a
base-vs-extras scope gap passes it silently. That property is load-bearing
for the `runpod` extras above, and it is also the reason the gap below is
still open: `aii_lib` base source imports `requests`
(`free_router/openrouter_free.py:17`, `workflows/guided_questions.py:24`)
and `aiohttp` (`run/runpod_message_forwarder.py:58`,
`run/agent_worker_server.py:44`) while the BASE dependency list declares
neither — both live only in extras, `requests` in `ability-client` and
`aiohttp` in `ability-server`, so a base-only install can lose them. This
rule does not see it and is not claimed to; enforcing base-list scope
needs a base-only environment or a separate check. The FE half of the same
idea is already covered by `rule-fallow-fe`
(`ignoreDependencies` in `aii_frontend/.fallowrc.json`).

Delete-check: The declared half cannot be deleted — an undeclared import
is a latent ImportError that fires only when a transitive provider's
closure shifts, and 720 such edges were live in package source as recently
as `b07138d18`. The unused half WAS the deletable part and is deleted from
this rule (see TRAP); with DEP002 off, the deliberate generated-code
runtime closure (scikit-learn, seaborn, matplotlib, numpy, datasets,
huggingface-hub, openpyxl, selectolax — the set
`aii_pipeline/src/aii_pipeline/prompts/components/resources.py:18`
advertises to agents) needs no `[tool.deptry]` ignores at all.

## History — the unused direction, measured and dropped

Unused direction: openai>=1.99.0 + anthropic>=0.62.0 + google-genai declared
in aii_lib/pyproject.toml AND aii_pipeline/pyproject.toml with
ZERO imports repo-wide (grepped all six package trees plus .claude/skills
scripts); tiktoken>=0.5.0 + psutil>=7.0.0 in aii_server/pyproject.toml
with zero references anywhere in aii_server;
websockets/rich/tqdm/fastapi/uvicorn/aiohttp/beautifulsoup4 in
aii_pipeline/pyproject.toml with zero imports in aii_pipeline/src. All
of these install into both production images (Dockerfile.server:74,
Dockerfile.pipeline:42). Missing direction: aii_lib base source imports
requests and aiohttp while its base deps declare neither. (The verification
below corrected the original "resolve only transitively via litellm" claim:
both live in aii_lib's own extras, and requests does not come from litellm
at all — the gap is base-list scope, not a transitive-only resolve.)

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Winner of the deps-hygiene trio: bidirectional (declared→imported and
imported→declared). ~13 dead declarations get deleted at adoption; the rule
enforces the end-state. Absorbs rule-declared-deps-consumed (same check) and
rule-members-declare-first-party-deps (its imported→declared half covers
sibling packages).
- KEEP: Canonical of the dependency-hygiene cluster (absorbs rule-declared-
deps-consumed and rule-members-declare-first-party-deps — both are subsets:
unused-direction and first-party-undeclared-direction). ~13 dead declarations
live now, plus siblings imported in 93 files but declared nowhere. Use a
deptry-style checker rather than hand-rolling; allowlist the deliberate
generated-code closure with reasons.
- KEEP: Survivor of the three dependency-hygiene proposals: demote to running
deptry per package (it checks BOTH directions — declared-unused and imported-
undeclared, including first-party siblings), with a commented allowlist for
the deliberate generated-code closure. Absorbs rule-declared-deps-consumed and
rule-members-declare-first-party-deps. Real findings confirmed
(openai/anthropic/google-genai declared, zero imports).

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Unused direction re-measured and it holds. `grep -rn
'^\s*\(import\|from\)\s\+anthropic\b' --include=*.py .` → 0 hits; same for
google.genai/`from google import genai` → 0; `git grep -n tiktoken` → only
aii_server/pyproject.toml and two rules-pending docs; `grep psutil` in
aii_server (all file types) → only pyproject.toml. For aii_pipeline/src:
websockets 0, rich 0, tqdm 0, fastapi 0, uvicorn 0, aiohttp 0, bs4 0.

Corrected statement of fact:
Corrected: openai/anthropic/google-genai/tiktoken and aii_server's psutil have
zero imports in package source (openai has one in the excluded
.claude/skills/archive tree), and the seven aii_pipeline web/CLI deps have
zero imports under aii_pipeline/src. But tiktoken+psutil ship only in the
server image (Dockerfile.server:483), not both. And the missing direction is
narrower than stated: requests and aiohttp are absent only from aii_lib's BASE
list while being declared in its ability-client and ability-server extras —
they do not 'resolve only transitively via litellm'; requests does not come
from litellm at all.

TRAP FOUND WHILE TRIAGING THIS (2026-08-24) — read before ever reviving the
"unused" half. A first scan called 23 distributions unused, a second (using
importlib.metadata for the real import names rather than a hand-written
alias map) said 15, and the truthful number is close to zero. Three
separate reasons a declared dependency legitimately has no first-party
import, and a checker that misses any of them proposes deleting something
load-bearing:

* It is a RUNTIME CONTRACT FOR GENERATED CODE. This repo runs coding
  agents, and prompts/components/resources.py:18 promises them "numpy,
  pandas, scikit-learn, scipy, matplotlib, requests, etc." — so
  scikit-learn, beautifulsoup4, selectolax and friends are declared
  precisely so the code an agent writes can import them. CLAUDE.md's build
  notes go further and pre-warm that closure in the builder stage. Nothing
  first-party imports them and nothing should.
* It is invoked, not imported: gunicorn is a binary.
* It is loaded by a framework from a STRING: pytest-asyncio and
  pytest-xdist are pytest plugins; django-cors-headers appears only as
  "corsheaders" in INSTALLED_APPS.

So the unused half needs an explicit allowlist with a reason per entry, and
the rule is worth far less than it looks. The DECLARED half (every import
resolves to a declared dependency) keeps its full value and has none of
these hazards.
