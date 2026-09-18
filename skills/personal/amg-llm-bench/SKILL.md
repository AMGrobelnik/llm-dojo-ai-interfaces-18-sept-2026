---
name: amg-llm-bench
description: "Benchmarks agentic LLMs for the research pipeline by aggregating published evidence — published list prices, agentic and domain benchmark boards, and same-source cost-per-task ratios — into one capability-per-cost ranking, an extended Pareto ladder, and the preset tier cuts. Use whenever a new model needs placing, a preset's subagent models need rechecking, a price change needs repricing the ladder, or someone asks which model to run a pipeline step on and at what cost. Carries the data files, the recompute script and the findings so far. Triggers: rank models, which model for this step, model tiers, subagent model, preset model cut, is this model worth it, OpenRouter price, cost per task, Terminal-Bench, SWE-bench, Pareto frontier, cheapest model that can do X, orchestrator model. NOT for: measuring this repo's own runs (read the run sinks), choosing an effort level for a Claude call alone, routing at runtime, or anything needing a live benchmark execution — everything here is aggregated from published numbers."
---

# amg-llm-bench — ranking agentic LLMs on price, cost per task and fit

We do not run benchmarks. We **aggregate published ones** — the
OpenRouter price catalogue, Arena's human preference boards,
Artificial Analysis's task sets, and per-run cost
figures — into conclusions nobody publishes: what a model costs *per
finished task* relative to its peers, how well it fits each kind of
research-pipeline work, and which models are worth their money at all.

Everything is reproducible from this directory:

```bash
.venv/bin/python .claude/skills/amg-llm-bench/scripts/rank_llms.py
```

It reads `data/models.yaml`, `data/task_groups.yaml`, the rest of
`data/` and every `data/boards/*.yaml` capture, prints the markdown to
stdout, and
writes `results/ranking.md`, `results/frontiers.html`,
`results/evidence.md` and `results/findings.md`. It reads no clock and
nothing outside `data/`, so two runs on the same data are byte
identical.

