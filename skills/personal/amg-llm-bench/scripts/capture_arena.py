#!/usr/bin/env python3
"""Capture the arena.ai leaderboards (`data/boards/arena.yaml`) for rank_llms.py.

arena.ai has no public data API for these boards (the internal
``/nextjs-api/factuality/ratings`` endpoint is keyed by opaque model slugs,
requires a browser-established Cloudflare cookie, and carries no display
name or vote count). The capture instead drives a real headless Chromium
via ``scripts/capture_arena.mjs`` (Node Playwright, borrowed from the
``aii_frontend`` package already in this worktree — the skill's own Python
venv has no Playwright install) and parses the rendered `<table>` DOM.

``capture_arena.mjs`` prints one JSON object to stdout:
``{"boards": {<board_key or "arena_agent">: BoardDump}, "errors": {...}}``,
where a ``BoardDump`` is
``{url, kind: "score"|"agent", style_control: bool|None, headers: [str],
rows: [[{text, title, direction}, ...], ...]}``. The Node helper turns the
style-control toggle ON (waiting for the table to re-render) before reading
the table whenever the page offers one, so ``style_control`` is ``True`` on
every captured board that has the toggle at all; it is ``None`` only when
the page has no style-control toggle in the DOM (a board that offers no
such control) — that ``None`` is carried through unchanged into
`arena.yaml` rather than coerced to `false`, so a no-toggle board is never
confused with an on/off one, and a board it reads is never left with stale
metadata from an earlier capture.

Twelve of the thirteen page loads are "score" boards: one row per model,
with a ``Score`` (Elo, plus a "±CI" or "+X/-Y" confidence suffix that is
dropped) and a ``Votes`` column. The 13th, the Agent board, has no
Score/Votes column at all; instead five task-metric columns (Net
Improvement, Confirmed Success, Steerability, Bash Recovery, Tool
Hallucination) each become their own board key. Its percentage cells carry
no sign in their text — the true sign is the cell's up/down trend icon
(``direction: "Up"|"Down"``); this capture negates the magnitude whenever
``direction == "Down"`` (confirmed empirically: a model with on-screen
"0.37%" and a "Down" icon has the negative -0.37 already on file in
``models.yaml`` for the same model/metric from an earlier capture).

Vote counts are stored as a `votes:` map on each score board, a sibling of
that board's `values:` map (only score boards show a Votes column; the
Agent board has no such counter to record — its "Sessions" column is a
different quantity this capture does not currently track).

Alias resolution runs the Text board first (it carries the fullest
roster), then every other board in turn, extending one shared alias map.
For each row, the model cell's ``title`` (a clean slug or display name,
e.g. ``claude-opus-5-high`` or ``Claude Fable 5.1 (Max)``) has a trailing
reasoning-effort word (low|medium|high|xhigh|max) stripped off if present,
then the remainder is matched against `models.yaml`'s ids and names by
exact match once every non-alphanumeric character is stripped — this
turned out to already be unambiguous for every case checked by hand (no
false-positive collisions). A resolved effort word becomes an `id@effort`
key unless it equals that model's own `default_effort` (or the model
carries none), in which case it folds into the bare `id`, per the shared
board-file convention.

The brief's own suggestion was to match by score first, extending by name
second. An earlier version of this script did exactly that (nearest
`arena_text_elo`/etc. candidate within a tolerance, rejected only when a
runner-up sat almost as close). Against the real capture it matched
correctly-looking historical bot names as coincidentally-close current
frontier models (e.g. deprecated Arena entries like
``gpt-3.5-turbo-0125`` or ``gemini-1.5-pro-001``, and unrelated names such
as ``KAT-Coder-Pro-V1``, latched onto whichever current model happened to
sit within the tolerance window) — roughly half of all "matched" aliases
were this kind of false positive. Elo scores are simply too dense in the
middle of the ranking for proximity alone to identify a model. This
capture therefore matches by name ONLY; a row that does not resolve by
name is left in `unmatched:` rather than guessed by score, even though
that leaves plenty of genuinely-retired Arena entries unmatched — which is
correct, since most of them have no current catalogue id at all.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = SKILL_DIR / "data" / "boards" / "arena.yaml"
MODELS_YAML = SKILL_DIR / "data" / "models.yaml"
NODE_HELPER = Path(__file__).resolve().parent / "capture_arena.mjs"
NODE_TIMEOUT_S = 900  # 13 page loads x (up to 45s load + 9s pacing), generous margin

EFFORT_WORDS = ("low", "medium", "high", "xhigh", "max")
_HYPHEN_EFFORT_RE = re.compile(
    r"^(?P<base>.+)-(?P<effort>low|medium|high|xhigh|max)$", re.IGNORECASE
)
_TRAILING_PARENS_RE = re.compile(r"^(?P<base>.+?)\s*\((?P<inside>[^()]*)\)\s*$")
_LEADING_NUMBER_RE = re.compile(r"^(-?\d+(?:\.\d+)?)")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")

#: The order score boards are resolved in: Text first (fullest roster),
#: everything else after.
SCORE_BOARD_ORDER = (
    "arena_text_elo",
    "arena_coding_elo",
    "arena_math_elo",
    "arena_hard_prompts",
    "arena_creative_elo",
    "arena_instr_follow",
    "arena_longer_query",
    "arena_multiturn_elo",
    "arena_expert_elo",
    "arena_webdev_elo",
    "arena_search_elo",
    "arena_document_elo",
)
#: Agent board column header -> output board key.
AGENT_METRICS: dict[str, str] = {
    "Net Improvement": "arena_agent_net_impr",
    "Confirmed Success": "arena_agent_success",
    "Steerability": "arena_agent_steer",
    "Bash Recovery": "arena_agent_bash_recovery",
    "Tool Hallucination": "arena_agent_tool_halluc",
}
TITLES: dict[str, str] = {
    "arena_text_elo": "Arena Text leaderboard, overall (style control on)",
    "arena_coding_elo": "Arena Text leaderboard, coding category (style control on)",
    "arena_math_elo": "Arena Text leaderboard, math category (style control on)",
    "arena_hard_prompts": "Arena Text leaderboard, hard prompts category (style control on)",
    "arena_creative_elo": "Arena Text leaderboard, creative writing category (style control on)",
    "arena_instr_follow": "Arena Text leaderboard, instruction following category (style control on)",
    "arena_longer_query": "Arena Text leaderboard, longer query category (style control on)",
    "arena_multiturn_elo": "Arena Text leaderboard, multi-turn category (style control on)",
    "arena_expert_elo": "Arena Text leaderboard, expert category (style control on)",
    "arena_webdev_elo": "Arena WebDev leaderboard, own Elo scale",
    "arena_search_elo": "Arena Search leaderboard",
    "arena_document_elo": "Arena Document leaderboard",
    "arena_agent_net_impr": "Arena Agent leaderboard: net improvement",
    "arena_agent_success": "Arena Agent leaderboard: confirmed success",
    "arena_agent_steer": "Arena Agent leaderboard: steerability",
    "arena_agent_bash_recovery": "Arena Agent leaderboard: bash recovery",
    "arena_agent_tool_halluc": "Arena Agent leaderboard: tool hallucination (negated: higher is fewer)",
}


class CaptureError(Exception):
    """A capture step failed loudly; there is no partial write after this."""


@dataclass
class Catalogue:
    """The bits of `models.yaml` this capture needs: id/name lookup."""

    by_slug: dict[str, str]
    by_name: dict[str, str]
    default_effort: dict[str, str]
    known_efforts: dict[str, set[str]]


def normalize(raw: str) -> str:
    """Lowercase and drop every non-alphanumeric character."""
    return _NON_ALNUM_RE.sub("", raw.lower())


def strip_effort_suffix(raw: str) -> tuple[str, str | None]:
    """Split a trailing reasoning-effort word off a model title.

    Handles both a hyphen slug suffix (``claude-opus-5-high``) and a
    trailing parenthetical that contains one (``Claude Fable 5.1 (Max)``,
    ``... (Adaptive Reasoning, Max Effort, Default Fallback)``). Some
    titles carry more than one trailing parenthetical group, e.g.
    ``DeepSeek V4 Pro (High) (0813)`` — the effort word can be in an
    earlier group than the last one, so each group is peeled off in turn
    (starting from the last) until one contains an effort word or none are
    left; a non-effort group (a date stamp, a harness name, ...) is
    dropped along the way rather than blocking the search.
    """
    match = _HYPHEN_EFFORT_RE.match(raw)
    if match:
        return match.group("base"), match.group("effort").lower()

    base = raw
    while True:
        match = _TRAILING_PARENS_RE.match(base)
        if not match:
            break
        words = re.findall(r"[A-Za-z]+", match.group("inside").lower())
        for word in words:
            if word in EFFORT_WORDS:
                return match.group("base").strip(), word
        base = match.group("base").strip()  # not an effort group; peel it and keep looking
    return raw, None


def parse_leading_number(text: str) -> float | None:
    """The leading signed number in `text`, ignoring any CI/units/flags after it."""
    match = _LEADING_NUMBER_RE.match(text.strip())
    return float(match.group(1)) if match else None


def parse_int_commas(text: str) -> int | None:
    stripped = text.strip().replace(",", "")
    return int(stripped) if stripped.isdigit() else None


def load_catalogue(path: Path) -> Catalogue:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    by_slug: dict[str, str] = {}
    by_name: dict[str, str] = {}
    default_effort: dict[str, str] = {}
    known_efforts: dict[str, set[str]] = {}

    for model in raw.get("models") or []:
        model_id = str(model["id"])
        slug = model_id.split("/", 1)[-1]
        by_slug.setdefault(normalize(slug), model_id)
        name = model.get("name")
        if name:
            by_name.setdefault(normalize(str(name)), model_id)
        effort = model.get("default_effort")
        if effort:
            default_effort[model_id] = str(effort)
        known_efforts[model_id] = set((model.get("scores_by_effort") or {}).keys())

    return Catalogue(
        by_slug=by_slug,
        by_name=by_name,
        default_effort=default_effort,
        known_efforts=known_efforts,
    )


def resolve_key(model_id: str, effort: str | None, catalogue: Catalogue) -> str:
    """`id`, or `id@effort` when `effort` is not that model's own default."""
    if effort is None or effort == catalogue.default_effort.get(model_id):
        return model_id
    return f"{model_id}@{effort}"


