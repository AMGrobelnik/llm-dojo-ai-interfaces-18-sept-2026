# Vendor logos

One monochrome SVG per model maker, inlined into `results/frontiers.html`
as an SVG `<symbol>` and drawn inside each scatter marker. The page is a
single self-contained file with no network access, so these are vendored
rather than fetched.

**Source.** [simple-icons](https://github.com/simple-icons/simple-icons),
released under **CC0 1.0 Universal** (public domain dedication). Fetched
once with:

```bash
curl -O https://cdn.jsdelivr.net/npm/simple-icons@<version>/icons/<slug>.svg
```

Most files come from `simple-icons@16.31.0`. A few brands were dropped
from later releases, so those were taken from the last release that
carried them:

| file | simple-icons version |
| --- | --- |
| `openai.svg`, `amazon.svg` | 13.0.0 |
| `ibm.svg` | 11.14.0 |
| everything else | 16.31.0 |

The brand marks themselves remain the trademarks of their owners; CC0
covers the SVG artwork in simple-icons, not the right to imply any
endorsement. They are used here only to identify which company made
which model on a chart.

**Adding one.** Drop `<slug>.svg` in this directory and add the
`<id prefix> -> <slug>` line to `VENDOR_LOGOS` in
`.claude/skills/amg-llm-bench/scripts/rank_llms.py`. A maker with no entry, or whose file is missing,
keeps the plain circle marker. `cohere` has no simple-icons file in any
release and is deliberately absent.
