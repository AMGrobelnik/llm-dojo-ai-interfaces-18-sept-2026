<!-- hook: user-dir-one-layering-rule -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every file under a per-user aii_config dir layers by ONE rule — sparse deep-merge over the shipped file — so no shipped default can be lost by a user simply having their own copy.

The per-user dir's own module docstring
(aii_server/dashboard/api/run_config/_bootstrap.py:3-8) declares the whole
directory sparse: "The per-user config dir (aii_data/users/<u>/aii_config/) is
a SPARSE overlay: it holds ONLY the keys that user changed … any file or key
the overlay omits falls through to canonical". One file in that same dir does
not obey it: aii_server/dashboard/api/__init__.py:360-361 reads `path =
user_path if user_path.exists() else settings.AII_CONFIG_DIR / "user.yaml"` —
a wholesale REPLACE — and only then `deep_merge(role_cfg, user_cfg)` (line
379). Ran a probe against the real files: `shipped aii_config/user.yaml keys :
[]` — the shipped file is comments-only, so REPLACE and MERGE coincide today
and nothing is lost. That is the whole safety margin: the first key added to
aii_config/user.yaml vanishes for every account that already has its own copy,
and the shipped file's own header (line 1) invites exactly that by documenting
itself as a settings file. Nothing claimed covers layering here — rule-server-
yaml-closed-schema [PENDING] covers user.yaml's schema, not how it composes.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: config-precedence)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_user_dir_layering.py  # asserts _load_user_limits composes shipped+per-user by deep_merge (no exists()-ternary REPLACE over an aii_config path), or, pre-fix, that yaml.safe_load('aii_config/user.yaml') is falsy

Proposed condition: `git diff --cached --name-only | grep -qE '(^aii_config/user\.yaml$|^aii_config/roles/|dashboard/api/__init__\.py$|run_config/_bootstrap\.py$)'`

Delete-check: Deletable and the rule should enforce the deleted end-state: change
_load_user_limits to `deep_merge(deep_merge(role_cfg, shipped_user_cfg),
per_user_cfg)` so the dir has exactly one layering rule and the REPLACE branch
disappears. Until then the enforceable proxy is that aii_config/user.yaml
parses to an empty mapping.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **partly-wrong**.
A different agent re-ran every measurement before this reached the owner.

