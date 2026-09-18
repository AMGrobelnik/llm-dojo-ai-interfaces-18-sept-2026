# Anonymization

This tree (`skills/`, `prompts/`, `libraries/`, `hooks/`) was written inside two
private repositories and is published here with every identifying detail about
its author, their employer, their machines and their accounts removed.

Nothing below lists an original value. Each row says what class of information
was found and what stands in its place now. The same placeholder is always used
for the same thing, so the documents stay internally consistent and still read
as prose.

## Replacements

| Class | Replaced with | Count |
|---|---|---|
| Author's given name, surname, full name | `the author` / `The author` | 73 |
| Author's code-forge / registry handle | `<author>` | 28 |
| Employer, its acronyms, its department | `institute` | 28 |
| City and timezone tied to the author | `Berlin`, `Europe/Berlin` | 11 |
| Author's home directory in paths | `/home/<user>` | 16 |
| Work email domain | `example.com` | 2 |
| Private research monorepo name | `research-monorepo` | 182 |
| Private notes & config repo name | `notes-repo` | 47 |
| Account, environment and app ids | `<REDACTED>` | 6 |
| Third-party app name tied to an account | `<dropbox-app>` | 1 |
| Private sub-project directory names | generic nouns | 3 |

Notes on individual classes:

- **Names.** Every occurrence of the author's first name, surname and full
  name became `the author` (capitalized at the start of a sentence, heading or
  list item). A byline constant in a script became `The Author`. Names of
  public figures and of paper authors in bibliographies were left alone, as
  were the attribution fields of vendored third-party skills.
- **Handle.** The author's forge/registry handle is `<author>`, including
  inside clone URLs and container-image references such as
  `<author>/aii_pipeline:latest`.
- **Employer.** The institute's name, both its acronyms, its internal
  department code and its slide-deck branding are all `institute` now
  ("institute template", "institute-style deck", "institute logo"). The work
  Google Workspace domain is `example.com`; one phrase that contrasted it with
  a personal account now reads "the work Google Workspace".
- **Geography.** The author's city, and the IANA timezone naming it, became
  `Berlin` / `Europe/Berlin`. That zone has the same `+02:00`/`+01:00` DST
  behaviour, so the daylight-saving hazard those hook documents describe is
  still correct. One bare local timezone abbreviation became `+02:00`.
- **Paths.** Absolute home paths are `/home/<user>/...`. A settings file that
  hard-coded one now uses `$HOME`. A transcript directory name derived from a
  home path became `-home-<user>-...`.
- **Repository names.** The two private repos are referred to as
  `research-monorepo` and `notes-repo` in identifiers and paths, and as "the
  research monorepo" / "the notes repo" in prose — the naming `hooks/README.md`
  and `libraries/*.md` already used. Container mount roots moved with them
  (`/research-monorepo/...`). The skill-name prefixes `aii-` and `amg-` are
  unchanged: they are tool names, not identity.
- **Secrets and account identifiers.** Every credential-shaped value is
  `<REDACTED>`: an API key placeholder, a remote-environment id, a feedback
  receipt id, and a cloud app's numeric account id. No live secret was found in
  the tree — `gitleaks` was clean before this pass as well as after it.
- **Other account-scoped names.** A cloud storage volume belonging to an
  unrelated project is now `other-project-vol`. A private directory name inside
  a `.gitignore` audit is `<private-dir>`.

## Deleted files

- The branded `.pptx` that sat in `skills/personal/amg-pptx/template/` — a
  presentation template whose slide master carried an organisation's logos and
  whose document properties carried the author's full name. It was binary, so it
  could not be edited in place the way the text files were. It is replaced by
  `skills/personal/amg-pptx/template/README.md`, which explains that you supply
  your own 16:9 template as `institute.pptx`; the rest of the skill, including
  every measured geometry constant, is unchanged.

No other file was deleted. `skills/personal/amg-pptx/assets/style-ref.jpeg` was
checked by eye and kept — it is a generic diagram with no identifying content.

## Renames

- The skill directory named after the private research monorepo is now
  `skills/research-monorepo/`.
- The repo-level prompt named after it is now
  `prompts/repo-level/research-monorepo-docker-CLAUDE.md`.
- The branded template file was deleted (see above); the scripts and docs that
  referenced it now name `template/institute.pptx`, and the scratch directory it
  created is `deck_work/`.

## What was deliberately kept

