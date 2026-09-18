#!/usr/bin/env python3
"""Recompute ``data/pipeline_steps.yaml`` medians from the run journal.

The 2026-09-16 numbers in that file were hand-aggregated from 41 runs'
journals. This script reproduces that aggregation mechanically, against
the same source: DBOS's own event journal, ``dbos.operation_outputs``,
where every ``journal_event_step`` call writes one row whose ``output``
column is a base64-pickled message dict (see
``aii_lib/src/aii_lib/run/events/_query/_decode.py`` and
``aii_lib/src/aii_lib/run/events/_query/_sql.py`` for the same pattern
used elsewhere in this repo).

Population rule (unchanged from the 2026-09-16 method): one sample per
``task_end`` event, grouped by the pipeline step its ``task_id`` maps to.
Non-LLM steps (``_1_gen_repo``, ``_5_deploy_gh``) never emit a task_id
that maps to a step, so they drop out on their own.

Per occurrence, the DBOS ``workflow_uuid`` column of the row is the
attempt-scoping key (not just ``task_id``, which stays constant across a
hot-resume rerun per the node-id stability contract in
``aii_lib/src/aii_lib/run/node_id.py``): a task's ``task_start``/
``task_end`` pair and every ``agent_summary`` emitted while it ran share
one ``workflow_uuid``, exactly the grouping key
``aii_server/dashboard/services/run_cost.py::aggregate_run_cost`` uses
for the same journal. Minutes come from wall-clock
``task_end.end_at - task_start.end_at`` (``agent_summary.extras
.runtime_seconds`` is observed to be always 0.0 in this journal, so it
is not a usable source); tool_calls/cost/tokens are summed across every
``agent_summary`` row sharing that ``workflow_uuid``.

Read-only: this only ever runs SELECT against the journal. The dev
cluster is live (see the repo's ``conftest.py``), so this never writes
to it.
"""

from __future__ import annotations

import base64
import pickle  # nosec B403 - decoding our own journal, mirrors _query/_decode.py
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import yaml
from loguru import logger

SKILL_DIR = Path(__file__).resolve().parent.parent
PIPELINE_STEPS_YAML = SKILL_DIR / "data" / "pipeline_steps.yaml"

DEFAULT_SOCKET_DIR = "/home/<user>/projects/research-monorepo/aii_data/db/sock"
DEFAULT_DBNAME = "aii_pipeline_dbos_sys"

_HASH_SUFFIX_RE = re.compile(r"_[0-9a-f]{12}$")
_IDX_SUFFIX_RE = re.compile(r"_\d+$")

# Stable name (after stripping the uuid5 hash suffix and the trailing
# per-type index) -> pipeline_steps.yaml step key. Built by reading the
# actual task-name emitters (aii_pipeline/src/aii_pipeline/steps/**), not
# guessed: ``gen_art_<type>_<idx>`` -> ``execute.<type>``,
# ``gen_plan_<type>_<idx>`` -> ``gen_plan.<type>``, everything else is a
# direct 1:1 rename. ``gen_art_demo_<type>`` is a dead pre-rename alias
# for the same ``gen_demo_art`` step (no current emitter produces it;
# confirmed via git log on _3_gen_demo_art.py), so it folds into
# ``gen_demo_art`` too. ``gen_viz_resume_<idx>`` is the resume path of
# the same gen_viz task, not a different step.
_ARTIFACT_TYPES = ("experiment", "research", "dataset", "evaluation", "proof")

STEP_ALIASES: dict[str, str] = {
    "gen_hypo": "gen_hypo",
    "gen_full_paper": "gen_full_paper",
    "gen_paper_text": "gen_paper_text",
    "gen_viz": "gen_viz",
    "gen_viz_resume": "gen_viz",
    "review_paper": "review_paper",
    "review_hypo": "review_hypo",
    "gen_strat": "gen_strat",
    "upd_hypo": "upd_hypo",
}
for _t in _ARTIFACT_TYPES:
    STEP_ALIASES[f"gen_art_{_t}"] = f"execute.{_t}"
    STEP_ALIASES[f"gen_plan_{_t}"] = f"gen_plan.{_t}"
    STEP_ALIASES[f"gen_demo_art_{_t}"] = "gen_demo_art"
    STEP_ALIASES[f"gen_art_demo_{_t}"] = "gen_demo_art"  # dead pre-rename alias