What it found:
$ sed -n '355,380p' aii_server/dashboard/api/__init__.py 359: user_path =
user_config_dir / "user.yaml" 360: path = user_path if user_path.exists() else
settings.AII_CONFIG_DIR / "user.yaml" ... 379: return deep_merge(role_cfg,
user_cfg) (REPLACE-then-merge-with-role confirmed; cited as :360-361, actually
:359-360) $ python3 -c "import yaml,pathlib;
d=yaml.safe_load(pathlib.Path('aii_config/user.yaml').read_text());
print(repr(d)); print('keys:', list(d.keys()) if isinstance(d,dict) else [])"
None keys: [] (shipped file is comments-only — the 'no loss today' half holds)
$ sed -n '1,8p' aii_config/user.yaml # Per-user settings — the fallback when a
user has no own copy at # data/users/<username>/aii_config/user.yaml. $ sed -n
'313p' aii_server/dashboard/api/__init__.py everyone else. The user.yaml
itself (per-user copy → global template) $ sed -n '1,8p'
aii_server/dashboard/api/run_config/_bootstrap.py """User-config-dir helpers
for the pipeline-config router (overrides-only model). The per-user config dir
(``aii_data/users/<u>/aii_config/``) is a SPARSE overlay: it holds ONLY the
keys that user changed, layered on canonical ``aii_config/`` at load time (see
:meth:`PipelineConfig.from_yaml`). ... $ grep -rn "user.yaml" --include=*.py
aii_server/ aii_lib/ aii_pipeline/ | grep -iE
"write_text|open\(.w|dump|mkdir|copy" (no output — nothing in package source
ever CREATES a per-user user.yaml) $ grep -n "user.yaml" .claude/skills/amg-
rule-engine/rules-pending/one-door/rule-config-overlay-one-door/SKILL.md
65:(and :364 raw-loads user.yaml), so the compute-cap path is not the only
door

Corrected statement of fact:
The mechanism is real (wholesale REPLACE at :359-360, not a sparse merge over
the shipped file) and the shipped file genuinely holds zero keys, so nothing
is lost today. But the framing 'does not obey it [silently]' is wrong: the
behaviour is declared deliberate in TWO places the proposal does not mention —
aii_config/user.yaml's own first two lines call itself 'the fallback when a
user has no own copy at data/users/<username>/aii_config/user.yaml', and the
loader docstring at __init__.py:313 writes the order as '(per-user copy →
global template)'. That is the exact 'comment above the defect declaring it
deliberate' failure mode. Two further weakenings: the sparse-overlay docstring
the proposal quotes is scoped to the pipeline-config router ('see
PipelineConfig.from_yaml'), not to every file in the dir; and no package-
source code ever writes a per-user user.yaml (only tests, and the manual
operator action staff_bootstrap.py:66 describes), so the loss scenario
requires a hand-created file. Line cite is off by one (:359-360, not
:360-361).

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Confirmed at _load_user_limits: a per-user user.yaml REPLACES the
shipped file rather than deep-merging, so a user having their own copy
silently loses shipped caps. Claimed rule-lib-config-merge-paths pins the
<thing>.yaml + private-overlay contract, not the per-user dir.
- KEEP: Mechanizes to a ban on the replace-not-merge shape (`user_path if
user_path.exists() else shipped`) plus a presence assertion on deep_merge,
both loud. Third layer, distinct from rule-lib-config-merge-paths (private
overlays) and rule-deep-merge-single-source (one implementation); losing a
shipped default by owning a file is a real defect neither catches.
- KILL: One-site fix (rewrite _load_user_limits as a nested deep_merge), on a
surface already claimed three ways: ENFORCED rule-lib-config-merge-paths owns
the deep-merge contract, PENDING rule-config-overlay-one-door owns the read
door, PENDING rule-server-yaml-closed-schema owns user.yaml's schema.


ADOPTION (2026-08-25): the REPLACE is FIXED. `limits_for_config_dir` now loads
the shipped `user.yaml` and deep-merges the per-user copy on top. Behaviour was
proven against the real `deep_merge` across six shapes: on today's state
(shipped file comments-only, zero keys) old and new agree exactly, so nothing
changed now; they diverge only where the old form dropped a shipped key the
user's sparse copy omitted, including the nested case where changing one leaf
discarded its siblings.

**Selecting a path is only a defect if the path is then READ**, and that is the
whole check rather than a refinement of it. The same ternary is correct when it
names a file for a log message — "where should a human look?" has one answer
even when two files were merged — and such a line SURVIVES in the fixed code,
precisely because the load beside it became a merge.

The first draft flagged it. It asked whether the assigned name appeared in a
loader call by SUBSTRING, so `role_path.open()` read as a load of `path`, and
the gate punished the fix it had asked for. It now compares identifiers through
the AST. Verified against history: on the tree before the fix it exits 1 naming
`__init__.py:386`, and on today's tree it exits 0 with the log-message ternary
left alone.

CONDITION WIDENED 2026-08-25: it named four specific paths, inherited from the
proposal, while the checker built for it scans EVERY tracked `aii_server` Python
module. Measured: 98 files scanned, 2 matched by the condition. A replace-ternary
added to any of the other 96 would not have fired the gate at all — inert for
98% of the surface it claims to cover, and silently, because a rule that never
runs looks exactly like a rule that passes.

The condition now matches the scan: `aii_server/**.py`, plus the two config
paths whose contents this rule is about (`aii_config/user.yaml` and
`aii_config/roles/`), since editing those can make a previously-harmless
replace start losing keys.

Found by applying `test_every_condition_pathspec_matches_something.py`'s own
logic to the PENDING tree — that guard enumerates `rules/` only, so no pending
rule's condition had ever been checked. All 21 pathspecs resolve; this was a
scope mismatch rather than a dead path, which that guard would not have caught
either.

**The same shape is NOT a defect in the enforced tree, and the difference is
the backstop.** Auditing `rules/` for it turns up 20 rules whose condition names
a few source paths while their script scans broadly — and every one is a
commit-scoped unit-test GROUP (`pytest $RULE_DIR`), where CLAUDE.md states the
design outright: the condition runs the group at commit when its source paths
are touched, and `pytest.ini`'s `testpaths` includes
`.claude/skills/amg-hooks/rules`, so CI collects every group regardless.
The condition there is a commit-time cost optimisation with CI behind it.

A cmd-check gate has no such backstop. Nothing else ever runs it, so a narrow
condition is not an optimisation — it is the whole of when the rule exists.
Widening those 20 conditions would slow every commit and buy nothing; widening
this one was the difference between a gate and an ornament.