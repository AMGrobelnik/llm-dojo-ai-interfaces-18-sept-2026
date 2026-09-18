# research-monorepo-ast-checks

Not a `research-monorepo/hooks/<name>/README.md` folder — this is the
dispatcher command wired in the research monorepo's repo-specific
`lefthook.yml` that runs a batch of AST-based hooks in one pass, the same
mechanism as the shared set's `general-ast-checks`. Documented here from its
inline comment, since the dispatcher itself has no dedicated folder (it
borrows another hook's folder purely to derive one internal path variable).

## What it does

The same dispatcher process (`lib/amg_hooks/ast_dispatch.py`, engine
`lib/amg_hooks/astcheck.py`) that runs `general-ast-checks` also discovers
every `dispatch.py`-owned hook folder under the repo-specific set's `hooks/`
directory and judges them all in a single pass over the staged index — one
`git` read, one AST parse cache, shared across every check in this set
instead of paid once per hook. Findings print as `hook: path:line: msg` and
are re-attributed to the owning hook by name. A `dispatch.py` hook declares a
`SCOPE` (file/tree/relation), trigger `GLOBS`, optional `EXCLUDES`, and a
`run(svc)` function; it is otherwise governed by the same checker contract as
a standalone `check.py`/`check.sh` hook (exit 0 clean, 1 findings, 2 cannot
run — any nonzero blocks the commit).

## The checks it batches

Each of the following is its own hook folder with its own `README.md` under
the repo-specific set's `hooks/`, each with its own statement, mechanism and
tests — they just fire through this one dispatcher command rather than a
separate `lefthook.yml` entry each. Statements, verbatim from each hook's own
README:

- **ability-spend-declares-no-retry** — A registered handler that can spend money or provision a billable resource declares retries=0
- **agent-dispatch-via-router** — Agent dispatch goes through the one router, not around it
- **agent-workspace-rail-one-door** — The agent's write-containment rail is stamped once, from `options.cwd`, at the `build_options` chokepoint — no prompt module renders `get_workspace_prompt` itself; no turn ships without the rail.
- **api-via-sdk** — New frontend code calls the API through the generated SDK, not raw fetch
- **artifact-json-schema-dual-source-parity** — The aii-json skill's exp_*.json required keys equal aii_pipeline's out_schema.py verifier key sets, every schema file compiles as a JSON Schema, and every tracked .json in the skill dir parses
- **async-inline-blocking** — No coroutine in aii_server performs blocking filesystem/subprocess/ORM work inline — it goes through asyncio.to_thread or sync_to_async
- **background-job-failure-is-durable** — Every background job that clears an in-flight start mark records a durable, user-visible terminal failure on its exception path — a client never learns a job died only by outliving a watchdog
- **big-module-docstring-floor** — A package-source module over 200 code lines opens with a multi-line WHY docstring, tree-wide
- **browser-tests-wait-on-conditions** — A browser test waits on a condition, never on `networkidle` (the app polls, so the wait burns its timeout) and never clicks with `force: true` (needing it is the finding)
- **cancel-then-await** — A function that creates and cancels an asyncio task awaits it after the cancel (CancelledError suppressed), so cancellation completes instead of dangling.
- **child-workflow-id-pinned** — Every DBOS.start_workflow_async call in aii_pipeline sits inside a `with SetWorkflowID(...)` block
- **color-tokens** — Colors come from the registered palette tokens; no arbitrary [#hex] Tailwind color utilities in frontend source
- **config-in-yaml** — A new setting arrives as a config key, not as a flag default or an env read
- **config-models-closed-schema** — Every pydantic model bound to aii_config yaml (config_models/, pipeline_config.py, run/config.py) declares extra="forbid" — no config model silently ignores unknown keys
- **config-overlay-one-door** — Tracked aii_config/**.yaml is read only via load_config_with_overrides (or load_yaml_cached where overlay-free is deliberate) — never raw yaml.safe_load, which drops the .private.yaml overlay
- **conftest-hermetic-env-pins** — Importing the staged root conftest under a hook-shaped environment leaves the process hermetic: no GIT_* survives and every module-scope setdefault pin holds
- **cred-writes-via-store** — Every persistent file write in the credential package goes through its store module — no bare write_text/write_bytes/json.dump/open-for-write elsewhere in the package
- **csrf-gate-once** — Browser CSRF enforcement has exactly one implementation — every auth gate calls the shared helper, never ninja's check_csrf directly
- **daemon-loop-stoppable** — An interval-paced daemon-thread loop paces itself on its stop-Event and runs in a named thread — never `while True: time.sleep(interval)`, which nothing can interrupt
- **dbos-list-metadata-only** — DBOS.list_workflows calls that consume only metadata pass load_input=False, load_output=False
- **deep-merge-single-source** — Exactly one deep-merge implementation exists in the workspace: aii_lib.utils.config_overrides.deep_merge — PipelineConfig._deep_merge is deleted and its callers import the canonical one
- **django-bootstrap-shared** — No test module hand-rolls Django bootstrap — django.setup()/sys.path surgery lives only in the shared tests/server/conftest.py, re-exported per group.
- **dotenv-root-override** — Every load_dotenv of the repo-root .env passes override=True so a rotated key in .env beats a stale shell export
- **e2e-suite-actually-runs** — The e2e suite is wired to run somewhere, and has not been gutted
- **endpoint-admission-parity** — A route carries the admission and access gates its siblings carry
- **error-envelope** — A failure response leaves the API in one envelope shape
- **fe-time-format-single-source** — Date/time display strings come from lib/format.ts helpers — no inline toLocaleDateString/toLocaleTimeString in features, app, or components
- **first-party-imports-resolve** — A first-party import names a module that actually exists
- **get-running-loop** — Package source obtains the event loop via asyncio.get_running_loop(), never asyncio.get_event_loop() — in sync context the old form silently binds a non-running loop instead of failing loud.
- **http-detail-no-exception-text** — A user-facing API error `detail` is curated copy — it never interpolates a caught exception; the exception goes to the log, and the response says what happened and what to do next.
- **httpx-explicit-timeout** — Every httpx client construction and module-level call carries an explicit timeout kwarg
- **httpx-only** — httpx is the only HTTP client in new code
- **image-tier-price-vocab-parity** — The paid image-tier vocabulary agrees across its repo seam
- **in-process-durations-monotonic** — An elapsed time or deadline that never leaves the process is measured with time.monotonic(); time.time() is reserved for stamps that cross a process, disk or wire boundary
- **journal-single-reader** — `operation_outputs` is read only inside aii_lib/run/events/, plus three named readers on the cleanup backlog
- **latex-figure-recipe-single-spelling** — The LaTeX figure recipe — placement token, includegraphics options, and package list — is spelled identically in the gen_full_paper prompt, its figure-fix retry, and the aii-paper-to-latex skill
- **launcher-flags-doc-parity** — The launcher flag table in README matches the aii_launcher argparse surface
- **light-only-theme** — The app stays light-only: zero dark: utilities, no .dark token block, color-scheme light declared
- **loguru-diagnose-off** — Every loguru sink configured in workspace package source passes diagnose=False — a traceback never renders local variable values into a log line
- **loguru-sink-single-source** — Loguru sink configuration (logger.add/logger.remove) lives only in one shared aii_lib helper — one format everywhere, not four looks
- **module-docstrings** — A new module's docstring explains WHY, in the house register
- **module-registration-complete** — A new pipeline module joins every place that already names all of its siblings
- **module-workflow-rebinds-config** — Every @DBOS.workflow whose input carries config_snapshot rebinds the ambient config before doing work
- **no-new-daemon-threads** — aii_server gains no new threading.Thread call sites
- **no-runtime-state-in-tree** — Every writable path declared in aii_server settings anchors under AII_DATA_DIR
- **outside-dismiss-via-hook** — Outside-click dismissal goes through useOutsideClick; no inline document mousedown/pointerdown listeners in app/components/features
- **owner-widening-explicit** — Owner-scope widening is always explicit and never the default
- **path-gate-one-door** — Untrusted path components in aii_server pass through the shared validation/containment helpers — zero inline '..'-membership checks or resolve().relative_to copies in handler code.
- **pipeline-config-files-enumerated** — Every tracked public yaml under aii_config/pipeline/ is enumerated in PIPELINE_CONFIG_FILES or BACKEND_CONFIG_FILES — no config file that ships but never loads
- **pipeline-error-emits-first** — Every `raise PipelineError` is immediately preceded by emit.status_public_error carrying the same message
- **pod-env-payload-least-scope** — Pod launches ship least-scope env: every POD_ENV_ALLOWLIST key keeps a verified pod-side reader, and encode_env_full stays confined to the two server-pod deploy call sites
- **prod-security-floor-pinned** — settings.py's non-DEBUG branch keeps the pinned transport/cookie security floor, and a non-DEBUG boot refuses allow-all credentialed CORS
- **prompt-claims-cite-surface** — Every capability claim a prompt makes about an external surface (skill flags, CLI commands, file extensions, supported options) is verified against that surface, whole-tree, with quoted evidence
- **prompt-data-via-yaml** — Structured data reaches a prompt through one serializer
- **prompt-format-placeholder-parity** — Every .format() call on a prompt template supplies exactly the placeholders the template declares — no missing (runtime KeyError mid-run), no extras (silent drift)
- **prompt-module-shape** — A prompt module keeps the shape the prompt package is read through
- **prompt-string-style** — A prompt template's section tags nest, close, and stand on their own lines
- **prompt-tag-balance** — Every structural XML-ish section tag opened in a prompt module's template strings is closed the same number of times, module-scoped over AST string fragments
- **prompt-text-in-prompts-tree** — Agent-facing instruction strings live under prompts/, never inline in step modules — steps/ contains zero non-docstring strings with imperative agent-instruction markers
- **publish-size-budget-single-source** — A file-size ceiling derives from DEFAULT_MAX_FILE_SIZE_MB — no budget name and no byte-scale literal is bound to a hand-typed number
- **published-arch-stays-amd64** — The published platform set stays exactly linux/amd64 on every build surface
- **reclaim-sweep-owns-target** — A reclaim sweep only ever matches resources this repo created
- **redeploy-one-door** — A redeploy is launched through scripts/local/redeploy_detached.sh — no tracked file instructs running bare `aii_launcher --redeploy`.
- **repo-root-one-helper** — Repo-root resolution in workspace package source goes through aii_lib.utils.paths.repo_root() — no hand-rolled parents[N] / .parent chains
- **request-log-credential-redaction** — A plaintext credential posted to the API never survives into a request-log line
- **restartable-workflow-id-one-door** — A restartable workflow id is never started through a NEW bare SetWorkflowID
- **retry-via-tenacity** — Retries are the tenacity decorator in the house shape — not a loop
- **route-decl-complete** — Every Ninja route declares an explicit operation_id and response schema; the streaming download is the sole pinned exception
- **run-dir-reserved-names-one-door** — run_dir's reserved layout names are minted only by their canonical owners: every other site imports WORKFLOW_INPUT_FILENAME or calls user_uploads_path_for_run instead of re-typing the literal
- **security-headers-parity** — The page security headers next.config.ts sets equal the values Django's settings.py declares
- **server-yaml-closed-schema** — No raw `.get`-chain or `yaml.safe_load` read of server.yaml, roles/*.yaml or user.yaml exists outside a typed closed-schema loader — a loader a refactor must first build
- **shipped-override-wins-merge** — An in-flight mutation of shipped config targets the layer that wins the overlay merge
- **spend-env-is-per-conversation** — The two environment variables that steer money — `AII_COST_LEDGER` and `AII_FREE_TOOLS` — are delivered in the agent subprocess's own env mapping, never by mutating `os.environ`
- **submission-record-once** — The .run_submission.json record and the flat shared-volume run path are written, located, and parsed only via one canonical helper
- **subprocess-deadline** — Every subprocess interaction carries an explicit deadline, with post-kill reaps and pinned deliberately-unbounded interactive streams as the only exceptions.
- **tmux-session-name-reclaimable** — Every tmux session this repo launches carries a name a FRESH process can reclaim — a literal some boot or teardown path kills by name, or a swept prefix.
- **toast-headline-curated** — A toast headline is curated copy — a raw wire/exception `.message` never appears as the first argument of toast.*; the raw detail rides in `description`.
- **tsx-extension** — JSX lives in .tsx; a .ts file exports no components
- **unit-test-docstring-present** — Every rule-engine unit test opens with a module docstring of at least 40 characters
- **unset-key-one-default** — A config key whose value when UNSET is declared by more than one reader resolves to the same value in all of them — GET /config's inline fallbacks equal PipelineConfig's field defaults.
- **user-dir-one-layering-rule** — Every file under a per-user aii_config dir layers by ONE rule — sparse deep-merge over the shipped file — so no shipped default can be lost by a user simply having their own copy.
- **user-paths-via-resolver** — Per-user data paths (USERS_DATA_DIR joins) are built only inside the canonical resolver helpers
- **wire-timestamp-via-helper** — Wire timestamps are minted by the aii_lib timestamp helper, never by inline datetime.now(UTC).isoformat() chains
- **wire-vocab-derived** — A hand-typed TS union is not a second copy of a declared vocabulary
- **workflow-id-suffix-single-source** — Workflow-id suffix grammar (-phase-/-iter-/-mod-/-retry-/-rerun-) is constructed only inside *_workflow_id helper functions
- **workflows-registered-eagerly** — Every module defining a @DBOS.workflow is imported at module scope by run/workflows/__init__.py (pipeline.py excepted)
