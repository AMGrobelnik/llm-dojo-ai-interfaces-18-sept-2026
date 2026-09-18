---
name: amg-iter-image-gen-human
description: "Organizes multi-round, multi-variant image generation into an image-gen / figure / batch-letter / numbered-tile tree with every prompt and log saved, fires a whole batch through GNU parallel, reads each result back, and opens loupe on one batch at a time. Use whenever several variants of the same figure are wanted for a paper, slide deck or other human-curated deliverable, and especially across successive rounds of feedback such as more options, another round, or refine the ones picked. Triggers: image variants, batch of options, iterate on a figure, another round, curate picks, top picks, loupe review, regenerate with feedback. NOT for: generating one image, which is aii-concept-fig-gen called directly; numeric charts, which are aii-data-fig-gen; and simply displaying images that already exist, which is amg-open-img-ubuntu."
---

# Iterative image-gen workflow (human-friendly organization)

A figure for a paper or deck rarely lands on the first try. Each round of user feedback spawns a new batch of variants. Without structure, the working directory becomes an unreadable pile of `final_v3_actually_final_v2.png`. This skill defines the tree we use so every variant is navigable, traceable, and comparable.

## The hierarchy

```
<project>/image-gen/
├── <figure-name-1>/                 # one folder per figure we're working towards
│   ├── _ref_*.png                   # source/reference images at parent level
│   ├── old-<figure>.png             # original we're iterating from
│   ├── _prompts/                    # one .txt per prompt; stays at parent level
│   │   ├── _context.txt             # shared content base reused across variants
│   │   ├── a01.txt … a30.txt
│   │   ├── b01.txt … b35.txt
│   │   └── c01.txt … c30.txt
│   ├── _logs/                       # image_gen.py stdout/stderr per variant
│   │   └── a01.log …
│   ├── a/                           # BATCH a — first round
│   │   ├── a01.png
│   │   ├── a02.png
│   │   └── …
│   ├── b/                           # BATCH b — second round (after user feedback)
│   │   ├── b01.png
│   │   └── …
│   └── c/                           # BATCH c — third round
│       └── …
├── <figure-name-2>/                 # next figure being worked on
│   └── …
└── _top_picks/                      # curated cross-figure best variants
    ├── 02_<figure>_a01_descriptor.png   # numeric prefix groups by paper-role
    └── …
```

## Core rules

1. **One folder per FIGURE, not per round.** All work toward the architecture diagram lives in `architecture/`, regardless of how many rounds of variants exist. The figure name describes the *artifact*, not the iteration.

2. **One letter-batch subfolder per ROUND.** The first batch of variants goes in `a/`, the second in `b/`, the third in `c/`, etc. A new batch starts whenever the user gives feedback that changes the design hypothesis (different style, different layout, different content). Stochastic regenerations of the *same* prompt do NOT need a new batch.

3. **Sequential 2-digit numbering within a batch:** `a01.png`, `a02.png`, …, `a30.png`. Two digits keeps alphabetical sort = numeric sort even up to 99.

4. **Optional descriptive suffix in `_top_picks/` only:** `a01_minimal.png`, `a13_avatar_style.png`. **Inside `<figure>/<batch>/` keep names short** (`a01.png`) — the prompt file `_prompts/a01.txt` carries the description.

5. **Save the prompt file alongside the image.** `<figure>/_prompts/<id>.txt` contains the full prompt sent to the image generator. The user (or you next session) can grep across `_prompts/` to find what produced a given image.

6. **Save logs.** `<figure>/_logs/<id>.log` = stdout/stderr from `image_gen.py`. Used for debugging failed generations or recovering aspect ratios / size info.

7. **References at parent level.** Source screenshots / inspirations / "old" images that don't belong to any batch live at `<figure>/` with an `_ref_` prefix or just the original filename. They are NOT inside a batch folder.

8. **Never delete an old batch.** Even if `a/` is "superseded" by `b/`, keep it — the user may want to compare or recover an earlier design direction.

## Workflow loop

1. **First batch.** User asks for a figure. You generate a diverse exploration:
   - Create `<project>/image-gen/<figure-name>/`
   - Write `_prompts/_context.txt` with shared content (the entities + relationships the figure needs to convey)
   - Write `_prompts/a01.txt` … `_prompts/aN.txt` — each varies one design axis (layout / aspect / typography / detail level / style)
   - Run `image_gen.py` for each, output `<figure>/a/aN.png`, log to `_logs/aN.log`
   - **READ each generated image** with the Read tool — your vision is good, use it. Don't fire-and-forget 30 generations and hope.

