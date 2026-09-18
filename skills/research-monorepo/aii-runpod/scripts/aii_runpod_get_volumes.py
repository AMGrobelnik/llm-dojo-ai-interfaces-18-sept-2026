#!/usr/bin/env python
"""
RunPod Get Volumes — list all network volumes, optionally filtered by name.

Usage (via ability server):
    python aii_runpod_get_volumes.py
    python aii_runpod_get_volumes.py --name aii-pipeline-data-eu
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
    SERVER_NAME_GET_VOLUMES,
    _items,
    rp,
)

# =============================================================================
# Core: get_volumes
# =============================================================================


@aii_ability(
    name="aii_runpod__get_volumes",
    description="List RunPod network volumes, optionally filtered by name.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=5,
    check_env="check_env.sh",
)
def core_runpod_get_volumes(name: str = "", prefix: str = "") -> dict:
    """List RunPod network volumes, optionally filtered by name.

    Args:
        name: Exact volume name to find (optional).
        prefix: Name prefix to filter by (optional).

    Returns:
        Dict with success, volumes list.
    """

    try:
        # v2 wraps collections ({"networkVolumes": [...]}) where v1 answered a bare list.
        # Iterating the dict yields KEYS, so the next .get() raises
        # AttributeError on a str — a silent, total failure of this ability.
        all_volumes = _items(rp("GET", "/network-volumes"), "networkVolumes")

        if name:
            all_volumes = [v for v in all_volumes if v.get("name") == name]
        elif prefix:
            all_volumes = [v for v in all_volumes if (v.get("name") or "").startswith(prefix)]

        volumes = []
        for v in all_volumes:
            volumes.append(
                {
                    "id": v.get("id", ""),
                    "name": v.get("name", ""),
                    "size": v.get("size"),
                    # v2 spells this ``dataCenter`` on a NetworkVolume while a
                    # Pod keeps ``dataCenterId`` — verified against the live
                    # response, whose volume objects carry exactly
                    # {dataCenter, id, name, size, type}. Reading the pod's
                    # spelling here returned "" for every volume, so the one
                    # field an operator needs to place a pod next to its data
                    # was blank in every listing.
                    "data_center_id": v.get("dataCenter", ""),
                }
            )

        return {"success": True, "volumes": volumes, "count": len(volumes)}

    except Exception as e:
        # Error flows back via response; ability middleware logs the call at
        # INFO. Caller decides escalation — no double-log at ERROR here.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="List RunPod network volumes")
    parser.add_argument("--name", default="", help="Filter by exact name")
    parser.add_argument("--prefix", default="", help="Filter by name prefix")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    payload = {}
    if args.name:
        payload["name"] = args.name
    if args.prefix:
        payload["prefix"] = args.prefix

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_GET_VOLUMES, payload, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_get_volumes(**payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        volumes = result.get("volumes", [])
        if not volumes:
            print("  [INFO] No volumes found")
        else:
            for v in volumes:
                size = f"{v['size']}GB" if v.get("size") else ""
                dc = v.get("data_center_id", "")
                print(f"  {v['id']:<14} {v['name']:<30} {size:<8} {dc}")
            print(f"  [OK]   {len(volumes)} volume(s)")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
