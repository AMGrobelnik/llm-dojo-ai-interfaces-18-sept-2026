# Hook lanes

This documents every pre-commit hook lane in a shared quality-gate repo (call it the
"hooks repo") and which lanes each of two consumer repos turns on. The hooks repo is
vendored into each consumer as a git submodule and driven by
[lefthook](https://lefthook.dev). Its `general/` set is a library any repo can adopt:
linters, secret scanning, dependency and container checks, shell/Python/frontend
conventions, and a handful of git-hygiene rules — one lefthook command per lane, each
backed by a `general/hooks/<lane>/README.md` stating what it checks and why. A consumer
picks lanes only by choosing which sets to `extends:` in its own `lefthook.yml`; it never
edits the shared set directly. It can still hand an individual lane its own configuration
— an environment variable (an ignore file, a config path) or, in principle, `skip: true`
— through a root-level entry that merges into the extended command, which is how a repo
narrows or disables a lane without forking it. Two hook sets are shared this way, plus a
per-repo set for each consumer's own domain-specific checks and a small self-gate the
hooks repo runs on itself.

Lanes run at four points in the commit lifecycle. `pre-commit` is where nearly
everything above lives: most lanes here judge the whole tracked tree on every commit
(not just staged files), so there is no narrower scope to grow stale — adopting a new
lane is a one-time sweep, not an ongoing ratchet. A `general-ast-checks` step batches
dozens of small structural/style rules (no bare `except`, `pathlib` over `os.path`,
positional-argument limits, and more) through one AST-parsing pass instead of one
process per rule. `commit-msg` enforces subject-line conventions. `pre-push` exists in
one consumer only, as a release-tag safety net that a commit hook cannot reach. A last
group of commands is pure plumbing, not a quality gate: keeping the vendored hooks
submodule fetched and fast-forwarded (`amg-hooks-advance-stage`, `amg-hooks-fetch`, and
their counterparts at `post-commit`/`post-checkout`/`post-merge`) and re-running the
whole gate on a clean, non-conflicting merge commit (`pre-merge-commit`), since git
otherwise skips `pre-commit` for that case.

## Legend

✅ enabled as shipped &nbsp;·&nbsp; ❌ disabled for this repo &nbsp;·&nbsp; ⚙️ enabled
with a repo-specific override (see footnote)

## pre-commit

| Lane | What it enforces | Research monorepo | Notes & config repo |
|---|---|---|---|
| shipped-migration-immutable | A migration that has already shipped is append-only | ✅ | ✅ |
| image-installs-lock-constrained | Every Python install in a container build file names a version constraint | ✅ | ✅ |
| git-deps-immutable-rev | A git dependency names an immutable rev, never a branch | ✅ | ✅ |
| fix-whitespace | Trailing whitespace, EOF newlines and non-Linux line endings are flagged, never fixed | ✅ | ✅ |
| actionlint | Workflow files under `.github/workflows/` pass actionlint | ✅ | ✅ |
| bandit-py | Staged Python carries no medium-or-higher bandit finding | ⚙️¹ | ✅ |
| build-fetches-name-a-version | Every new artifact an image build downloads names an explicit, content-verified version | ✅ | ✅ |
| bun-lock-fe | The frontend's `bun.lock` stays in sync with `package.json` | ✅ | ✅² |
| bun-audit-fe | The resolved frontend dependency set carries no high/critical advisory | ✅ | ✅² |
| check-added-large-files | No newly-added file exceeds 100 MB | ✅ | ✅ |
| check-case-conflict | No tracked filenames conflict on case-insensitive filesystems | ✅ | ✅ |
| check-merge-conflict | No conflict markers anywhere in the index | ✅ | ✅ |
| check-toml | Every tracked `.toml` file parses cleanly | ✅ | ✅ |
| check-yaml | Every tracked YAML file parses cleanly | ✅ | ✅ |
| ci-actions-sha-pinned | Every `uses:` in a workflow names a full commit SHA, version in a comment | ✅ | ✅ |
| commit-author-identity | A commit's author/committer email matches the configured git identity | ✅ | ✅ |
| commit-uses-a-named-file-list | A commit in a shared checkout names its files explicitly, never a plain `git commit` | ✅ | ✅ |
| deps-in-pyproject | No new `requirements.txt` — dependencies go in `pyproject.toml` | ✅ | ✅ |
| detect-private-key | No tracked file contains a private key block | ✅ | ✅ |
| doc-paths-resolve | Every repo path named in tracked markdown resolves to a real file | ✅ | ✅ |
| exec-bit-has-shebang | Every executable-bit file starts with a shebang | ✅ | ✅ |
| fallow-fe | The frontend tree carries no dead code | ✅ | ✅² |
| gitignore-tells-truth | `.gitignore` and the index never contradict each other | ✅ | ✅ |
| gitleaks | Staged content carries no secrets | ⚙️¹ | ✅ |
| hadolint | Every tracked Dockerfile passes hadolint | ✅ | ✅ |
| index-symlink-free | The git index contains no symlink entries | ✅ | ✅ |
| lefthook-validate | A changed `lefthook.yml` validates against lefthook's schema | ✅ | ✅ |
| next-build-fe | The frontend's production `next build` passes | ✅ | ✅² |
| no-lint-silencers | A lint warning is fixed at the smell, not silenced or allowlisted | ✅ | ✅ |
| no-new-root-files | The repo root gains no new files | ✅ | ✅ |
| no-pkill-by-pattern | No shipped script kills processes by command-line pattern match | ✅ | ✅ |
| no-project-claude-settings | No project-level Claude settings file is committed | ✅ | ✅ |
| no-root-claude-md | No `CLAUDE.md` is committed at the repo root | ✅ | ✅ |
| oxfmt-fe | The frontend tree is oxfmt-formatted | ✅ | ✅² |
| oxlint-fe | The frontend tree passes oxlint, type-aware and check-only | ✅ | ✅² |
| pip-audit-py | The resolved Python dependency set carries no known vulnerability | ⚙️¹ | ⚙️¹ |
| private-config-never-tracked | No private-config or `.env` file is ever git-tracked | ✅ | ✅ |
| react-compiler-fe | Staged frontend files carry no React Compiler bailouts | ✅ | ✅² |
| ruff | The whole Python tree passes ruff lint, project-wide | ✅ | ✅ |
| ruff-format | The whole Python tree is ruff-formatted, project-wide | ✅ | ✅ |
| rumdl | Tracked markdown passes rumdl, with a few rules disabled | ✅ | ✅ |
| shared-dep-floors-agree | A dependency named in more than one `pyproject.toml` carries one identical floor | ✅ | ✅ |
| shell-exit-capture-adjacent | `$?` is only ever captured immediately after the command it checks | ✅ | ✅ |
| shell-strict-mode | A shell script declares a `set -` strictness mode in its first ten lines | ✅ | ✅ |
| shellcheck | Every tracked shell script passes shellcheck | ✅ | ✅ |
| shfmt | Every tracked shell script is shfmt-formatted | ✅ | ✅ |
| tsgo-fe | The frontend tree typechecks clean | ✅ | ✅² |
| ty | The `ty` type checker passes whenever Python is staged | ✅ | ✅ |
| typos | The working tree is free of spelling errors | ✅ | ✅ |
| uv-lock | `uv.lock` is consistent with every workspace `pyproject.toml` | ✅ | ✅ |
| vitest-fe | Frontend unit tests related to the staged files pass | ✅ | ✅² |
| vitest-sb-fe | Storybook component tests related to the staged files pass | ✅ | ✅² |
| workflow-agents-name-their-type | Every `agent()` call in a tracked workflow script names its agent type | ✅ | ✅ |
| worktree-fresh | A worktree more than a day behind its upstream tip fails the commit | ✅ | ✅ |
| general-ast-checks³ | One AST-dispatch pass batches ~25 structural/style lanes (see below) | ✅ | ✅ |
| amg-hooks-advance-stage⁴ | Pins the vendored hooks submodule at the sha this commit will judge | ✅ | ✅ |
| amg-hooks-fetch⁴ | Fallback fetch of the hooks submodule when no background timer is installed | ✅ | ✅ |

### general-ast-checks bundle (25 lanes, one AST pass)

| Lane | What it enforces |
|---|---|
| comment-drift | Prose naming a path, line or symbol names one that exists |
| discovery-never-fails-open | A guard's discovery step never turns its own failure into a clean result |
| endpoint-urls-once | A third-party endpoint host is declared in one module per environment |
| failover-walk-budget | A multi-provider failover walk is bounded by one wall-clock budget |
| gate-can-fire | A hook command's gate can actually fire |
| keyword-only-past-five | A Python `def` takes at most five positional parameters |
| loguru-is-the-logger | Logging goes through loguru with the house format |
| md-table-width | Markdown table rows added by a commit stay under 70 characters |
| neutral-register | Added lines carry none of the banned offense-register words |
| no-actions-invocations | No script invokes CI workflows — builds and deploys stay local |
| no-runtime-self-skip | A test never decides its own applicability at runtime |
| no-shell-true | No code-execution/deserialization sink takes an untrusted value |
| no-silent-except | An `except` block logs, re-raises, or explains — never swallows silently |
| no-sys-path-mutation | No mutation of `sys.path` — imports resolve through the package layout |
| pathlib-over-os-path | Filesystem paths use `pathlib.Path`, not `os.path.*` |
| state-file-replaced-atomically | A polled state file is replaced by rename, never truncated in place |
| sweep-population-floor | A guard over a discovered population proves that population was non-empty |
| test-genre-declared | A test module declares exactly one genre, as a pytest marker |
| test-seam-private-patch | A new `monkeypatch.setattr` does not name a private seam |
| tests-reap-their-children | A test that starts a subprocess reaps it on every path |
| tmux-kill-server-names-its-socket | No script runs `tmux kill-server` without naming a private socket |
| tmux-launch-one-door | tmux sessions start only through one approved launcher |
| toolchain-pinned | Every host binary a hook can invoke is pinned in the installer |
| tracked-script-carries-no-hook-bypass | No tracked script ships a git-hook bypass or a sweeping `git add` |
| watcher-log-stamps-utc | Every timestamp a repo-owned script writes carries an explicit UTC marker |

All 25 run identically in both consumer repos — the bundle has no per-lane override
surface at the consumer level.

## commit-msg

| Lane | What it enforces | Research monorepo | Notes & config repo |
|---|---|---|---|
| commit-one-concern | A commit subject does not openly join two concerns | ✅ | ✅ |
| commit-subject-length | Commit subjects stay at or under 72 characters | ✅ | ✅ |
| commit-subject-unrepeated | A commit subject is not the subject of any of the last 200 commits | ✅ | ✅ |
| conventional-commit | The subject is `type(scope): summary` with a known type | ✅ | ✅ |

Footnotes:

1. ⚙️ — the lane runs with a repo-supplied `env:` override instead of the shared
   default: a config path (`bandit-py`, `gitleaks`) or an ignore-list file
   (`pip-audit-py`) that lives in the consumer repo. The check and its pass/fail logic
   are unchanged; only the config it reads differs.
2. ✅² — wired and enabled, but the notes-and-config repo ships no frontend, so these
   frontend-only lanes see no matching files and pass as a population-of-zero no-op
   there. They are not disabled; they simply have nothing to check.
3. `general-ast-checks` is one lefthook command that fans out into the 25-lane bundle
   detailed below it; it is listed once here to match the shared set's own naming.
4. Housekeeping, not a quality gate: keeps the vendored hooks submodule fetched and
   pinned so every other lane judges the hook code this commit will actually record.

## Repo-local extra lanes

Beyond the shared `general/` set, each consumer also extends a second, repo-specific
hook set that lives in the same shared repo but is wired into only one consumer, plus a
handful of lanes defined directly in that consumer's own `lefthook.yml`.

**Research monorepo** (Python/Django backend, React frontend):

- A repo-specific shared set (~80 pre-commit lanes, 2 commit-msg lanes, 1 pre-push
  lane) covering things the general set cannot know about this codebase: an OpenAPI
  snapshot that must match what the server generates, a full frontend test run before
  every push, Django-migration and API-contract conventions, component/story parity,
  and several others.
- `pre-push` carries exactly one lane in this repo: a release-tag guard for version-tag
  pushes, the one place amg-hooks keeps a `pre-push` check at all — everything else
  runs at `pre-commit` by design, and a tag push carries no commit of its own for a
  commit hook to intercept.
- Defined directly in this repo's own `lefthook.yml` (not vendored): two unit-test
  runners (`unit-tests-*`, `fe-unit-tests-*`) that run only the test groups related to
  the staged files, from test trees that live in this repo rather than the hooks repo.

**Notes & config repo** (notes, scripts, config — no test suite, no build, no type
checker of its own):

- A repo-specific shared set (~17 pre-commit lanes) covering the domain rules for one
  app this repo hosts: verdict-recording cadence, playlist composition invariants, a
  discovery-rate floor, and similar checks specific to that app.
- Defined directly in this repo's own `lefthook.yml` (not vendored): a snapshot-drift
  check that a local rules snapshot still matches its live source; a whole-tree
  markdown-link checker (every link in this repo's notes must resolve); and a
  systemd-unit health check for one background daemon, skipped on hosts with no
  systemd.

## Why

- **One hook, one folder.** Every lane is a `hooks/<name>/` directory holding its
  statement, its mechanism and its own tests — a lane is read, not inferred from a
  script.
- **Whole-tree over per-commit.** Nearly every lane judges the entire tracked index on
  every commit, not just the staged diff, so there is no narrow lane that can quietly
  drift stale between the commits that happen to touch it.
- **Adopt with a sweep, not a switch, and no ledger.** Turning a lane on means clearing
  everything it already finds, once; there is no tolerated backlog and no allowlist of
  known violations left standing indefinitely.
- **Configure at the edge, never fork the set.** A consumer hands a lane its own
  environment variable or exclude pattern at its own root; it never edits the shared
  hook to special-case itself.
- **Shared, and kept current automatically.** The hook set is a git submodule that
  fetches and advances itself on a timer, pinned to the exact commit each gate judges
  — a consumer is always close to the shared set's latest without a manual bump.
- **Safe under concurrent and shared use.** Commands read a point-in-time snapshot of
  the index rather than the live working tree, so another process's unstaged edit in a
  shared checkout cannot flip a verdict, and a lock file serializes concurrent
  worktrees of the same repo.
- **Batch what can be batched.** Dozens of small structural rules run through one
  shared AST pass instead of one process each, so adding a narrow style rule is cheap
  enough to actually add.
- **A gate that cannot run is a bug, not a warning.** Anything other than a clean pass
  blocks the commit; a check that errors out is fixed immediately rather than left to
  fail open.
- **Prove the wiring, not just the checker.** A passing unit test for a lane's logic is
  not treated as proof the lane actually fires through lefthook on a real commit — the
  wiring itself gets audited separately.
