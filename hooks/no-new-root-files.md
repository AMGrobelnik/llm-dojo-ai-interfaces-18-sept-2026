<!-- hook: no-new-root-files -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MODE
# The repo root gains no new files

Applies to files ADDED at the top level by the staged diff. The existing
tracked root set (~25 files: configs, Dockerfiles, README...) is
grandfathered; anything new belongs in a package directory or the scratch
dir, and a genuinely new root config is added to this rule's allowlist in
the same commit — making root growth a reviewable event.

Why: measured 231 entries at this repo's root, 25 tracked — the rest is scratch (125 .png, 24 .jpeg, 25 .yml...) hidden by 29 root-anchored gitignore rules added reactively, one per past accident (measured 2026-08-22 at 29, of which 15 are root-level file globs; the body previously said ~18, a figure the .gitignore history never carries — it stepped 13 -> 22 -> 25 -> 29 across June to August). Every session pays the navigation cost.

Fix when blocked: move the file into the package it belongs to, or the
scratch dir; if it is truly a new root-level config, add its name to
`check.sh` here in the same commit.

`check.sh`'s `ALLOW` list is pre-seeded with the standard tool-convention
configs — `pyproject.toml`, `_typos.toml`, `ruff.toml`, `.rumdl.toml`,
`.python-version` — since
each of those tools requires its config at the repo root by its own
convention, not by this repo's choice.

Delete-check: partially deletable upstream — a single scratch-dir
convention removes the reason files land at root; this rule holds the
line meanwhile.

RE-MEASURED 2026-08-24 — **the tracked root set has not moved. That is the
whole point of the rule, and it is the number to watch.**

| quantity | body | today |
|---|---|---|
| entries at root | 231 | 253 |
| **tracked** at root | 25 | **25** |
| root-anchored gitignore lines | 29 | 29 |
| `.png` / `.jpeg` / `.yml` | 125 / 24 / 25 | 126 / 24 / 25 |

The two rows tell opposite stories on purpose. Untracked scratch at the root
grew by 22 entries in the same period, so the mess this rule was written
beside is still accumulating — but the set the rule actually governs is
**unchanged at 25**, which is a gate holding rather than a backlog.

So when re-measuring this, compare the TRACKED count. The 231 → 253 figure
moves with whatever someone last left lying around and says nothing about
whether the rule works; 25 → 25 says it does.

The `.png` count moved 125 → 126, which is the same story one file smaller.