def match_by_name(raw_title: str, catalogue: Catalogue) -> tuple[str, str | None] | None:
    base, effort = strip_effort_suffix(raw_title)
    model_id = catalogue.by_slug.get(normalize(base)) or catalogue.by_name.get(normalize(base))
    if model_id:
        return model_id, effort
    # Some ids genuinely end in what looks like an effort word; try the
    # untouched title too before giving up on name-matching.
    model_id = catalogue.by_slug.get(normalize(raw_title)) or catalogue.by_name.get(
        normalize(raw_title)
    )
    if model_id:
        return model_id, None
    return None


@dataclass
class ResolvedRow:
    key: str  # `id` or `id@effort`, ready to use as a `values:`/`votes:` map key


def resolve_row(
    raw_title: str,
    catalogue: Catalogue,
    alias_cache: dict[str, str],
) -> ResolvedRow | None:
    if raw_title in alias_cache:
        return ResolvedRow(key=alias_cache[raw_title])

    named = match_by_name(raw_title, catalogue)
    if named is not None:
        model_id, effort = named
        key = resolve_key(model_id, effort, catalogue)
        alias_cache[raw_title] = key
        return ResolvedRow(key=key)

    # No score-based fallback: on the real capture this matched ~190 rows
    # (mostly retired/deprecated Arena entries with no current catalogue id
    # at all, e.g. "gpt-3.5-turbo-0125", "gemini-1.5-pro-001") to whichever
    # unrelated current model happened to sit within `tolerance` Elo of it,
    # producing aliases like "KAT-Coder-Pro-V1" -> a Gemini id that share no
    # name overlap whatsoever. Score proximity alone is not a reliable
    # identity signal in the dense middle of an Elo ranking; a row that
    # doesn't resolve by name is genuinely unmatched.
    return None


