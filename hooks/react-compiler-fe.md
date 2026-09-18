<!-- hook: react-compiler-fe -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_STAGED
# Staged frontend files carry no React Compiler bailouts

Runs `eslint-plugin-react-compiler` against the staged `.ts(x)` files so
any Rules-of-React violation that would make the compiler skip a
component is caught at commit time. Without this gate, bailouts only
surface in `next build` output (CI / dev-server log) and silently
disable per-component memoization in production.

Scope is the staged files rather than the whole project because the
React Compiler bailout analysis is **file-local** — the compiler
operates on one function at a time and doesn't cross file boundaries to
detect bailouts. So running only on changed files catches every
newly-introduced bailout and is ~10× faster than scanning the full
project (~17 s warm → ~1 s for a typical commit). The trade-off: a
bailout introduced via a path that bypasses local pre-commit (e.g. a
teammate's GitHub-UI merge never touched on your machine) won't be
flagged until that file is touched by a later commit.

Why ESLint when the rest of the FE moved to oxlint: oxlint hasn't ported
this rule (the analysis is React-team-specific — see
`oxc-project/oxc#20791`). The Rust port
(`oxc-plugin-react-compiler@0.2.0`) ships ESLint subpaths but panics on
non-trivial files and runs 3-4× slower than the JS plugin via its NAPI
bridge — revisit once that matures (late 2026 / 2027 timeline).

Speed via `eslint_d` daemon: warm linting of a single file is
sub-second; cold daemon spawn is ~14 s (first commit after a ~24 h
pause). The daemon auto-spawns on first invocation — no `eslint_d start`
step required for new clones. `ESLINT_D_IDLE=1440` (24 h) is set in
`check.sh` so the daemon survives day-long pauses.

Content cache: `check.sh` also passes `--cache --cache-strategy content`,
cache file under `<git-common-dir>/amg-hooks/cache/react-compiler-fe/` of
the REAL checkout — resolved from `AMG_HOOKS_WORKTREE`, not from the cwd.
The gate runs this hook inside the whole-index snapshot, which carries a
`.git` of its own; a cache resolved from there lands in a directory named
after that one index and is reaped at post-commit, so every commit gets a
different snapshot, finds no cache, and pays the cold lint.
Measured: 11.4 s → 0.25 s warm over 736 files whose content did not
change since the last pass. The file is named by a hash of
`eslint.react-compiler.mjs` plus the resolved versions of the plugin,
`eslint` and `@typescript-eslint/parser` — every installed input the
verdict depends on, since eslint decides which rules run and the parser
decides what AST the plugin sees. A config edit or any of those bumps
starts a fresh cache instead of serving stale verdicts; the stale file is
pruned on the next run.

Fix when blocked: restructure the component to satisfy the Rules of
React (no mutation of props/state, hooks called unconditionally, no
side effects during render) so the compiler can memoize it — do not
suppress the rule.

Delete-check: tool-enforced, cannot delete — the compiler silently skips
non-conforming components, so without the gate the regression is
invisible until a production performance report.
