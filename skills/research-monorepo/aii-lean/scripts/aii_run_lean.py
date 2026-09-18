#!/usr/bin/env python
"""
Lean 4 Code Runner

Compiles and verifies Lean 4 code using lean-interact library.
Mathlib is always enabled. Each request gets a fresh LeanServer (no memory accumulation).
When code contains sorry, returns goal states at each sorry position.

Usage:
    python aii_run_lean.py proof.lean
    echo "theorem test : 1 + 1 = 2 := rfl" | python aii_run_lean.py -
"""

import argparse
import atexit
import os
import queue
import re
import sys
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


SERVER_NAME = "aii_lean__run"
MATHLIB_LEAN_VERSION = "v4.14.0"
DEFAULT_TIMEOUT = 120.0

# Cached config (reused across requests, lightweight)
_config = None

# ---------------------------------------------------------------------------
# Persistent LeanServer pool
# ---------------------------------------------------------------------------
# Previously every request spawned a FRESH ``LeanServer`` and re-ran
# ``import Mathlib`` (~6-17s, ~4GB) before discarding it — the dominant latency
# AND the load-driven memory vector (up to ``max_workers`` concurrent fresh
# Mathlib envs at once). Instead we keep a small pool of pre-warmed servers:
# Mathlib is imported ONCE per server, and each request runs against that
# server's pristine base env (``env=base_env``), so warm queries drop to ~25ms
# with full state isolation (a def/import in one request never leaks into the
# next). Memory is bounded to the pool size — the heavy Mathlib ``.olean`` pages
# are mmap'd and shared across servers. The pool fills lazily on first use, so
# runs that never touch Lean pay nothing.
_LEAN_POOL_SIZE = max(1, int(os.environ.get("AII_LEAN_POOL_SIZE", "2")))
_lean_pool: "queue.Queue[list]" = queue.Queue()
_lean_pool_lock = threading.Lock()
_lean_servers_created = 0
# Every live server (pooled or checked-out) so they can be killed on shutdown.
# Without this the old code killed each server after its request; the pool keeps
# them alive, so a worker restart could orphan ~4GB Mathlib processes.
_all_lean_servers: list = []
# Recycling — a persistent server accumulates a small derived-env snapshot per
# request (~0.1-1 MB/query), so over weeks of heavy use (10k+ requests) it would
# creep multi-GB. On check-in we kill + drop a server once it has served
# ``_LEAN_RECYCLE_AFTER`` requests OR its REPL memory exceeds ``_LEAN_RECYCLE_MB``
# (checked every ``_LEAN_MEM_CHECK_EVERY`` requests — ``get_memory_usage`` is
# ~3 ms, so amortized to a few µs/query). The memory cap is load-independent: it
# bounds each server regardless of request weight; the count cap is the backstop
# for light steady creep. A fresh server is created on the next checkout (~6 s
# cold, amortized over thousands of fast queries → negligible). Net: lean memory
# is permanently bounded no matter how long the server lives.
_LEAN_RECYCLE_AFTER = max(1, int(os.environ.get("AII_LEAN_RECYCLE_AFTER", "2000")))
_LEAN_RECYCLE_MB = float(os.environ.get("AII_LEAN_RECYCLE_MB", "6000"))
_LEAN_MEM_CHECK_EVERY = 32
# Global soft ANON cap (MB): when >0, a server is ALSO recycled on check-in if
# the whole container's ANONYMOUS memory exceeds it — a gentle, between-requests
# auto-adjust below the hard cgroup cap. Keyed on anon, NOT total
# (``memory.current``): current is dominated by the reclaimable mathlib mmap,
# which the kernel refills to the hard cap regardless, so a current-based cap
# would recycle Lean endlessly with zero benefit. anon is the real,
# non-reclaimable heap that recycling a server actually frees. 0 = disabled
# (default); on a 16 GB box with a 14 GB hard cap, set ~10000-11000. Evaluated
# on the same amortized cadence as the per-server cap (one tiny read per ~32 req).
_LEAN_SOFT_CAP_MB = float(os.environ.get("AII_LEAN_SOFT_CAP_MB", "0"))
# Leading ``import X`` lines are stripped when X is within Mathlib's transitive
# closure (already loaded in base_env — re-importing on a non-empty env errors
# with "invalid 'import' command, it must be used in the beginning of the file").
_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z0-9_.]+)")