# gen_plan.proof and execute.proof both exist as *task ids* in the
# journal, but data/pipeline_steps.yaml only carries a gen_plan.* row
# for experiment/research/dataset/evaluation, not proof. Recomputing
# "every existing per-step median" means every row already in the yaml
# — adding a brand-new gen_plan.proof row is out of scope for this
# script; see the report for the raw count instead.
KNOWN_BUT_UNMAPPED_YAML_ROWS: frozenset[str] = frozenset({"gen_plan.proof"})
STEP_ALIASES["gen_plan_proof"] = "gen_plan.proof"  # kept for counting only


def derive_step(task_id: str) -> str | None:
    """Map a task_end's ``task_id`` to a pipeline_steps.yaml step key.

    Strips the trailing uuid5 hash suffix (``strip_hash_suffix`` in
    ``aii_lib.run.node_id``) and the trailing per-type index, then looks
    the stable name up in :data:`STEP_ALIASES`. Returns ``None`` for
    anything unrecognized (git-plumbing steps, or task ids belonging to
    an unrelated subsystem sharing this journal).
    """
    stripped = _HASH_SUFFIX_RE.sub("", task_id)
    stripped = _IDX_SUFFIX_RE.sub("", stripped)
    return STEP_ALIASES.get(stripped)


@dataclass
class _Attempt:
    """Everything one task_end occurrence contributes to its step's medians."""

    task_start_end_at: datetime | None = None
    task_end_end_at: datetime | None = None
    status: str | None = None
    task_id: str | None = None
    total_cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    tool_calls: int = 0
    has_summary: bool = False


@dataclass
class ConnParams:
    """Read-only connection target for the journal's Postgres cluster."""

    socket_dir: str = DEFAULT_SOCKET_DIR
    port: int = 5432
    dbname: str = DEFAULT_DBNAME
    user: str | None = None

    def conninfo(self) -> str:
        import os

        user = self.user or os.environ["USER"]
        return f"host={self.socket_dir} port={self.port} dbname={self.dbname} user={user}"


def _decode_row(raw: str | bytes | None) -> dict[str, Any] | None:
    """Decode one ``operation_outputs.output`` cell to its message dict.

    Mirrors ``decode_output_raw`` in
    ``aii_lib/src/aii_lib/run/events/_query/_decode.py``: base64 then
    pickle, both wrapped since a handful of rows in this journal predate
    the current wire schema and fail to unpickle cleanly — those are
    skipped, not fatal.
    """
    if raw is None:
        return None
    try:
        obj = pickle.loads(base64.b64decode(raw))  # nosec B301 - our own journal
    except (pickle.PickleError, EOFError, ValueError, TypeError) as exc:
        logger.debug(f"skipping undecodable journal row: {exc}")
        return None
    return obj if isinstance(obj, dict) else None


def iter_journal_messages(conn: psycopg.Connection) -> Any:
    """Stream ``(workflow_uuid, decoded_message)`` for every journal row.

    Uses a server-side cursor so the ~455k-row scan (measured at ~30s
    locally) never materializes the whole result set in the client.
    """
    with conn.cursor(name="aggregate_steps_scan") as cur:
        cur.itersize = 5000
        cur.execute(
            "SELECT workflow_uuid, output FROM dbos.operation_outputs "
            "WHERE function_name = 'journal_event_step'"
        )
        for workflow_uuid, raw in cur:
            msg = _decode_row(raw)
            if msg is not None:
                yield workflow_uuid, msg


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect_attempts(rows: Any) -> dict[str, _Attempt]:
    """Fold streamed ``(workflow_uuid, message)`` pairs into one :class:`_Attempt` per workflow.

    ``rows`` is any iterable of ``(workflow_uuid, message_dict)`` — either
    :func:`iter_journal_messages` against the live journal, or a fixture
    list in tests.
    """
    attempts: dict[str, _Attempt] = defaultdict(_Attempt)
    for workflow_uuid, msg in rows:
        mtype = msg.get("type")
        attempt = attempts[workflow_uuid]
        if mtype == "task_start":
            attempt.task_start_end_at = _parse_ts(msg.get("end_at"))
        elif mtype == "task_end":
            attempt.task_end_end_at = _parse_ts(msg.get("end_at"))
            attempt.status = msg.get("status")
            attempt.task_id = msg.get("task_id")
        elif mtype == "agent_summary":
            attempt.has_summary = True
            attempt.total_cost += float(msg.get("total_cost") or 0.0)
            attempt.input_tokens += int(msg.get("input_tokens") or 0)
            attempt.output_tokens += int(msg.get("output_tokens") or 0)
            attempt.cache_read_tokens += int(msg.get("cache_read_tokens") or 0)
            extras = msg.get("extras") or {}
            tool_calls = extras.get("tool_calls") or {}
            if isinstance(tool_calls, dict):
                attempt.tool_calls += sum(
                    v for v in tool_calls.values() if isinstance(v, (int, float))
                )
    return attempts


