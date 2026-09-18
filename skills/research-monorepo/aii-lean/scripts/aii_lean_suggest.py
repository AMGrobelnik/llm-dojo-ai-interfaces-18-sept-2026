#!/usr/bin/env python
"""
Lean 4 Tactic Suggest Tool

Runs code with sorry placeholders and tries tactics (exact?, apply?, simp?, etc.)
at each sorry position. Returns goal states and tactic suggestions.

Usage:
    python aii_lean_suggest.py --code "theorem ex : 1 + 1 = 2 := by sorry"
    python aii_lean_suggest.py --code "..." --tactics "exact?,simp?,omega"
"""

import argparse
import atexit
import os
import queue
import re
import threading
from pathlib import Path

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


SERVER_NAME = "aii_lean__suggest"
MATHLIB_LEAN_VERSION = "v4.14.0"
DEFAULT_TIMEOUT = 180.0
DEFAULT_TACTICS = [
    # Discovery (find the right lemma/tactic)
    "exact?",
    "apply?",
    "simp?",
    "rw?",
    # Automation (close goals directly)
    "simp",
    "aesop",
    "omega",
    "decide",
    "ring",
    "linarith",
    "nlinarith",
    "norm_num",
    # Field-specific
    "field_simp",
    "positivity",
]

# Cached config (reused across requests)
_config = None

# ---------------------------------------------------------------------------
# Persistent LeanServer pool (mirrors aii_run_lean.py — see there for rationale)
# ---------------------------------------------------------------------------
# Previously every request spawned a FRESH LeanServer and re-ran ``import
# Mathlib`` (~6-17s, ~4GB) before discarding it — the dominant latency and a
# load-driven memory vector. A small pool loads Mathlib ONCE per server and
# reuses it: each request runs against the server's pristine base env
# (``env=base_env``), isolated, ~25ms warm. The whole request (run code → read
# sorry proof_states → ProofStep tactics) stays on its one checked-out server,
# since proof_state handles are server-local. Inline (not shared with
# aii_run_lean) so the script still runs standalone without aii_lib; the two
# lean abilities are separate worker processes with independent pools anyway.
_LEAN_POOL_SIZE = max(1, int(os.environ.get("AII_LEAN_POOL_SIZE", "2")))
_lean_pool: "queue.Queue[list]" = queue.Queue()
_lean_pool_lock = threading.Lock()
_lean_servers_created = 0
_all_lean_servers: list = []
# Recycle a pooled server once it has served _LEAN_RECYCLE_AFTER requests OR its
# REPL memory exceeds _LEAN_RECYCLE_MB (checked every _LEAN_MEM_CHECK_EVERY
# requests) — bounds the small per-request env accumulation over weeks of heavy
# use, independent of total volume. See aii_run_lean.py for the full rationale.
_LEAN_RECYCLE_AFTER = max(1, int(os.environ.get("AII_LEAN_RECYCLE_AFTER", "2000")))
_LEAN_RECYCLE_MB = float(os.environ.get("AII_LEAN_RECYCLE_MB", "6000"))
_LEAN_MEM_CHECK_EVERY = 32
# Global soft ANON cap (MB): when >0, also recycle on check-in if the whole
# container's ANONYMOUS memory exceeds it — gentle between-requests auto-adjust
# below the hard cgroup cap. Keyed on anon, not total (memory.current is mostly
# reclaimable mathlib mmap). 0 = disabled (default). See aii_run_lean.py.
_LEAN_SOFT_CAP_MB = float(os.environ.get("AII_LEAN_SOFT_CAP_MB", "0"))
_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z0-9_.]+)")
_MATHLIB_CLOSURE = (
    "Mathlib",
    "Aesop",
    "Batteries",
    "Std",
    "Init",
    "Lean",
    "Qq",
    "ImportGraph",
    "ProofWidgets",
)


# =============================================================================
# Core Logic (used by server handler)
# =============================================================================


