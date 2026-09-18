<!-- hook: first-party-imports-resolve -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A first-party import names a module that actually exists

Whole-tree, every run: resolves every `aii_*` / `claude_cred_manager` import in
tracked Python against the files on disk. Exit 1 lists `file:line -> module`.

Why this needs its own gate, when the repo already runs ruff, ty and 98
pytest-backed rules: **the failure it catches is invisible to all three.**

Measured 2026-08-25. `aii_server/agent_abilities/_credentials/_bootstrap.py`
imported `AccountManager` from `aii_lib.claude_oauth.account_manager` — a module
that raises `ModuleNotFoundError` and matches nothing under
`find -name "account_manager*.py"`. The class lives in
`aii_lib/src/aii_lib/claude_oauth/autologin/accounts.py:165`. Two layers hid it:

  * the import sits in `if TYPE_CHECKING:`, so **it never executes** — no test,
    no run, no import of that module can fail on it;
  * **`ty check` on that file reported "All checks passed"** with the import
    unresolvable, so the annotation `-> AccountManager | None` silently degraded
    to an unknown type. The function read as type-checked and was not.

Five other sites used the correct path, including line ~64 of the SAME file at
runtime. The file contradicted itself 48 lines apart and nothing noticed. Fixed
in `9058aa5c1`; this rule is what stops it recurring, because nothing else can.

Cost: 1.89 s, 23 MB RSS, 1466 imports over 1258 files. Cheap enough to run
unconditioned — and it should be, since a rename anywhere can strand an importer
that the staged diff does not touch.

**Proven to bite before being proposed.** On a synthetic tree: correct imports
plus a PEP 420 namespace package -> rc=0; the exact defect re-introduced ->
rc=1 naming `aii_server/good.py:3 -> aii_lib.claude_oauth.account_manager`.

Two scope decisions, both learned by measuring rather than assumed:

  * `claude_agent_sdk` is a THIRD-PARTY dependency that a naive `claude_`
    prefix matches. It is not in the tree, so the prefix list names the
    workspace packages explicitly instead.
  * `.claude/skills/**/scripts` import their SIBLINGS by bare name, which works
    because the script's own directory is on `sys.path` when run directly.
    That is a different import contract, not a defect, so those files are out
    of scope — a directory rule, not a per-file exemption.

**Scoped to the repo root on purpose — do NOT point it at the public export.**
Measured: against `aii_public`'s staged export it exits 1 with six hits, and
FIVE are the design. `aii_runpod` is deployment infrastructure the allowlist
deliberately omits, and every import of it is lazy and guarded by a runtime mode
check (`if config.execute_env.mode == "runpod": from aii_runpod... `), so local
mode — the export's stated purpose — never executes them. The rule cannot tell
"missing by mistake" from "optional package deliberately absent, imported behind
a guard". On the repo root that distinction does not arise: everything is
present and the check passes 1466/1466. A boundary to know, not a bug to fix.

Resolution is PURE: filesystem + AST, no `importlib.util.find_spec`. `find_spec`
imports every parent package on the way to the target, which for `aii_server`
drags in Django setup; a guard must not have side effects, and one that needs
`AII_WEB_APP_MODE` to pass will fail confusingly elsewhere. It also maps plain
directories, so PEP 420 namespace packages resolve — an earlier version that
mapped only `__init__.py` reported 11 false positives against 1 real one.

**Adjacent rule, disclosed: `rule-import-linter` (aii/python). NOT a duplicate,
and the evidence is empirical rather than argued.** import-linter enforces
`layers` / `forbidden` / `independence` contracts over grimp's static graph — it
checks WHICH modules import WHICH, not whether the target EXISTS. A module that
cannot be resolved is simply not a node in that graph, so an import pointing at
nothing is invisible to a layering contract.

Measured, not reasoned: the dangling import was introduced 2026-08-19 in
`4fe52e6bb` (the refactor that created `_credentials/`), and lived until
`9058aa5c1` on 2026-08-25 — **six days**, with import-linter running in CI the
whole time. It reports `Contracts: 4 kept, 0 broken` today and reported the same
throughout. Six days of a green architectural gate over a broken import is the
disjointness proof.

The same disjointness holds against the other import-adjacent gates:
`rule-dead` finds symbols nothing READS (this finds reads with no symbol),
`rule-module-lines` counts lines, `rule-module-docstrings` checks prose.

Fix when blocked: point the import at the module that exists (find it with
`grep -rn "^class <Name>"`), or restore the module that was moved. If the name
is genuinely gone, delete the import — a `TYPE_CHECKING` import of a dead module
is annotating nothing.

Delete-check: cannot delete. The dimension is "does this name resolve", and the
two tools that should answer it do not — the runtime never executes the import,
and `ty` passes on it. Deleting the rule restores a silent-failure class with a
measured instance. It is already fully mechanized (a cmd rule, no judgment), so
there is nothing to promote and nothing an agent must decide.
