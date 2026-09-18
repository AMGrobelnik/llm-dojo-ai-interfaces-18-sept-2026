# Hook lanes

This documents every git-hook lane the research monorepo runs, and whether
each is enabled as shipped or overridden. All of it is driven by
[lefthook](https://lefthook.dev) and comes from `amg-hooks`, a shared hook
repo vendored into the research monorepo as a git submodule. `amg-hooks`
publishes lane sets: a `general/` set that is a library any repo can adopt —
linters, secret scanning, dependency and container checks, shell/Python/
frontend conventions, and a handful of git-hygiene rules — plus a
repo-specific set for this repo's own domain-specific checks and a small
self-gate the hooks repo runs on itself. Each lane is one lefthook command,
backed by a `hooks/<lane>/README.md` in the owning set stating what it checks
and why.

The research monorepo picks lanes only by choosing which sets to `extends:`
in its own `lefthook.yml`; it never edits a shared set directly. It can still
hand an individual lane its own configuration — an environment variable (an
ignore file, a config path) or, in principle, `skip: true` — through a
root-level entry that merges into the extended command, which is how a repo
narrows or disables a lane without forking it.

Lanes run at several points in the commit lifecycle. `pre-commit` is where
nearly everything above lives: most lanes here judge the whole tracked tree
on every commit (not just staged files), so there is no narrower scope to
grow stale — adopting a new lane is a one-time sweep, not an ongoing ratchet.
An AST-dispatch step (`general-ast-checks` for the shared set,
`research-monorepo-ast-checks` for the repo-specific set) batches dozens of
small structural/style rules through one AST-parsing pass instead of one
process per rule. `commit-msg` enforces subject-line conventions. `pre-push`
carries exactly one lane, a release-tag safety net that a commit hook cannot
reach — a tag push carries no commit of its own for `pre-commit` to
intercept. A last group of commands is pure plumbing, not a quality gate:
keeping the vendored hooks submodule fetched and fast-forwarded and
re-running the whole gate on a clean, non-conflicting merge commit, since git
otherwise skips `pre-commit` for that case.

## Legend

✅ enabled as shipped &nbsp;·&nbsp; ❌ disabled for this repo &nbsp;·&nbsp; ⚙️ enabled
with a repo-specific override (see footnote)

## pre-commit

### Shared general set

| Lane | What it enforces | Enabled |
|---|---|---|
| shipped-migration-immutable | A migration that has already shipped is append-only | ✅ |
| image-installs-lock-constrained | Every Python install in a container build file names a version constraint | ✅ |
| git-deps-immutable-rev | A git dependency names an immutable rev, never a branch | ✅ |
| fix-whitespace | Trailing whitespace, EOF newlines and non-Linux line endings are flagged, never fixed | ✅ |
| actionlint | Workflow files under `.github/workflows/` pass actionlint | ✅ |
| bandit-py | Staged Python carries no medium-or-higher bandit finding | ⚙️¹ |
| build-fetches-name-a-version | Every new artifact an image build downloads names an explicit, content-verified version | ✅ |
| bun-lock-fe | The frontend's `bun.lock` stays in sync with `package.json` | ✅ |
| bun-audit-fe | The resolved frontend dependency set carries no high/critical advisory | ✅ |
| check-added-large-files | No newly-added file exceeds 100 MB | ✅ |
| check-case-conflict | No tracked filenames conflict on case-insensitive filesystems | ✅ |
| check-merge-conflict | No conflict markers anywhere in the index | ✅ |
| check-toml | Every tracked `.toml` file parses cleanly | ✅ |
| check-yaml | Every tracked YAML file parses cleanly | ✅ |
| ci-actions-sha-pinned | Every `uses:` in a workflow names a full commit SHA, version in a comment | ✅ |
| commit-author-identity | A commit's author/committer email matches the configured git identity | ✅ |
| commit-uses-a-named-file-list | A commit in a shared checkout names its files explicitly, never a plain `git commit` | ✅ |
| deps-in-pyproject | No new `requirements.txt` — dependencies go in `pyproject.toml` | ✅ |
| detect-private-key | No tracked file contains a private key block | ✅ |
| doc-paths-resolve | Every repo path named in tracked markdown resolves to a real file | ✅ |
| exec-bit-has-shebang | Every executable-bit file starts with a shebang | ✅ |
| fallow-fe | The frontend tree carries no dead code | ✅ |
| gitignore-tells-truth | `.gitignore` and the index never contradict each other | ✅ |
| gitleaks | Staged content carries no secrets | ⚙️¹ |
| hadolint | Every tracked Dockerfile passes hadolint | ✅ |
| index-symlink-free | The git index contains no symlink entries | ✅ |
| lefthook-validate | A changed `lefthook.yml` validates against lefthook's schema | ✅ |
| next-build-fe | The frontend's production `next build` passes | ✅ |
| no-lint-silencers | A lint warning is fixed at the smell, not silenced or allowlisted | ✅ |
| no-new-root-files | The repo root gains no new files | ✅ |
| no-pkill-by-pattern | No shipped script kills processes by command-line pattern match | ✅ |
| no-project-claude-settings | No project-level Claude settings file is committed | ✅ |
| no-root-claude-md | No `CLAUDE.md` is committed at the repo root | ✅ |
| oxfmt-fe | The frontend tree is oxfmt-formatted | ✅ |
| oxlint-fe | The frontend tree passes oxlint, type-aware and check-only | ✅ |
| pip-audit-py | The resolved Python dependency set carries no known vulnerability | ⚙️¹ |
| private-config-never-tracked | No private-config or `.env` file is ever git-tracked | ✅ |
| react-compiler-fe | Staged frontend files carry no React Compiler bailouts | ✅ |
| ruff | The whole Python tree passes ruff lint, project-wide | ✅ |
| ruff-format | The whole Python tree is ruff-formatted, project-wide | ✅ |
| rumdl | Tracked markdown passes rumdl, with a few rules disabled | ✅ |
| shared-dep-floors-agree | A dependency named in more than one `pyproject.toml` carries one identical floor | ✅ |
| shell-exit-capture-adjacent | `$?` is only ever captured immediately after the command it checks | ✅ |
| shell-strict-mode | A shell script declares a `set -` strictness mode in its first ten lines | ✅ |
| shellcheck | Every tracked shell script passes shellcheck | ✅ |
| shfmt | Every tracked shell script is shfmt-formatted | ✅ |
| tsgo-fe | The frontend tree typechecks clean | ✅ |
| ty | The `ty` type checker passes whenever Python is staged | ✅ |
| typos | The working tree is free of spelling errors | ✅ |
| uv-lock | `uv.lock` is consistent with every workspace `pyproject.toml` | ✅ |
| vitest-fe | Frontend unit tests related to the staged files pass | ✅ |
| vitest-sb-fe | Storybook component tests related to the staged files pass | ✅ |
| workflow-agents-name-their-type | Every `agent()` call in a tracked workflow script names its agent type | ✅ |
| worktree-fresh | A worktree more than a day behind its upstream tip fails the commit | ✅ |
| general-ast-checks² | One AST-dispatch pass batches ~25 structural/style lanes (see below) | ✅ |
| amg-hooks-advance-stage³ | Pins the vendored hooks submodule at the sha this commit will judge | ✅ |
| amg-hooks-fetch³ | Fallback fetch of the hooks submodule when no background timer is installed | ✅ |

### Repo-specific set

| Lane | What it enforces | Enabled |
|---|---|---|
| aria-invalid-names-reason | A control that sets aria-invalid also wires aria-describedby to its visible reason — an invalid mark never ships with an orphaned error line. | ✅ |
| big-blob-public-only | A newly-added file over 2 MB lands only under aii_frontend/public/ — the product-asset surface — so bulk data can never again creep into permanent history below the 100 MB per-file gate. | ✅ |
| build-pin-parity | A toolchain pinned at multiple build sites carries one version everywhere: uv image tag, Lean toolchain, lean-interact, bun and python base tags | ✅ |
| buildcache-single-auto-writer | The registry buildcache keeps exactly one automatic writer | ✅ |
| builder-prewarm-parity | Every workspace package installed editable in a role Dockerfile's final stage is pre-warmed in its builder stage (stub COPY, matching extras) or named on the pinned no-prewarm list with its reason | ✅ |
| builder-single-flight | Every `docker buildx bake` caller waits on one shared flock, and every caller resolves that lock to the same path | ✅ |
| buildplatform-stage-manifest | Each build stage's platform pin matches a declared manifest | ✅ |
| canonical-nouns | New identifiers use the canonical run-tree nouns: phase, module, iteration, task | ✅ |
| check-json | Every tracked .json file is strict JSON (project-wide, curated exclusions) | ✅ |
| classname-prop-merged-with-cn | A component's className prop is merged with cn(), never concatenated | ✅ |
| config-duration-keys-carry-seconds-suffix | Every duration-valued key added to tracked aii_config YAML names its unit in the key — a suffix like `_s`, `_ms`, `_seconds` — no bare `agent_timeout:`, no unit living only in a trailing comment | ✅ |
| copy-exclude-parity | Every --exclude=<pkg> on a role Dockerfile's catch-all source COPY has a later per-package COPY of that pkg in the same stage, so no package can be silently dropped from an image | ✅ |
| cred-manager-importable | claude_cred_manager imports from the project venv and is backed by a real file | ✅ |
| dead | No dead code in aii_lib / aii_pipeline / aii_server / aii_launcher / aii_runpod | ✅ |
| deploy-image-refs-pinned | Every image ref in deploy config (tracked or private overlay) is an immutable 12-hex-SHA tag — never :latest | ✅ |
| deps-declared-and-used | Every package-source import resolves to a dependency declared where it runs | ✅ |
| django-migrations | Django models and committed migrations stay in sync | ✅ |
| doc-facts-recompute | Registered numeric/structural claims in CLAUDE.md and README recompute to what the prose says | ✅ |
| docker-context-no-big-ignored-dirs | Every gitignored directory over 100 MB on disk is excluded from both role images' build contexts, evaluated with dockerignore (root-anchored) semantics, and both role dockerignore files exist | ✅ |
| docker-context-no-credentials | Every credential-bearing file present on disk (.env at any depth, aii_config *.private.yaml, cookies.txt, .mcp.json) is excluded from every role build context, re-include rules notwithstanding | ✅ |
| dsn-structural-redacted | Postgres DSNs are composed with URL.create (never f-strings) and logged only through the password-masked form — hide_password=False stays inside the composer | ✅ |
| empty-state-honest | Newly added empty-state copy sits in a function that knows whether its data resolved, so "nothing here" is never printed over an unresolved request | ✅ |
| env-single-door | Server-only process.env reads live only in lib/env.ts; app code sees env only as NEXT_PUBLIC_ values or props | ✅ |
| error-boundary-copy-curated | A React error boundary shows curated copy plus the `digest` ref — never the raw `error.message`; the exception text goes to `console.error`, which every boundary already calls. | ✅ |
| escape-owned-by-layer | Window/document-level Escape handlers either register with the dismissable-layer stack or stand down on e.defaultPrevented | ✅ |
| fe-a11y-lint-floor | The a11y lint floor in aii_frontend/.oxlintrc.json only grows: the jsx_a11y plugin stays enabled and its ten pinned rules stay at error. | ✅ |
| fe-exclusions-live | Every exclusion entry in aii_frontend lint/format/tsconfig configs names a path that exists and is genuinely generated | ✅ |
| fe-fetch-timeout-signal | Every frontend fetch that can hang carries an abort signal, so a stalled request fails visibly instead of leaving the UI spinning | ✅ |
| fe-poll-budget-parity | Frontend poll cadences and the server's rate limits are checked against each other, so a cadence change cannot silently exceed a throttle bucket. | ✅ |
| fe-session-boundary-hard-nav | Every navigation across a session boundary is a full-document load, so the shared QueryClient and the module-level run-events store go away with the session | ✅ |
| fe-write-invalidates-its-reader | Every write operation that shares an OpenAPI path with a GET operation has that GET in the QueryClient, and the write's wiring invalidates or patches it | ✅ |
| fix-dbos-determinism | DBOS workflow determinism is checked before every commit; a violation the checker can auto-fix is left unstaged for you to review and add | ✅ |
| flow-byo-openrouter-key | OpenHands needs a key of your own unless you are a superuser, and every backend shows its capacity | ✅ |
| flow-share-link | A share link opens the run read-only, logged out | ✅ |
| font-tokens | Fonts come from the three registered tokens (--font-sans / --font-mono / --font-serif), no fourth family | ✅ |
| gallery-asset-referential-integrity | Every /gallery, /landing and /about asset path in frontend source resolves to a tracked file under public/, and every tracked file there is referenced or recorded as a deliberate exception. | ✅ |
| gallery-covers-immutable | A published gallery cover is append-only — a cover already shipped under a name is never modified or deleted in place | ✅ |
| gate-steps-resolve | Every single-line lefthook.yml run command and ci-watcher run_in step resolves its first executable token and is never a bare no-op (:/true) — a retired step is deleted outright, never stubbed. | ✅ |
| hey-api-client-regen-clean | lib/api/_hey-api/** is byte-identical to a fresh openapi-ts generation from the committed openapi.json | ✅ |
| image-optimizer-pinned-on | The Next image optimizer stays on and effective | ✅ |
| import-linter | The import-layering contracts in [tool.importlinter] hold | ✅ |
| journal-wire-compat-manifest | The journal's durable-read contract holds: no AnyMessage union member grows a required field beyond the committed per-model manifest, and BaseMessage keeps extra="allow" | ✅ |
| latex-preamble-ships-in-pipeline-image | Every \usepackage the paper prompts and aii-paper-to-latex skill prescribe maps in a pinned manifest to a texlive package Dockerfile.pipeline installs — an unsatisfiable addition blocks the commit | ✅ |
| legacy-client-allauth-only | The legacy apiFetch transport carries only /_allauth traffic and the binary download_file blob fetch; every other /api operation goes through the generated SDK | ✅ |
| metered-skill-spend-contract | Every skill script reading a paid provider key implements the spend-contract pair from aii_lib.run_cost — book via AII_COST_LEDGER, gate on AII_FREE_TOOLS — or sit on a pinned exemption table. | ✅ |
| module-lines | Package-source Python modules stay under 600 code lines | ✅ |
| no-backend-pins-in-canonical | Canonical pipeline.yaml carries no per-step agent_backend_name pins — the harness active: is the single backend selector, so flipping it switches a whole run | ✅ |
| no-orphan-tool-configs | Every tool config file or section in the tree belongs to a tool actually present in the toolchain | ✅ |
| one-help-tip | The app has exactly one "?" help-tip primitive; the InfoTip/InfoTooltip twin is collapsed and the retired name never reappears | ✅ |
| openapi-drift | Before a commit that touches backend source or the committed OpenAPI snapshot, the snapshot still equals what the server generates | ✅ |
| parity-fixture-two-readers | Every shared parity fixture under tests/fixtures/ is read by both its Python test and its frontend twin — a fixture never silently reverts to one-sided truth. | ✅ |
| pipeline-cli-surface-closed | The pipeline subprocess parser's flag set stays exactly {--run-id, --run-dir, --fork-from-workflow, --fork-target-module, --fork-id, --aii-user} — config values travel in YAML, never as CLI args | ✅ |
| presets-fixture-drift | Before a commit that touches the preset YAMLs, the run-config projection or the real-presets fixture, the fixture still equals the catalog the server would return | ✅ |
| private-template-parity | The tracked agent_backend.private.template.yaml stays disjoint from its public sibling AND covers every key path the machine's real private overlay uses | ✅ |
| prompt-figure-vocab-once | The figure vocabulary (aspect_ratio and figure_type Literal sets) is declared exactly once and imported everywhere else, never re-typed | ✅ |
| prompt-tree-mirrors-step-tree | prompts/steps/_N_phase/_M_module dirs and steps/_N_phase/_M_module.py modules agree exactly, numbering included | ✅ |
| public-images-decode | Every raster asset under aii_frontend/public decodes cleanly with sharp | ✅ |
| query-keys-single-source | Every hand-rolled TanStack queryKey namespace literal is declared exactly once, in a shared constants module | ✅ |
| reduced-motion-covenant | Reduced motion is honored end to end | ✅ |
| role-limits-fit-presets | Every preset a role lists in allowed_presets fits that role's limits caps for each _INT_CAPS field — no role offers a preset its own caps would clamp | ✅ |
| rotate-helper-uniform | The `_rotate_if_large` helper's rotation mechanism is byte-identical across its four carrier scripts (only the final notice line may differ) | ✅ |
| rotating-loader-one-door | Rotating-loader UI funnels through the Spinner primitive or registers with useAlignedAnimationStart — no raw animate-spin outside components/ui — so spinners share one phase and the a11y protocol | ✅ |
| selector-stable-refs | Exported select* factories return fallbacks only as module-level frozen constants or scalars, never a []/{} or new expression minted per call, so snapshot reference equality short-circuits re-renders | ✅ |
| side-table-column-adds-alter | A column added to a SQLAlchemy side table after it first shipped is also added by `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in its `ensure_*` function, with DEFAULT and index parity | ✅ |
| skeleton-mirrors-subject | A skeleton's cites resolve, and a subject edit reaches the skeleton that mirrors it | ✅ |
| stdlib-logging-bridges-only | In the five aii_* packages, stdlib logging appears only at the two framework bridge files — application logging is loguru | ✅ |
| story-only-components-reported | A component reachable only from its own story is reported | ✅ |
| systemd-units-parse-clean | Versioned systemd units under scripts/local/watchers/ carry no directive `systemd-analyze verify` reports as unknown or unparseable | ✅ |
| test-basenames-unique | Every test module basename under the rule tree is unique. | ✅ |
| tsconfig-strictness-floor | The frontend tsconfig keeps its strictness floor — no pinned flag is dropped and no strict-family flag is set to its loose value | ✅ |
| ui-primitive-has-story | A shared UI primitive ships with a story, so a change to it is reviewable in isolation rather than only through its consumers | ✅ |
| unit-lane-loopback-spend-guard | The unit lane cannot spend money through a loopback daemon. | ✅ |
| unit-test-paths-cover-their-sources | A unit-test group triggers on every consumer file its tests read as source text | ✅ |
| untrusted-content-framed-once | Third-party text entering a prompt — the user-folder block and prior-artifact context blocks — carries the house 'data, not instructions' framing, declared once, never re-typed. | ✅ |
| uv-cache-mount-discipline | In each role Dockerfile's final stage, every package-installing uv invocation carries the shared id=uv-aii cache mount, and the cache-clearing rm -rf /root/.cache/uv never carries any mount | ✅ |
| vitest-fe-full | Before a commit that carries frontend source, the whole frontend unit suite passes — the related-only rule covers the common case; this is the full run, once per commit | ✅ |
| volume-mount-proven-before-durable-writes | A pod boot proves the shared network volume is mounted before writing any durable state under it; an absent mount fails the boot closed instead of being `mkdir -p`'d onto container-local disk | ✅ |
| watcher-net-calls-bounded | Every network-reaching command in a watcher script carries a numeric `timeout` | ✅ |
| wire-fixture-validates-live | Every wire-shaped fixture under tests/fixtures/ stays wire-true | ✅ |
| research-monorepo-ast-checks¹ | One AST-dispatch pass batches ~86 structural/style lanes (see below) | ✅ |

## general-ast-checks bundle

### Shared general set (25 lanes, one AST pass)

| Lane | What it enforces | Enabled |
|---|---|---|
| comment-drift | Prose naming a path, line or symbol names one that exists | ✅ |
| discovery-never-fails-open | A guard's discovery step never turns its own failure into a clean result | ✅ |
| endpoint-urls-once | A third-party endpoint host is declared in one module per environment | ✅ |
| failover-walk-budget | A multi-provider failover walk is bounded by one wall-clock budget | ✅ |
| gate-can-fire | A hook command's gate can actually fire | ✅ |
| keyword-only-past-five | A Python `def` takes at most five positional parameters | ✅ |
| loguru-is-the-logger | Logging goes through loguru with the house format | ✅ |
| md-table-width | Markdown table rows added by a commit stay under 70 characters | ✅ |
| neutral-register | Added lines carry none of the banned offense-register words | ✅ |
| no-actions-invocations | No script invokes CI workflows — builds and deploys stay local | ✅ |
| no-runtime-self-skip | A test never decides its own applicability at runtime | ✅ |
| no-shell-true | No code-execution/deserialization sink takes an untrusted value | ✅ |
| no-silent-except | An `except` block logs, re-raises, or explains — never swallows silently | ✅ |
| no-sys-path-mutation | No mutation of `sys.path` — imports resolve through the package layout | ✅ |
| pathlib-over-os-path | Filesystem paths use `pathlib.Path`, not `os.path.*` | ✅ |
| state-file-replaced-atomically | A polled state file is replaced by rename, never truncated in place | ✅ |
| sweep-population-floor | A guard over a discovered population proves that population was non-empty | ✅ |
| test-genre-declared | A test module declares exactly one genre, as a pytest marker | ✅ |
| test-seam-private-patch | A new `monkeypatch.setattr` does not name a private seam | ✅ |
| tests-reap-their-children | A test that starts a subprocess reaps it on every path | ✅ |
| tmux-kill-server-names-its-socket | No script runs `tmux kill-server` without naming a private socket | ✅ |
| tmux-launch-one-door | tmux sessions start only through one approved launcher | ✅ |
| toolchain-pinned | Every host binary a hook can invoke is pinned in the installer | ✅ |
| tracked-script-carries-no-hook-bypass | No tracked script ships a git-hook bypass or a sweeping `git add` | ✅ |
| watcher-log-stamps-utc | Every timestamp a repo-owned script writes carries an explicit UTC marker | ✅ |

All 25 run identically in every consumer of the general set — the bundle has
no per-lane override surface at the consumer level.

### Repo-specific set (86 lanes, one AST pass)

| Lane | What it enforces | Enabled |
|---|---|---|
| ability-spend-declares-no-retry | A registered handler that can spend money or provision a billable resource declares retries=0 | ✅ |
| agent-dispatch-via-router | Agent dispatch goes through the one router, not around it | ✅ |
| agent-workspace-rail-one-door | The agent's write-containment rail is stamped once, from `options.cwd`, at the `build_options` chokepoint — no prompt module renders `get_workspace_prompt` itself; no turn ships without the rail. | ✅ |
| api-via-sdk | New frontend code calls the API through the generated SDK, not raw fetch | ✅ |
| artifact-json-schema-dual-source-parity | The aii-json skill's exp_*.json required keys equal aii_pipeline's out_schema.py verifier key sets, every schema file compiles as a JSON Schema, and every tracked .json in the skill dir parses | ✅ |
| async-inline-blocking | No coroutine in aii_server performs blocking filesystem/subprocess/ORM work inline — it goes through asyncio.to_thread or sync_to_async | ✅ |
| background-job-failure-is-durable | Every background job that clears an in-flight start mark records a durable, user-visible terminal failure on its exception path — a client never learns a job died only by outliving a watchdog | ✅ |
| big-module-docstring-floor | A package-source module over 200 code lines opens with a multi-line WHY docstring, tree-wide | ✅ |
| browser-tests-wait-on-conditions | A browser test waits on a condition, never on `networkidle` (the app polls, so the wait burns its timeout) and never clicks with `force: true` (needing it is the finding) | ✅ |
| cancel-then-await | A function that creates and cancels an asyncio task awaits it after the cancel (CancelledError suppressed), so cancellation completes instead of dangling. | ✅ |
| child-workflow-id-pinned | Every DBOS.start_workflow_async call in aii_pipeline sits inside a `with SetWorkflowID(...)` block | ✅ |
| color-tokens | Colors come from the registered palette tokens; no arbitrary [#hex] Tailwind color utilities in frontend source | ✅ |
| config-in-yaml | A new setting arrives as a config key, not as a flag default or an env read | ✅ |
| config-models-closed-schema | Every pydantic model bound to aii_config yaml (config_models/, pipeline_config.py, run/config.py) declares extra="forbid" — no config model silently ignores unknown keys | ✅ |
| config-overlay-one-door | Tracked aii_config/**.yaml is read only via load_config_with_overrides (or load_yaml_cached where overlay-free is deliberate) — never raw yaml.safe_load, which drops the .private.yaml overlay | ✅ |
| conftest-hermetic-env-pins | Importing the staged root conftest under a hook-shaped environment leaves the process hermetic: no GIT_* survives and every module-scope setdefault pin holds | ✅ |
| cred-writes-via-store | Every persistent file write in the credential package goes through its store module — no bare write_text/write_bytes/json.dump/open-for-write elsewhere in the package | ✅ |
| csrf-gate-once | Browser CSRF enforcement has exactly one implementation — every auth gate calls the shared helper, never ninja's check_csrf directly | ✅ |
| daemon-loop-stoppable | An interval-paced daemon-thread loop paces itself on its stop-Event and runs in a named thread — never `while True: time.sleep(interval)`, which nothing can interrupt | ✅ |
| dbos-list-metadata-only | DBOS.list_workflows calls that consume only metadata pass load_input=False, load_output=False | ✅ |
| deep-merge-single-source | Exactly one deep-merge implementation exists in the workspace: aii_lib.utils.config_overrides.deep_merge — PipelineConfig._deep_merge is deleted and its callers import the canonical one | ✅ |
| django-bootstrap-shared | No test module hand-rolls Django bootstrap — django.setup()/sys.path surgery lives only in the shared tests/server/conftest.py, re-exported per group. | ✅ |
| dotenv-root-override | Every load_dotenv of the repo-root .env passes override=True so a rotated key in .env beats a stale shell export | ✅ |
| e2e-suite-actually-runs | The e2e suite is wired to run somewhere, and has not been gutted | ✅ |
| endpoint-admission-parity | A route carries the admission and access gates its siblings carry | ✅ |
| error-envelope | A failure response leaves the API in one envelope shape | ✅ |
| fe-time-format-single-source | Date/time display strings come from lib/format.ts helpers — no inline toLocaleDateString/toLocaleTimeString in features, app, or components | ✅ |
| first-party-imports-resolve | A first-party import names a module that actually exists | ✅ |
| get-running-loop | Package source obtains the event loop via asyncio.get_running_loop(), never asyncio.get_event_loop() — in sync context the old form silently binds a non-running loop instead of failing loud. | ✅ |
| http-detail-no-exception-text | A user-facing API error `detail` is curated copy — it never interpolates a caught exception; the exception goes to the log, and the response says what happened and what to do next. | ✅ |
| httpx-explicit-timeout | Every httpx client construction and module-level call carries an explicit timeout kwarg | ✅ |
| httpx-only | httpx is the only HTTP client in new code | ✅ |
| image-tier-price-vocab-parity | The paid image-tier vocabulary agrees across its repo seam | ✅ |
| in-process-durations-monotonic | An elapsed time or deadline that never leaves the process is measured with time.monotonic(); time.time() is reserved for stamps that cross a process, disk or wire boundary | ✅ |
| journal-single-reader | `operation_outputs` is read only inside aii_lib/run/events/, plus three named readers on the cleanup backlog | ✅ |
| latex-figure-recipe-single-spelling | The LaTeX figure recipe — placement token, includegraphics options, and package list — is spelled identically in the gen_full_paper prompt, its figure-fix retry, and the aii-paper-to-latex skill | ✅ |
| launcher-flags-doc-parity | The launcher flag table in README matches the aii_launcher argparse surface | ✅ |
| light-only-theme | The app stays light-only: zero dark: utilities, no .dark token block, color-scheme light declared | ✅ |
| loguru-diagnose-off | Every loguru sink configured in workspace package source passes diagnose=False — a traceback never renders local variable values into a log line | ✅ |
| loguru-sink-single-source | Loguru sink configuration (logger.add/logger.remove) lives only in one shared aii_lib helper — one format everywhere, not four looks | ✅ |
| module-docstrings | A new module's docstring explains WHY, in the house register | ✅ |
| module-registration-complete | A new pipeline module joins every place that already names all of its siblings | ✅ |
| module-workflow-rebinds-config | Every @DBOS.workflow whose input carries config_snapshot rebinds the ambient config before doing work | ✅ |
| no-new-daemon-threads | aii_server gains no new threading.Thread call sites | ✅ |
| no-runtime-state-in-tree | Every writable path declared in aii_server settings anchors under AII_DATA_DIR | ✅ |
| outside-dismiss-via-hook | Outside-click dismissal goes through useOutsideClick; no inline document mousedown/pointerdown listeners in app/components/features | ✅ |
| owner-widening-explicit | Owner-scope widening is always explicit and never the default | ✅ |
| path-gate-one-door | Untrusted path components in aii_server pass through the shared validation/containment helpers — zero inline '..'-membership checks or resolve().relative_to copies in handler code. | ✅ |
| pipeline-config-files-enumerated | Every tracked public yaml under aii_config/pipeline/ is enumerated in PIPELINE_CONFIG_FILES or BACKEND_CONFIG_FILES — no config file that ships but never loads | ✅ |
| pipeline-error-emits-first | Every `raise PipelineError` is immediately preceded by emit.status_public_error carrying the same message | ✅ |
| pod-env-payload-least-scope | Pod launches ship least-scope env: every POD_ENV_ALLOWLIST key keeps a verified pod-side reader, and encode_env_full stays confined to the two server-pod deploy call sites | ✅ |
| prod-security-floor-pinned | settings.py's non-DEBUG branch keeps the pinned transport/cookie security floor, and a non-DEBUG boot refuses allow-all credentialed CORS | ✅ |
| prompt-claims-cite-surface | Every capability claim a prompt makes about an external surface (skill flags, CLI commands, file extensions, supported options) is verified against that surface, whole-tree, with quoted evidence | ✅ |
| prompt-data-via-yaml | Structured data reaches a prompt through one serializer | ✅ |
| prompt-format-placeholder-parity | Every .format() call on a prompt template supplies exactly the placeholders the template declares — no missing (runtime KeyError mid-run), no extras (silent drift) | ✅ |
| prompt-module-shape | A prompt module keeps the shape the prompt package is read through | ✅ |
| prompt-string-style | A prompt template's section tags nest, close, and stand on their own lines | ✅ |
| prompt-tag-balance | Every structural XML-ish section tag opened in a prompt module's template strings is closed the same number of times, module-scoped over AST string fragments | ✅ |
| prompt-text-in-prompts-tree | Agent-facing instruction strings live under prompts/, never inline in step modules — steps/ contains zero non-docstring strings with imperative agent-instruction markers | ✅ |
| publish-size-budget-single-source | A file-size ceiling derives from DEFAULT_MAX_FILE_SIZE_MB — no budget name and no byte-scale literal is bound to a hand-typed number | ✅ |
| published-arch-stays-amd64 | The published platform set stays exactly linux/amd64 on every build surface | ✅ |
| reclaim-sweep-owns-target | A reclaim sweep only ever matches resources this repo created | ✅ |
| redeploy-one-door | A redeploy is launched through scripts/local/redeploy_detached.sh — no tracked file instructs running bare `aii_launcher --redeploy`. | ✅ |
| repo-root-one-helper | Repo-root resolution in workspace package source goes through aii_lib.utils.paths.repo_root() — no hand-rolled parents[N] / .parent chains | ✅ |
| request-log-credential-redaction | A plaintext credential posted to the API never survives into a request-log line | ✅ |
| restartable-workflow-id-one-door | A restartable workflow id is never started through a NEW bare SetWorkflowID | ✅ |
| retry-via-tenacity | Retries are the tenacity decorator in the house shape — not a loop | ✅ |
| route-decl-complete | Every Ninja route declares an explicit operation_id and response schema; the streaming download is the sole pinned exception | ✅ |
| run-dir-reserved-names-one-door | run_dir's reserved layout names are minted only by their canonical owners: every other site imports WORKFLOW_INPUT_FILENAME or calls user_uploads_path_for_run instead of re-typing the literal | ✅ |
| security-headers-parity | The page security headers next.config.ts sets equal the values Django's settings.py declares | ✅ |
| server-yaml-closed-schema | No raw `.get`-chain or `yaml.safe_load` read of server.yaml, roles/*.yaml or user.yaml exists outside a typed closed-schema loader — a loader a refactor must first build | ✅ |
| shipped-override-wins-merge | An in-flight mutation of shipped config targets the layer that wins the overlay merge | ✅ |
| spend-env-is-per-conversation | The two environment variables that steer money — `AII_COST_LEDGER` and `AII_FREE_TOOLS` — are delivered in the agent subprocess's own env mapping, never by mutating `os.environ` | ✅ |
| submission-record-once | The .run_submission.json record and the flat shared-volume run path are written, located, and parsed only via one canonical helper | ✅ |
| subprocess-deadline | Every subprocess interaction carries an explicit deadline, with post-kill reaps and pinned deliberately-unbounded interactive streams as the only exceptions. | ✅ |
| tmux-session-name-reclaimable | Every tmux session this repo launches carries a name a FRESH process can reclaim — a literal some boot or teardown path kills by name, or a swept prefix. | ✅ |
| toast-headline-curated | A toast headline is curated copy — a raw wire/exception `.message` never appears as the first argument of toast.*; the raw detail rides in `description`. | ✅ |
| tsx-extension | JSX lives in .tsx; a .ts file exports no components | ✅ |
| unit-test-docstring-present | Every rule-engine unit test opens with a module docstring of at least 40 characters | ✅ |
| unset-key-one-default | A config key whose value when UNSET is declared by more than one reader resolves to the same value in all of them — GET /config's inline fallbacks equal PipelineConfig's field defaults. | ✅ |
| user-dir-one-layering-rule | Every file under a per-user aii_config dir layers by ONE rule — sparse deep-merge over the shipped file — so no shipped default can be lost by a user simply having their own copy. | ✅ |
| user-paths-via-resolver | Per-user data paths (USERS_DATA_DIR joins) are built only inside the canonical resolver helpers | ✅ |
| wire-timestamp-via-helper | Wire timestamps are minted by the aii_lib timestamp helper, never by inline datetime.now(UTC).isoformat() chains | ✅ |
| wire-vocab-derived | A hand-typed TS union is not a second copy of a declared vocabulary | ✅ |
| workflow-id-suffix-single-source | Workflow-id suffix grammar (-phase-/-iter-/-mod-/-retry-/-rerun-) is constructed only inside *_workflow_id helper functions | ✅ |
| workflows-registered-eagerly | Every module defining a @DBOS.workflow is imported at module scope by run/workflows/__init__.py (pipeline.py excepted) | ✅ |

All 86 are specific to the research monorepo's own codebase — see
[`research-monorepo-ast-checks.md`](research-monorepo-ast-checks.md) for how
the dispatcher works.

## commit-msg

### Shared general set

| Lane | What it enforces | Enabled |
|---|---|---|
| commit-one-concern | A commit subject does not openly join two concerns | ✅ |
| commit-subject-length | Commit subjects stay at or under 72 characters | ✅ |
| commit-subject-unrepeated | A commit subject is not the subject of any of the last 200 commits | ✅ |
| conventional-commit | The subject is `type(scope): summary` with a known type | ✅ |

### Repo-specific set

| Lane | What it enforces | Enabled |
|---|---|---|
| commit-scopes | Commit scope comes from the closed vocabulary in this rule's check.sh | ✅ |
| nightly-red | While the nightly full suite is red, each failure is one worktree's job and blocks its commits until fixed | ✅ |

## pre-push

The shared general set defines no `pre-push` lane — this stage exists only
because a tag push structurally cannot be caught by a commit hook.

### Repo-specific set

| Lane | What it enforces | Enabled |
|---|---|---|
| release-tag-guard | A push that creates or updates a `refs/tags/v*` ref is refused unless `AII_RELEASE=1` — every pushed `v*` tag is a production release to the image watcher | ✅ |

## plumbing

Not quality gates — they keep the vendored hooks submodule fetched and
pinned so every other lane judges the hook code a commit will actually
record. The `pre-commit`-stage half of this (`amg-hooks-advance-stage`,
`amg-hooks-fetch`) is already listed in the pre-commit table above; the rest
runs at other git-hook stages, listed here by stage.

### Shared general set

#### pre-merge-commit

| Lane | What it enforces | Enabled |
|---|---|---|
| merge-commit-runs-pre-commit | Re-runs the whole `pre-commit` gate on a clean, non-conflicting merge commit, since git otherwise skips `pre-commit` for that case | ✅ |

#### post-commit

| Lane | What it enforces | Enabled |
|---|---|---|
| snapshot-cleanup | Cleans up the point-in-time index snapshot lefthook commands read from, now that the gate is over | ✅ |
| amg-hooks-advance | Advances the vendored hooks submodule's working tree to the sha the gate already judged, now that the commit has recorded it | ✅ |

#### post-checkout

| Lane | What it enforces | Enabled |
|---|---|---|
| amg-hooks-advance | Advances the vendored hooks submodule's working tree to match the newly checked-out state | ✅ |
| amg-hooks-fetch-timer | Installs the background systemd timer that keeps the hooks submodule fetched, idempotently, on a machine where it is missing | ✅ |

#### post-merge

| Lane | What it enforces | Enabled |
|---|---|---|
| snapshot-cleanup | Cleans up the point-in-time index snapshot lefthook commands read from, now that the gate is over | ✅ |
| amg-hooks-advance | Advances the vendored hooks submodule's working tree to match the newly merged state | ✅ |
| amg-hooks-fetch-timer | Installs the background systemd timer that keeps the hooks submodule fetched, idempotently, on a machine where it is missing | ✅ |

### Repo-specific set

#### post-checkout

| Lane | What it enforces | Enabled |
|---|---|---|
| deps-stale-warn | After a checkout that changes a lockfile or a migration, says so and names the fix — a notice, never a block | ✅ |

#### post-merge

| Lane | What it enforces | Enabled |
|---|---|---|
| deps-stale-warn | After a merge that changes a lockfile or a migration, says so and names the fix — a notice, never a block | ✅ |

## Repo-local extra lanes

Two lanes are defined directly in this repo's own root `lefthook.yml`, not
vendored from either `amg-hooks` set — because the test trees they run
against live in this repo, not the hooks submodule:

| Lane | What it enforces | Enabled |
|---|---|---|
| unit-tests-research-monorepo | The unit-test groups whose trigger paths are staged run in one pytest process, from this repo's own `tests/unit` tree | ✅ |
| fe-unit-tests-research-monorepo | The FE vitest groups whose trigger paths are staged run in one vitest process, from this repo's own `aii_frontend/tests/unit` tree | ✅ |

Footnotes:

1. ⚙️ — the lane runs with a repo-supplied `env:` override instead of the
   shared default: a config path (`bandit-py`, `gitleaks`) or an ignore-list
   file (`pip-audit-py`) that lives in this repo. The check and its
   pass/fail logic are unchanged; only the config it reads differs.
2. `general-ast-checks` is one lefthook command that fans out into the
   25-lane bundle detailed below it; it is listed once here to match the
   shared set's own naming.
3. Housekeeping, not a quality gate: keeps the vendored hooks submodule
   fetched and pinned so every other lane judges the hook code this commit
   will actually record.

## Why

- **One hook, one folder.** Every lane is a `hooks/<name>/` directory holding
  its statement, its mechanism and its own tests — a lane is read, not
  inferred from a script.
- **Whole-tree over per-commit.** Nearly every lane judges the entire
  tracked index on every commit, not just the staged diff, so there is no
  narrow lane that can quietly drift stale between the commits that happen
  to touch it.
- **Adopt with a sweep, not a switch, and no ledger.** Turning a lane on
  means clearing everything it already finds, once; there is no tolerated
  backlog and no allowlist of known violations left standing indefinitely.
- **Configure at the edge, never fork the set.** A consumer hands a lane its
  own environment variable or exclude pattern at its own root; it never
  edits the shared hook to special-case itself.
- **Shared, and kept current automatically.** The hook set is a git
  submodule that fetches and advances itself on a timer, pinned to the exact
  commit each gate judges — a consumer is always close to the shared set's
  latest without a manual bump.
- **Safe under concurrent and shared use.** Commands read a point-in-time
  snapshot of the index rather than the live working tree, so another
  process's unstaged edit in a shared checkout cannot flip a verdict, and a
  lock file serializes concurrent worktrees of the same repo.
- **Batch what can be batched.** Dozens of small structural rules run
  through one shared AST pass instead of one process each, so adding a
  narrow style rule is cheap enough to actually add.
- **A gate that cannot run is a bug, not a warning.** Anything other than a
  clean pass blocks the commit; a check that errors out is fixed immediately
  rather than left to fail open.
- **Prove the wiring, not just the checker.** A passing unit test for a
  lane's logic is not treated as proof the lane actually fires through
  lefthook on a real commit — the wiring itself gets audited separately.