**Reading the output.** Every column is spelled out in words, and the
same words are used in all three files: **capability per cost** (the ranking
key, equal thirds of price, cost per task and raw capability), **raw capability
(0-100)**, **effective cost (x reference)**, **evidence coverage** (the
share of the group's benchmark weight this variant was measured on),
**measured boards** (how many of the group's boards that was, out of how
many) and **ability band** (the standard error the fit puts on the row).
A status column carries the caveats in words too — *on frontier*,
*off frontier*, *too thin for the frontier*,
*n of m boards measured*, *preference pillar missing*,
*capability pillar missing*,
*price-only, no cost-per-task data*,
*no cost-per-task data at this reasoning effort*,
*placed relative to …*, *free
listing exists* — with the legend printed above the first table.
**Every group table is ordered frontier first, then the rest by raw
capability**, and a *N least-measured models* fold at the
foot of each section lists the ranked rows with the least evidence
behind them, always including every row held off the frontier. A second
fold, *N models not scored in this group*, names the
variants that carry a board in the group and still cannot be read on
their own — too few boards, or only one pillar — with the boards they
do have and the bar they missed. They are named rather than
numbered, because the only way to give them a number is to take it from
somewhere they were never run.
On the charts **every frontier point is labelled**, and as many further
points as fit without a single overlap; a frontier label with
no clear seat beside its dot steps out to a ring further away and is
drawn joined to it by a leader line, which is what keeps an effort
ladder readable. **A ring around a dot is how much of the group that
point was never measured on**: it grows and darkens as the evidence
coverage falls, and a fully measured point has none. **Hovering any
point**, labelled or not, shows its card — variant, capability per cost,
raw capability, effective cost, evidence coverage, measured boards,
ability band, what its cost per task rests on, and status. The page carries a
**sticky contents list** that highlights the section being read, **every
table sorts** on a click of any column header, and under every chart a
**Benchmarks used** table names each board with its pillar, weight,
what it measures, its dated source, that source's style control on or
off, how much of the pool it covers and what would make it wrong. The page opens with
a **How to judge this** section, carries an **Evidence** block under
each group holding every board, its weight, its dated source link and
every raw score beside what it normalised to, and ends with a per-model
drilldown; `results/evidence.md` is the same evidence as text.

---

## 1. Scope — agentic models only

Every research pipeline step is a tool-using agent: it reads files, runs
commands, writes code, retries. A model earns a place only on evidence
from that kind of work — the Artificial Analysis coding, agentic and
terminal boards, Arena's agentic and coding categories, and the older
captures `data/models.yaml` keeps but no group now weights (§4):
Terminal-Bench, SWE-bench, KiloBench, LiveCodeBench. A chat-only score
does not qualify a model; inside a group it is one half of the answer,
never the whole of it.

**A candidate must be a text-out, tool-calling LLM.** Output modality
exactly `text` — not text alongside audio or images — and
`supported_parameters` containing `tools` in the OpenRouter catalogue.
The harness's only channel to the world is a tool call, so a model that
cannot make one cannot run a step whatever it scores.

**Every such model created in the last three years is a candidate.**
The catalogue filter is the whole of the entry rule: text-out,
tool-calling, `created` within three years of the run date. Nothing is
left out for looking too small, too old or too obscure — the last sweep
pulled 257 rows on that filter alone. What a model does *not* have is
board evidence, and that is the board's decision, not ours: a candidate
with no score on any board is recorded with `evidence: none`, appears
only in the **priced, no evidence** appendix as a count and a collapsed
table, and never enters a ranking table, a frontier or a chart. It
costs one line to carry, and the next sweep that finds it on a board
promotes it without re-litigating whether it should have been listed.
Pre-filtering the pool by reputation is how a cheap model that quietly
became good stays invisible for a year.

**Reject a model, with the reason written down, when:**

- its output modality is not text alone, or its endpoint does not
  support tools: music and image generators (Lyria, the Gemini and GPT
  image models), audio models (`gpt-audio`), translation models, safety
  classifiers and code-apply models are all out **even when OpenRouter
  files them under text**;
- it is vision-first or chat-first and publishes no agentic board;
- its headline price is a teaser — a sub-32k-prompt tier, a launch
  discount, a single-provider promotion. An agentic subagent lives above
  32k almost immediately, so the teaser price is never the price paid;
- its tool-call error rate or structured-output retry rate is high.
  A harness absorbs a wrong answer; it does not absorb a malformed tool
  call on one call in eleven;
- its board evidence cannot be re-checked at all. Vendor-published
  numbers are *not* a rejection on their own — several rows are carried
  on a lab's own announcement — but a score whose source page cannot be
  recovered is labelled `(unverified)` in the source list, kept undated,
  and reads as the weakest evidence on the page rather than quietly as
  a measurement;
- it is strictly dominated — worse on the boards *and* dearer than a
  model already on the ladder;
- it exists only as a `:free` listing, with no paid listing anywhere to
  price it (§2).

Rejections stay in `data/models.yaml` with `rejected:` prose and their
sources. A rejection that is not written down gets re-litigated monthly.

---

## 2. Price — list price, discounts ignored

Prices come from the OpenRouter models API, the catalogue `pricing`
field, converted to $/M tokens. The same capture records what each
endpoint can do — `context_window`, `max_output_tokens` and
`tool_calling`, from `context_length`, `top_provider`'s completion
ceiling and whether `supported_parameters` lists tools — because the
cheapest model on the page is worth nothing if it cannot hold the
step's prompt (§6). **Use the list price and ignore
temporary discounts.** A launch promotion or a single cheap endpoint
lapses; the ladder should not reshuffle when it does. Where a cheaper
route exists it is recorded as `discount_route` next to the list price,
so the saving is visible without being scored.

**A `:free` listing is not a price.** It is a shared, rate-limited,
temporary pool that throttles, queues and lapses, and nothing is priced
at zero anywhere in capability per cost. Every model in the paid ranking and
on every frontier is priced at its **paid list price** — the same
model's non-free listing, from the OpenRouter models API or already in
`models.yaml`, recorded as `free_of:` on the free row. A model with no
paid listing anywhere is excluded from the paid ranking and marked
**free-only, no list price**.

The free pool keeps its own table only because the free backend needs an
ordering of `:free` listings. That table is **ranked by raw capability alone**,
carries evidence coverage, has no cost chart, and states that free
availability is unreliable. Free rows never enter a paid table or a frontier.

**A slug inherits its paid row's scores.** `free_of:` names the paid
listing of the same weights, and the free row takes that row's boards,
fit, coverage and band straight across rather than being fitted on its
own — a pool of five slugs shares too few boards to fit anything. What
it does not inherit is the endpoint: the free lane's own context
window, response ceiling and tool-calling flag stay on the free row,
because those are what a task group's floors are checked against and
they routinely differ from the paid endpoint's. A free-only slug with
no `free_of:` inherits nothing and reads as no evidence.

The cost axis needs one number per model, so:

```
blended $/M = (input + w x output) / (1 + w)
```

**`w` is measured per task group, and every group says so.** A group
is a set of pipeline steps, and `data/pipeline_steps.yaml` now records
an output-token median beside the input-token median for each of them,
so the weight a group blends on is that group's own output-to-input
ratio over its own steps — not a guess, and not one number for the
whole catalogue. Those ratios are **well under one**: agentic traffic
reads far more than it writes once the prompt, the tools and the cache
reads are counted, which is the opposite of the assumption this file
used to carry.

A group with no measured steps falls back to the pool-wide
`price_blend:` in `data/task_groups.yaml`, which is **one number to
change**, with a `basis:` beside it saying where it came from. The
per-group weights sit under `by_group:` with their own
`by_group_basis:`, and the pages print `measured` or `assumed` per
group accordingly. The script hard-codes nothing: change a weight and
every price, every relative price and every effective cost that group
ranks on move with it.

---

## 3. Cost per task — same-source ratios only

List price is not cost. A model that thinks twice as long, retries, or
burns tool calls costs more per finished task than its rate card says,
and a terse one costs less. The public evidence for that is always
*within* one run: a leaderboard that publishes $/task, a harness report
that priced two models on the same suite.

**The rule for `data/cost_ratios.yaml`: a row may only relate two models
measured on the same tasks in the same published run.** Nothing in the
data file crosses sources. Each row is `model_a`, `model_b`, `ratio`
(cost_a / cost_b as published), `benchmark`, `source`, `date`.

Chaining across sources is the script's job, not the data's.
`solve_relative_cost` turns every row into `log cost_a − log cost_b =
log ratio`, pins the reference model at zero, and relaxes the
over-determined system to its least-squares solution. Where two runs
disagree about the same pair, the fit splits the difference rather than
letting whichever chain was walked first win — that is the whole reason
for solving the graph instead of multiplying ratios along a path.

**A model no ratio reaches has no cost per task.** It used to be given
one — its list price times its provider's median cost-to-price ratio —
and that is a claim about how long that model thinks, made up from
other models. The ranking no longer makes it. The row says *price-only,
no cost-per-task data*, its capability per cost is the two thirds it
has rather than three with one invented (§5), and its effective cost on
the chart is its list price alone. A variant at a reasoning effort
nobody published a multiplier for is the same case for the same reason
— the default effort's cost is not that effort's cost — and says *no
cost-per-task data at this reasoning effort*.

---

## 4. Raw capability — one score per task group

One capability number for all work is wrong: writing a paper section
and debugging a training script fail differently. Steps are grouped in
`data/task_groups.yaml`, and each group scores models on **two
pillars of evidence, an equal half each**:

| pillar | source | what it is |
|---|---|---|
| preference | Arena | blind human A/B, live |
| capability | Artificial Analysis | scored task sets |

```
raw capability = mean of the pillars this variant has a board in
```

Each pillar lists the boards that answer its question **for that
group** — Arena's coding and WebDev boards in coding-experiments, its
creative-writing and long-query boards in scientific-writing — and the
boards inside a pillar split its half equally unless the group hands
one of them a weight. So the mix is argued once, per group, in the
language of *what evidence answers this*, and never in the language of
*how many boards happen to exist*.

**One group reads everything.** `general` scores the planning steps —
`gen_strat` and the `gen_plan.*` briefs — and its two pillars are the
union of the other groups': every Arena board on the preference side,
every Artificial Analysis board on the capability side, equal halves
and equal weight inside each half. A plan is written against every
kind of work the round will then do, so nothing in this file justifies
scoring it on a narrower slice than all of them.

**Two pillars because each is blind to what the other sees.** A
preference-only ranking rewards the model that writes longer,
friendlier answers and cannot see a wrong one: the votes are cast on
the answer as it reads, not on whether it is right. A capability-only
ranking rewards the model that memorised the test set and cannot see
prose quality at all: the scoring key never changes its mind, which is
its virtue and its blindness. Neither is allowed to be the ranking.
Where the two disagree that is a finding about the model, and each
group table prints both columns beside the blended raw capability so a
reader can see the disagreement rather than a number that hid it.

**There is no spend pillar.** There was one — OpenRouter's 30-day
routed dollars — and it is gone: one marketplace's routed traffic is
not the market, it is published per model with no reasoning effort
attached, and a model absent from the published window looked
unmeasured in a way nothing could resolve. Money now enters the page
only where it can be checked, as the list price a lab publishes per
token (§2). Nothing under `data/boards/` is read for spend any more,
and no group weights an `or_*` board.

**Nothing else is weighted.** SWE-bench, LiveBench, KiloBench, SEAL,
Vellum, TokenMix and VulcanBench are still in `data/models.yaml` — they
are evidence, and the catalogue keeps evidence — but no group
references them, because a board nobody can re-pull on a schedule goes
stale in place and there is no honest way to date it. The two
sources above are captured by `scripts/capture_arena.py` and
`scripts/capture_aa.py` into
`data/boards/*.yaml`, each file carrying its own `source:` block —
title, url, captured date, method, style control — which is what every
evidence table and every page cites. A board cell in a board file
**overrides** the same cell in `data/models.yaml`; cells no board file
carries stay as the catalogue has them.

**A pillar is scored as its own fit, and the two are averaged.** One
flat weighted fit over all the cells lets whichever pillar has the most
cells dominate whatever the declared weights say — a row sitting on
four Arena columns and one Artificial Analysis row would be scored
mostly on Arena however the halves are declared, because a weight only
binds where the cell exists. So each pillar is fitted separately over
its own boards (the least-squares fit below), and the row's raw
capability is the **mean of the pillar scores it has**. A half is a
half whether it is two boards or seven.

**A pillar with no board measured is absent, never averaged in.** The
row's status gains *capability pillar missing*, and the mean is taken
over the pillar that answered. The column prints `-` where nothing can
supply it; on a placed row the anchor's reading for that pillar stands
in (below), and the status still names the pillar as missing for the
row itself. One measured board
is enough to answer a pillar — a board is evidence however light it is
— but a variant that answers fewer than `MIN_MEASURED_PILLARS` (two,
which is both of them) is not ranked on its own boards, because a
single pillar is one source's opinion and this ranking is the
disagreement between two. Such a row can still appear, placed against a
sibling effort of the same model (below), and it is named under the
group either way.

**A board may say it describes the model rather than the effort.** A
board file marks it `per_effort: false`, and then its one cell reaches
every effort variant of that model. Such a board is **not** a board
measured at one reasoning effort, so it cannot buy a thin row the
`MIN_MEASURED_BOARDS` it needs, and two siblings both carrying it have
not thereby shared a board. No board in the current captures is marked
that way; the rule stays because the next one might be.

**A cell tagged with an effort the catalogue does not declare is
dropped.** A board file may key a cell `<id>@<effort>` — Arena carries
`deepseek/deepseek-v4-pro@high` — and the effort is honoured only when
`data/models.yaml` declares that effort for that model: a
`default_effort:`, a key under `scores_by_effort:`, an `efforts:` list,
or an effort a published cost ratio names (an `alias_of:` pair shares
one set). Otherwise the cell would invent a whole ranked variant out of
one board and one tag nobody else recognises. Dropped cells are counted
and listed by name in `results/findings.md`, so the fix — declare the
effort, or fix the capture — is one line away rather than invisible.
`efforts:` is for exactly that: a level the provider sells that nothing
in this file has scored yet.

**Every board is put on 0–100 by its own median and inter-quartile
range over every plotted variant that carries it, before anything is
weighted.** An Arena Elo of 1486 and a Terminal-Bench 31.2 cannot be
averaged raw, so a board has to be rescaled before it can be weighted;
the question is what sets the ends. Min-max, which this used to do, put
*every* board's ends at 0 and 100 whatever the board did — which says
every board discriminates equally before a single weight is applied. A
near-flat board (AA-LCR runs 0.803 to 0.887 over this pool, GPQA 86.6 to
96.1) was stretched across the whole scale, so noise on it counted for
as much as a real 40-point spread on Terminal-Bench, and one runaway
capture could set an end of a board's scale on its own.

So the **middle half of the plotted variants sets the unit**: the median
lands on 50, one inter-quartile range is worth `50 / ROBUST_CLIP` points,
and the scale is clipped at `±ROBUST_CLIP` IQR (`ROBUST_CLIP` is 3 in
`scripts/rank_llms.py`). A board whose pool is near-flat has its ends
about one IQR from its median and so spans roughly 33–67, contributing
proportionally less than a board whose ends are three IQR out and use
the whole 0–100. Median and clip are both robust: one extreme reading
moves neither. Where the middle half is a single value the IQR is 0 and
half the full range stands in for it; where that is 0 too — every
variant on the same number — everyone lands on 50, because the board
separates nobody. How much a board *should* count beyond that is a
weight, where it can be argued with.

**Arena style control.** Arena's default adjustment regresses length
and markdown out of the Elo. Whether a captured board had it on is in
the board file's `source:` block and on every board's row in the
*Benchmarks used* table, never assumed here: a board captured with
style control off still has length and formatting inside it, so a
verbose model is flattered there, and the page says which boards those
are on the run that captured them.


### No one harness, and no one board, decides a group

Equal halves already stop a source from buying influence by publishing
more boards, and a pillar splits its half over its own members. What
is left to go wrong is *inside* a pillar: four Arena category boards
that move together are one opinion poll counted four times. Three
bounds, declared under `weight_guards:` in `data/task_groups.yaml` and
checked against every resolved weight map, stop a run rather than
publish one that breaks them:

- **`max_family_share`** (0.50) — no *evaluation family* may hold more
  than this share of a group. A family is the harness a board comes
  from, listed under `eval_families:`: every Terminal-Bench variant and
  capture is one family, every Arena category board is one family,
  every Artificial Analysis index is one. This is not a pillar, which
  is about which of the two questions a board answers; this is about
  who ran it, and one lab's harness can appear in more than one pillar.
  Every Arena board is one family, so the preference pillar *is* a
  family carrying exactly half: the bound can be no tighter than 0.50,
  and what it catches is a family that reaches past its own pillar —
  which is what Terminal-Bench did at 0.710 of coding-experiments,
  under three names, from inside capability.
- **`max_board_weight`** (0.34) — no single board may carry more than
  this share of a group, whatever family it is in. About a third: past
  that, one column is not evidence among others either. With two
  pillars at halves it also means no pillar may come down to a single
  board — two a side is the floor, and a group that drops below it
  stops the run instead of publishing a coin flip.
- **`coverage_leverage`** (3.0) — a board's weight may not exceed this
  multiple of the share of ranked variants that actually carry it. A
  board measured on a twentieth of the pool cannot be a fifth of the
  answer; weight has to follow evidence, not the other way round.

The guards are skipped entirely where a file declares no
`weight_guards:` block, so a fixture can stay a fixture.

**No board may sit in two pillars.** A board answers one of the two
questions, and a board in both would be one measurement holding the
whole group. The loader stops the run on it by name. The duplicate check of
§5 goes after the subtler version — two *different* boards inside one
pillar that turn out to be the same column under two names — on every
run, over the pillar columns themselves.

**A step is scored on its group's weights and no others.** A step used
to be able to re-split its group, which meant a weight map no
group-level guard ever saw. Two equal pillars leave nothing to
re-split, so a step is scored by its group, full stop.

Every step gets a row in **Best pick per pipeline step** in
`results/ranking.md`: its own frontier, and the best raw capability
inside each of three bands of effective cost. Three picks rather than
one, because the frontier spans two orders of magnitude of cost and the
cheapest frontier row and the best one are rarely the same buy.

**A band the frontier never reaches still names a model.** Where no
frontier row falls in a band, the pick is the best scored row in that
band and the cell is marked `+`, with the legend saying what the mark
means. Printing `none` there answered a question nobody asked: a reader
in that budget is not told to buy nothing, they are told what the best
thing they can afford is and that it is off the line.

**One board should not be holding a shortlist up.** Every run refits
each group with each heavily-weighted board removed in turn and prints,
under *What one board is holding up* in `results/findings.md`, the
largest move in the top ten and how much the top five changed. It is
reported rather than asserted, because a group where one board matters
is not wrong — it is a group with little other evidence, and a reader
picking from it should know which board they are trusting.

**The evidence is sparse, and the comparison is built for that.**
Every variant sits on a different handful of boards, and which boards
two variants share differs per pair. Averaging each row over the boards
it happens to hold compares a model measured on the hard boards against
one measured on the easy ones and calls the second better. The two
earlier answers were both worse than the problem: a guard that hollowed
out and barred any row under two boards, which threw away exactly the
newest models a reader opens the page for; and shrinkage toward a
provider prior, which is a number taken from other models and handed to
this one, and which in practice let one-board rows from frontier labs
top whole groups on their lab's record.

**Per group and per pillar, one weighted least-squares fit over the
cells that exist.** Every board is put on 0–100 by its median and IQR
first, then the fit
reads every score in the pillar at once as two numbers added together: a
**board level**, how hard or how generous that board is, and an
**ability**, what is left of the row once the board is accounted for.
Each cell is weighted by its board's weight in the group, and only
cells that exist are in the system — no board a variant was never run
on appears anywhere in it. The mean of a row's pillar abilities is the
**raw capability** printed on the page, and each pillar ability is
printed beside it in its own column. Two variants that share boards are compared
through those boards; two that share none are compared through the
chain of variants that connects them, which is exactly the overlap the
data has and nothing more.

`numpy.linalg.lstsq` returns the minimum-norm solution, so the one free
constant per connected piece of the variant–board graph does not blow
the fit up; each piece is then shifted so its board levels sit where
those boards' own measured means sit, which puts the pieces on one
scale without inventing a cell. Where the fit runs past either end of
0–100 the whole group is squeezed back in by one affine map, which
keeps every distance and every ordering rather than flattening the top
rows into a tie the way a clip would. A **Bradley–Terry** pairwise
model would answer the same question, but it recasts each pair as a win
and loses the size of the gap, and the sizes are the finding here.

**Reasoning efforts of one model are placed against each other, not
against the group.** The fit has a level per board and an ability per
row and no term for the two together, so a weakness a whole model family
shares on the boards only one of its efforts was run on is charged to
that effort alone. The shape is everywhere in the captures: in
coding-experiments GPT-6 Astra sits on 9 of the group's 10 boards at
max and on 3 to 5 at its other efforts, and those thinner rows are
Artificial Analysis rows only — one pillar, no Arena column — so the
group's own fit has nothing to read them against. Placed against max
on the boards they share, they are readable; left to the global fit
they would either be dropped or scored on which boards their lab
happened to enter them in.

So within a family — the variants of one catalogue id, which differ only
in reasoning effort — the **variant measured on the most of the group's
boards is the anchor** and keeps the ability the global fit gave it
(ties go to the one whose boards carry more of the group's weight, then
to the variant key). Every other sibling is placed at **anchor ability +
the weighted mean of (sibling − anchor) on the boards both were measured
on**, in the boards' own scaled units and with the group's board
weights, before the group's 0–100 squeeze. It is direction-free: a
sibling that beats its anchor on their shared boards lands above it, by
what it beat it by. The band is the anchor's band and the standard error
of those shared-board gaps, combined.

**A gap moves the pillar it was measured in, and nothing else.** The
placement is done **per pillar**: the shared boards are split by the
pillar they belong to, each pillar's gap is read off its own shared
boards and shrunk on its own agreement, and the sibling's ability in
that pillar is the anchor's plus that gap. A pillar the two share no
board in keeps the **anchor's** value for that pillar — it is the best
reading available and it is not moved by evidence from the other one —
and the row's raw capability is, as for every other row, the mean of
its pillar abilities. So a row measured against its anchor on two Arena
agent boards alone moves the preference half by what those boards say
and the capability half not at all, which halves that gap's reach into
the printed score. Before this, one pillar's gap was added to the whole
ability: DeepSeek V4 Pro (0813) at high, on the two Arena agent boards
and nothing else, carried its ~10-point agent-board lead over the
default effort into every column and came out top of the coding
frontier on it. Such a row's status names the pillars it was read in —
*placed relative to GPT-6 Astra (max) on 5 shared boards in the
capability pillar*.

`MIN_SIBLING_SHARED` is **1**, because what is being read is a distance,
not an ability, and a distance needs one board at both ends — the row is
not being scored on that board, it is being put at a measured remove
from a row the global fit pinned down on everything *it* was run on. One
shared board is a thin reading of the distance, and the band says so: a
single gap has no spread of its own, so the standard error falls back to
the anchor's own residual scatter — how far that model's boards disagree
about it — widened by √2, since a one-board gap carries the noise of
both rows' readings on that board. A sibling sharing **no** board is
left exactly where the group found it, and its status says *no board
shared with …*.

**A gap is charged for how well the boards behind it agree.** Read off
one board a distance is that board's noise as much as it is a distance,
and on a board this pool is near-flat on, noise is most of what there
is: a rounding difference is worth a whole inter-quartile range up the
scale. That is how, on the previous run, a medium-effort row arrived at
the top of coding-experiments on a single shared board nobody would
have bet on. So each measured gap is read as a true gap plus reading
error, with the true gaps spread by `tau` — the root-mean-square of the
placements that stand on more than one board, the ones with a scatter
of their own to read — and kept at

```
gap x tau^2 / (tau^2 + error^2)
```

which is 1.0 where the shared boards agree tightly, a half where the
noise is the size of a typical real gap, and near zero where it swamps
it. **It is not a clamp**: nothing is bounded, no direction is flipped,
a well-measured placement moves exactly as far as it did before, and a
model family whose efforts really do differ widens `tau` and so keeps
more of its gaps. Where the kept share drops below 95% the status says
so — *placed relative to … on 1 shared board, at 38% of the measured
gap* — and the **band is left un-shrunk**, at the full reading error,
because the one thing a reader must not be sold is a thin placement
wearing a confident band.

This also overrides `MIN_MEASURED_BOARDS` for siblings. A variant on one
or two boards of its own cannot be told from one lucky reading and is
unranked — but measured against a well-covered effort of the same model
it can be, so it is placed and ranked, and that is the only number it
gets. A variant on no board of the group, or on boards its anchor lacks,
stays unranked and is named in the *not scored in this group* list,
with the bar it missed.

**A placed row inherits nothing.** Its score is a measured distance
from its anchor and that is worth printing, but the frontier is the one
line a reader traces, and a row holds it on **its own** evidence or not
at all (below). A placed sibling on one shared board is drawn hollow
and cannot hold the line; a placed sibling that was itself measured on
enough of the group clears the bars on its own and is drawn solid, its
anchor's eligibility neither helping nor hurting it.

The fit has a check it must pass, printed in `results/findings.md` and
asserted in the tests: for every pair of scored variants sharing at
least `MIN_MEASURED_BOARDS` boards, the sign of the gap between their
abilities should match the sign of their mean difference on the boards
they actually share. A fit that reorders pairs against their own
overlap is not reading the overlap. The count is the headline; **every
pair that came out the other way is named**, with how many boards it
shares, the fitted gap and the shared-board gap, under *Where the fit
disagrees with the overlap* in `results/evidence.md`, because a
percentage says the method holds without saying where it did not.

**Below `MIN_MEASURED_BOARDS` a variant is named, not scored — unless
a sibling effort places it.** Three measured boards in a group is the
floor for reading an ability off a row's *own* boards, a constant in
`scripts/rank_llms.py`. Under it the row is left out of that group's
fit and, where no effort of the same model shares a board with it,
out of the chart and table too, listed by name with the boards it does
have in a *models not scored in this group* fold under the
group. Where such a sibling exists the row is placed against it
instead (§ sibling placement above), which reads a distance rather
than an ability and needs one board at both ends. The same fold holds
the rows that clear the board floor and answer only one pillar
(`MIN_MEASURED_PILLARS`), for the same reason and with the reason
printed beside them. What stays banned is a number taken from another
effort *as if it were this row's*, from another model, or from a
pool-wide ratio.

**Uncertainty is coverage, not a fabricated value.** Every row prints
**measured boards** (how many of the group's boards it sits on, out of
how many), **evidence coverage** (the share of the group's benchmark
weight those boards carry) and an **ability band** (the standard error
the fit puts on that row, from its own residuals). On the chart the
ring around a dot is the share of the group the point was never
measured on: it grows and darkens as coverage falls, and a fully
measured point has none.

**Read a sparse row as optimistic.** Which boards a lab publishes is
not a coin toss — a model is entered where it does well — and across
this catalogue a row's coverage and its score rise together. The fit
cannot correct for that, because the missing cells are missing. It is
left visible instead, which is what the band and the ring are for.

**A scored row may still not anchor the frontier.** Three boards are
enough to be ranked and not enough to hold the one line a reader traces
at face value: a cheap listing measured on a tenth of a group would
otherwise arrive at the cheap corner and hold it. Two bars, both under
`shrinkage:` in `data/task_groups.yaml`, have to be cleared:

- **`frontier_min_weight`** (0.5) — at least this share of the group's
  benchmark weight must be measured on the row. It is a share, so it
  has to be between 0 and 1 and the script exits if it is not. Zero
  clears every scored row.
- **`frontier_min_boards`** (2) — the row must sit on at least this
  many of the group's boards. A positive whole number, or the script
  exits. Weight alone can be cleared by one heavy column, and one
  column is one reading of one thing.

**Both bars are read per row, per reasoning effort, off that row's own
measured boards, and nothing is inherited.** An anchor effort can be
eligible while a sibling placed on one shared board is barred, and a
placed sibling that carries two boards and half the group's weight
itself is eligible whatever its anchor does. A row's status names the
bar it missed — *too thin for the frontier: 1 board of its own, under
2 and 8% of the group's weight, under 50%*.

A barred row is **still scored, ranked, plotted and labelled** — it is
only kept from defining the line. It says *too thin for the frontier*
in its status, is drawn as a hollow dashed dot with its own legend
entry, and is named in that section's *least-measured models* fold,
which widens when it has to so that every barred row appears there.

**The fit is per variant (§7).** A reasoning effort is scored on the
board rows published for that effort and on no others. Nothing is
carried across the ladder.

---

## 5. Capability per cost — equal thirds

The ranking key is one number per model per group: the **mean of three
components, each min-max scaled to 0–1 over the models present**, higher
being better.

1. **list-price cheapness** — `1 − minmax(log blended price)`
2. **cost-per-task cheapness** — `1 − minmax(log relative cost/task)`,
   the cost per task being solved where a same-source ratio reaches the
   model (§3); where none does, the model has no cost per task and this
   third is dropped, the mean renormalising over the two that remain
3. **raw capability** — the group score from §4

Cheap on the rate card, cheap per finished task, and good at the job, in
equal thirds. **The name is a name, not a division**: capability per
cost is the mean of those three thirds, never capability divided by
cost. Scaling happens in log space for the two cost components
because price spans three orders of magnitude and a linear scale would
flatten every model below a dollar into one indistinguishable clump.

**No two weighted terms may be one measurement.** `aa_hle` and
`aa_gpqa_diamond` were Artificial Analysis's own captures of Humanity's
Last Exam and GPQA Diamond, which the group already carried under their
better-sourced keys, so a model carrying both had one board counted
twice. The check is a **correlation** rather than an equality: any two
boards inside one pillar of one group that share at least
`DUPLICATE_MIN_SHARED` variants and correlate above `DUPLICATE_R` fail
the run, and so do two whole pillar columns that turn out to be the same
ranking. Equality only ever caught a copied capture; the expensive case
was four different Arena boards, none identical, ranking the catalogue
the same way. Terminal-Bench 4.0 and 2.1 are not that case: they are
different task sets, they correlate well below the line, and a model can
sit high on one and low on the other.

Within the capability pillar, Artificial Analysis's **Intelligence and
Coding indexes are carried beside their own components**. The index is
one board among several rather than a wrapper around the rest, and the
duplicate check above is what stops a component from being weighted
twice; a model scored on the index alone still gets a capability score,
prorated by the boards it has, because coverage never renormalises
inside a pillar — partial membership earns partial credit.

**Every weight lives in one place: `data/task_groups.yaml`.** The
capability-per-cost thirds are `calibrated_intelligence_weights:`; the
board weights are each group's `pillars:` map, where a pillar's members
split its half equally unless one is given a number. The script
hard-codes none of them, so retuning the ranking is a YAML edit and a
rerun — and `data/boards/*.yaml` hold the measurements, which are a
capture's output and never hand-edited.

The charts keep the older two-axis view, which is easier to read than a
single score: **x is effective cost on a log scale — the geometric mean
of relative price and relative cost per task, a 50/50 blend in log
space — and y is raw capability.** The Pareto frontier is drawn through the
points nothing beats on both at once, and each point carries its
capability per cost in the label and tooltip.

**A point is a model at one reasoning effort** (§7), named
`Model (effort)` everywhere — label, hover, table row, ranking line and
preset cut. Every scale, the fit, the frontier and calibrated
intelligence are computed over those variants, because `Fable 5.1 (low)`
and `Fable 5.1 (max)` are two different buys, not one model with an
asterisk.

Every plotted variant sets the ends of the fit component's scale, the
same rule as §4. Rejected rows and `:free` listings are out of
every capability per cost, ladder and frontier; they keep their own sections,
the free pool ordered by fit inside itself so the ordering survives
being far below the paid models.

---

## 6. Cutting presets from the ladder

The models sort into one **extended ladder**, r1 upward, by ascending
capability-per-dollar rather than by price alone; the Pareto frontier is
the ladder's spine. Presets are cuts from that one ladder, never
separate lists.

Each preset carries **three difficulty levels**, matched to the measured
step difficulty in `data/pipeline_steps.yaml`:

| level | steps | model |
|---|---|---|
| 3 hardest | execute.*, gen_hypo | the preset's own cut |
| 2 moderate | reviews, papers, viz | the preset below |
| 1 easiest | gen_strat, plans, upd | two presets below |

So Max level 2 runs the Pro model and Max level 1 runs the Lite model.
**Lite clamps to itself** — it has nothing below it — and the levels
overlap across presets on purpose: a rung is the hard tier of one preset
and the easy tier of another, which is what keeps the ladder single.

**The orchestrator sits above the hard tier.** It holds the plan, and a
weak planner wastes the strong workers underneath it, so it should be a
stronger and dearer model than that preset's level 3 — unless nothing
affordable exists above it, in which case it matches level 3 and the
choice is recorded.

**Descend strictly.** Never place a level-2 model above its level-3
model on the ladder; if that happens the ladder is wrong, not the cut.

**The ladder is per task group and per backend, and it is generated.**
`results/cuts.yaml` holds every cut the runtime would need: preset,
agent backend, task group, then the orchestrator and the three subagent
tiers with the model id and the reasoning effort to dial. Nothing in it
is chosen by hand and nothing in it is invented — an effort appears
only because a row scored at that effort, and an id appears only if
that backend can route it. `terminal_claude_agent` takes the native
Claude ids its roster ships, at the efforts that roster names, and
Haiku takes no effort at all; `sdk_openhands_agent` takes any
`vendor/model` OpenRouter id; `sdk_openhands_free` takes only the
`:free` slugs the free router's pool declares, and every role there
carries two fallbacks because the pool exhausts.

**A rung has to be able to do the work.** Each group declares
`requirements:` in `data/task_groups.yaml` — a minimum context window,
a minimum response ceiling and whether tool calling is needed —
derived from the token medians of that group's own steps. A model
below a group's floor stays in that group's ranking table, flagged
with the field it fails, and is kept off the frontier and out of every
cut: a cheap model that cannot hold the prompt is not a cheap model.
Unknown is not a failure; only a published number below the floor is.

**A ladder shorter than the presets is left short.** Where a backend
and group have fewer rungs than the four presets plus an orchestrator
need, the top presets clamp onto the top rung and the clamp is
recorded. Padding the ladder by repeating a rung would hand two tiers
the same model while claiming they differ.

---

## 7. Effort levels are frontier points

Models take `effort` (low / medium / high / xhigh / max; `high` is the
API default; **haiku-4.5 rejects the parameter with a 400**). The
multipliers are large enough to move a model a whole rung, so running
one at low effort is a different cost/ability trade-off from running it
at max — a different point on the frontier, not a footnote on one
point. **Each (model, effort) is its own candidate.**

**A variant exists where a source actually split the model.** The
efforts are the union of

- every effort with a board row of its own, in `scores_by_effort:` in
  `data/models.yaml`, and
- every effort with a published cost multiplier, in `effort_ratios:` in
  `data/cost_ratios.yaml`,
- plus the model's own `default_effort:`.

A model no source splits keeps one point, labelled with the effort the
source ran it at where `default_effort:` says so and `(default)` where
nothing does.

**The untagged rows belong to `default_effort`.** That is the rule the
whole expansion rests on: `scores:` is whatever the board published
without an effort tag, and a ladder's row at the model's own
`default_effort` is supposed to restate that untagged number. **The
script checks it.** Where a default-effort ladder row and the untagged
row disagree by more than a couple of percent, the run warns, names the
board and both numbers, and the clash is listed in
`results/findings.md` — because the two captures are then not of the
same thing, and averaging them is how that gets buried. The fix is a
re-capture or a corrected `default_effort:`, never an average. So the
default-effort variant is the untagged rows merged with its own tagged
rows (the tagged row wins, being the more specific measurement), and
**every other variant starts with only what was measured at that
effort**.

**The gaps stay gaps.** A low-effort variant used to inherit the
untagged row verbatim for every board nobody ran at low, which put the
model's *default-effort ability* on the *low-effort price* — the
cheapest way there is to invent a frontier point, and it is how Claude
Opus 5 (low) sat on the coding frontier with Opus 5's own scores. A
later version moved the missing board by a ratio between efforts
instead, which is the same borrowing with an adjustment on top. Neither
survives: a board nobody ran at that effort is simply **not a cell for
that variant**, and the fit of §4 never sees it. A variant left under
`MIN_MEASURED_BOARDS` boards in a group, and sharing no board with a
better-measured effort of the same model, is named in that group's
too-few-boards fold and scored nowhere. One that does share a board is
placed at a measured distance from that effort, which is a reading of
the overlap and not a number copied across it.

**Effort moves cost and only cost.** The list-price third is the same
for every variant of a model — the rate card does not change with how
hard the model thinks — while the cost-per-task third and, through it,
the effective cost are multiplied by the variant's effort multiplier.
The multipliers are fitted by the same least-squares solve as the
cross-model ratios, on one model's own ladder with its `default_effort`
pinned at 1.0; a ladder that does not touch the default effort is
dropped with a warning rather than guessed at.

**Where nobody published a multiplier, effort has no cost per task.**
Holding such a variant at what its model's default effort costs would
be an invented number, and almost certainly too cheap at the top of a
ladder — a model run at max burns more tokens than the same model run
at low. So the cost-per-task third is dropped for that row, the mean
renormalising over the thirds that remain, and the status says *no
cost-per-task data at this reasoning effort*. The run warns with the
list of models and `results/findings.md` counts both kinds. Those rows
are placed on the x axis by list price alone, which is a floor. Since
effective cost is a geometric mean, a quarter of the cost per task
moves a point half way along the x axis, not all the way.

Effort does not buy quality monotonically. One harness has Opus 5
solving *fewer* tasks at xhigh than at high while costing more, and the
frontiers below show several models whose cheap effort dominates their
dear one outright. Raise effort only when a cheaper level has actually
under-delivered — and read the frontier, which now answers that
question directly.

---

## 8. How to update

0. **Re-capture the two boards**, each script writing its own file
   and nothing else:

   ```bash
   .venv/bin/python .../scripts/capture_arena.py        # data/boards/arena.yaml
   .venv/bin/python .../scripts/capture_aa.py           # data/boards/aa.yaml
   ```

   Keys live in `~/.config/aii/llm_bench.env` and are never printed,
   logged or committed. Each script takes `--dry-run`, writes sorted
   deterministic YAML so a re-capture diffs cleanly, and exits non-zero
   rather than writing half a file. A capture **replaces its file's
   board columns wholesale** — the pull is the whole board, so a value
   it does not repeat is stale, not missing — and stamps the `source:`
   block the pages cite. Read each file's `unmatched:` list: a source
   row that matched no catalogue id is either a model missing from
   `data/models.yaml` or an alias the capture needs taught.
1. **Re-pull the catalogue with the date filter, then the prices.**
   Take every OpenRouter row whose output modality is exactly `text`,
   whose `supported_parameters` contains `tools`, and whose `created`
   is inside three years of today — that list *is* the candidate pool
   (§1), so do not trim it by reputation. Diff it against
   `data/models.yaml`: new ids get an entry, ids that fell out of the
   window get dropped with a line saying why. Then refresh every
   `list_price` from the same pull. List price, not the discounted
   endpoint; record a lapsing cheaper route as `discount_route`. Price
   a `:free` row from its paid sibling (`free_of:`) — never at zero —
   and mark it free-only when no paid listing exists.
2. **Add the new models** to `data/models.yaml`: OpenRouter id, prices,
   context, `created`, an `agentic:` flag, scores as `{value, src}`
   against a key in the `sources:` map, a `default_effort:` naming the
   effort the untagged rows were captured at, any effort-tagged rows
   under `scores_by_effort:` (only where the default-effort row agrees
   with the untagged one, §7), and a `rung:` once you have placed it.
   **Every score carries a source URL and a date.** A number
   without one does not go in. A candidate on no board gets
   `evidence: none` and nothing else; it lands in the appendix. That
   tag means *no scores*, so a row carrying both it and a `scores:`
   block is a data error: the run keeps the scores, ranks the model and
   warns, naming every id whose tag disagrees with its data. An
   OpenRouter id that is an undated alias for a dated snapshot in the
   same file gets `alias_of:` pointing at that snapshot — its boards are
   folded in, the snapshot's price stands, and the alias leaves every
   table, because one purchasable endpoint should be one point.
   Boards captured into `data/boards/` need none of this: a cell there
   overrides the same cell here, and the board file carries the source.
3. **Only keep sources dated after the previous run.** The newest
   `captured:` date already in `data/models.yaml` is the cutoff; older
   pages restate what is already scored and re-adding them
   double-counts a single measurement. A source nothing cites is
   deleted rather than kept "for later": a test fails on an unused
   `sources:` entry, and a dangling `src:` fails the run.
4. **Add cost ratios** only from runs that priced two models on the same
   tasks — one row per pair, per run, never a figure assembled from two
   pages. Effort ratios go in `effort_ratios:` under the same rule, and
   at least one row must touch the model's `default_effort` or the whole
   ladder is dropped.
5. **Check the scope filter** on every candidate: output modality
   exactly text and `tools` in `supported_parameters`. Reject image,
   audio and music models, translation models, safety classifiers and
   code-apply models as `out of scope: not a text-out tool-calling LLM`
   even when the catalogue files them under text.
6. **Write down the rejections** as you go, with the disqualifying
   number in the prose, plus a `rejected_short:` of a few words for the
   rejected table.
7. **Rerun** `scripts/rank_llms.py` and read the diff in
   `results/ranking.md`. A model moving several rungs on one new
   benchmark row usually means thin coverage, not a real move — check
   its measured-board count and its ability band before believing it.
   **Read the warnings the run prints** — a mislabelled `evidence:`
   tag, a ladder row contradicting its untagged row, a board id in a
   capture that matches no model, a weight map that does not add to 1
   (that one stops the run outright) — and fix the data rather than the
   report.
8. **Re-cut the presets** from the new ladder (§6) and update the
   preset configs if a tier changed.
9. **Commit `data/`, `results/` and this file together.** There is no
   findings section here to update by hand: `results/findings.md` is
   regenerated by the same run, and a test fails if this file starts
   restating numbers from it.

---

## 9. What this run found

**Nothing is written here.** Every finding — the variant and model
counts, what each group's frontier holds, how many rows had too few
measured boards to rank, where the two pillars disagree,
which models score worse at a dearer effort, and everything the data
checks flagged — is regenerated by the same run that writes the
ranking, into

```
results/findings.md
```

Read that file, not this section. It is rebuilt from `data/*.yaml` on
every run, so it cannot be stale in the way a hand-written section is:
the old version of this section quoted counts from a run several
rewrites old, and there was no way to tell which of its numbers had
since moved.

A test enforces it. If a number finds its way back into this section,
the test fails and points here. State the method in this file and let
the run state the results.

The generated file also carries the material this section used to hold
by hand: the price ladder with each rung's blended price, the split
between arena and static evidence in every group, the models with no
agentic board at all, the models whose efforts nobody priced, the
aliases folded into a snapshot, and the rejections. The ladder and its
legend are printed under **Cost basis** in `results/ranking.md`, since
that is where a reader comparing prices already is.

---

## 10. What is in here

| path | holds |
|---|---|
| `data/models.yaml` | models, prices, scores, rejections |
| `data/boards/*.yaml` | captured boards, one file per source |
| `data/cost_ratios.yaml` | same-source cost and effort ratios |
| `data/task_groups.yaml` | every tunable weight |
| `data/pipeline_steps.yaml` | measured per-step difficulty |
| `scripts/rank_llms.py` | the whole computation |
| `scripts/capture_*.py` | the two board captures |
| `scripts/cut_diff.py` | before/after top 5 + frontier, two runs |
| `scripts/board_diff.py` | before/after board counts and dates |
| `tests/test_rank_llms.py` | toy fixtures, one per axis |
| `tests/test_invariants.py` | the rules, over the real data |
| `tests/test_cut_diff.py` | `cut_diff.py`, hand-built fixtures |
| `tests/test_board_diff.py` | `board_diff.py`, hand-built fixtures |
| `results/ranking.md` | the committed run output |
| `results/frontiers.html` | charts, evidence, navigation; one file |
| `results/evidence.md` | every board, ratio and price, as text |
| `results/findings.md` | what the run found; §9 points here |
| `results/rank_llms.log` | the warnings the run printed |

---

## 11. Refresh cadence

`.github/workflows/llm-bench-refresh.yml` recaptures both boards, reruns
the ranker, and opens or updates a PR on `llm-bench/weekly-refresh` with
the board and ranking diff in its body, every Monday at 06:00 UTC (also
runnable on demand via `workflow_dispatch`). A failed capture fails the
job before `rank_llms.py` or the PR step ever run, so a partial capture
never reaches a PR.

It needs one repo secret: `ARTIFICIAL_ANALYSIS_API_KEY`, the same key
`capture_aa.py` reads from `~/.config/aii/llm_bench.env` locally. The
model list, cost ratios and preset cuts are never touched by the
workflow; that judgment stays with whoever reviews the PR.
