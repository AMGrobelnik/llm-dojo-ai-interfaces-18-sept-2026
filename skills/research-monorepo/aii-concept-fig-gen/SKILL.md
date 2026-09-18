---
name: aii-concept-fig-gen
description: "Generates and edits CONCEPT FIGURES — architecture and pipeline diagrams, flow charts, cover and hero artwork — with Gemini Nano Banana image models through OpenRouter, at a chosen aspect ratio and resolution, free or paid, in parallel batches. Use whenever a figure must be DRAWN because no dataset sits behind it, or an existing image needs editing from a text instruction. Triggers: concept figure, figure_type='concept', architecture diagram, pipeline diagram, flow chart, cover image, conceptual artwork, image generation, image editing, nano banana, gemini image. NOT for: anything with numbers behind it — bars, curves, heatmaps, confusion matrices, scaling laws — which an image model only approximates, so use aii-data-fig-gen; multi-round variant batches are amg-iter-image-gen-human; calling a TEXT model over OpenRouter is aii-openrouter-llms; displaying a file is amg-open-img-ubuntu."
---

# Image Generation & Editing (nano_banana)

> **Not for data figures.** An image model approximates numbers: bars come
> back close to but not equal to their labels, and axis ticks do not divide
> evenly. Nothing downstream detects it. If the figure has numbers behind
> it, use `aii-data-fig-gen`, which renders them deterministically.

Generate images via OpenRouter's dedicated images API (`/api/v1/images`) through the ability server, on the two Gemini "Nano Banana" tiers. The `OPENROUTER_API_KEY` lives on the ability server — this skill routes requests through `call_server()`.

## Setup

```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/aii-concept-fig-gen"
G="$SKILL_DIR/scripts/concept_fig_gen.py"
PY="$SKILL_DIR/../.ability_client_venv/bin/python"
```

## Generate Image

```bash
$PY $G --prompt "prompt describing the image" --output output.jpg --aspect-ratio 16:9
```

## Free vs paid — check before you generate

Two billing paths. **You do not normally choose**: the run's backend already
set the default, and the flags below only override it.

| Path | Cost | Editing |
|---|---|---|
| paid (default) | ~$0.067/image @1K | yes |
| `--free` | $0 | no |

The paid path is OpenRouter's `gemini-3.1-flash-image-preview` (Nano Banana
2); `--free` is Cloudflare Workers AI (FLUX / SDXL), falling back to Hugging
Face `stabilityai/stable-diffusion-3-medium-diffusers` (SD3).

`--free` serves inside Cloudflare's 10,000-neuron **daily** free allocation.
Gemini has no free image tier at all, so this is the only genuinely $0 route.

**`flash` is not one price.** ~$0.067/image at 1K but ~$0.101 at 2K, measured
live at $0.1017 for a 2K edit. It matters because the figure step deliberately
uses both: it explores at 1K and then makes exactly TWO 2K passes per figure,
so those two passes alone cost ~$0.20 a figure rather than the ~$0.134 the 1K
number implies. `pro` is flat at ~$0.134 across 1K and 2K, so it is only twice
the price of flash at 1K and about a third more at 2K.

The paid path has two quality tiers, selected with `--model` (orthogonal to
`--free`/`--paid`): the default `flash` (Nano Banana 2, ~$0.067/image @1K) and
`pro` (`gemini-3-pro-image-preview` / Nano Banana Pro, ~$0.134/image @1K-2K —
higher fidelity for hero/cover figures). **You do not normally choose this
either**: the pipeline sets it from the run's `gen_paper_repo.gen_viz.image_model`
config, and the Max/Ultra presets pick `pro`. A `pro` call that exhausts its
retries falls back to `flash`, and every charge the provider reports is
recorded — including one on a response that came back priced and carrying no
image, which is a refusal (quota, moderation) rather than a blank a retry
fills in. Such a response is not asked for again at the same price, and the
figure's failure still names what the body said.

- **On a free-tier run the default is already `--free`** (the backend exports
  `AII_FREE_TOOLS=1`). Do not pass `--paid` there: six figures on the paid
  path cost $0.81, which was 78% of a measured "free" run's entire bill.
- Pass `--paid` only when you must EDIT an existing image, which the free
  provider cannot do — it takes a prompt with no image input.
- The free path has TWO providers and walks between them. Cloudflare's
  10,000-neuron daily allocation is shared with the free LLM pool, so a busy day
  spends it; the call then fails over to Hugging Face automatically. You do not
  need to do anything for this.