@dataclass
class StepStats:
    """The aggregate a step's :class:`_Attempt` population rolls up into."""

    n: int = 0
    failures: int = 0
    tool_calls: list[int] = field(default_factory=list)
    minutes: list[float] = field(default_factory=list)
    cost_usd: list[float] = field(default_factory=list)
    input_tokens: list[int] = field(default_factory=list)
    output_tokens: list[int] = field(default_factory=list)
    cache_read_tokens: list[int] = field(default_factory=list)


def aggregate_by_step(
    attempts: dict[str, _Attempt],
) -> tuple[dict[str, StepStats], dict[str, int]]:
    """Group attempts by step name and return (per-step stats, unmapped-prefix counts)."""
    by_step: dict[str, StepStats] = defaultdict(StepStats)
    unmapped: dict[str, int] = defaultdict(int)
    for attempt in attempts.values():
        task_id = getattr(attempt, "task_id", None)
        if not task_id or attempt.task_end_end_at is None:
            continue
        step = derive_step(task_id)
        if step is None:
            stripped = _IDX_SUFFIX_RE.sub("", _HASH_SUFFIX_RE.sub("", task_id))
            unmapped[stripped] += 1
            continue
        stats = by_step[step]
        stats.n += 1
        if attempt.status != "done":
            stats.failures += 1
        if attempt.has_summary:
            stats.tool_calls.append(int(attempt.tool_calls))
            stats.cost_usd.append(attempt.total_cost)
            stats.input_tokens.append(attempt.input_tokens)
            stats.output_tokens.append(attempt.output_tokens)
            if attempt.cache_read_tokens:
                stats.cache_read_tokens.append(attempt.cache_read_tokens)
        if attempt.task_start_end_at is not None:
            delta = (attempt.task_end_end_at - attempt.task_start_end_at).total_seconds() / 60.0
            if delta >= 0:
                stats.minutes.append(delta)
    return by_step, unmapped


