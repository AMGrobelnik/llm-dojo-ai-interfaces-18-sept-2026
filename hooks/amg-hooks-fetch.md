# amg-hooks-fetch

Not a `general/hooks/<name>/README.md` folder — this is a submodule-plumbing
command wired directly in `general/lefthook.yml`, documented here from its
inline comment and the README's "Staying on main by itself" section, since it
has no dedicated hook folder of its own.

## What it does

Fallback fetch for a machine with no systemd user manager, where the
background two-minute fetch timer (`tools/install_fetch_timer.py`) was never
installed: fetches the `amg-hooks` submodule inline, but only when this clone
has not fetched in the last 120 seconds — a silent no-op everywhere the timer
IS running. Capped at ten seconds and cannot fail a commit.

Command (verbatim from `general/lefthook.yml`):

```
'[ -f {amg_hooks}/tools/amg_hooks_fetch.py ] && python3 {amg_hooks}/tools/amg_hooks_fetch.py --if-stale 120 || true'
```

Together with `amg-hooks-advance-stage`, this is what lets a consumer follow
`amg-hooks` `main` on its own, at most about two minutes behind, with nothing
to remember and nothing to run beyond `lefthook install`.