- If BOTH are down the call fails. Do not silently fall back to paid on a free
  run: report it and continue without the figure.

### Free costs you the labels, not just the fidelity

The returned JSON's `model` field says which of the three served the image, and
it is worth reading: they are tiers apart on the thing concept figures are
mostly made of — words in boxes. Same prompt, same day, measured live:

| Model that served it | Diagram | Labels came out as |
|---|---|---|
| paid `gemini-3.1-flash-image-preview` | right | all three correct |
| CF `flux-1-schnell` | right | `Enc:der`, `conveged?` |
| HF SD3 medium | wrong | `erooder`, `routter` |

Three paid runs, three clean figures — every word right, and the flow chart
came back with the NO branch actually looping back, which neither free model
managed once. SD3 went the other way and put text in a figure that asked for
none: a prompt ending "no text of any kind" came back with `Kat q` and
`Wet ker wee Bir Sauh` lettered across it, in red and green as its two main
colours under `--style neurips`. Treat an HF-served image as a draft to check
hard, not a figure to ship.

That is where the $0.067 goes, so spend the verification effort to match: on a
free run read every word in the image letter by letter, and on a paid one look
first for the things a good speller still gets wrong — a stage you do not have,
an arrow the wrong way round.

None of it is checked automatically. `success: true` means a valid JPEG of the
right size arrived — nothing reads the words in it.

## Edit Image

```bash
$PY $G --edit input.jpg --prompt "Make the background blue" --output edited.jpg
```

**Parameters:**
- `--prompt` / `-p` (required) — image description or edit instruction
- `--output` / `-o` (default: `./generated_image.jpg`) — output file path (always saved as `.jpg`; suffix is forced)
- `--edit` — path to source image for editing (omit for generation)
- `--aspect-ratio` (default: `16:9`) — valid: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`
- `--image-size` (default: `1K`) — resolution: `1K`, `2K`, `4K`
- `--model` (default: `flash`) — paid Gemini tier: `flash` (Nano Banana 2, ~$0.067/img) or `pro` (Nano Banana Pro, ~$0.134/img @1K-2K). Normally set by the pipeline from `gen_paper_repo.gen_viz.image_model` (Max/Ultra presets pick `pro`); ignored on `--free`.
- `--style neurips` — appends NeurIPS academic style guidance
- `--negative-prompt` — things to exclude from the image
- `--system` — system-level style instruction
- `--timeout` (default: `180`) — the WHOLE call's deadline, and therefore the
  retry budget. Each attempt gets the lesser of 180 s and whatever is left, and
  the loop will not start one it cannot finish: with 180 s and fast failures
  (a connection error, a 5xx) all six paid attempts run, while on slow
  responses it stops and says how much budget was left rather than being cut
  off mid-request. Raise it if you want the full budget under slow responses —
  six attempts of 180 s would need 1092 s.

## Parallel Batch Generation

Use GNU `parallel` for multiple images:

```bash
export SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/aii-concept-fig-gen"
export PY="$SKILL_DIR/../.ability_client_venv/bin/python"
export G="$SKILL_DIR/scripts/concept_fig_gen.py"
parallel -j 5 -k --group --will-cite 'eval {}' ::: \
  "\$PY \$G -p \"prompt 1\" -o output_1.jpg --aspect-ratio 21:9" \
  "\$PY \$G -p \"prompt 2\" -o output_2.jpg --aspect-ratio 16:9" \
  "\$PY \$G -p \"prompt 3\" -o output_3.jpg --aspect-ratio 1:1"
