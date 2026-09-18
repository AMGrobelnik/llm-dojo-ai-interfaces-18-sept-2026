<!-- hook: amg-hooks-fetch-timer -->

| stage | scope | budget | status |
|---|---|---|---|
| post-checkout | tree | — | active |
| post-merge | tree | — | active |

# Installs the background systemd timer that keeps the hooks submodule fetched

No dedicated `README.md` exists for this lane — it is documented here from
its `general/lefthook.yml` comment, since it is a plain invocation rather
than a `dispatch.py`-owned check folder.

A fresh clone, a branch switch or a pull is a moment the submodule pin may
need to move, and the fetch timer is what keeps it fetched afterward without
relying on `amg-hooks-fetch`'s inline fallback at every commit. The install
is idempotent and takes a no-systemctl fast path once it has already run, so
repeating it at both `post-checkout` and `post-merge` is what makes
`lefthook install` plus any ordinary checkout enough to enable the feature on
a new machine.

    run: '[ -f {amg_hooks}/tools/install_fetch_timer.py ] && python3 {amg_hooks}/tools/install_fetch_timer.py --quiet || true'

Never fails a checkout or merge — a missing `install_fetch_timer.py` (an
older submodule pin) is a silent no-op.
