#!/usr/bin/env python3
"""Stop hook: post a one/two-sentence recap of the session via ``claude -p``.

Interactive sessions show no summary of a turn unless the terminal was
unfocused for 5+ minutes (the built-in "away summary"). A long turn watched
the whole time gets nothing. This hook fills that gap: when a turn takes
longer than ``CLAUDE_CODE_RECAP_TURN_SECONDS`` (default 10s, "0" disables
it), it asks a cheap, tool-less ``claude -p`` subprocess to write a recap
for someone re-entering the session cold, and surfaces that via
``systemMessage`` -- the Stop-hook field Claude Code shows the user in the
terminal (see https://code.claude.com/docs/en/hooks.md).

Format: one or two plain sentences, under ``MAX_RECAP_WORDS`` words -- the
overall goal the session was started for and the current task (naming where
the work moved, if it moved), then the one next action. No markdown, no
root-cause narrative, no secondary to-dos. The line leads with a bare "\\n"
so it sits alone starting on the second line.

Verified against the Claude Code 2.1.271 renderer: ``systemMessage`` is
shown as plain gray text, prefixed on its first line with "Stop says: ";
internal newlines and blank lines are preserved; trailing newlines are
trimmed; ANSI escapes are stripped; markdown is NOT rendered; and there is
a hard cap of 4000 characters / 20 lines (silently truncated beyond that).
The recap here stays within its own smaller cap (``MAX_RECAP_CHARS``), well
under that hard cap.

**It never crashes the session.** Every step is wrapped so any failure
(malformed payload, unreadable transcript, subprocess timeout, whatever)
falls through to a quiet exit 0 with no stdout -- the same "warn or stay
silent, never break the turn" discipline as ``guard_destructive_git.py``.

**Recursion guard.** The subprocess this hook spawns is itself a Claude Code
session, which itself fires a Stop hook when it finishes -- potentially this
same script. ``CLAUDE_CODE_RECAP_HOOK_RUNNING=1`` is set on the subprocess's
env and checked first thing on entry, before anything else runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "hooks" / "turn_recap.log"
LOG_MAX_BYTES = 1_000_000
LOG_KEEP_LINES = 200
# Section 1, "Session summary": the compaction-continuation message, if any.
MAX_COMPACTION_SUMMARY_CHARS = 2500
# Section 2, "All user messages so far": every real user message, one per line.
ALL_MESSAGES_BUDGET = 9_000
ALL_MESSAGES_KEEP_HEAD = 5
ALL_MESSAGES_KEEP_TAIL = 15
ALL_MESSAGES_TRUNC_LENGTHS = (300, 200, 120)
# Section 3, "Recent turns in detail": last N real user turns plus what
# happened after each, plus the payload's last_assistant_message.
NUM_CONTEXT_TURNS = 5
MAX_RECENT_USER_MESSAGE_CHARS = 500
RECENT_DETAIL_BUDGET = 9_000
# Total cap across all three sections combined.
MAX_CONTEXT_CHARS = 20_000
SUBPROCESS_TIMEOUT_SECONDS = 45
DEFAULT_THRESHOLD_SECONDS = 10.0
# Output-formatting caps for the recap line (see _format_recap):
# MAX_RECAP_WORDS is enforced first, cutting at the last sentence end at or
# before the cap; MAX_RECAP_CHARS is then an absolute safety net (also cut
# on a sentence boundary), comfortably under the renderer's hard cap of
# 4000 chars / 20 lines.
MAX_RECAP_WORDS = 45
MAX_RECAP_CHARS = 350
# Real-looking user turns that are actually local-command echoes or injected
# system notifications, not something the user said -- excluded from the
# prompt context (but not from the duration check; see _run).
_EXCLUDED_PREFIXES = ("<local-command", "<command-name>", "[SYSTEM NOTIFICATION")
_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
# A leading "<word>: " label the model added on its own (a guessed project
# prefix, a "Note:" preamble, whatever) -- stripped so it never leaks into
# the note. One token: letters/digits/-/_ only.
_LEADING_LABEL_RE = re.compile(r"^[\w-]+:\s*")
# transcript_path is written asynchronously, so the turn's own final text
# block can still be missing when Stop fires. One short wait-and-reread
# before falling back to tool-only context (see _run).
TRANSCRIPT_RETRY_SECONDS = 1.5


def _log(line: str) -> None:
    """Append one line to the log, size-capping the file first.

    Logging is diagnostic only and must never be the reason the hook fails.
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            kept = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[
                -LOG_KEEP_LINES:
            ]
            LOG_PATH.write_text("\n".join(kept) + "\n", encoding="utf-8")
        timestamp = datetime.now(timezone.utc).isoformat()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{timestamp} {line}\n")
    except Exception:
        # This is the logging helper itself: it must never raise or call
        # _log recursively, so a failure here is swallowed silently.
        pass


