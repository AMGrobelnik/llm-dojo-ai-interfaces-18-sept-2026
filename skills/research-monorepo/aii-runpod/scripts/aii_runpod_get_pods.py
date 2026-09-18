#!/usr/bin/env python
"""
RunPod Get Pods — list all pods, optionally filtered by name prefix or ID.

Usage (via ability server):
    python aii_runpod_get_pods.py
    python aii_runpod_get_pods.py --prefix aii-worker-
    python aii_runpod_get_pods.py --pod-id abc123
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
    SERVER_NAME_GET_PODS,
    _items,
    rp,
)

# =============================================================================
# Core: get_pods
# =============================================================================


@aii_ability(
    name="aii_runpod__get_pods",
    description="List RunPod pods, optionally filtered by name prefix or ID.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=5,
    check_env="check_env.sh",
)
def core_runpod_get_pods(prefix: str = "", pod_id: str = "") -> dict:
    """List RunPod pods, optionally filtered by name prefix or ID.

    Args:
        prefix: Name prefix to filter by (optional).
        pod_id: Single pod ID to fetch (optional, returns list of one).

    Returns:
        Dict with success, pods list.
    """

    try:
        # v2 wraps collections ({"pods": [...]}) where v1 answered a bare list.
        # Iterating the dict yields KEYS, so the next .get() raises
        # AttributeError on a str — a silent, total failure of this ability.
        all_pods = _items(rp("GET", "/pods"), "pods")

        if pod_id:
            all_pods = [p for p in all_pods if p.get("id") == pod_id]
        elif prefix:
            all_pods = [p for p in all_pods if (p.get("name") or "").startswith(prefix)]

        pods = []
        for p in all_pods:
            pods.append(
                {
                    "id": p.get("id", ""),
                    "name": p.get("name", ""),
                    "status": p.get("status", p.get("desiredStatus", "UNKNOWN")),
                    "gpu_type": p.get("gpuType") or p.get("machine", {}).get("gpuDisplayName"),
                    "cost_per_hr": p.get("cost", p.get("costPerHr")),
                    "image": p.get("image", p.get("imageName", "")),
                    "template_id": p.get("templateId", ""),
                }
            )

        return {"success": True, "pods": pods, "count": len(pods)}

    except Exception as e:
        # Error flows back via response; ability middleware logs the call at
        # INFO. Caller decides escalation — no double-log at ERROR here.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="List RunPod pods")
    parser.add_argument("--prefix", default="", help="Filter by name prefix")
    parser.add_argument("--pod-id", default="", help="Get single pod by ID")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    payload = {}
    if args.prefix:
        payload["prefix"] = args.prefix
    if args.pod_id:
        payload["pod_id"] = args.pod_id

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_GET_PODS, payload, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_get_pods(**payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        pods = result.get("pods", [])
        if not pods:
            print("  [INFO] No pods found")
        else:
            for p in pods:
                cost = f"${p['cost_per_hr']}/hr" if p.get("cost_per_hr") else ""
                gpu = f" [{p['gpu_type']}]" if p.get("gpu_type") else ""
                print(f"  {p['status']:<12} {p['id']}  {p['name']}{gpu} {cost}")
            print(f"  [OK]   {len(pods)} pod(s)")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
