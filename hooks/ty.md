<!-- hook: ty -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |
# ty type check passes whenever Python is staged

Astral's `ty` type checker over the project. Install once:
`uv tool install ty==0.0.34`. Config in `[tool.ty]` under root
pyproject.toml.

The check is project-wide (ty resolves the whole module graph) but gated on
a `.py`/`.pyi` file being in the staged set — the same `*.{py,pyi}` glob
gate the lefthook hook used — so non-Python commits pay nothing. In
all-mode the tracked-file list contains Python, so the full check always
runs there.

Fix when blocked: fix the type error at its root — adjust the annotation or
the code, never a `# type: ignore` to silence a real mismatch.

Delete-check: tool-enforced, cannot delete — static type errors are only
caught by a checker; scope and strictness tuning live in `[tool.ty]`, not
in this rule.