def cell_text(cell: dict[str, Any] | None) -> str:
    return str(cell.get("text", "")) if cell else ""


def cell_title(cell: dict[str, Any] | None) -> str:
    if not cell:
        return ""
    title = cell.get("title")
    return str(title) if title else cell_text(cell)


@dataclass
class CaptureResult:
    source: dict[str, Any]
    boards: dict[str, Any]
    aliases: dict[str, str]
    unmatched: list[str]
    notes: list[str] = field(default_factory=list)

    def to_yaml_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "source": self.source,
            "boards": self.boards,
            "aliases": dict(sorted(self.aliases.items())),
        }
        if self.unmatched:
            out["unmatched"] = sorted(set(self.unmatched))
        if self.notes:
            out["notes"] = sorted(set(self.notes))
        return out


def build_score_board(
    board_key: str,
    dump: dict[str, Any],
    catalogue: Catalogue,
    alias_cache: dict[str, str],
    unmatched: list[str],
) -> dict[str, Any]:
    headers: list[str] = dump["headers"]
    try:
        model_idx = headers.index("Model")
        score_idx = headers.index("Score")
    except ValueError as exc:
        raise CaptureError(f"{board_key}: expected Model/Score columns, got {headers}") from exc
    votes_idx = headers.index("Votes") if "Votes" in headers else None

    values: dict[str, float] = {}
    votes: dict[str, int] = {}
    for row in dump["rows"]:
        raw_title = cell_title(row[model_idx])
        score_value = parse_leading_number(cell_text(row[score_idx]))
        resolved = resolve_row(raw_title, catalogue, alias_cache)
        if resolved is None:
            unmatched.append(raw_title)
            continue
        if score_value is not None and resolved.key not in values:
            values[resolved.key] = score_value
            if votes_idx is not None:
                vote_count = parse_int_commas(cell_text(row[votes_idx]))
                if vote_count is not None:
                    votes[resolved.key] = vote_count

    style_control = dump.get("style_control")
    board: dict[str, Any] = {
        "title": TITLES[board_key],
        "unit": "elo",
        "higher_is_better": True,
        "style_control": style_control,
        "values": dict(sorted(values.items())),
    }
    if votes:
        board["votes"] = dict(sorted(votes.items()))
    return board


