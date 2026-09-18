<!-- hook: import-linter -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# The import-layering contracts in [tool.importlinter] hold

Enforces the import-layering contracts in `[tool.importlinter]` (root
pyproject.toml). Currently one `forbidden` contract: `aii_lib` is the
dependency-free base layer and must never import aii_pipeline / aii_runpod /
aii_server / aii_launcher.

grimp builds the import graph by STATIC AST analysis — it does not execute
your code — but it must import the root packages to locate their source, so
this runs the project-venv `.venv/bin/lint-imports` where aii_* are
editable-installed (same pattern as the FE's `./node_modules/.bin`
binaries), not a global uv tool.

Project-wide by nature: a layering contract is a property of the whole
module graph, so it runs whenever any .py is staged regardless of which
package the edit touched. Best-of-7 wall time ~150ms — the cheapest of the
project-wide checks (ty ~1.2s, tsgo cold ~8s).

Fix when blocked: move the code so the dependency points downward — a
helper aii_lib needs must live in aii_lib (or the import inverted), never a
contract exception for a convenience import.

Delete-check: tool-enforced, cannot delete — the layering IS the dimension;
without the contract the base layer accretes upward imports silently.