2. **Curate.** Identify which variants are NeurIPS-grade / on-style / off-brand. Mention the strongest 3–5 and the obvious dropouts. Open loupe pointed at `<figure>/a/aN.png` so the user navigates only this batch.

3. **User picks / gives feedback.** They might say "I like 1, 3, 7", or "all are too cluttered, simpler", or "use a different font". This is the start of batch `b`.

4. **Second batch — refinement OR new direction.**
   - If the user picked specific variants, write `_prompts/bN.txt` for each, derived from the picks' prompts plus the requested changes.
   - If the user redirected the design entirely, write fresh prompts. The shared `_context.txt` usually still applies; only the styling/layout instructions change.
   - Run, log, output to `<figure>/b/bN.png`, READ each, present.

5. **Repeat for `c/`, `d/`, etc.** until the figure is locked in.

6. **Top picks.** When the user picks a final from each figure, copy it (don't symlink — copies are portable across machines/uploads) into `_top_picks/` with a meaningful name: `<paperRolePrefix>_<figure>_<id>_<descriptor>.png`. Numeric prefix (`02_`, `03_`, …) groups by figure-role so loupe sorts them in paper-reading order.

## Naming conventions

Each entry is the element, its pattern, then an example.

- **Figure folder** — `<short-noun>`: `architecture/`, `trace/`,
  `method-comparison/`
- **Batch subfolder** — single letter: `a/`, `b/`, `c/`
- **Variant filename** — `<batch><nn>.png`: `a01.png`, `b15.png`
- **Prompt file** — `<batch><nn>.txt`: `_prompts/a01.txt`
- **Log file** — `<batch><nn>.log`: `_logs/a01.log`
- **Shared context** — `_context.txt`: `_prompts/_context.txt`
- **Reference / source** — `_ref_<descriptor>.png`:
  `_ref_user_screenshot.png`, `_ref_avatar_fig2.png`
- **Top pick** — `<prefix>_<figure>_<id>_<desc>.png`:
  `_top_picks/07_trace_c30_ultra_minimal.png`

## Loupe-driven review

The whole point of the structure: opening loupe on a single batch folder lets the user arrow-navigate **only that batch** without seeing references, prompts, logs, or earlier batches.

```bash
nohup loupe /path/to/<project>/image-gen/<figure>/<batch>/<id>.png >/dev/null 2>&1 &
disown
```

- Open on `<batch>/<first-id>.png` so the user starts at the beginning.
- Loupe shows files in that directory only; arrow keys cycle alphabetically. Two-digit numbering keeps the ordering correct.
- Don't `pkill loupe` before opening a new instance — it disrupts the user's workflow if they have other windows. Just `nohup loupe … & disown` a new one; users close the stale ones themselves.

### Closing the previous batch's loupe when moving on

When the user has clearly moved on from a batch (they've given feedback, you've started a new batch, they explicitly said "now do X"), close the *previous* batch's loupe window so it doesn't pile up. Find the loupe PID by its command-line path and `kill <pid>` — graceful SIGTERM is sufficient:

```bash
# Find the loupe process pointing at the previous batch:
pgrep -af "^[0-9]+ loupe .*/<figure>/<previous-batch>/" | awk '{print $1}'
# Then kill it (loupe closes cleanly on SIGTERM):
kill <pid>
```

When the user moves on from c → d, kill the c-batch loupe (don't pkill all loupes — only the one whose command line points at the previous batch's path). After spawning loupe for the new batch, the previous one is no longer needed.

Do NOT close loupes that point at unrelated paths (e.g., `_top_picks/`, other figures' batches) — those may belong to a different workflow the user has open.

See `amg-open-img-ubuntu` for environment variables / Wayland gotchas.

## Generation pattern (gemini-3-pro-image-preview)

Use the `aii-concept-fig-gen` skill for the actual generation. Key choices in this workflow:

- **Image size per round:** `--image-size 1K` for exploration (fast, ~20s/image, ~1 MP), `--image-size 4K` only once a layout is locked in (~17 MP, slower, more expensive). **A whole 30-variant batch at 1K costs much less than a single 4K final.**
- **Aspect ratio:** Match the paper's intended placement. Wide figures = `21:9`. Side-by-side comparisons = `16:9`. Square heatmaps / radar = `1:1`. Portrait detail callouts = `9:16`. Gemini also supports `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`. Don't mix randomly — a whole batch should usually share an aspect.
- **MAXIMIZE PARALLELISM via GNU `parallel`, one Bash tool call.** Gemini's image-gen endpoint handles many concurrent calls fine; the bottleneck is generation latency, not request rate. Don't waste time with shell `for` loops, fixed batches of 3-5, or 20 separate Bash tool calls — fire the whole batch in a single `parallel` invocation:

  ```bash
  ids=(b01 b02 ... b20)
  parallel --jobs 0 --keep-order --line-buffer --will-cite \
    "$PY $G --prompt \"\$(cat <figure>/_prompts/{}.txt)\" \
            --output <figure>/<batch>/{}.jpg \
            --aspect-ratio 21:9 --image-size 2K --timeout 360 \
            > <figure>/_logs/{}.log 2>&1" \
    ::: "${ids[@]}"
  ```

  `--jobs 0` = unlimited concurrency. Wall-clock = slowest single image (~30-60s at medium), not 20× sequential. See `aii-concept-fig-gen` for the full export-vars setup.

- **Retry only the failures, not the whole batch.** When `parallel` finishes, scan each `_logs/<id>.log` for `"success": true`. Re-fire `parallel` over only the missing ids:

  ```bash
  failed_ids=()
  for id in "${ids[@]}"; do
    grep -q '"success": true' "<figure>/_logs/$id.log" 2>/dev/null || failed_ids+=("$id")
  done
  [ ${#failed_ids[@]} -gt 0 ] && parallel --jobs 0 ... ::: "${failed_ids[@]}"
  ```

- **Prompt structure:** A common `_context.txt` at the top, a per-variant directive that varies one or two axes, and a strict guard at the end ("NO X, NO Y, ONLY Z"). The guard goes LAST so it overrides anything the LLM might infer from the context.

## What batches typically vary

- **Round a (exploration):** layout (vertical / horizontal / grid / radial), aspect ratio, density (sparse / dense), style register (academic clean / iconographic / dashboardy).
- **Round b (refinement):** holds the layout the user liked, varies typography, color treatment, label placement, level of annotation.
- **Round c (lock-in):** small tweaks based on specific user-pointed flaws (e.g. "remove the title", "make font lighter", "no problem cards"). Often produces the final.

If user feedback is dramatic ("scrap that, totally different approach"), it's a fresh round, not a refinement — start a new letter, don't shoehorn into the previous batch's prompts.

## Anti-patterns

- ❌ All variants in one flat folder (`final.png`, `final_v2.png`, `final_actually_final.png`).
- ❌ Batch-letter inside the filename only (`pipeline-example/a01_minimal.png` mixed with `pipeline-example/b01_minimal_light.png`). Loupe sees them all together → user can't focus.
- ❌ No prompts saved → can't retrace why an image looks the way it does.
- ❌ Reading none of the generated images and presenting them blindly to the user. Vision review is the deliverable, not just the bytes.
- ❌ Reusing letter prefixes between rounds (e.g. starting "a" over each session). Letters are per-figure, not per-conversation. If `a/` exists, the next batch is `b/`.
- ❌ Generating high-resolution (4K) images during exploration. Burns budget; wait for layout to stabilize, use 1K-2K for iteration.

## Example session

```
1. User: "Make a figure showing the trace."
2. Assistant: creates trace/, writes _prompts/_context.txt + _prompts/a01..a18.txt,
              runs gemini-3-pro-image-preview → trace/a/a01..a18.jpg, READS each, opens loupe on
              trace/a/a01.jpg, summarizes 5 strongest picks.
3. User: "All cluttered. Just tiles + relations + legend."
4. Assistant: writes _prompts/b01..b35.txt with stricter prompts, generates
              trace/b/, READS each, opens loupe on trace/b/b01.png.
5. User: "Better but still busy. Drop the problem cards and metadata."
6. Assistant: writes _prompts/c01..c30.txt, generates trace/c/, READS each,
              opens loupe on trace/c/c01.png. Updates _top_picks/ with the best.
7. User locks in. Final image lives at trace/c/c30.png; copy to
   _top_picks/07_trace_c30_ultra_minimal.png for paper assembly.
```

The whole tree is grep-able, replayable, and reviewable forever.
