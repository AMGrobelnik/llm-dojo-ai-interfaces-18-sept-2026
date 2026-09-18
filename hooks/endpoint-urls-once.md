# A third-party endpoint host is declared in one module per environment

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The completeness critic found the Claude OAuth token endpoint declared at
two different hosts for one client id — a live divergence, not style — and
duplicate OpenRouter catalogue fetchers on both sides of the
`aii_lib`/`aii_server` line. One home per provider ends that class.

It never paid for itself as an agent rule: 189 recorded outcomes (123
apply, 66 fail), not one stored evidence line, and a
condition (`git diff --cached -U0 -- '*.py' | grep -q 'https://'`) that
fires on 2 of every 100 commits. A judged gate that asks a question twice
in a hundred commits is a program.

The mechanical guard that already exists — the pytest group
`research-monorepo/unit-tests/provider-endpoints-declared-once` — proves the same
invariant over a
hand-maintained list of 3 hosts, keyed on the full URL, scoped to four
first-party roots, with raw-text regex so a docstring counts. 89 tracked
`.py` files carrying an `https://` literal sit outside those roots. This
checker is wider on every axis and the closed host list disappears with it,
so that pytest group becomes a candidate for deletion rather than a reason
to keep this one hand-judged.

## Mechanism

Every non-test tracked `*.py` blob is read from the index in one
`git cat-file --batch`, filtered on the `https://` substring (58 of 743
files at the measured HEAD carry one), parsed with `ast`, and grouped
`host -> {module: [lines]}`. Two or more modules of one island declaring
the same host is a finding.

| failure mode | mechanism |
|---|---|
| second literal for a live host | AST string walk, host key |
| the second is a worked example | docstring Constants skipped |
| the two cannot import each other | islands from packaging data |
| `example.com` read as a provider | `ignore_hosts` |
| userinfo read as a host | `(?:[^/@\s"']*@)?` in URL_RE |

The docstring skip is not cosmetic: it removes exactly 2 of 7 duplicate
groups in the consumer (`github.com` and `x-access-token`, both
docstring-only). Comments never enter the AST at all.

Islands come from the repo's own `pyproject.toml`, never a path list. The
uv workspace members plus every `tool.uv.sources` path entry install into
one environment and form one island; any other directory carrying its own
`pyproject.toml` is its own island; each `.claude/skills/*` bundle is its
own island, because those scripts are meant to be copied out and run
alone. A host is duplicated only inside ONE island, so "import the
existing declaration" is always an available fix for a reported pair.

Scope is `relation`: the question "is this host declared elsewhere" cannot
be answered from the changed file, so the whole population is scanned
every run. PATH args narrow only the OUTPUT — groups that touch none of
the given paths are dropped — which is why the fragment keeps
`{staged_files}` rather than dropping them as a tree hook would.

Content comes from the index, so a concurrent editor's unstaged change
cannot move the verdict. A PATH argument absent from the index is read
from disk instead, for a file written but not yet staged.

**The shipped default does not exclude `.claude/skills/*`.** The exclusion
is a CONFIG knob (`exclude_globs`, also `--exclude-glob`) and it is left
empty: the two bundle groups below are duplicates WITHIN one skill's
`scripts/` directory, where a shared module travels with the bundle, so
they are fixable rather than structural — at the cost of trading one
convention for another, which is the owner's call to make when one of
those files is next touched. Setting the knob drops 7 of the 20 stock
findings and the coverage of 89 files with them.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD
`eaf82761cddc`: **20 findings in 5 host groups**, from a population of 743
non-test tracked `*.py` files. Whole-tree runtime **0.23 s** (median of
three: 0.23 / 0.26 / 0.22), hence the 1s budget.

`datasets-server.huggingface.co`, bundle `aii-hf-datasets`:

- `.claude/skills/aii-hf-datasets/scripts/aii_hf_download_datasets.py:114`
- `.claude/skills/aii-hf-datasets/scripts/aii_hf_preview_datasets.py:286`
- `.claude/skills/aii-hf-datasets/scripts/aii_hf_search_datasets.py:131`

`openrouter.ai`, bundle `aii-openrouter-llms`:

- `.claude/skills/aii-openrouter-llms/scripts/aii_or_call_llms.py:39`
- `.claude/skills/aii-openrouter-llms/scripts/aii_or_call_llms.py:60`
- `.claude/skills/aii-openrouter-llms/scripts/aii_or_get_llm_params.py:37`
- `.claude/skills/aii-openrouter-llms/scripts/aii_or_search_llms.py:37`

`claude.ai`, island `env:main`:

- `aii_lib/src/aii_lib/claude_oauth/autologin/_browser_login/_magic_link.py:50`
- `aii_lib/src/aii_lib/claude_oauth/autologin/oauth_flow.py:213`

`img.shields.io`, island `env:main`:

- `aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo/_gen_demo_art/gen_lean_demo.py:50`
- `aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo/utils/readme.py:162`
- `…/utils/readme.py:168`, `:185`, `:299`, `:311`, `:315`, `:366`

`cdn.jsdelivr.net`, island `env:main`:

- `aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo/utils/naming.py:72`
- `…/utils/naming.py:93`
- `scripts/debug/redeploy_finished_run.py:200`

With `--exclude-glob '.claude/skills/*'` the count is 13 findings in 3
groups — the `env:main` rows only.

**The stock does not block an unrelated commit, and that is measured, not
assumed.** Run from the consumer root with one clean staged path,
`check.py aii_lib/src/aii_lib/config.py` prints nothing and exits 0 while
all 20 findings are still in the tree; `check.py` with no arguments prints
all 20 and exits 1. Only a commit touching one of the eight files listed
above sees a finding — twelve files in all — and it then sees only its
own lines. That is why the
status is `active` rather than `debt`.

One group was transient and is worth recording. At HEAD `3f1060fa7499`
the checker also reported `registry-1.docker.io` and `auth.docker.io`
between `aii_pipeline/…/bundles.py` and `aii_pipeline/…/_bundles/_registry.py`
— an in-flight module split with the constants written twice. The split
finished and both groups are gone at `eaf82761cddc`. The checker saw a
real duplicate during the hours it existed.

## Fragility

| refactor | effect | guard |
|---|---|---|
| package roots move | population empties | floor of 20 (`AMG_HOOKS_MIN_ENDPOINT_POPULATION`) |
| URLs leave Python | nothing extracted | zero-literal guard |
| uv stanza restructured | islands collapse | over-reports, loud |
| `BASE + path` built URLs | only the base seen | by design |

The uv row is the one worth stating plainly: if the workspace stanza is
removed, `_main_environment_roots` returns an empty set, every path
collapses into `env:main`, and the check gets STRICTER. It fails loud
rather than silent, so it needs no guard of its own. Foreign
distributions still island out on their own `pyproject.toml`.

A variable-built URL is not a gap either. Only the base literal is seen,
which is exactly right — that base IS the single declaration, and the
per-call path suffixes are not endpoints to deduplicate.

## Residue

Two things the agent rule could judge and the program deliberately does
not.

The rule's own motivating defect — ONE PROVIDER reached at TWO DIFFERENT
hosts for the same client id — is invisible to a host-keyed check. It sees
two hosts, each with one home, and is right to. Detecting it needs a
provider-to-host map that no program can infer from the tree.

A genuinely new provider whose single literal should have gone straight
into a provider endpoints module is also not detectable: one declaration
is the invariant, so there is nothing to compare it against. The judged
version of this rule could ask "should this have been a module?"; the
program can only ask "is this the second one?".