def count_root_runs(*, conn: psycopg.Connection, workflow_uuids: set[str]) -> int:
    """Count distinct root ``run_pipeline_workflow`` ancestors of ``workflow_uuids``.

    Walks ``dbos.workflow_status.parent_workflow_id`` in Python (the
    table is small — ~52k rows — so one bulk fetch beats a recursive
    query per id) because the workflow_uuid string format itself changed
    across schema eras and cannot be parsed reliably.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT workflow_uuid, parent_workflow_id FROM dbos.workflow_status")
        parent_of = dict(cur.fetchall())

    roots: set[str] = set()
    for wf in workflow_uuids:
        seen: set[str] = set()
        cur_id: str | None = wf
        root = wf
        while cur_id and cur_id not in seen:
            seen.add(cur_id)
            root = cur_id
            cur_id = parent_of.get(cur_id)
        roots.add(root)
    return len(roots)


def _median_int(values: list[int | float]) -> int | None:
    return round(statistics.median(values)) if values else None


def _median_float(values: list[float], *, ndigits: int) -> float | None:
    return round(statistics.median(values), ndigits) if values else None


def build_step_update(stats: StepStats) -> dict[str, Any]:
    """Build the numeric-field update for one existing yaml step entry."""
    update: dict[str, Any] = {"n": stats.n}
    if stats.tool_calls:
        update["tool_calls_median"] = _median_int(stats.tool_calls)
    if stats.minutes:
        update["minutes_median"] = _median_int(stats.minutes)
    if stats.cost_usd:
        update["cost_usd_median"] = _median_float(stats.cost_usd, ndigits=2)
    if stats.input_tokens:
        update["input_tokens_median"] = _median_int(stats.input_tokens)
    if stats.output_tokens:
        update["output_tokens_median"] = _median_int(stats.output_tokens)
    if stats.cache_read_tokens:
        update["cache_read_tokens_median"] = _median_int(stats.cache_read_tokens)
    update["failure_rate"] = round(stats.failures / stats.n, 2) if stats.n else None
    return update


_LEVEL_BOUNDARY_HINT = (
    "levels are cut by hand from these numbers; report only, never relevel automatically"
)

# Canonical on-disk order of a step's numeric fields, observed across
# every existing entry in pipeline_steps.yaml. note/failure_note are
# always the last lines of a step block (verified against every entry
# in the file) and are never touched by this script — they are
# hand-authored editorial text (review scores, failure-mode
# descriptions) a mechanical aggregation has no basis to rewrite.
NUMERIC_FIELD_ORDER = (
    "n",
    "tool_calls_median",
    "minutes_median",
    "cost_usd_median",
    "input_tokens_median",
    "output_tokens_median",
    "cache_read_tokens_median",
    "failure_rate",
)
FREETEXT_FIELD_ORDER = ("failure_note", "note")

_STEP_HEADER_RE = re.compile(r"^  - step: ")
_FIELD_LINE_RE = re.compile(r"^    (\w+):\s?(.*)$")


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text in ("null", "~", ""):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def split_step_chunks(steps_block: str) -> list[str]:
    """Split the ``steps:`` block body into one raw text chunk per step entry."""
    chunks: list[str] = []
    current: list[str] = []
    for line in steps_block.splitlines(keepends=True):
        if _STEP_HEADER_RE.match(line) and current:
            chunks.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("".join(current))
    return chunks


def patch_step_chunk(chunk: str, update: dict[str, Any]) -> str:
    """Rewrite one step's numeric fields in place, verbatim otherwise.

    Preserves the first three lines (``step``/``group``/``level``)
    untouched, reconstructs the numeric-field lines in
    :data:`NUMERIC_FIELD_ORDER` (filling in any that were previously
    absent, e.g. a step that had ``n: 0`` and no medians at all), and
    re-appends any ``failure_note``/``note`` block byte-for-byte at the
    end, exactly where it already was.
    """
    lines = chunk.splitlines(keepends=True)
    top, rest = lines[:3], lines[3:]

    numeric_values: dict[str, Any] = {}
    freetext_blocks: dict[str, list[str]] = {}
    i = 0
    while i < len(rest):
        m = _FIELD_LINE_RE.match(rest[i])
        if not m:
            i += 1
            continue
        key, inline_val = m.group(1), m.group(2)
        if key in NUMERIC_FIELD_ORDER:
            numeric_values[key] = _parse_scalar(inline_val)
            i += 1
        elif key in FREETEXT_FIELD_ORDER:
            block = [rest[i]]
            i += 1
            while i < len(rest) and not _FIELD_LINE_RE.match(rest[i]):
                block.append(rest[i])
                i += 1
            freetext_blocks[key] = block
        else:
            i += 1  # unrecognized field — never seen in this file, skip defensively

    for key, value in update.items():
        if key in NUMERIC_FIELD_ORDER and value is not None:
            numeric_values[key] = value

    out = list(top)
    for key in NUMERIC_FIELD_ORDER:
        if key in numeric_values:
            out.append(f"    {key}: {_format_scalar(numeric_values[key])}\n")
    for key in FREETEXT_FIELD_ORDER:
        if key in freetext_blocks:
            out.extend(freetext_blocks[key])
    if chunk.endswith("\n\n") and not "".join(out).endswith("\n\n"):
        out.append("\n")  # preserve the blank separator line between entries
    return "".join(out)


def rewrite_pipeline_steps_yaml(
    *,
    path: Path,
    updates: dict[str, dict[str, Any]],
    runs_sampled: int,
    run_date: str,
) -> list[str]:
    """Surgically patch ``pipeline_steps.yaml`` in place; return level-boundary warnings.

    Works on the raw text rather than a yaml load/dump round-trip so
    the header comments, the ``levels:`` prose, comment placement and
    every step's existing formatting survive untouched — only the
    ``evidence:`` block and each step's numeric fields change.
    """
    raw_text = path.read_text(encoding="utf-8")
    lines = raw_text.splitlines(keepends=True)

    steps_idx = next(i for i, line in enumerate(lines) if line.startswith("steps:"))
    head = "".join(lines[:steps_idx])
    steps_block = "".join(lines[steps_idx + 1 :])

    old_runs_sampled_m = re.search(r"runs_sampled: (\d+)", head)
    old_date_m = re.search(r"date: ([\d-]+)", head)
    old_runs_sampled = old_runs_sampled_m.group(1) if old_runs_sampled_m else "?"
    old_date = old_date_m.group(1) if old_date_m else "?"

    head = re.sub(r"runs_sampled: \d+", f"runs_sampled: {runs_sampled}", head)
    head = re.sub(r"date: [\d-]+", f"date: {run_date}", head)
    head = re.sub(
        r"  method: >-\n(?:    .*\n)+",
        "  method: >-\n"
        "    Median over task_end events per step, aggregated by\n"
        "    scripts/aggregate_steps.py directly from the DBOS run\n"
        "    journal (dbos.operation_outputs); failures counted as any\n"
        "    task_end event with status != 'done'.\n",
        head,
    )
    # The header comment duplicates runs_sampled/date in prose; keep it
    # in sync rather than leaving a stale claim next to a fresh one.
    head = re.sub(
        rf"{re.escape(old_runs_sampled)} real pipeline runs",
        f"{runs_sampled} real pipeline runs",
        head,
    )
    head = re.sub(
        rf"{re.escape(old_date)} \({re.escape(old_runs_sampled)} runs sampled",
        f"{run_date} ({runs_sampled} runs sampled",
        head,
    )

    chunks = split_step_chunks(steps_block)
    new_chunks = []
    warnings: list[str] = []
    for chunk in chunks:
        step_m = re.match(r"  - step: (\S.*)\n", chunk)
        step_name = step_m.group(1) if step_m else None
        update = updates.get(step_name)
        if update is None:
            new_chunks.append(chunk)
            continue
        level_m = re.search(r"    level: (\d+)", chunk)
        n_m = re.search(r"    n: (\d+)", chunk)
        old_level = level_m.group(1) if level_m else None
        old_n = n_m.group(1) if n_m else None
        new_chunks.append(patch_step_chunk(chunk, update))
        if old_n != str(update.get("n")):
            logger.info(f"{step_name}: n {old_n} -> {update.get('n')}")
        if old_level is not None:
            warnings.append(
                f"{step_name}: level={old_level} left unchanged ({_LEVEL_BOUNDARY_HINT})"
            )

    new_text = head + "steps:\n" + "".join(new_chunks)
    try:
        yaml.safe_load(new_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"aggregate_steps.py produced invalid yaml, not writing: {exc}") from exc

    path.write_text(new_text, encoding="utf-8")
    return warnings


def run(*, conn_params: ConnParams | None = None) -> dict[str, Any]:
    """Run the full aggregation against the live journal and rewrite the yaml.

    Returns a report dict with the before/after per-step numbers, the
    runs sampled and any unmapped task-id prefixes seen more than once
    (candidates for a future STEP_ALIASES entry).
    """
    conn_params = conn_params or ConnParams()
    logger.info(f"connecting read-only to {conn_params.dbname} via {conn_params.socket_dir}")
    with psycopg.connect(conn_params.conninfo()) as conn:
        conn.read_only = True
        attempts = collect_attempts(iter_journal_messages(conn))
        by_step, unmapped = aggregate_by_step(attempts)
        sampled_workflow_uuids = {
            wf
            for wf, a in attempts.items()
            if getattr(a, "task_id", None) and derive_step(a.task_id) is not None
        }
        runs_sampled = count_root_runs(conn=conn, workflow_uuids=sampled_workflow_uuids)

    updates = {step: build_step_update(stats) for step, stats in by_step.items()}
    run_date = datetime.now(UTC).date().isoformat()
    warnings = rewrite_pipeline_steps_yaml(
        path=PIPELINE_STEPS_YAML,
        updates=updates,
        runs_sampled=runs_sampled,
        run_date=run_date,
    )
    for w in warnings:
        logger.warning(w)

    frequent_unmapped = {k: v for k, v in unmapped.items() if v >= 5}
    if frequent_unmapped:
        logger.warning(f"unmapped task-id prefixes seen >=5 times: {frequent_unmapped}")

    return {
        "runs_sampled": runs_sampled,
        "updates": updates,
        "unmapped": frequent_unmapped,
    }


def main() -> None:
    logger.add(SKILL_DIR / "scripts" / "aggregate_steps.log", rotation="1 MB")
    report = run()
    logger.info(f"runs_sampled={report['runs_sampled']}")
    for step, update in sorted(report["updates"].items()):
        logger.info(f"{step}: {update}")


if __name__ == "__main__":
    main()