def build_agent_boards(
    dump: dict[str, Any],
    catalogue: Catalogue,
    alias_cache: dict[str, str],
    unmatched: list[str],
) -> dict[str, dict[str, Any]]:
    headers: list[str] = dump["headers"]
    if "Model" not in headers:
        raise CaptureError(f"arena_agent: expected a Model column, got {headers}")
    model_idx = headers.index("Model")
    metric_idx = {name: headers.index(name) for name in AGENT_METRICS if name in headers}
    if not metric_idx:
        raise CaptureError(f"arena_agent: none of the tracked metric columns found in {headers}")

    values: dict[str, dict[str, float]] = {board_key: {} for board_key in AGENT_METRICS.values()}
    for row in dump["rows"]:
        raw_title = cell_title(row[model_idx])
        # Name-matching only: no single "the" ground-truth score exists for
        # a row spanning five different metric columns.
        resolved = resolve_row(raw_title, catalogue, alias_cache)
        if resolved is None:
            unmatched.append(raw_title)
            continue
        for metric_name, board_key in AGENT_METRICS.items():
            idx = metric_idx.get(metric_name)
            if idx is None:
                continue
            cell = row[idx]
            magnitude = parse_leading_number(cell_text(cell))
            if magnitude is None:
                continue
            signed = -magnitude if cell.get("direction") == "Down" else magnitude
            if resolved.key not in values[board_key]:
                values[board_key][resolved.key] = signed

    boards: dict[str, Any] = {}
    style_control = dump.get("style_control")
    for board_key, board_values in values.items():
        if not board_values:
            continue
        boards[board_key] = {
            "title": TITLES[board_key],
            "unit": "fraction",
            "higher_is_better": True,
            "style_control": style_control,
            "values": dict(sorted(board_values.items())),
        }
    return boards