# =============================================================================
# Core Logic (used by server handler)
# =============================================================================


def init_run_lean():
    """Initialize Lean environment - setup PATH, warm up disk cache."""
    import fcntl
    import os

    global _config

    # Add elan/lake to PATH
    elan_bin = Path.home() / ".elan" / "bin"
    if elan_bin.exists() and str(elan_bin) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{elan_bin}:{os.environ.get('PATH', '')}"

    # Create config (downloads/builds Mathlib on first run, then cached on disk)
    # File lock prevents parallel workers from racing on the same REPL build cache
    from lean_interact import Command, LeanREPLConfig, LeanServer, TempRequireProject

    lock_path = Path("/tmp/lean_repl_build.lock")
    lock_path.touch(exist_ok=True)
    with open(lock_path, encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        project = TempRequireProject(lean_version=MATHLIB_LEAN_VERSION, require="mathlib")
        _config = LeanREPLConfig(project=project, verbose=False)

    # Warmup: populate disk cache with a temp server
    warmup_server = LeanServer(_config)
    warmup_server.run(Command(cmd="#check Nat"))
    warmup_server.run(Command(cmd="import Mathlib.Tactic\nexample : 1 + 1 = 2 := by ring"))
    warmup_server.kill()


# Top-level modules reachable from ``import Mathlib`` (its transitive closure).
# Imports rooted here are already present in a pooled server's base env, so the
# leading ``import`` line is stripped and the body runs on that env. Anything
# else needs its own fresh server (it isn't loaded in base_env).
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


def _split_imports(code: str) -> tuple[list[str], str]:
    """Split leading ``import X`` lines (returned as module names) from the body."""
    imports: list[str] = []
    body: list[str] = []
    in_body = False
    for line in code.splitlines():
        match = _IMPORT_RE.match(line)
        if match and not in_body:
            imports.append(match.group(1))
        elif line.strip() == "" and not in_body:
            continue  # skip blank lines above/between the import block
        else:
            in_body = True
            body.append(line)
    return imports, "\n".join(body)


def _imports_in_mathlib(imports: list[str]) -> bool:
    """True if every import's root module is within Mathlib's transitive closure."""
    return all(imp.split(".")[0] in _MATHLIB_CLOSURE for imp in imports)


def _summarize_lean_response(response) -> dict:
    """Turn a lean-interact response into the ability's result dict."""
    errors, warnings, infos = [], [], []
    for msg in response.messages:
        severity = getattr(msg, "severity", "info")
        data = getattr(msg, "data", str(msg))
        if severity == "error":
            errors.append(data)
        elif severity == "warning":
            warnings.append(data)
        else:
            infos.append(data)

    has_sorries = bool(response.sorries) if hasattr(response, "sorries") else False

    sorry_goals = []
    if has_sorries:
        for i, sorry in enumerate(response.sorries):
            goal_info = {"sorry_index": i}
            if hasattr(sorry, "proof_state"):
                goal_info["proof_state"] = sorry.proof_state
            if hasattr(sorry, "goal"):
                goal_info["goal"] = sorry.goal
            elif hasattr(sorry, "goals"):
                goal_info["goal"] = sorry.goals
            sorry_goals.append(goal_info)

    return {
        "success": True,
        "verified": len(errors) == 0 and not has_sorries,
        "has_sorries": has_sorries,
        "sorry_goals": sorry_goals,
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
    }


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
    total usage — is the right soft-cap signal: usage is mostly reclaimable
    mathlib mmap that the kernel refills to the hard cap, while anon is the real
    heap that recycling a server actually frees (verified live: anon ~4 GB while
    usage ~13 GB). Reads whichever cgroup layout the host exposes: v2
    ``memory.stat`` ``anon`` (local Docker) or v1 ``memory/memory.stat``
    ``total_rss`` (RunPod pods run cgroup v1 — without this fallback the cap
    reads nothing and is silently inert there)."""
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
    whole container is over the global soft cap — so accumulated per-request env
    state can't creep unbounded and the pool self-sheds under memory pressure."""
    item[2] += 1
    recycle = item[2] >= _LEAN_RECYCLE_AFTER
    if not recycle and item[2] % _LEAN_MEM_CHECK_EVERY == 0:
        try:
            recycle = item[0].get_memory_usage() > _LEAN_RECYCLE_MB
        except Exception:
            recycle = True  # can't measure → assume wedged, recycle
        # Gentle global auto-adjust: shed even a healthy server when the whole
        # container's anon heap is over its soft budget (keeps it below the hard cap).
        if not recycle and _LEAN_SOFT_CAP_MB and _global_cgroup_anon_mb() > _LEAN_SOFT_CAP_MB:
            recycle = True
    if recycle:
        _discard_lean_server(item)  # killed; a fresh one is created on next checkout
    else:
        _lean_pool.put(item)


def _checkout_lean_server() -> list:
    """Return a pre-warmed ``[server, base_env]``: reuse a pooled one, create a
    new one up to ``_LEAN_POOL_SIZE``, else block for one to be returned."""
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
    return _lean_pool.get()  # at capacity — wait for a returned server


def _discard_lean_server(item: list) -> None:
    """Kill a server that raised (it may be wedged) so a fresh one replaces it."""
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


@aii_ability(
    name="aii_lean__run",
    description="Compile and verify Lean 4 code with Mathlib support.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_run_lean",
    max_workers=4,
    timeout=120.0,
    check_env="check_env.sh",
)
def core_run_lean(code: str = "") -> dict:
    """
    Run Lean 4 code and return compilation results.

    Runs against a pooled, pre-warmed LeanServer (Mathlib imported once, reused
    per request against its isolated base env — no state leaks between requests).
    When code has sorry placeholders, returns goal states at each sorry position.

    Args:
        code: Lean 4 code to compile

    Returns:
        Dict with:
            - success: bool - tool ran without exceptions
            - verified: bool - proof compiled without errors/sorries
            - errors: list[str] - error messages
            - warnings: list[str] - warnings
            - infos: list[str] - info messages
            - has_sorries: bool - code contains sorry
            - sorry_goals: list[dict] - goal state at each sorry position
              Each dict has: proof_state (int), goal (str if available)
    """
    if not code.strip():
        return {"success": False, "verified": False, "error": "No code provided"}

    if _config is None:
        init_run_lean()

    from lean_interact import Command, LeanServer

    imports, body = _split_imports(code)

    # Rare path: imports outside Mathlib's closure aren't in a pooled server's
    # base env (where Mathlib is already loaded), and ``import`` can't run on a
    # non-empty env. Use a throwaway fresh server so they resolve correctly.
    if imports and not _imports_in_mathlib(imports):
        server = LeanServer(_config)
        try:
            return _summarize_lean_response(server.run(Command(cmd=code)))
        except Exception as e:
            return {"success": False, "verified": False, "error": str(e)}
        finally:
            server.kill()

    # Common path: Mathlib-only (or no) imports — run the body against a pooled
    # server's pristine base env (Mathlib pre-loaded, isolated, ~25ms warm).
    try:
        item = _checkout_lean_server()
    except Exception as e:
        return {"success": False, "verified": False, "error": f"Lean server unavailable: {e}"}

    try:
        response = item[0].run(Command(cmd=body or "example : True := trivial", env=item[1]))
        result = _summarize_lean_response(response)
        _checkin_lean_server(item)  # return to pool, or recycle if over caps
        return result
    except Exception as e:
        _discard_lean_server(item)  # may be wedged — drop so a fresh one replaces it
        return {"success": False, "verified": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    import json

    parser = argparse.ArgumentParser(description="Compile and verify Lean 4 code (with Mathlib)")
    parser.add_argument("file", help="Lean file to verify, or '-' for stdin")
    args = parser.parse_args()

    if args.file == "-":
        code = sys.stdin.read()
    else:
        file_path = Path(args.file)
        if not file_path.exists():
            print(
                json.dumps(
                    {"success": False, "error": f"File not found: {args.file}"},
                    indent=2,
                )
            )
            sys.exit(1)
        code = file_path.read_text(encoding="utf-8")

    params = {
        "code": code,
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
        init_run_lean()
        result = core_run_lean(**params)

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("verified", False) else 1)


if __name__ == "__main__":
    main()
