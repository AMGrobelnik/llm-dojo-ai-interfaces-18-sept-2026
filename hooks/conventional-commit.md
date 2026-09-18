<!-- hook: conventional-commit -->

| stage | scope | budget | status |
|---|---|---|---|
| commit-msg | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MSG_FILE
# The subject is `type(scope): summary` with a known type

Ported verbatim from the lefthook `commit-msg` hook. Types: build chore ci
docs feat fix perf refactor revert style test. Merge/Revert/fixup!/squash!
subjects pass untouched (git generates those). The scope VOCABULARY is a
separate rule (rule-commit-scopes); this one checks only the format and
the type list.

Delete-check: cannot delete while rule-commit-scopes and the log-filter
workflow depend on the format existing.
