#!/usr/bin/env python3
"""Capture the Artificial Analysis board (`data/boards/aa.yaml`) for rank_llms.py.

One call, `GET /api/v2/data/llms/models` (header `x-api-key`), returns one
row per (model, reasoning-effort) listing: AA folds the effort into the
`name` string itself, e.g. `"Claude Fable 5.1 (Adaptive Reasoning, Max
Effort, Default Fallback)"` or the terser `"GPT-6 Astra (xhigh)"`. This
capture:

1. strips every trailing `(...)` group off `name` to get the model's
   base name and the tag text inside;
2. reads an effort word out of that tag text — a bare `low|medium|high|
   xhigh|max|minimal`, an `"X Effort"` phrase, or a bare `Reasoning` /
   `Non-reasoning` toggle when no effort word is present;
3. matches the base name to a `models.yaml` id by normalizing both sides
   (lowercase, alphanumeric only) and looking up the catalogue's own
   `name:` field, so `openai/gpt-6-astra`'s `name: GPT-6 Astra` matches
   AA's `"GPT-6 Astra"` regardless of hyphenation;
4. writes `<id>@<effort>` when an effort was found, else the bare `<id>`.

`models.yaml` carries its own AA-sourced ground truth in
`scores_by_effort.<effort>.aa_intelligence_index` (and, for a model whose
untagged top-level `scores.aa_intelligence_index` already IS one effort's
number — see `default_effort`), both tagged `src: aa_leader`. Every one of
those cells is checked against this capture's own
`aa_api_intelligence_index` board and any cell off by more than one point
is reported: the check is "did the name parser wire up the same effort
model.yaml already believes", not a new opinion about the models.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import requests
import yaml
from loguru import logger

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = SKILL_DIR / "data" / "boards" / "aa.yaml"
MODELS_YAML = SKILL_DIR / "data" / "models.yaml"
ENV_FILE = Path.home() / ".config" / "aii" / "llm_bench.env"
API_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
REQUEST_TIMEOUT_S = 60
#: 1 point of Intelligence Index, the tolerance the brief sets for the
#: effort-mapping self-check against models.yaml's own aa_leader numbers.
VALIDATION_TOLERANCE = 1.0
#: A model with no release_date, or one older than this, is not flagged
#: as "current-generation" when it goes unmatched.
CURRENT_GEN_CUTOFF = date(2025, 6, 1)
#: `evaluations` key (as the API spells it) -> board key this skill tracks.
EVAL_KEY_TO_BOARD = {
    "artificial_analysis_intelligence_index": "aa_api_intelligence_index",
    "artificial_analysis_coding_index": "aa_api_coding_index",
    "artificial_analysis_math_index": "aa_api_math_index",
    "hle": "aa_api_hle",
    "gpqa": "aa_api_gpqa",
    "scicode": "aa_api_scicode",
    "lcr": "aa_api_lcr",
    "terminalbench_v2_1": "aa_api_terminalbench_v2_1",
    "terminalbench_hard": "aa_api_terminalbench_hard",
    "tau2": "aa_api_tau2",
    "tau_banking": "aa_api_tau_banking",
    "livecodebench": "aa_api_livecodebench",
    "ifbench": "aa_api_ifbench",
    "aime_25": "aa_api_aime_25",
    "mmlu_pro": "aa_api_mmlu_pro",
    "math_500": "aa_api_math_500",
    "aime": "aa_api_aime",
}
#: Boards on AA's own 0-100 index scale; every other tracked eval is a
#: 0-1 fraction.
INDEX_BOARDS = {"aa_api_intelligence_index", "aa_api_coding_index", "aa_api_math_index"}
EFFORT_WORDS = {"low", "medium", "high", "xhigh", "max", "minimal"}
PAREN_RE = re.compile(r"\(([^()]*)\)\s*$")
EFFORT_LEVEL_RE = re.compile(r"^(low|medium|high|xhigh|max|minimal)(\s+effort)?$")


class CaptureError(Exception):
    """A capture step failed loudly; there is no partial write after this."""


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass
class Catalogue:
    """`models.yaml`, indexed for AA name matching and effort validation."""

    name_index: dict[str, str]
    alias_of: dict[str, str]
    raw_models: list[dict[str, Any]]

    def resolve(self, model_id: str) -> str:
        seen: set[str] = set()
        current = model_id
        while current in self.alias_of and current not in seen:
            seen.add(current)
            current = self.alias_of[current]
        return current

    def match_name(self, name: str) -> str | None:
        return self.name_index.get(norm(name))


def load_catalogue(path: Path) -> Catalogue:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    models = list(raw.get("models") or [])
    alias_of: dict[str, str] = {str(m["id"]): str(m["alias_of"]) for m in models if "alias_of" in m}
    name_index: dict[str, str] = {}
    for model in models:
        model_id = str(model["id"])
        resolved = model_id
        seen: set[str] = set()
        while resolved in alias_of and resolved not in seen:
            seen.add(resolved)
            resolved = alias_of[resolved]
        name = model.get("name")
        if name:
            name_index.setdefault(norm(str(name)), resolved)
        # Fallback: the id's own tail, in case `name:` diverges from AA's title.
        tail = model_id.rsplit("/", 1)[-1]
        name_index.setdefault(norm(tail), resolved)
    return Catalogue(name_index=name_index, alias_of=alias_of, raw_models=models)


def load_api_key() -> str:
    key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
    if key:
        return key
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ARTIFICIAL_ANALYSIS_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise CaptureError(f"ARTIFICIAL_ANALYSIS_API_KEY not set and not found in {ENV_FILE}")


def fetch_models(session: requests.Session, api_key: str) -> list[dict[str, Any]]:
    response = session.get(API_URL, headers={"x-api-key": api_key}, timeout=REQUEST_TIMEOUT_S)
    if response.status_code != 200:
        raise CaptureError(f"GET {API_URL} -> HTTP {response.status_code}: {response.text[:300]!r}")
    try:
        body = response.json()
    except ValueError as exc:
        raise CaptureError(f"GET {API_URL} returned a non-JSON body") from exc
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise CaptureError(
            f"GET {API_URL} response has no data list (status {body.get('status')!r})"
        )
    return rows


def strip_trailing_parens(name: str) -> tuple[str, list[str]]:
    """Peel every trailing `(...)` group off `name`, outermost-last."""
    tags: list[str] = []
    remainder = name.strip()
    while True:
        match = PAREN_RE.search(remainder)
        if not match:
            break
        tags.insert(0, match.group(1).strip())
        remainder = remainder[: match.start()].strip()
    return remainder, tags


def extract_effort(tags: list[str]) -> str | None:
    """A reasoning-effort token out of AA's parenthetical tag list, if any."""
    subtags = [part.strip() for tag in tags for part in tag.split(",")]
    for subtag in subtags:
        match = EFFORT_LEVEL_RE.match(subtag.lower())
        if match:
            return match.group(1)
    for subtag in subtags:
        low = subtag.lower()
        if low == "non-reasoning":
            return "non-reasoning"
        if low == "reasoning":
            return "reasoning"
    return None


