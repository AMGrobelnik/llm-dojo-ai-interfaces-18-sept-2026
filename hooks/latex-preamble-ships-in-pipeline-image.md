<!-- hook: latex-preamble-ships-in-pipeline-image -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every \usepackage the paper prompts and aii-paper-to-latex skill prescribe maps in a pinned manifest to a texlive package Dockerfile.pipeline installs — an unsatisfiable addition blocks the commit

The skill preamble prescribes 9 packages (graphicx, geometry, amsmath,
hyperref, url, natbib, booktabs, xcolor, listings — .claude/skills/aii-paper-
to-latex/SKILL.md:14; url was added 2026-08-26, closing the gap where only
the gen_full_paper prompt demanded it at
prompts/steps/_4_gen_paper_repo/_4_gen_full_paper/u_prompt.py:67), while the
image installs exactly texlive-latex-base, texlive-latex-extra, texlive-fonts-
recommended, texlive-science and latexmk (Dockerfile.pipeline's `tex` stage).
Nothing ties the two sides together: a plausible preamble addition (algorithm2e, tikz-
heavy extras beyond latex-extra, a font package) would fail EVERY paper build
at runtime, and the emulated-build constraint means the image cannot even be
`docker run` locally to discover it (CLAUDE.md: amd64 under QEMU, inspect via
docker create+export only). A RULE_DIR manifest (package -> owning texlive
deb) forces the one-time availability verification per new package at commit
instead of per run at pdflatex time. Different seam from enforced rule-viz-
figure-pipeline's prompt-vs-skill-CLI parity (that pins the aii-data-fig-gen
script surface) and from pending rule-prompt-claims-cite-surface (prompt
claims about skills) — this pins skill/prompt LaTeX prescriptions against the
Docker image's tex tree.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **low** (proposer: pipeline-paper-quality)

Proposed command (implemented at approval):

    scripts/check_tex_preamble_manifest.py   # superseded; prefix dropped so
                                            # ready.py does not read these as
                                            # scripts still owed. Built as
                                            # check_preamble_ships.py with a
                                            # yaml manifest rather than a tsv.  # extract usepackage tokens from SKILL.md + gen_full_paper prompt modules; each must appear in preamble_manifest.yaml, and each owning deb named there must be grep-able in Dockerfile.pipeline's texlive install block

Proposed condition: `[ "$RULES_MODE" = commit ] || exit 1; git diff --cached --name-only -- '.claude/skills/aii-paper-to-latex/' 'aii_pipeline/src/aii_pipeline/prompts/steps/_4_gen_paper_repo/_4_gen_full_paper/' 'Dockerfile.pipeline' | grep -q .`


## IMPLEMENTED 2026-08-26 — `scripts/check_preamble_ships.py` + `preamble_manifest.yaml`

    .venv/bin/python $RULE_DIR/scripts/check_preamble_ships.py

Arrives green: 9 distinct packages across the skill and the prompts, all
mapped, all satisfied. Re-run 2026-08-28: still green (exit 0).

**The manifest is DERIVED, not guessed.** Every row was resolved on a machine
that has texlive — `kpsewhich <pkg>.sty`, then `dpkg -S` on the resulting path.
The image cannot be consulted: it is amd64 under QEMU and CLAUDE.md records it
cannot be `docker run` locally at all, only inspected via `docker create` +
`docker export`. That constraint is the reason a manifest exists rather than a
runtime probe.

**Three of the nine are satisfied by a package the Dockerfile never names, and
missing that would have reported working code as broken.** `booktabs`, `xcolor`
and `listings` come from `texlive-latex-recommended`; the image installs
`texlive-latex-extra`, which **Depends** on it, and `--no-install-recommends`
suppresses Recommends, never Depends. Verified with `apt-cache show`. The
manifest records that as an `implied_by` row, and dropping it makes those three
fire — probed, so the row is load-bearing rather than decorative.

Two parsing details that would each have produced a silent pass:

- The skill preamble is ONE comma-separated `\usepackage{graphicx, geometry,
  amsmath, …}`, not one per line. Splitting on braces alone yields a single
  entry named "graphicx, geometry, …" that matches nothing in the manifest.
