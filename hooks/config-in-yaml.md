# A new setting arrives as a config key, not as a flag default or an env read

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The agent rule behind this was applied 1610 times and blocked 649. Its FAIL
clause is *"the diff plainly introduces a new setting as an argparse flag or a
read of a new environment variable, where a config file key would serve"*, and
it converts almost cleanly because the rule was already written as an
enumeration.

Its PASS list is four exceptions: secrets, debug or dev-only switches,
standard tool flags and reads of EXISTING variables, and per-invocation IPC
parameters. Three are name tests. The fourth is the interesting one and it
needs no exception list at all — a variable this repository both WRITES and
reads is an argument handed to a child process, not a knob a person turns,
and that is visible in the tree.

## Mechanism

`check.py` parses each changed module with `ast` and compares it against the
same module at `--base`, so what it reports is what the change ADDS.

| id | what it reports |
|---|---|
| C1 | a new option whose `default=` is a literal |
| C2 | a read of a new environment variable this repo owns |
| C4 | a pydantic settings field or `Field(env=...)` |
| C3 | module-level constants — implemented, off by default |

**C2 passes five gates in order**, each of which removed a measured false
positive: not in the same file at the base; not read anywhere in the tree at
the base (the "existing variable" exception, where existing means anywhere);
its first token is in the derived owned namespace; not a secret and not a
debug switch by name; and not WRITTEN anywhere in the tree.

**The owned namespace is derived, not listed.** The first underscore-token of
every distinct top-level tracked directory, kept when two or more share it —
on this repo exactly `{AII}`. No vendor list, so `HF_HOME` and
`DJANGO_SETTINGS_MODULE` fall out of scope automatically and adding a
dependency cannot rot the rule. Counting files instead of directories was the
first implementation and it yielded six prefixes, a namespace wide enough to
fire on other people's variables.

Writers are found by shape rather than by name: a fixed-string prefilter on
the namespace prefix, then eight write shapes. Handing git the eight-shape
alternation directly costs 1.34 s and returns the identical 55 names; the
prefilter costs 0.09 s, which took the per-file runtime from 1.4 s to 0.10 s.

Reads go to the git INDEX, so `--base HEAD` compares exactly the staged diff
and a peer's unstaged edit is neither judged nor counted as an existing read.
The module is split into `_config.py` and `_gitio.py` siblings under the
600-code-line cap.

## Stock

Whole tree, at HEAD, with no `--base`: **7 findings**, 0.71 s over 582 judged
modules. As the hook runs it — `--base HEAD` over the staged files —
those 7 are silent, because they are not what any one change adds; 11
changed files cost 0.32 s.

| id | n | what they are |
|---|---|---|
| C1 | 3 | a retry budget, a watchdog TTL, a workspace path |
| C2 | 4 | deployment name and version, demo admin identity |

The negative control sits three lines above one of the findings: `--port` has
`default=WORKER_PORT` and does not fire, because a name is not a literal
— the value already comes from somewhere. That distinction is what makes
C1 precise rather than noisy.

Replayed over history: the last 200 commits would have blocked **0** times;
across the 252 commits that touch an option or env site, 18 would have
blocked with 31 findings, about 25 of which name a value the repo now keeps in
config or plainly would. Two false-positive classes were found by that replay
and fixed — a moved file re-reporting the flags it carried (rename
detection), and the env dict a launcher builds as a plain local rather
than `os.environ`
(the commonest writer shape here, which had missed six parent-to-child
parameters).

## Fragility

| refactor | effect and guard |
|---|---|
| source roots renamed | exit 2 if nothing matches a root |
| the config tree moves | exit 2, nowhere to put a setting |
| every judged file fails to parse | exit 2 on zero judged |
| a writer or base-rev grep errors | any exit but 0/1 is exit 2 |
| the repo is renamed | the namespace is derived per run |

A failed grep treated as "nothing is written" would turn every IPC parameter
into a blocking finding, which is why that path is exit 2 rather than a
default. No checkout at all prints `skipped: not a git checkout` and
exits 0 — the one environment verdict, deliberate and separate from every
vacuity guard.

## Residue

"Where a config file key would serve" is the judgement clause and stays with
the agent. The program decides *is this a new setting*, not *would a key serve
better*; in practice the two coincide, since all 7 stock findings are values a
key would serve, but a genuine exception has no mechanical signature.

C3, module-level tunable constants, measures 524 findings on this tree and is
off by design: the ledger says naming an existing magic number is not new
configuration, so a gate would punish the refactor the repo wants.

A setting introduced in a shell script, a Dockerfile `ENV` or a `docker run -e`
is read as a WRITER and never judged as a setting; widening would need each
language's notion of "new". "Debug or dev-only" is decided by name, so a
dev-only switch named neutrally is reported.