def _parse_timestamp(value: str) -> datetime | None:
    """Parse a transcript entry's ISO-8601 timestamp (``...Z`` included)."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        # Malformed/missing timestamp on one transcript entry: caller treats
        # None as "skip this entry", the rest of the transcript is unaffected.
        return None


def _is_real_user_message(entry: dict) -> bool:
    """True for a genuine user-typed turn, not a tool_result or meta entry.

    Claude Code stores tool results as ``type: "user"`` messages too (the
    role the model sees them as), so ``type == "user"`` alone is not enough:
    exclude ``isMeta`` system-reminder injections, sidechain (subagent)
    entries, anything carrying ``toolUseResult``, and content whose blocks
    are not plain text/image.
    """
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta") or entry.get("isSidechain"):
        return False
    if "toolUseResult" in entry:
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        block_types = {b.get("type") for b in content if isinstance(b, dict)}
        return bool(block_types) and block_types <= {"text", "image"}
    return False


def _extract_user_text(entry: dict) -> str:
    """Full plain text of a real user message, untruncated."""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    else:
        text = ""
    return text.strip()


def _find_last_user_turns(lines: list[str], count: int) -> list[tuple[int, datetime]]:
    """Return up to ``count`` most recent real user turns, oldest first.

    Used only for the duration check: local-command echoes and system
    notifications still count here, same as before this still counts them
    for recency even though they are excluded from the prompt context.
    """
    found: list[tuple[int, datetime]] = []
    for idx in range(len(lines) - 1, -1, -1):
        try:
            entry = json.loads(lines[idx])
        except json.JSONDecodeError:
            # malformed transcript line: skip it, the rest is still usable
            continue
        if _is_real_user_message(entry):
            ts = _parse_timestamp(entry.get("timestamp", ""))
            if ts is not None:
                found.append((idx, ts))
                if len(found) >= count:
                    break
    found.reverse()
    return found


def _find_context_user_turns(
    lines: list[str], count: int, from_start: bool = False
) -> list[tuple[int, dict, str]]:
    """Up to ``count`` real user turns usable as prompt context, oldest first.

    Like ``_find_last_user_turns`` but also drops local-command echoes and
    system notifications, and can search forward from the start of the
    transcript (for session-start context) instead of backward from the end.
    """
    found: list[tuple[int, dict, str]] = []
    indices = range(len(lines)) if from_start else range(len(lines) - 1, -1, -1)
    for idx in indices:
        try:
            entry = json.loads(lines[idx])
        except json.JSONDecodeError:
            # malformed transcript line: skip it, the rest is still usable
            continue
        if not _is_real_user_message(entry):
            continue
        text = _extract_user_text(entry)
        if text.startswith(_EXCLUDED_PREFIXES):
            continue
        found.append((idx, entry, text))
        if len(found) >= count:
            break
    if not from_start:
        found.reverse()
    return found


def _tool_summary(block: dict) -> str:
    """Short label for a tool_use block: what it acted on, not just its name."""
    name = block.get("name", "")
    raw_input = block.get("input")
    tool_input: dict = raw_input if isinstance(raw_input, dict) else {}
    if name == "Bash":
        detail = (
            tool_input.get("description") or str(tool_input.get("command", ""))[:80]
        )
        return f"[Bash: {detail}]" if detail else "[tool: Bash]"
    if name in ("Read", "Edit", "Write"):
        file_path = tool_input.get("file_path")
        return f"[{name}: {file_path}]" if file_path else f"[tool: {name}]"
    if name == "Agent":
        desc = tool_input.get("description")
        return f"[Agent: {desc}]" if desc else "[tool: Agent]"
    return f"[tool: {name}]" if name else ""


def _collect_context(
    lines: list[str], after_idx: int, before_idx: int
) -> tuple[str, bool]:
    """Assistant text and tool summaries between two transcript lines.

    Returns ``(context, has_text)``; ``has_text`` tells the caller whether any
    assistant text block was found, so it can decide whether a re-read is
    worth trying (see ``TRANSCRIPT_RETRY_SECONDS`` in ``_run``).
    """
    parts: list[str] = []
    has_text = False
    for line in lines[after_idx + 1 : before_idx]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # malformed transcript line: skip it, the rest is still usable
            continue
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
                has_text = True
            elif block.get("type") == "tool_use" and block.get("name"):
                summary = _tool_summary(block)
                if summary:
                    parts.append(summary)
    return " ".join(parts), has_text


def _session_summary_segment(lines: list[str]) -> str | None:
    """Section 1, "Session summary": the compaction-continuation message, if any.

    The transcript's first real user message opens with "This session is
    being continued from a previous conversation" only when this session
    resumed from a compaction; that message is usually the single best
    source of what the session is about, so it gets a much larger cap than
    an ordinary message. Returns ``None`` when the session was not resumed
    this way.
    """
    turns = _find_context_user_turns(lines, 1, from_start=True)
    if not turns:
        return None
    _idx, _entry, text = turns[0]
    if not text.startswith(
        "This session is being continued from a previous conversation"
    ):
        return None
    return text[:MAX_COMPACTION_SUMMARY_CHARS]


def _all_user_texts(lines: list[str]) -> list[str]:
    """Every real user message's text, in transcript order.

    Same filter as ``_find_context_user_turns``: real user turns only, with
    local-command echoes and system notifications excluded.
    """
    texts: list[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # malformed transcript line: skip it, the rest is still usable
            continue
        if not _is_real_user_message(entry):
            continue
        text = _extract_user_text(entry)
        if not text or text.startswith(_EXCLUDED_PREFIXES):
            continue
        texts.append(text)
    return texts


def _render_all_messages(
    texts: list[str], per_message_chars: int, omit_note: str | None
) -> str:
    """One "- <text>" line per message, each capped at ``per_message_chars``.

    When ``omit_note`` is given, ``texts`` is assumed to already be the kept
    head+tail messages and the note is inserted at the gap between them.
    """
    if omit_note is None:
        rows = [f"- {t[:per_message_chars]}" for t in texts]
        return "\n".join(rows)
    rows = [f"- {t[:per_message_chars]}" for t in texts[:ALL_MESSAGES_KEEP_HEAD]]
    rows.append(omit_note)
    rows.extend(f"- {t[:per_message_chars]}" for t in texts[-ALL_MESSAGES_KEEP_TAIL:])
    return "\n".join(rows)


def _all_user_messages_section(lines: list[str]) -> str:
    """Section 2, "All user messages so far": every real user message.

    Tries the full list at ``ALL_MESSAGES_TRUNC_LENGTHS[0]`` chars per
    message first. If that is over ``ALL_MESSAGES_BUDGET``, keeps only the
    first ``ALL_MESSAGES_KEEP_HEAD`` and last ``ALL_MESSAGES_KEEP_TAIL``
    messages with a single omission line at the gap, trying progressively
    shorter per-message lengths until one fits.
    """
    texts = _all_user_texts(lines)
    if not texts:
        return ""

    body = _render_all_messages(texts, ALL_MESSAGES_TRUNC_LENGTHS[0], None)
    if len(body) > ALL_MESSAGES_BUDGET:
        can_split = len(texts) > ALL_MESSAGES_KEEP_HEAD + ALL_MESSAGES_KEEP_TAIL
        omitted = len(texts) - ALL_MESSAGES_KEEP_HEAD - ALL_MESSAGES_KEEP_TAIL
        omit_note = (
            f"- [... {omitted} earlier messages omitted ...]" if can_split else None
        )
        for per_message_chars in ALL_MESSAGES_TRUNC_LENGTHS:
            body = _render_all_messages(texts, per_message_chars, omit_note)
            if len(body) <= ALL_MESSAGES_BUDGET:
                break
    return f"All user messages so far:\n{body}"


def _gather_recent_segments(
    lines: list[str], turns: list[tuple[int, dict, str]]
) -> tuple[list[str], bool]:
    """Item 2: one "User asked: ... <assistant/tool activity>" segment per turn.

    ``has_text`` reflects only the most recent turn's segment, matching the
    old single-turn behavior: that is the segment whose final text block can
    still be missing at Stop time (see ``TRANSCRIPT_RETRY_SECONDS``).
    """
    segments: list[str] = []
    has_text = False
    for i, (idx, _entry, text) in enumerate(turns):
        user_text = text[:MAX_RECENT_USER_MESSAGE_CHARS]
        before_idx = turns[i + 1][0] if i + 1 < len(turns) else len(lines)
        tool_context, seg_has_text = _collect_context(lines, idx, before_idx)
        if i == len(turns) - 1:
            has_text = seg_has_text
        bits = []
        if user_text:
            bits.append(f"User asked: {user_text}")
        if tool_context:
            bits.append(tool_context)
        if bits:
            segments.append(" ".join(bits))
    return segments, has_text


def _render_recent_detail_section(
    segments: list[str], last_assistant_message: str | None
) -> str:
    """Section 3, "Recent turns in detail": last turns plus tool activity.

    Takes the segments already built by ``_gather_recent_segments`` (oldest
    first), appends the payload's ``last_assistant_message`` as the final
    line, and trims to ``RECENT_DETAIL_BUDGET`` chars by dropping the oldest
    turn segments first.
    """
    segs = list(segments)
    if last_assistant_message:
        segs.append(f"Final reply: {last_assistant_message}")
    if not segs:
        return ""

    def render(s: list[str]) -> str:
        return "Recent turns in detail:\n" + "\n".join(s)

    body = render(segs)
    while len(body) > RECENT_DETAIL_BUDGET and len(segs) > 1:
        segs.pop(0)
        body = render(segs)
    return body[:RECENT_DETAIL_BUDGET]


def _assemble_context(
    session_summary: str | None, all_messages_section: str, recent_detail_section: str
) -> str:
    """Join the three sections under the total ``MAX_CONTEXT_CHARS`` cap.

    Sections 1 and 2 already enforce their own budgets and are not trimmed
    further here; if the total is still over the cap, "recent turns in
    detail" is trimmed line by line, oldest turn first, with a final hard
    truncation as a last resort.
    """

    def render(recent: str) -> str:
        parts = [
            p
            for p in (
                f"Session summary:\n{session_summary}" if session_summary else "",
                all_messages_section,
                recent,
            )
            if p
        ]
        return "\n\n".join(parts)

    context = render(recent_detail_section)
    recent_lines = recent_detail_section.splitlines()
    while len(context) > MAX_CONTEXT_CHARS and len(recent_lines) > 1:
        recent_lines.pop(1)  # index 0 is the "Recent turns in detail:" header
        context = render("\n".join(recent_lines))
    return context[:MAX_CONTEXT_CHARS]


def _generate_recap(context: str) -> str | None:
    """Ask a cheap, tool-less ``claude -p`` subprocess for a recap.

    Flags (verified against ``claude --help`` on this install; no literal
    ``--max-turns`` exists in this CLI version, so ``--tools ""`` is what
    keeps the subprocess to a single text exchange instead -- see the
    module docstring):

    - ``-p``                        non-interactive: print the reply, exit
    - ``--model sonnet``            won a 5-of-6 blind test vs haiku (Sep 2026)
    - ``--no-session-persistence``  don't save/resume this throwaway call
    - ``--tools=""``                disable all tools, so it can only reply
      (the ``=`` form matters: ``--tools`` is variadic, so a separate
      ``["--tools", ""]`` pair would swallow the prompt argument that
      follows it into the tools list instead of leaving it as the prompt)
    """
    prompt = (
        "Below is a partial log of a Claude Code session that has ALREADY "
        "finished a turn. You are writing a note for the user, who "
        "stepped away, runs several sessions at once, and is coming back "
        "to this one cold. Never say input is missing and never answer "
        "as the assistant; only write the note. No markdown, no hashes, "
        "no internals. Recap in under 40 words, 1-2 plain sentences, no "
        "markdown, no hashes, no internals. Lead with the overall goal "
        "the session was started for and the current task (say if the "
        "work moved elsewhere), then the one next action. Skip "
        "root-cause narrative, fix internals, secondary to-dos, and "
        "em-dash tangents.\n"
        f"Log:\n{context}"
    )
    env = dict(os.environ)
    env["CLAUDE_CODE_RECAP_HOOK_RUNNING"] = "1"
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                "sonnet",
                "--no-session-persistence",
                # ``--tools`` is variadic (accepts multiple values), so a
                # separate ["--tools", ""] pair would swallow the prompt
                # argument that follows it into the tools list, leaving no
                # prompt at all. The ``--tools=""`` single-token form binds
                # the empty value to the flag only.
                "--tools=",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log(f"decision=recap-subprocess-failed error={exc!r}")
        return None
    if result.returncode != 0:
        return None
    return _format_recap(result.stdout)


def _truncate_at_sentence(text: str, cap: int) -> str:
    """Truncate ``text`` to at most ``cap`` chars, ending on a sentence."""
    if len(text) <= cap:
        return text
    kept = ""
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        candidate = f"{kept} {sentence}".strip() if kept else sentence
        if len(candidate) > cap:
            break
        kept = candidate
    return kept if kept else text[:cap].rstrip()


def _cap_words_at_sentence(text: str, max_words: int) -> str:
    """Cap ``text`` at ``max_words`` words, cutting at the last sentence end
    at or before the cap (falls back to a hard word cut if even the first
    sentence alone is over the cap, since there is no earlier boundary).
    """
    kept = ""
    kept_words = 0
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence_words = len(sentence.split())
        if kept and kept_words + sentence_words > max_words:
            break
        kept = f"{kept} {sentence}".strip() if kept else sentence
        kept_words += sentence_words
        if kept_words >= max_words:
            break
    if kept and kept_words <= max_words:
        return kept
    return " ".join(text.split()[:max_words])


def _format_recap(raw: str) -> str | None:
    """Turn the model's raw reply into the recap systemMessage.

    Defensive regardless of what the model actually returns: strips markdown
    bold (``**text**``), backticks, and stray asterisks/hashes, then
    collapses all whitespace and newlines to single spaces. Any leading
    "<word>: " label the model added on its own (a guessed project prefix, a
    "Note:" preamble, whatever) is stripped. The result is capped at
    ``MAX_RECAP_WORDS`` words, cutting at the last sentence end at or before
    the cap, then at an absolute ``MAX_RECAP_CHARS`` as a safety net.
    Returns ``None`` if nothing usable remains.
    """
    text = _BOLD_RE.sub(r"\1", raw)
    text = text.replace("`", "").replace("*", "").replace("#", "")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return None

    text = _LEADING_LABEL_RE.sub("", text)

    text = _cap_words_at_sentence(text, MAX_RECAP_WORDS)
    text = _truncate_at_sentence(text, MAX_RECAP_CHARS)
    return "\n" + text if text else None


def _run() -> None:
    """Do the work; any exception here is swallowed by ``main``."""
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return
    transcript_file = Path(transcript_path)
    lines = transcript_file.read_text(encoding="utf-8", errors="replace").splitlines()

    duration_turns = _find_last_user_turns(lines, 1)
    if not duration_turns:
        _log("decision=skip reason=no-user-turn-found")
        return
    _idx, ts = duration_turns[-1]

    duration = (datetime.now(timezone.utc) - ts).total_seconds()
    threshold_raw = os.environ.get(
        "CLAUDE_CODE_RECAP_TURN_SECONDS", str(DEFAULT_THRESHOLD_SECONDS)
    )
    try:
        threshold = float(threshold_raw)
    except ValueError:
        threshold = DEFAULT_THRESHOLD_SECONDS

    if threshold == 0 or duration < threshold:
        _log(
            f"duration={duration:.1f}s threshold={threshold}s decision=below-threshold"
        )
        return

    recent_turns = _find_context_user_turns(lines, NUM_CONTEXT_TURNS)
    segments, has_text = _gather_recent_segments(lines, recent_turns)
    if not has_text:
        # transcript_path lags the live conversation (see module docstring);
        # give the turn's own final text block one chance to land before
        # settling for tool-only context.
        time.sleep(TRANSCRIPT_RETRY_SECONDS)
        lines = transcript_file.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        recent_turns = _find_context_user_turns(lines, NUM_CONTEXT_TURNS)
        segments, has_text = _gather_recent_segments(lines, recent_turns)

    session_summary = _session_summary_segment(lines)
    all_messages_section = _all_user_messages_section(lines)

    last_assistant_message = payload.get("last_assistant_message")
    recent_detail_section = _render_recent_detail_section(
        segments, last_assistant_message
    )

    context = _assemble_context(
        session_summary, all_messages_section, recent_detail_section
    )

    recap = _generate_recap(context)
    if recap is None:
        _log(f"duration={duration:.1f}s threshold={threshold}s decision=recap-failed")
        return

    sys.stdout.write(json.dumps({"systemMessage": recap}))
    _log(
        f"duration={duration:.1f}s threshold={threshold}s decision=recap outcome=ok recap={recap!r}"
    )


def main() -> int:
    if os.environ.get("CLAUDE_CODE_RECAP_HOOK_RUNNING"):
        return 0
    try:
        _run()
    except Exception as exc:  # never let this hook break the turn
        _log(f"decision=error outcome={exc!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
