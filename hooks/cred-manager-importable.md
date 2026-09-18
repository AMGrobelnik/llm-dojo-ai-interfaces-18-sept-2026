# claude_cred_manager imports from the project venv and is backed by a real file

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 1s | active |

## Why

`claude_cred_manager` is deliberately not a uv workspace member — it is a
separate service with its own deploy unit — so it is absent from the lock and
every `uv sync` prunes it. CLAUDE.md records the trap and the repair
(`uv pip install --python .venv/bin/python -e claude_cred_manager --no-deps -q`),
because nothing else reports it.

The removal is silent. The checkout keeps a `claude_cred_manager/` directory at
the repo root, and the repo root is on `sys.path`, so after a prune the package
still resolves — as an implicit PEP 420 namespace portion with `__file__` None.
Measured against this repo on 2026-09-08 with an interpreter that lacks the
install: `import claude_cred_manager` succeeds with `__file__` None, and
`import claude_cred_manager.config` raises `ModuleNotFoundError`. A checker that
catches only `ImportError` sees the second and misses the first.

The failure surfaces far from the cause. The 16 test modules under
`research-monorepo/unit-tests/cred-manager-service/` import the package outright and
all 16 turn into collection errors, but that group runs only when
`claude_cred_manager/` is staged — so an unrelated commit after a `uv sync`
runs nothing that would notice. A 0.14 s import probe at commit closes that
window. As an agent rule this was consulted 74 times with no evidence recorded;
the question it asked has one machine answer, which is what makes it a program.

One documentation defect is still live at HEAD `eaf82761cddc` (re-checked
2026-09-08, not corrected here): CLAUDE.md's Notes entry names
`…/claude-creds-lifecycle/test_autologin_magic_link.py` as the only symptom, but
that module uses `pytest.importorskip` at line 471 and skips instead of failing;
the 16-module sibling group is the real coverage.

## Mechanism

`check.py` resolves the repo root from `git rev-parse --show-toplevel`, confirms
the package is still in the tree by reading the index (`git ls-files`, with a
disk fallback for a package added but not yet staged), then runs the venv's own
interpreter once as a subprocess and imports each configured module in it.

| failure mode | mechanism |
|---|---|
| pruned outright | the import raises: finding |
| pruned silently | `__file__` is None: finding |
| no venv present | `skipped: …`, exit 0 |
| package moved away | `cannot run: …`, exit 2 |

The probe runs with cwd set to the repo root, so the verdict does not depend on
where the hook was invoked from, and reproduces the namespace shadow the
consumer actually has; `-B` keeps it from writing `__pycache__` into the tree it
inspects. A regular package beats a same-named namespace portion during the
`sys.path` scan, so a healthy install still passes with the shadow present — a
fixture pins that. Findings print as `path:line: message` against the package's
tracked `pyproject.toml`, each naming the interpreter probed and the reinstall
command verbatim. Both project knobs and the module list live in one `CONFIG`
dict.

The hook runs under `python3`, not `.venv/bin/python`: the venv is the thing
under judgment, so the checker must not depend on it.

`tree` is the closest of the three scope words, and it is an approximation —
the state read is the venv, not any file, so it is neither `file` nor
`relation`. PATH arguments are accepted for contract uniformity and are
ignored; a test pins that they move neither the passing nor the failing verdict.
For the same reason the lefthook fragment carries no `glob` and no
`{staged_files}`: gating it on `uv.lock`, `pyproject.toml` or
`claude_cred_manager/` being staged would recreate the exact window this probe
exists to close, since the commit after a `uv sync` usually touches none of
them. This was the old engine's `flow` tier.

## Stock

0 findings against `/home/<user>/projects/research-monorepo` at HEAD
`eaf82761cddc` (2026-09-08): the venv holds the package editable, and both
probed modules resolve to
`claude_cred_manager/src/claude_cred_manager/`. Whole-tree runtime 0.15 / 0.14 /
0.13 s, median **0.14 s** — one interpreter start plus two `git` reads.

Pointing `--python` at an interpreter without the install, on the same tree,
produces the two findings described above, so the hook is measured biting rather
than only measured quiet.

## Fragility

| refactor | effect | guard |
|---|---|---|
| package renamed or moved | probe fails forever | exit 2 |
| venv moved or removed | nothing to probe | `skipped:` |
| package becomes a member | probe passes trivially | none |
| one probed module vanishes | reads as a finding | intended |

The third row is deliberate: making `claude_cred_manager` a workspace member is
the correct end state, and CLAUDE.md records it as explicitly rejected, so a
trivially-passing probe there would be a signal to delete this hook rather than
a defect. The fourth is also deliberate — a single missing submodule is what a
partial install looks like, and only the wholesale disappearance of the package
directory is treated as the tree having moved.

## Residue

The rule's agent form could weigh things the program does not, and they are left
out on purpose:

- Whether the package should be a workspace member at all. The program never
  argues the design; it reports the state.
- Whether the installed copy is the right version, editable rather than a
  wheel, or resolving against this lock. Only "imports and has a real
  `__file__`" is checked.
- Whether some other non-member package needs the same probe. Only the one
  package CLAUDE.md names is configured.
- Repair. The repo's hook convention is warn-only, never auto-sync, so the
  finding prints the reinstall command and stops.
- The documentation defect in CLAUDE.md's Notes entry is reported here and left
  for a person to correct.