Public third-party service domains (`huggingface.co`, `openrouter.ai`,
`api.anthropic.com`, `api.runpod.io`, `api.dropbox.com`, registrar and
benchmark sites), public documentation URLs, model and tool names, benchmark
result tables, the `amg-hooks` tool name and the `aii-` / `amg-` skill
prefixes, loopback and documentation addresses (`127.0.0.1`, `0.0.0.0`,
`1.2.3.4`), example emails (`user@example.com` and friends), fixture-shaped
emails that a hook document exists to describe, and the attribution and licence
metadata of vendored third-party skills.

## Verification

The sweep that produced this pass was re-run afterwards over the whole tree,
case-insensitively, for every class above: the author's names and handle, the
institute's name and acronyms, the city and its timezone, home-directory paths,
the work email domain, both private repository names, private sub-project
directory names, and the key prefixes of the credential formats in use
(OpenAI-, GitHub-, RunPod-, HuggingFace-, Slack- and Context7-shaped tokens).
Every one of them returns nothing, in file contents and in file and directory
names alike. The exact expressions are not reproduced here, because spelling
them out would put the originals back into the repository.

Every email address left in the tree is an `example.com`-style placeholder or a
documented test fixture; the only IPv4-shaped strings left are version numbers,
`127.0.0.1`, `0.0.0.0` and `1.2.3.4`.

Secret scan:

```text
INF scan completed in 736ms
INF no leaks found
```

(`gitleaks detect --no-git -s . -v`)

After the edits, every `.py` file still compiles, every `.json` and `.yaml`
file still parses, and every `.sh` file still passes `bash -n`.

## Second-pass audit

An independent reviewer re-swept the tree with different angles from the ones
above — binary and image metadata, URL-host and email inventories, author
metadata fields, secret-shaped strings, non-English text, and internal-path
reconstruction — and fixed three further classes. As above, no original value
is reproduced here.

| Class | Replaced with | Count |
|---|---|---|
| Private hobby-project directory and its out-of-repo tools path | generic noun | 4 |
| Funding-proposal acronym in a filename | `<proposal>` | 1 |
| Private research repo's name spelled out in prose and in an identifier | neutral wording / `aii_pipeline` | 4 |

Notes:

- **Hobby project.** A personal sub-project directory under `apps/`, named
  after the consumer service and personal account it drives, appeared in three
  hook documents, together with an absolute out-of-repo path for its helper
  library.
  Both now use the same generic noun the earlier pass applied to other
  private sub-project directories.
- **Proposal.** A research-proposal filename under `resources/research/
  proposals/` carried a funding-call acronym; the acronym is `<proposal>`.
- **Repo name by contrast.** Four places spelled the private research
  monorepo's name out in full — twice as ordinary prose describing the work,
  once as a pipeline-stage nickname, once inside a default database name —
  which un-redacted `research-monorepo` for anyone who read them next to the
  `aii-` prefix. They now read as `research-pipeline work`, `the pipeline
  loop`, a generic example name, and `aii_pipeline_dbos_sys`.

Checked and found clean: the one JPEG (no EXIF, generic diagram) and the
twenty brand SVGs (`<title>` elements only, from a public icon set); every
email address and URL host in the tree; `__author__`-style metadata,
copyright lines and commit-trailer patterns; long base64/hex strings,
`Authorization:` headers, UUIDs, Google client ids, Cloudflare and RunPod
ids, and `.env` templates (the only 40-hex strings are public HuggingFace
dataset revision pins); absolute home paths, `~`-prefixed paths, ssh
`user@host`, `.local`/`.lan` hostnames, tmux socket and session names, and
container-registry references; every timezone string (all `Europe/Berlin`
and consistent offsets); and every non-ASCII file, for prose in a language other
than English — there is none, and no place name, national top-level domain
or local currency survives anywhere.

Borderline, deliberately kept: internal module and directory names carrying
the accepted `aii_` / `amg-` prefixes; two short commit hashes from a private
repository, which resolve nowhere public; and relative links in
`prompts/claude-code-setup-README.md` that point at parts of the original
private repo which were never published — they were already dangling before
this pass and are not artifacts of any rename. Intra-tree links, including
every reference to the renamed skill directory and to the removed slide
template, all resolve.

A third reviewer then read every new hook page in full, prose included, rather
than by regex, specifically for identifiers a pattern cannot see: names in
review attributions, line-split repo names, institute/course/grant wording,
private hostnames, ports, tokens and absolute paths. One class needed fixing —
the private monorepo's name left truncated mid-word at a line break inside a
quoted container-build line, which no whole-word pattern matched; it now reads
`research-monorepo`. Everything else read clean: roles appear only as generic
nouns ("the owner", "a peer", "a different agent"), paths as `/home/<user>`,
and hosts only as loopback or public vendor endpoints.