def build_capture(
    catalogue: Catalogue,
    boards_json: dict[str, Any],
    errors_json: dict[str, str],
    *,
    captured_on: str,
) -> CaptureResult:
    alias_cache: dict[str, str] = {}
    unmatched: list[str] = []
    boards: dict[str, Any] = {}
    notes: list[str] = [
        "Vote counts are stored as a `votes:` map, a sibling of `values:`, on "
        "every score board (the Agent board has no comparable counter).",
        "arena_agent_tool_halluc is stored negated from its on-screen "
        "percentage (the page shows an unsigned number plus an up/down trend "
        "icon; a 'Down' icon means the true value is negative) so that, "
        "consistent with the other four Agent metrics, higher stays better.",
    ]
    skipped: list[str] = []

    for board_key in SCORE_BOARD_ORDER:
        dump = boards_json.get(board_key)
        if dump is None or not dump.get("rows"):
            reason = errors_json.get(board_key, "no rows captured")
            skipped.append(f"{board_key}: {reason}")
            continue
        boards[board_key] = build_score_board(board_key, dump, catalogue, alias_cache, unmatched)

    agent_dump = boards_json.get("arena_agent")
    if agent_dump is None or not agent_dump.get("rows"):
        reason = errors_json.get("arena_agent", "no rows captured")
        skipped.append(f"arena_agent (5 metric boards): {reason}")
    else:
        boards.update(build_agent_boards(agent_dump, catalogue, alias_cache, unmatched))

    if skipped:
        notes.append(
            "Boards skipped this capture (left out, not written empty): " + "; ".join(skipped)
        )

    source = {
        "title": "arena.ai public leaderboards",
        "url": "https://arena.ai/leaderboard",
        "captured": captured_on,
        "method": "playwright scrape",
    }
    return CaptureResult(
        source=source, boards=boards, aliases=alias_cache, unmatched=unmatched, notes=notes
    )


def run_node_helper() -> tuple[dict[str, Any], dict[str, str]]:
    if not NODE_HELPER.is_file():
        raise CaptureError(f"missing Node helper: {NODE_HELPER}")
    proc = subprocess.run(
        ["node", str(NODE_HELPER)],
        capture_output=True,
        text=True,
        timeout=NODE_TIMEOUT_S,
        check=False,
    )
    for line in proc.stderr.splitlines():
        logger.info(f"capture_arena.mjs: {line}")
    if proc.returncode != 0:
        raise CaptureError(f"capture_arena.mjs exited {proc.returncode}: {proc.stderr[-2000:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CaptureError("capture_arena.mjs did not print valid JSON") from exc
    return payload.get("boards") or {}, payload.get("errors") or {}


def run_capture(*, dry_run: bool) -> CaptureResult:
    catalogue = load_catalogue(MODELS_YAML)
    boards_json, errors_json = run_node_helper()
    result = build_capture(
        catalogue, boards_json, errors_json, captured_on=datetime.now(UTC).date().isoformat()
    )
    if not result.boards:
        raise CaptureError("every board failed to capture; refusing to write an empty arena.yaml")
    if dry_run:
        logger.info("--dry-run: not writing to disk")
    return result


ARENA_YAML_HEADER = """\
# arena.ai public leaderboard capture (scripts/capture_arena.py owns this file).
#
# Vote counts live in a `votes:` map, a sibling of each score board's
# `values:` map (the Agent board has no comparable counter to record).
# `style_control` is recorded per board from what the live page actually
# showed at capture time, not carried over from any earlier capture. The
# capture turns the toggle ON when a board offers one, so every board with
# a toggle is `true`; `style_control: null` means the board's page has no
# style-control toggle at all (observed for the five arena_agent_* metric
# boards, and possibly arena_webdev_elo/arena_search_elo/arena_document_elo
# depending on what the live page actually offers at capture time).
"""


def write_board(result: CaptureResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        result.to_yaml_dict(), sort_keys=True, default_flow_style=False, allow_unicode=True
    )
    out_path.write_text(ARENA_YAML_HEADER + body, encoding="utf-8")


@logger.catch(reraise=True)
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

    try:
        result = run_capture(dry_run=args.dry_run)
    except CaptureError as exc:
        logger.error(str(exc))
        return 1

    n_boards = len(result.boards)
    n_matched = len(result.aliases)
    n_unmatched = len(set(result.unmatched))
    logger.info(f"{n_boards} boards, {n_matched} matched names, {n_unmatched} unmatched")
    if result.unmatched:
        logger.warning(f"unmatched: {', '.join(sorted(set(result.unmatched))[:20])}")

    if args.dry_run:
        print(yaml.safe_dump(result.to_yaml_dict(), sort_keys=True, default_flow_style=False))
        return 0

    write_board(result, args.out)
    logger.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
