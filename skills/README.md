# Skills

Each skill is a folder with a `SKILL.md` (frontmatter `name`/`description`, then the instructions) plus optional `scripts/`, `style/`, templates.

## Personal skills (`amg-*`)

General-purpose skills the author uses across all projects.

| Name | Description |
|---|---|
| [amg-claude5-prompting](personal/amg-claude5-prompting) | Captures how to prompt and drive the Claude 5 model family (Fable 5.1 orchestrator, Opus 5 / Sonn... |
| [amg-cloudflare](personal/amg-cloudflare) | Drives the Cloudflare API for a domain ALREADY OWNED through a stdlib-only CLI, scripts/cf.py: li... |
| [amg-dropbox](personal/amg-dropbox) | Uploads, archives and backs up a file or folder to Dropbox by streaming a tar.gz in 140MB chunks,... |
| [amg-frontend-testing](personal/amg-frontend-testing) | Drives a real browser against a frontend the way a human tester does — hover, click, tab, drag, r... |
| [amg-gmail](personal/amg-gmail) | Reads, searches, sends, drafts, replies to, labels and archives the author's personal Gmail through t... |
| [amg-handbook-forge](personal/amg-handbook-forge) | Generates a new aii-handbook-auto-DOMAIN skill for a research field: maps the field, mines real s... |
| [amg-is-domain-taken](personal/amg-is-domain-taken) | Checks whether given domain names are already registered, sweeping one keyword across up to 32 TL... |
| [amg-iter-image-gen-human](personal/amg-iter-image-gen-human) | Organizes multi-round, multi-variant image generation into an image-gen / figure / batch-letter /... |
| [amg-llm-bench](personal/amg-llm-bench) | Benchmarks agentic LLMs for the research pipeline by aggregating published evidence — publishe... |
| [amg-open-img-ubuntu](personal/amg-open-img-ubuntu) | Displays existing image files on Ubuntu GNOME/Wayland by copying them into an isolated batch fold... |
| [amg-paper-verification](personal/amg-paper-verification) | Critically stress-tests a finished paper, abstract or argument in three passes and returns CRITIQ... |
| [amg-pptx](personal/amg-pptx) | Build the author's institute-style presentations (.pptx) with python-pptx: institute template, colour-coded l... |
| [amg-prompt-optim](personal/amg-prompt-optim) | Compresses an existing LLM prompt file for conciseness with zero information loss: renders the fu... |

## Research-platform skills (`aii-*`)

Skills specific to the author's AI research platform (paper writing, figures, datasets, compute).

| Name | Description |
|---|---|
| [aii-colab](research-monorepo/aii-colab) | Pins Google Colab's runtime for generated Jupyter notebooks — Python 3.12, the exact pre-installe... |
| [aii-concept-fig-gen](research-monorepo/aii-concept-fig-gen) | Generates and edits CONCEPT FIGURES — architecture and pipeline diagrams, flow charts, cover and... |
| [aii-data-fig-gen](research-monorepo/aii-data-fig-gen) | Renders publication-quality DATA FIGURES deterministically from a JSON spec via matplotlib — bar,... |
| [aii-file-size-limit](research-monorepo/aii-file-size-limit) | Splits an oversized generated output file into numbered parts that each fit a size limit: checks... |
| [aii-handbook-auto-computational-linguistics](research-monorepo/aii-handbook-auto-computational-linguistics) | Field handbook for computational linguistics as a SCIENCE of language — grammaticality and minima... |
| [aii-handbook-auto-mechanistic-interpretability](research-monorepo/aii-handbook-auto-mechanistic-interpretability) | Field handbook for mechanistic interpretability of neural networks — circuit discovery, activatio... |
| [aii-handbook-auto-multi-agent-llm-systems](research-monorepo/aii-handbook-auto-multi-agent-llm-systems) | Field handbook for multi-agent LLM systems (MAS) — orchestration topology, multi-agent debate, mi... |
| [aii-handbook-auto-neurosymbolic](research-monorepo/aii-handbook-auto-neurosymbolic) | Field handbook for neuro-symbolic AI — text-to-logic autoformalization (NL to FOL), LLM-plus-solv... |
| [aii-hf-datasets](research-monorepo/aii-hf-datasets) | Searches, previews, and downloads machine-learning datasets from the HuggingFace Hub catalogue —... |
| [aii-json](research-monorepo/aii-json) | Validates JSON files against this repo's experiment-pipeline schemas (exp_sel_data_out, exp_gen_s... |
| [aii-lean](research-monorepo/aii-lean) | Compiles and verifies Lean 4 proofs against Mathlib with aii_run_lean.py, tries closing tactics a... |
| [aii-long-running-tasks](research-monorepo/aii-long-running-tasks) | Scales an experiment or evaluation up in stages — mini, 10, 50, 100, 200, then the largest run th... |
| [aii-openrouter-llms](research-monorepo/aii-openrouter-llms) | Searches the OpenRouter model catalog and calls any text model in it (Claude, GPT, Gemini, Llama,... |
| [aii-owid-datasets](research-monorepo/aii-owid-datasets) | Searches and downloads country-and-year statistical tables from the Our World in Data (OWID) cata... |
| [aii-paper-to-latex](research-monorepo/aii-paper-to-latex) | Assembles and compiles a LaTeX paper into paper.pdf: documentclass and package preamble, figure f... |
| [aii-paper-writing](research-monorepo/aii-paper-writing) | Writes the PROSE of an AI research paper: abstract, introduction, related work, methods, experime... |
| [aii-parallel-computing](research-monorepo/aii-parallel-computing) | Parallelises compute-heavy Python: asyncio with aiohttp and a bounded Semaphore for I/O-bound wor... |
| [aii-python](research-monorepo/aii-python) | Applies this repo's Python conventions to experiment and evaluation scripts: uv-only environment... |
| [aii-runpod](research-monorepo/aii-runpod) | Creates, lists and terminates RunPod GPU and CPU pods, plus pod templates, network volumes, SSH a... |
| [aii-semscholar-bib](research-monorepo/aii-semscholar-bib) | Fetches real BibTeX entries in one batch from Semantic Scholar by DOI, ArXiv ID or title via aii_... |
| [aii-use-hardware](research-monorepo/aii-use-hardware) | Detects the CPU, RAM, GPU and VRAM actually available — cgroup v1 and v2 container quotas and CPU... |
| [aii-web-research-tools](research-monorepo/aii-web-research-tools) | Runs multi-source web research campaigns — literature reviews, deep cross-verification of many cl... |
| [aii-web-tools](research-monorepo/aii-web-tools) | Runs web search, page fetch as markdown, and regex grep over full HTML or PDF text via this skill... |

## Third-party skills

Skills authored by others (Anthropic's document skills, Playwright, etc.), vendored as-is or lightly adapted.

| Name | Description |
|---|---|
| [anthropic-docx](third-party/anthropic-docx) | Creates, edits and analyzes Microsoft Word .docx files: pandoc extraction to markdown, docx-js au... |
| [anthropic-pdf](third-party/anthropic-pdf) | Extracts text and tables from .pdf files, fills fillable and flat PDF forms, creates PDFs with re... |
| [anthropic-pptx](third-party/anthropic-pptx) | Creates, edits and analyzes PowerPoint .pptx presentations: building decks from HTML through html... |
| [anthropic-skill-creator](third-party/anthropic-skill-creator) | Creates new Claude skills and improves existing ones: drafts SKILL.md, runs with-skill versus bas... |
| [anthropic-webapp-testing](third-party/anthropic-webapp-testing) | Tests a LOCAL web application with Python Playwright scripts, using scripts/with_server.py to sta... |
| [anthropic-xlsx](third-party/anthropic-xlsx) | Creates, edits, cleans and analyzes spreadsheets — .xlsx, .xlsm, .csv, .tsv — with openpyxl and p... |
| [domain-hunter](third-party/domain-hunter) | Brainstorms brandable domain names and turns them into a purchase decision: compares registrar pr... |
| [playwright](third-party/playwright) | General-purpose browser automation in Node: writes a custom Playwright script to /tmp and runs it... |
| [seo-geo](third-party/seo-geo) | Optimizes a live website for traditional search (Google, Bing) and for AI search engines (ChatGPT... |

Excluded from the copy: the `amg-hooks` submodule (see `../HOOKS.md`), archived skills, lock files and one 4.5 MB results page.