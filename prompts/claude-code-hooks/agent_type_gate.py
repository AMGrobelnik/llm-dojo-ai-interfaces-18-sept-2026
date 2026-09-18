#!/usr/bin/env python3
"""Allow only agent types whose definition fixes the model and effort.

Every launchable agent is a user or project definition whose name encodes the
model and, for sonnet and opus, the effort: Explore, gen-haiku,
gen-sonnet-<effort>, gen-opus-<effort>. Picking the type picks the model, so a
launch needs no ``model`` argument. If one is passed anyway it must equal the
definition's model, because a passed model would silently override it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
_DEFAULT_TYPE = "general-purpose"
_DENIED_TYPES = {"Plan", "general-purpose", "fork"}
_CHOICES = "Explore, gen-haiku, gen-sonnet-<effort> or gen-opus-<effort>"


def _deny(reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def _definition(agent_type: str, cwd: str) -> Path | None:
    for base in (Path(cwd) / ".claude" / "agents", Path.home() / ".claude" / "agents"):
        candidate = base / f"{agent_type}.md"
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _deny(f"Could not read the Agent launch. Retry with one of {_CHOICES}.")
        return 0

    tool_input = payload.get("tool_input") or {}
    agent_type = tool_input.get("subagent_type") or _DEFAULT_TYPE
    if agent_type in _DENIED_TYPES:
        _deny(f"Agent type '{agent_type}' is not used. Launch {_CHOICES}.")
        return 0

    definition = _definition(agent_type, payload.get("cwd") or ".")
    if definition is None:
        _deny(f"Agent type '{agent_type}' has no definition. Launch {_CHOICES}.")
        return 0
    fields = _frontmatter(definition)
    defined_model = fields.get("model")
    if not defined_model:
        _deny(f"{definition} declares no model. Launch {_CHOICES}.")
        return 0
    passed_model = tool_input.get("model")
    if passed_model is not None and passed_model != defined_model:
        _deny(
            f"'{agent_type}' runs on {defined_model}; the launch passed "
            f"{passed_model!r}. Drop the model argument or pick {_CHOICES}."
        )
        return 0
    if defined_model != "haiku" and fields.get("effort") not in _ALLOWED_EFFORTS:
        _deny(
            f"{definition} runs on {defined_model} but declares no valid effort "
            "(low, medium, high, xhigh or max)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