- The prompts are Python f-strings, so their braces are DOUBLED
  (`\usepackage{{url}}`). Both spellings are read.

The manifest is checked in both directions: a package no preamble asks for any
more is reported, so it keeps describing the tree.

Probed five ways: an unmapped `\usepackage`, a missing apt package, a dropped
`implied_by` row, and a stale manifest row all fire; the real skill and prompt
together do not. One probe initially failed as a CONTROL — my synthetic tree
omitted the prompts, so `url` looked orphaned. The harness was wrong, not the
check; rebuilt with a prompt file, it passes.

Delete-check: The seam cannot be deleted while papers compile inside the image, and
shrinking the preamble is orthogonal. The manifest IS the minimal pin: if the
preamble ever moves to a single templated block (per the latex-figure-recipe-
single-spelling delete path), the manifest shrinks to covering that one block,
and the rule enforces exactly that end-state.

Filter verdicts (3-lens adversarial, kept 2/3):
- KILL: A prompt/skill prescribing a \usepackage the pipeline image cannot
satisfy is a capability claim about an external surface — pending rule-prompt-
claims-cite-surface's dimension. Add the package-to-texlive manifest as that
rule's check for the LaTeX surface; value=low doesn't justify a separate seam
rule. [merge->rule-prompt-claims-cite-surface]
- KEEP: Converts an expensive mid-run pod-side compile failure into a commit-
time diff; the manifest is small (9 packages) over two rarely-churning
surfaces, so upkeep is proportionate to the value despite the low rating.
- KEEP: Real seam (a prescribed \usepackage the image can't satisfy fails at
compile time, late and remotely); extract-usepackage + manifest + Dockerfile-
membership is mechanizable. Low value but cheap; the manifest must fail on an
unmapped package, not skip it.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Line refs check out: `grep -n usepackage .claude/skills/aii-paper-to-
latex/SKILL.md` -> `14:\usepackage{graphicx, geometry, amsmath, hyperref,
natbib, booktabs, xcolor, listings}` (claim said 13-16, which contains it); `a
ii_pipeline/src/aii_pipeline/prompts/steps/_4_gen_paper_repo/_4_gen_full_paper
/u_prompt.py:67` -> `Include \\usepackage{{hyperref}} and
\\usepackage{{url}}`; `grep -n texlive Dock

Corrected statement of fact:
The three file:line refs and the 'no automated tie exists' claim hold.
Corrected: every package the skill and prompt currently prescribe IS
satisfiable by Dockerfile.pipeline:91-93 (6 from texlive-latex-base, 3 from
texlive-latex-recommended, which texlive-latex-extra hard-Depends on --
verified via apt-cache show). Two of the three named at-risk examples are also
already present (algorithm2e -> texlive-science, installed; tikz/pgf ->
texlive-pictures, pulled in by texlive-latex-extra's Depends). A genuinely
missing package would not 'fail EVERY paper build' -- step_runner.py:259-260
deliberately treats a PDF-compile failure as partial success and deploys the
tex source. So this is a preventive parity pin with no live gap, not a latent
outage.

## Where "the image" is, since the TeX tree moved out (2026-09-07)

The apt line this rule reads is unchanged and lives where it always did — the
`tex` stage of `Dockerfile.pipeline`. What changed is where its output ends up:
TeX Live no longer ships inside the `aii_pipeline` runtime. The extracted tree
is published as `<author>/aii_tex:<TAG>` (a `FROM scratch`, one-layer image
built from the same file's `tex_image` stage) and
`aii_pipeline/src/aii_pipeline/bundles.py` fetches it at the paper phase, so
worker pods no longer pay 259 MB at boot for a toolchain only `gen_full_paper`
opens.

The seam is therefore one hop longer and the checker is unaffected: it reads
`Dockerfile.pipeline` for the apt packages, and that is still the single place
the toolchain is chosen. Read the rule's title as "the image the paper step
runs TeX from", which is now the bundle rather than the runtime. Re-measured
2026-09-07 after the move: exit 0, same 9 packages, same satisfaction paths.
