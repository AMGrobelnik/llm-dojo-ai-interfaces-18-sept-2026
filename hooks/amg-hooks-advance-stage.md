# amg-hooks-advance-stage

Not a `general/hooks/<name>/README.md` folder — this is a submodule-plumbing
command wired directly in `general/lefthook.yml`, documented here from its
inline comment and the README's "Staying on main by itself" section, since it
has no dedicated hook folder of its own.

## What it does

Priority-1 pre-commit command, run before every other lane. It fast-forwards
a CLEAN vendored `amg-hooks` submodule onto the tip the background fetch
already pulled, then pins the submodule's gitlink at whatever sha is now
checked out — so every hook lane that runs after it, in the same commit,
judges the exact hook code this commit is about to record. It moves no
working-tree file: the checkout itself only advances later, at
post-commit / post-checkout / post-merge (see `amg-hooks-advance.md`
equivalent behavior in the README), after the gate rather than during it. A
dirty submodule, or a local HEAD carrying commits `origin/<branch>` does not
have, is left untouched — a stderr note names what is blocking it instead.

Command (verbatim from `general/lefthook.yml`):

```
'[ -f {amg_hooks}/tools/amg_hooks_advance.py ] && python3 {amg_hooks}/tools/amg_hooks_advance.py --stage || true'
```

It can never fail a commit (`|| true`), and is a no-op wherever the
`amg_hooks_advance.py` tool is absent.