def match_model(catalogue: Catalogue, name: str) -> tuple[str | None, str | None]:
    """`(models.yaml id, effort)` for one AA model name, or `(None, effort)`.

    A bare "Reasoning" tag most often means a distinct `-thinking` id in
    this catalogue rather than an effort of the base id, so that
    candidate is tried first; only once it fails to match does "Reasoning"
    fall back to an `@reasoning` suffix on the base id.
    """
    base_name, tags = strip_trailing_parens(name)
    effort = extract_effort(tags)

    if effort == "reasoning":
        for candidate in (f"{base_name} Thinking", f"{base_name} Reasoning"):
            resolved = catalogue.match_name(candidate)
            if resolved is not None:
                return resolved, None  # the id itself carries "thinking"
    resolved = catalogue.match_name(base_name)
    if resolved is not None:
        return resolved, effort
    return None, effort


@dataclass
class CaptureResult:
    source: dict[str, Any]
    boards: dict[str, Any]
    aliases: dict[str, str]
    unmatched: list[str]
    meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_yaml_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "source": self.source,
            "boards": self.boards,
            "aliases": dict(sorted(self.aliases.items())),
        }
        if self.meta:
            out["meta"] = dict(sorted(self.meta.items()))
        if self.unmatched:
            out["unmatched"] = sorted(set(self.unmatched))
        if self.notes:
            out["notes"] = sorted(set(self.notes))
        return out


