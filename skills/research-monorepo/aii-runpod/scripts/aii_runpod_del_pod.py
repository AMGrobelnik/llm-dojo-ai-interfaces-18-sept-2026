#!/usr/bin/env python
"""
RunPod Delete Pod — terminate pod and/or delete network volume by name.

Closely mirrors stop_runpod.sh: finds resources by name, terminates/deletes,
verifies they're gone. Volume deletion retries on 4xx/5xx (RunPod needs time
to detach pods from the volume).

Usage (via ability server):
    python aii_runpod_del_pod.py --pod-name aii_orchestrator
    python aii_runpod_del_pod.py --pod-id abc123def456
    python aii_runpod_del_pod.py --pod-name my-pod --volume-name my-vol
    python aii_runpod_del_pod.py --volume-name my-vol

Prefer ``--pod-id`` when you have one: deleting by NAME resolves through a
listing, and a name that does not match reports "No pod found" and exits 0 —
indistinguishable from a successful delete.
"""

import argparse
import json
import sys
import time

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


# Shared helpers from the template script
from aii_runpod_gen_template import (
    DEFAULT_TIMEOUT,
    SERVER_NAME_DEL_POD,
    _find_by_name,
    _items,
    rp,
)
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

# =============================================================================
# Core: del_pod
# =============================================================================


