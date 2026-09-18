#!/usr/bin/env python
"""
RunPod Get Pod Status — real container runtime state.

Detects a stuck pod: one RunPod calls up while its container never actually
started, because the image is still pulling or the start command hung.

WHAT CHANGED IN v2, because this docstring described v1 and was quoted as
evidence for it:

  - ``desiredStatus`` is GONE. It meant "what RunPod was asked to do", and it
    read RUNNING from the moment of creation, so it never distinguished a
    booting pod from a serving one. v2's ``status`` is the state the pod is
    actually IN — one of PROVISIONING / STARTING / RUNNING / EXITED / ERROR /
    TERMINATED. Code that compared ``desiredStatus == "RUNNING"`` to mean
    "alive" must now accept the first three; see
    ``RunPodAPI.find_running_pod_by_prefix``, where that exact narrowing
    disarmed a single-writer guard.
  - ``runtime.uptimeInSeconds`` -> ``runtime.uptime``. Still 0 while the image
    pulls, and ``runtime`` itself is null unless the pod is RUNNING.
  - ``machine.podHostId`` is GONE and has no v2 equivalent — v2 exposes no
    machine identifier at all. "Has RunPod placed this pod" is answered by
    ``status`` plus ``startedAt`` instead.

There is also no GraphQL here any more: v2's ``GET /pods/{id}`` serves the
runtime section REST v1 lacked, which is why the old two-call split is gone.

Usage (via ability server):
    python aii_runpod_get_pod_status.py --pod-id abc123
"""

import argparse
import json
import sys

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


from aii_runpod_gen_template import (
    DEFAULT_TIMEOUT,
    SERVER_NAME_GET_POD_STATUS,
    rp,
)

# =============================================================================
# Core: get_pod_status
# =============================================================================


@aii_ability(
    name="aii_runpod__get_pod_status",
    description="Get real container runtime state for a RunPod pod via GraphQL.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=5,
    check_env="check_env.sh",
)
def core_runpod_get_pod_status(pod_id: str = "") -> dict:
    """Get real container runtime state for a pod via GraphQL.

    Args:
        pod_id: Pod ID (required).

    Returns:
        Dict with success and pod status fields:
          - pod_id: The pod ID
          - desired_status: the status the pod is IN (PROVISIONING /
            STARTING / RUNNING / EXITED / ERROR / TERMINATED). The KEY still
            says "desired" because it is a v1 name every caller in
            ``aii_runpod`` reads, but v2 retired the asked-for/actually-in
            distinction and serves only the latter — so EXITED here means the
            pod HAS exited, never that someone asked it to. Same shim, same
            reason, as ``_v2_pod_to_legacy``'s ``desiredStatus``.
          - uptime_seconds: Container uptime (0 = not started yet)
          - container_running: True if uptime > 0 (container actually started)
          - host_id: NOT a machine id — v2 exposes none. Carries the
            placement timestamp and is only ever read for truthiness: empty
            while unplaced, non-empty once RunPod has allocated a host, which
            is the contract v1's ``machineId`` had and the sole signal a CPU
            stock-out gives. ``RunPodAPI._placement_marker`` is the canonical
            implementation; this is its standalone twin.
          - gpu_display: GPU display name (if applicable)
          - ports: List of port mappings
          - cost_per_hr: Cost per hour
    """
    if not pod_id:
        return {"success": False, "error": "--pod-id is required"}

    try:
        # REST v2 (was GraphQL; v1 REST had no runtime section at all).
        # ``runtime`` is null unless the pod is RUNNING, ports moved to
        # ``private``/``public`` with no ``isIpPublic`` flag (a port is public
        # exactly when it has both a public port and an ip), and v2 exposes no
        # machine identifier — ``host_id`` therefore reports PLACEMENT, empty
        # while ``PROVISIONING`` ("pod is being allocated") and non-empty once
        # allocated, which is the emptiness contract every caller relies on.
        pod_data = rp("GET", f"/pods/{pod_id}")
        if not isinstance(pod_data, dict) or not pod_data.get("id"):
            return {"success": False, "error": f"Pod {pod_id} not found"}

        runtime = pod_data.get("runtime") or {}
        uptime = int(runtime.get("uptime") or 0)
        status_str = str(pod_data.get("status") or "")
        host_id = (
            "" if status_str.upper() == "PROVISIONING" else str(pod_data.get("startedAt") or "")
        )

        ports = []
        for p in runtime.get("ports") or []:
            ports.append(
                {
                    "ip": p.get("ip") or "",
                    # tcp only: an http port is proxy-served on a CGNAT ip that
                    # cannot be dialed, and v1 excluded those.
                    "is_public": bool(p.get("type") == "tcp" and p.get("public") and p.get("ip")),
                    "private_port": p.get("private"),
                    "public_port": p.get("public"),
                    "type": p.get("type", ""),
                }
            )

        return {
            "success": True,
            "pod_id": pod_id,
            "name": pod_data.get("name", ""),
            "desired_status": pod_data.get("status", "UNKNOWN"),
            "uptime_seconds": uptime,
            "container_running": uptime > 0,
            "host_id": host_id,
            "gpu_display": (pod_data.get("gpu") or {}).get("id") or "",
            "ports": ports,
            "cost_per_hr": pod_data.get("cost"),
        }

    except Exception as e:
        # Error flows back via response; ability middleware logs the call at
        # INFO. Caller decides escalation — no double-log at ERROR here.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Get real pod container status via GraphQL")
    parser.add_argument("--pod-id", required=True, help="Pod ID to check")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    params = {"pod_id": args.pod_id}
    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(
            SERVER_NAME_GET_POD_STATUS,
            params,
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_get_pod_status(**params)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        status = result["desired_status"]
        uptime = result["uptime_seconds"]
        host = result.get("host_id") or "none"
        running = "YES" if result["container_running"] else "NO"
        cost = f"${result['cost_per_hr']}/hr" if result.get("cost_per_hr") else ""
        # "(desired)" was v1's label and inverts the meaning under v2: it read
        # as "someone asked for this", so a crashed pod printed
        # "EXITED (desired)". v2 reports the status the pod is IN.
        print(f"  Pod:       {result['pod_id']} ({result.get('name', '')})")
        print(f"  Status:    {status} (actual)")
        print(f"  Container: {running} (uptime={uptime}s)")
        # Labelled by what the value MEANS rather than by its key: v2 has no
        # machine id, so this is the placement timestamp, read for presence.
        print(f"  Placed:    {host}")
        if result.get("ports"):
            ports_str = ", ".join(
                f"{p['private_port']}->{p['public_port']}" for p in result["ports"]
            )
            print(f"  Ports:     {ports_str}")
            # Show SSH command if port 22 is mapped
            for p in result["ports"]:
                if p["private_port"] == 22 and p.get("ip") and p.get("is_public"):
                    print(
                        f"  SSH:       ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519 root@{p['ip']} -p {p['public_port']}"
                    )
        if cost:
            print(f"  Cost:      {cost}")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