def build_capture(
    catalogue: Catalogue, rows: list[dict[str, Any]], *, captured_on: str
) -> CaptureResult:
    board_values: dict[str, dict[str, float]] = {board: {} for board in EVAL_KEY_TO_BOARD.values()}
    aliases: dict[str, str] = {}
    unmatched: list[str] = []
    unmatched_current_gen: list[str] = []
    meta: dict[str, dict[str, Any]] = {}

    for row in rows:
        name = str(row.get("name", ""))
        if not name:
            continue
        resolved, effort = match_model(catalogue, name)
        if resolved is None:
            unmatched.append(name)
            release_date_str = row.get("release_date")
            if release_date_str:
                try:
                    if date.fromisoformat(str(release_date_str)) >= CURRENT_GEN_CUTOFF:
                        unmatched_current_gen.append(name)
                except ValueError:
                    pass
            continue

        key = f"{resolved}@{effort}" if effort else resolved
        if key in aliases.values():
            logger.warning(f"{key}: already captured from another AA row; keeping the first")
        aliases[name] = key

        evaluations = row.get("evaluations") or {}
        for eval_key, board_key in EVAL_KEY_TO_BOARD.items():
            value = evaluations.get(eval_key)
            if value is None:
                continue
            if key in board_values[board_key]:
                continue
            board_values[board_key][key] = round(float(value), 6)

        pricing = row.get("pricing") or {}
        meta[key] = {
            "input_per_m": pricing.get("price_1m_input_tokens"),
            "output_per_m": pricing.get("price_1m_output_tokens"),
            "release_date": row.get("release_date"),
        }

    boards: dict[str, Any] = {}
    for board_key, values in sorted(board_values.items()):
        if not values:
            continue
        boards[board_key] = {
            "title": f"Artificial Analysis API: {board_key.removeprefix('aa_api_')}",
            "unit": "index" if board_key in INDEX_BOARDS else "fraction",
            "higher_is_better": True,
            "values": dict(sorted(values.items())),
        }

    source = {
        "title": "Artificial Analysis API",
        "url": API_URL,
        "captured": captured_on,
        "method": "data api",
    }
    notes = []
    if unmatched_current_gen:
        notes.append(
            "unmatched names that look current-generation (release_date >= "
            f"{CURRENT_GEN_CUTOFF.isoformat()}): " + "; ".join(sorted(set(unmatched_current_gen)))
        )
    return CaptureResult(
        source=source, boards=boards, aliases=aliases, unmatched=unmatched, meta=meta, notes=notes
    )


def validate_effort_mapping(catalogue: Catalogue, boards: dict[str, Any]) -> list[str]:
    """Cross-check `aa_api_intelligence_index` against models.yaml's own
    `scores_by_effort.<effort>.aa_intelligence_index` (src `aa_leader`).
    """
    intelligence = (boards.get("aa_api_intelligence_index") or {}).get("values", {})
    mismatches: list[str] = []
    checked = 0
    for model in catalogue.raw_models:
        if "alias_of" in model:
            continue
        model_id = str(model["id"])
        checks: list[tuple[str, float]] = []
        top_scores = model.get("scores") or {}
        top_cell = top_scores.get("aa_intelligence_index")
        default_effort = model.get("default_effort")
        if top_cell and top_cell.get("src") == "aa_leader" and default_effort:
            checks.append((str(default_effort), float(top_cell["value"])))
        for effort, scores in (model.get("scores_by_effort") or {}).items():
            cell = (scores or {}).get("aa_intelligence_index")
            if cell and cell.get("src") == "aa_leader":
                checks.append((str(effort), float(cell["value"])))
        for effort, expected in checks:
            actual = intelligence.get(f"{model_id}@{effort}")
            if actual is None:
                continue
            checked += 1
            if abs(actual - expected) > VALIDATION_TOLERANCE:
                mismatches.append(
                    f"{model_id}@{effort}: models.yaml={expected:g} api={actual:g} "
                    f"diff={actual - expected:+.1f}"
                )
    logger.info(f"effort-mapping validation: {checked} checked, {len(mismatches)} over tolerance")
    return mismatches


def run_capture(*, dry_run: bool) -> tuple[CaptureResult, list[str]]:
    catalogue = load_catalogue(MODELS_YAML)
    api_key = load_api_key()
    session = requests.Session()
    rows = fetch_models(session, api_key)
    logger.info(f"models: {len(rows)} rows")

    result = build_capture(catalogue, rows, captured_on=datetime.now(UTC).date().isoformat())
    mismatches = validate_effort_mapping(catalogue, result.boards)
    if dry_run:
        logger.info("--dry-run: not writing to disk")
    return result, mismatches


def write_board(result: CaptureResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        result.to_yaml_dict(), sort_keys=True, default_flow_style=False, allow_unicode=True
    )
    out_path.write_text(text, encoding="utf-8")


@logger.catch(reraise=True)
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

    try:
        result, mismatches = run_capture(dry_run=args.dry_run)
    except CaptureError as exc:
        logger.error(str(exc))
        return 1

    n_boards = len(result.boards)
    n_matched = len(result.aliases)
    n_unmatched = len(set(result.unmatched))
    logger.info(f"{n_boards} boards, {n_matched} matched names, {n_unmatched} unmatched")
    if mismatches:
        logger.warning(f"effort-mapping mismatches: {'; '.join(mismatches[:20])}")

    if args.dry_run:
        print(yaml.safe_dump(result.to_yaml_dict(), sort_keys=True, default_flow_style=False))
        return 0

    write_board(result, args.out)
    logger.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