```

## Preview

Do **NOT** open generated images in a GUI viewer (`loupe`, `xdg-open`, `eog`,
etc.). This skill is for automated / headless generation (e.g. pipeline figure
steps), and popping image windows clutters the user's desktop. Inspect images
programmatically if needed (read the file, check the returned JSON), not by
opening a viewer.

For interactive, human-curated review of multiple figure variants — where the
user wants to arrow-navigate batches in `loupe` — use the
`amg-iter-image-gen-human` skill instead; loupe-driven review is its job, not
this one's.

## Features

- **Model**: default `gemini-3.1-flash-image-preview` (Nano Banana 2, `--model flash`); `--model pro` selects `gemini-3-pro-image-preview` (Nano Banana Pro), which falls back to flash if it exhausts its retries
- **Auth**: API key on ability server (routed via `call_server()`)
- **Retries**: 3 attempts with exponential backoff, then fallback model — as far as `--timeout` allows, since it is the deadline for the whole call
- **Edit mode**: Edit existing images with text instructions
- **Parallel**: GNU `parallel` with `-j 5` for batch generation
- **Headless**: never auto-opens a viewer (use `amg-iter-image-gen-human` for human review)

## Prompting Tips

- Name every element and where it sits — boxes, arrows, groupings, labels.
  The model places what you describe and invents what you leave out
- **Put the labels in their own closing sentence**, not inline in the sentence
  that describes the layout. "…three boxes joined by arrows. The boxes read
  Tokenizer, Transformer, Classifier." rendered all three words correctly;
  "…three labelled boxes left to right, Encoder, Router, Decoder, joined by
  arrows…" rendered `Enc:der`. Four out of four runs that stated the labels
  as a separate final sentence spelled every one of them right, including the
  same words the inline phrasing had corrupted. Word length was not the
  driver — `Transformer` and `Classifier` both came out clean
- Specify colors, fonts, layout, and what to exclude
- Use `--style neurips` for academic papers. It also pins the figure to the
  same colours every DATA figure in the paper uses — seaborn's `colorblind`
  — and tells the model not to let red-versus-green be the only difference
  between two elements, which is the one pairing that carries no meaning for
  about 8% of male readers
- Any number that DOES appear — a throughput on an arrow, a stage count —
  has to be stated explicitly, and read back off the image to check it
  survived. If the figure is mostly numbers, it is a data figure: stop and
  use `aii-data-fig-gen`, which renders them instead of approximating them
- 1K resolution is default and most reliable

## Figure type templates

An image model draws what you name and invents what you leave out, so the
prompt for each kind of concept figure has a different set of things it
cannot omit. Each entry below names the kind, its usual aspect ratio and those
things; start from the one that matches and add the specifics.

- **Architecture / pipeline diagram** (`21:9`) — every stage in order, left to
  right; what flows along each arrow and which way it points; which stages are
  yours vs. baseline or off-the-shelf; where the boundary of the system sits.
- **Flow chart** (`21:9` or `16:9`) — each decision point and both of its
  outcomes; where a branch rejoins; the start and the terminal states; that
  arrows are labelled, not bare.
- **Side-by-side comparison** (`16:9`) — what the two panels are, in which
  order; that both use the SAME visual vocabulary so only the difference
  differs; a caption strip or heading per panel.
- **Conceptual artwork / cover** (`1:1`, `16:9`) — the single idea in one
  sentence; the metaphor and what maps to what; that no text appears unless you
  asked for it, since invented labels are the usual failure.

Two things every entry shares: state the sans-serif requirement (`--style
neurips` does it for you), and read the image back to check that nothing was
invented — a stage that is not in your pipeline, an arrow that runs the wrong
way, a label you never wrote.

Reading it back is not optional, and re-running is a real fix. The same prompt
sent twice gave a correct three-box chain once and, the other time, four boxes
with `Encoder` in two of them and an arrow pointing at nothing — identical
text, different diagram. So a structure you cannot check by looking is a
structure you do not have; when it comes back wrong, generate it again rather
than editing the prompt, because the prompt was not what failed.

## Aspect Ratios

Pick by shape, not by venue. `--help` lists all ten; these are the ones a
paper figure normally wants.

| Ratio | Use Case |
|-------|----------|
| `21:9` | Ultra-wide — pipelines, architecture, the hero figure |
| `16:9` | Wide — side-by-side comparisons, multi-panel concepts |
| `4:3`, `3:2`, `5:4` | Standard — one diagram with room around it |
| `1:1` | Square — a symmetric diagram, a cover image |
| `9:16`, `3:4`, `2:3`, `4:5` | Vertical — a stacked flow or poster |

**If the ability server is not running**, nothing needs doing: the CLI already
falls back to running the same function in-process, so `concept_fig_gen.py`
works standalone. Verified — with no server reachable it still resolves the
free/paid path and reports its own errors ("OPENROUTER_API_KEY not set")
rather than a connection failure.

What it needs is the deps. If the import fails, install them INTO THE VENV
`$PY` names above — creating a `.venv` in whatever directory you happen to be
standing in leaves `$PY` pointing at the same broken interpreter:
```bash
CLIENT_VENV="$SKILL_DIR/../.ability_client_venv"
uv venv "$CLIENT_VENV" --python=3.12          # only if it is not there yet
uv pip install --python="$CLIENT_VENV/bin/python" \
  -r "$SKILL_DIR/scripts/server_requirements.txt"
```