@aii_ability(
    name="aii_runpod__del_pod",
    description="Terminate a RunPod pod and/or delete a network volume by name or ID.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=10,
    check_env="check_env.sh",
)
def core_runpod_del_pod(
    pod_name: str = "", pod_id: str = "", volume_name: str = "", volume_id: str = ""
) -> dict:
    """Terminate a pod and/or delete a network volume by name or ID.

    Args:
        pod_name: Pod name to terminate (optional).
        pod_id: Pod ID to terminate directly (optional, takes precedence).
        volume_name: Volume name to delete (optional).
        volume_id: Volume ID to delete directly (optional, takes precedence).
        At least one must be provided.

    Returns:
        Dict with success, pod_terminated, volume_deleted, details.
    """

    if not pod_name and not pod_id and not volume_name and not volume_id:
        return {
            "success": False,
            "error": "Provide pod_name/pod_id and/or volume_name/volume_id",
        }

    results = {
        "success": True,
        "pod_terminated": None,
        "volume_deleted": None,
        "details": [],
    }

    try:
        # --- Terminate pod ---
        if pod_id or pod_name:
            # Resolve pod_id from pod_name if needed
            resolved_pod_id = pod_id
            if not resolved_pod_id and pod_name:
                # v2 wraps collections ({"pods": [...]}) where v1 answered a
                # bare list. Iterating the dict yields KEYS, so the next
                # .get() raises AttributeError on a str — a silent, total
                # failure of delete-by-name. That used to be the only mode the
                # CLI exposed; ``--pod-id`` now skips this lookup entirely.
                all_pods = _items(rp("GET", "/pods"), "pods")
                pod = _find_by_name(all_pods, pod_name)
                if not pod:
                    results["pod_terminated"] = False
                    results["details"].append(f"No pod found: {pod_name}")
                    logger.warning(f"No pod found: {pod_name}")
                else:
                    resolved_pod_id = pod["id"]

            if resolved_pod_id:
                display_name = pod_name or resolved_pod_id
                logger.info(f"Terminating: {display_name} ({resolved_pod_id})...")

                # Single DELETE call — client.py terminate_pod() already
                # retries at the HTTP level. No verification loop needed:
                # if DELETE returns 200, the pod is gone. The old retry+verify
                # loops (up to 180s blocking) exceeded Cloudflare's ~100s
                # proxy timeout, causing 524 errors and pod orphaning.
                try:
                    rp("DELETE", f"/pods/{resolved_pod_id}")
                except RuntimeError as e:
                    results["success"] = False
                    results["error"] = f"Failed to delete pod: {display_name} — {e}"
                    results["pod_terminated"] = False
                    results["details"].append(results["error"])
                    return results

                results["pod_terminated"] = True
                results["details"].append(f"Pod terminated: {display_name} ({resolved_pod_id})")
                logger.info(f"Pod terminated: {display_name} ({resolved_pod_id})")

        # --- Delete volume ---
        if volume_id or volume_name:
            resolved_volume_id = volume_id
            display_vol_name = volume_name or volume_id
            if not resolved_volume_id and volume_name:
                all_volumes = _items(rp("GET", "/network-volumes"), "networkVolumes")
                volume = _find_by_name(all_volumes, volume_name)
                if not volume:
                    results["volume_deleted"] = False
                    results["details"].append(f"No volume found: {volume_name}")
                    logger.warning(f"No volume found: {volume_name}")
                else:
                    resolved_volume_id = volume["id"]

            if resolved_volume_id:
                logger.info(f"Deleting volume: {display_vol_name} ({resolved_volume_id})...")

                # Retry — RunPod may still be detaching pods from the volume
                @retry(
                    stop=stop_after_attempt(12),
                    wait=wait_fixed(5),
                    retry=retry_if_exception_type(RuntimeError),
                    reraise=True,
                )
                def _delete_volume():
                    rp("DELETE", f"/network-volumes/{resolved_volume_id}")

                try:
                    _delete_volume()
                except RuntimeError:
                    results["success"] = False
                    results["volume_deleted"] = False
                    results["details"].append(
                        f"Failed to delete volume after retries: {display_vol_name}"
                    )
                    return results

                # Verify volume is gone
                logger.info("Verifying volume deleted...")
                verified = False
                for _ in range(12):
                    all_volumes = _items(rp("GET", "/network-volumes"), "networkVolumes")
                    if volume_name:
                        check = _find_by_name(all_volumes, volume_name)
                    else:
                        check = any(v.get("id") == resolved_volume_id for v in all_volumes)
                    if not check:
                        verified = True
                        break
                    time.sleep(5)

                if not verified:
                    results["success"] = False
                    results["volume_deleted"] = False
                    results["details"].append(
                        f"Volume still exists after deletion: {display_vol_name}"
                    )
                    return results

                results["volume_deleted"] = True
                results["details"].append(
                    f"Volume deleted: {display_vol_name} ({resolved_volume_id})"
                )
                logger.info(f"Volume deleted: {display_vol_name} ({resolved_volume_id})")

        return results

    except Exception as e:
        # Recoverable conditions (transient API 5xx, "in use", etc.) flow back
        # via the response; the ability middleware logs them at INFO. Logging
        # ERROR here would falsely escalate cases the caller will retry.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI (calls ability server endpoint)
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Delete RunPod pod and/or volume")
    parser.add_argument("--pod-name", default="", help="Pod name to terminate")
    # The ability has taken pod_id/volume_id since it was written (and treats
    # pod_id as taking PRECEDENCE over the name), but the CLI never exposed
    # them — so the precise selector was unreachable from the command line the
    # skill tells you to use. Deleting by name is strictly weaker: it resolves
    # through a listing, and when the name does not match it reports "No pod
    # found" and exits 0, which reads exactly like a successful delete.
    parser.add_argument("--pod-id", default="", help="Pod ID to terminate (wins over --pod-name)")
    parser.add_argument("--volume-name", default="", help="Volume name to delete")
    parser.add_argument(
        "--volume-id", default="", help="Volume ID to delete (wins over --volume-name)"
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if not (args.pod_name or args.pod_id or args.volume_name or args.volume_id):
        parser.error("Provide --pod-name/--pod-id and/or --volume-name/--volume-id")

    payload = {}
    if args.pod_name:
        payload["pod_name"] = args.pod_name
    if args.pod_id:
        payload["pod_id"] = args.pod_id
    if args.volume_name:
        payload["volume_name"] = args.volume_name
    if args.volume_id:
        payload["volume_id"] = args.volume_id

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_DEL_POD, payload, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_del_pod(**payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        for detail in result.get("details", []):
            print(f"  [OK]   {detail}")
        print("  [OK]   Done")
    else:
        error = result.get("error", "")
        details = result.get("details", [])
        for detail in details:
            print(f"  [INFO] {detail}")
        if error:
            print(f"  [FAIL] {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