def init_lean_suggest():
    """Initialize Lean environment - setup PATH, warm up disk cache."""
    import fcntl
    import os

    global _config

    # Add elan/lake to PATH
    elan_bin = Path.home() / ".elan" / "bin"
    if elan_bin.exists() and str(elan_bin) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{elan_bin}:{os.environ.get('PATH', '')}"

    # File lock prevents parallel workers from racing on the same REPL build cache
    from lean_interact import Command, LeanREPLConfig, LeanServer, TempRequireProject

    lock_path = Path("/tmp/lean_repl_build.lock")
    lock_path.touch(exist_ok=True)
    with open(lock_path, encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        project = TempRequireProject(lean_version=MATHLIB_LEAN_VERSION, require="mathlib")
        _config = LeanREPLConfig(project=project, verbose=False)

    # Warmup
    warmup_server = LeanServer(_config)
    warmup_server.run(Command(cmd="#check Nat"))
    warmup_server.run(Command(cmd="import Mathlib.Tactic\nexample : 1 + 1 = 2 := by ring"))
    warmup_server.kill()


def _split_imports(code: str) -> tuple[list[str], str]:
    """Split leading ``import X`` lines (as module names) from the body."""
    imports: list[str] = []
    body: list[str] = []
    in_body = False
    for line in code.splitlines():
        match = _IMPORT_RE.match(line)
        if match and not in_body:
            imports.append(match.group(1))
        elif line.strip() == "" and not in_body:
            continue
        else:
            in_body = True
            body.append(line)
    return imports, "\n".join(body)


def _imports_in_mathlib(imports: list[str]) -> bool:
    """True if every import's root module is within Mathlib's transitive closure."""
    return all(imp.split(".")[0] in _MATHLIB_CLOSURE for imp in imports)


def _make_lean_server() -> list:
    """Spawn a LeanServer and import Mathlib once; return ``[server, base_env]``."""
    from lean_interact import Command, LeanServer

    server = LeanServer(_config)
    resp = server.run(Command(cmd="import Mathlib"))
    item = [server, getattr(resp, "env", None), 0]  # [server, base_env, request_count]
    with _lean_pool_lock:
        _all_lean_servers.append(item)
    return item


def _global_cgroup_anon_mb() -> float:
    """Whole-container ANONYMOUS memory (MB), or 0.0 if unreadable. anon — not
    total usage — is the right soft-cap signal (usage is mostly reclaimable
    mathlib mmap). Reads cgroup v2 ``memory.stat`` ``anon`` (local Docker) or
    falls back to v1 ``memory/memory.stat`` ``total_rss`` (RunPod pods run
    cgroup v1). See aii_run_lean.py for the full rationale."""
    for path, key in (
        ("/sys/fs/cgroup/memory.stat", "anon "),  # cgroup v2
        ("/sys/fs/cgroup/memory/memory.stat", "total_rss "),  # cgroup v1
    ):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith(key):
                        return int(line.split()[1]) / (1024 * 1024)
        except (OSError, ValueError):
            continue
    # Neither layout readable (not Docker cgroup-v2 nor RunPod cgroup-v1):
    # disable the soft-cap (return 0 < any cap) rather than recycle blindly.
    # Deliberate, safe default — the per-server RSS/count recycle still bounds
    # memory; revisit if a host with yet another cgroup layout appears.
    return 0.0


def _checkin_lean_server(item: list) -> None:
    """Return a healthy server to the pool, OR recycle it (kill + drop) once it
    has served too many requests, its REPL memory has grown past the cap, or the
    whole container is over the global soft cap (gentle auto-adjust)."""
    item[2] += 1
    recycle = item[2] >= _LEAN_RECYCLE_AFTER
    if not recycle and item[2] % _LEAN_MEM_CHECK_EVERY == 0:
        try:
            recycle = item[0].get_memory_usage() > _LEAN_RECYCLE_MB
        except Exception:
            recycle = True  # can't measure → assume wedged, recycle
        # Gentle global auto-adjust: shed even a healthy server when the whole
        # container is over its soft memory budget (keeps it below the hard cap).
        if not recycle and _LEAN_SOFT_CAP_MB and _global_cgroup_anon_mb() > _LEAN_SOFT_CAP_MB:
            recycle = True
    if recycle:
        _discard_lean_server(item)  # killed; a fresh one is created on next checkout
    else:
        _lean_pool.put(item)


def _checkout_lean_server() -> list:
    """Reuse a pooled ``[server, base_env]``, create one up to ``_LEAN_POOL_SIZE``,
    else block for one to be returned."""
    global _lean_servers_created
    try:
        return _lean_pool.get_nowait()
    except queue.Empty:
        pass
    with _lean_pool_lock:
        make_new = _lean_servers_created < _LEAN_POOL_SIZE
        if make_new:
            _lean_servers_created += 1
    if make_new:
        try:
            return _make_lean_server()
        except Exception:
            with _lean_pool_lock:
                _lean_servers_created -= 1
            raise
    return _lean_pool.get()


def _discard_lean_server(item: list) -> None:
    """Kill a server that raised (may be wedged) so a fresh one replaces it."""
    global _lean_servers_created
    try:
        item[0].kill()
    except Exception:
        pass  # best-effort: the server may already be dead
    with _lean_pool_lock:
        _lean_servers_created -= 1
        if item in _all_lean_servers:
            _all_lean_servers.remove(item)


@atexit.register
def _shutdown_lean_pool() -> None:
    """Kill every live LeanServer on interpreter exit (graceful worker stop)."""
    for item in _all_lean_servers:
        try:
            item[0].kill()
        except Exception:
            pass


def _suggest_on_server(server, cmd: str, env, tactics: list[str]) -> dict:
    """Run ``cmd`` on ``server`` (``env`` = base env for reuse, or None for fresh),
    then try each tactic at every sorry's proof state. Returns the result dict."""
    from lean_interact import Command, ProofStep

    command = Command(cmd=cmd, env=env) if env is not None else Command(cmd=cmd)
    response = server.run(command)

    # Compilation errors (not sorry-related)
    errors = []
    for msg in response.messages:
        if getattr(msg, "severity", "") == "error":
            errors.append(getattr(msg, "data", str(msg)))
    if errors:
        return {"success": True, "goals": [], "suggestions": [], "errors": errors}

    if not response.sorries:
        return {
            "success": True,
            "goals": [],
            "suggestions": [],
            "errors": [],
            "note": "No sorry found in code — nothing to suggest tactics for.",
        }

    goals = [
        {"sorry_index": i, "goal": sorry.goal, "proof_state": sorry.proof_state}
        for i, sorry in enumerate(response.sorries)
    ]

    suggestions = []
    for i, sorry in enumerate(response.sorries):
        if sorry.proof_state is None:
            suggestions.append(
                {
                    "sorry_index": i,
                    "tactic": None,
                    "success": False,
                    "result": "No proof state available for this sorry",
                    "closes_goal": False,
                }
            )
            continue

        for tactic in tactics:
            try:
                step = server.run(ProofStep(proof_state=sorry.proof_state, tactic=tactic))
                result_parts = []
                if hasattr(step, "messages"):
                    for msg in step.messages:
                        data = getattr(msg, "data", str(msg))
                        if data:
                            result_parts.append(data)
                result_text = "\n".join(result_parts) if result_parts else ""
                status = getattr(step, "proof_status", "")
                closes_goal = status.lower() == "completed" if status else False
                remaining_goals = getattr(step, "goals", []) or []
                suggestions.append(
                    {
                        "sorry_index": i,
                        "tactic": tactic,
                        "success": True,
                        "result": result_text,
                        "closes_goal": closes_goal,
                        "remaining_goals": remaining_goals,
                    }
                )
            except Exception as e:
                error_msg = getattr(e, "message", "") or str(e)
                suggestions.append(
                    {
                        "sorry_index": i,
                        "tactic": tactic,
                        "success": False,
                        "result": error_msg,
                        "closes_goal": False,
                    }
                )

    return {"success": True, "goals": goals, "suggestions": suggestions, "errors": []}


@aii_ability(
    name="aii_lean__suggest",
    description="Try tactics at sorry positions in Lean 4 code.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_lean_suggest",
    max_workers=4,
    timeout=120.0,
    check_env="check_env.sh",
)
def core_lean_suggest(code: str = "", tactics: str | list[str] = DEFAULT_TACTICS) -> dict:
    """
    Run Lean 4 code and try tactics at sorry positions.

    Submits code with sorry placeholders, extracts goal states, then
    applies each requested tactic via ProofStep. Returns what worked.

    Args:
        code: Lean 4 code with `sorry` placeholders
        tactics: Comma-separated tactics or list (default: "exact?,apply?,simp?")

    Returns:
        Dict with:
            - success: bool
            - goals: list[dict] - goal at each sorry position
              Each: {sorry_index, goal, proof_state}
            - suggestions: list[dict] - tactic results
              Each: {sorry_index, tactic, success, result, closes_goal}
            - errors: list[str] - compilation errors (if any)
    """
    if isinstance(tactics, str):
        tactics = [t.strip() for t in tactics.split(",") if t.strip()]
    else:
        tactics = list(tactics)

    if not tactics:
        tactics = DEFAULT_TACTICS

    if not code.strip():
        return {"success": False, "error": "No code provided"}

    if _config is None:
        init_lean_suggest()

    from lean_interact import LeanServer

    imports, body = _split_imports(code)

    # Rare path: imports outside Mathlib's closure aren't in a pooled server's
    # base env — use a throwaway fresh server and run the full code.
    if imports and not _imports_in_mathlib(imports):
        server = LeanServer(_config)
        try:
            return _suggest_on_server(server, code, None, tactics)
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            server.kill()

    # Common path: Mathlib-only / no imports — run the body against a pooled
    # server's pristine base env (Mathlib pre-loaded, isolated, ~25ms warm).
    try:
        item = _checkout_lean_server()
    except Exception as e:
        return {"success": False, "error": f"Lean server unavailable: {e}"}

    try:
        result = _suggest_on_server(item[0], body or "example : True := trivial", item[1], tactics)
        _checkin_lean_server(item)  # return to pool, or recycle if over caps
        return result
    except Exception as e:
        _discard_lean_server(item)  # may be wedged — drop so a fresh one replaces it
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    import json

    parser = argparse.ArgumentParser(description="Try tactics at sorry positions in Lean 4 code")
    parser.add_argument("--code", "-c", required=True, help="Lean 4 code with sorry placeholders")
    parser.add_argument(
        "--tactics",
        "-t",
        default=",".join(DEFAULT_TACTICS),
        help=f"Comma-separated tactics to try (default: {','.join(DEFAULT_TACTICS)})",
    )
    args = parser.parse_args()

    params = {
        "code": args.code,
        "tactics": args.tactics,
    }

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(
            SERVER_NAME,
            params,
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        result = None

    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        init_lean_suggest()
        result = core_lean_suggest(**params)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
