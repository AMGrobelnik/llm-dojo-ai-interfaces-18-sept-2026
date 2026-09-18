<!-- hook: bandit-py -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# Staged Python carries no medium-or-higher bandit finding

`bandit -ll` over the staged `*.py` files. It is the one gate here that
asks the *tool's* question — "does this call shape have a known abuse" —
rather than a question about this codebase, so it catches the classes no
hand-written check enumerates: `subprocess(shell=True)`, `os.system`,
`eval`/`exec`, unsafe `yaml.load`, `pickle`, `tarfile.extractall`,
bind-to-all-interfaces, string-built SQL, weak hashes, disabled TLS
verification.

## bandit rather than semgrep, measured

Both were installed and run over the same twenty staged files on
2026-09-16 (aarch64, warm caches):

| tool | what it ran | wall |
|---|---|---|
| `bandit -ll` | the bundled plugin set, no network | **1.1 s** |
| `semgrep scan` | `p/python` + `p/django` | 25.4 s |

semgrep's cost is structural rather than incidental: both rulesets are
fetched from its registry, so the run needs the network at commit time and
a machine without it has no rules at all. bandit ships its plugins in the
wheel. Neither reported anything on that population, so the faster one wins
outright.

## Scope: the staged files, and why

lefthook's `{staged_files}`, filtered to `*.py`, rather than the whole index
every other checker judges. Measured over research-monorepo's 1445 tracked `*.py`:

| population | wall |
|---|---|
| whole tracked tree, cold | 16.5 s |
| 20 staged files | 1.1 s |
| 1 staged file | 0.11 s |

Every bandit plugin reads one module's AST and crosses no file boundary, so
the analysis is file-local and the staged set catches every newly introduced
finding. The trade is react-compiler-fe's: a finding that arrives through a
path which never ran this gate stays unreported until that file is touched
again. 16.5 s whole-tree is inside the 30 s hard cap but three times the 5 s
target, and it would be paid on every commit including the ones that stage
no Python at all — hence the `glob:` and the staged list.

## The floor and the config

`-ll` reports MEDIUM severity and above. LOW here is 13368 B101
(`assert_used`, almost all pytest) plus the B404/B603/B607 "you imported
subprocess" advisories — 13741 of the tree's 14003 raw findings, none of
them a verdict.

A repo hands in its own config as `BANDIT_CONFIG` from its root
`lefthook.yml`, the same shape `gitleaks` takes `GITLEAKS_CONFIG`; a
variable naming a file that is not there is dropped rather than fatal, so a
clone without it still scans on bandit's defaults. research-monorepo's is
`aii_public/bandit.yaml`: it excludes the test trees (a test asserts,
pickles its own fixture and binds a throwaway socket by design, and none of
that is bandit's threat model) and skips exactly one plugin, with the reason
on the line — B108 `hardcoded_tmp_directory`, which fires on any `"/tmp/…"`
literal and whose 23 sites here are all fixed artifact paths rather than
predictable temp files opened for writing.

Fix when blocked: fix the call. Where the shape is genuinely intended and
contained, bandit's own per-line `# nosec B301  # <reason>` marker is the
escape — it is per-site and carries its reason, which a config-wide `skips:`
entry cannot. It is deliberately NOT one of the silencer comments
`no-lint-silencers` bans (`noqa`, `type: ignore`, `eslint-disable`): those
suppress a style verdict repo-wide from the line, while a `nosec` names one
plugin at one call and is read by this hook and `no-shell-true` alone.

Delete-check: tool-enforced, cannot delete — the whole point is the classes
nobody wrote a check for.
