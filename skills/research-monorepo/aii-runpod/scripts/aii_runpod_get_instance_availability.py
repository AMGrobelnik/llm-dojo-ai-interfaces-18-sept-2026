#!/usr/bin/env python
"""
RunPod Get Instance Availability — check GPU stock via GraphQL.

Queries the ``gpuTypes`` GraphQL endpoint for stock status and availability
of a specific GPU type in the Secure Cloud.

CPU instances don't have an availability query — this is GPU-only.

Usage (via ability server):
    python aii_runpod_get_instance_availability.py --gpu-type-id "NVIDIA RTX A4500"
    python aii_runpod_get_instance_availability.py --gpu-type-id "NVIDIA GeForce RTX 4090" --gpu-count 1
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
    SERVER_NAME_GET_INSTANCE_AVAILABILITY,
    _items,
    rp,
)

# =============================================================================
# Core: get_instance_availability
# =============================================================================


@aii_ability(
    name="aii_runpod__get_instance_availability",
    description="Check GPU instance availability on RunPod via GraphQL.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=5,
    check_env="check_env.sh",
)
def core_runpod_get_instance_availability(
    gpu_type_id: str = "", gpu_count: int = 1, secure_cloud: bool = True
) -> dict:
    """Check GPU instance availability via GraphQL.

    Args:
        gpu_type_id: GPU type ID (e.g. "NVIDIA RTX A4500"). Required.
        gpu_count: Number of GPUs needed (default: 1).
        secure_cloud: Whether to check Secure Cloud (default: True).

    Returns:
        Dict with success and availability fields:
          - gpu_type_id: The queried GPU type ID
          - display_name: Human-readable GPU name
          - memory_gb: GPU VRAM in GB
          - stock_status: "High", "Medium", "Low", or null (unavailable)
          - available: True if stock_status is not null
          - max_gpu_count: the tier's per-request GPU ceiling (``maxCount``).
            A static limit — it says nothing about stock.
          - available_gpu_counts: GPU counts that could actually be
            provisioned right now: ``1..max_gpu_count`` when ``available``,
            and EMPTY when not. It must never disagree with ``available``.
          - secure_price: On-demand price in Secure Cloud
          - spot_price: Minimum bid price (spot)
    """
    if not gpu_type_id:
        return {"success": False, "error": "--gpu-type-id is required"}

    # Normalise string "false"/"true" from CLI
    if isinstance(secure_cloud, str):
        secure_cloud = secure_cloud.lower() not in ("false", "0", "no")

    try:
        # REST v2 catalog. ``count`` and ``cloud`` are the same two inputs the
        # GraphQL ``lowestPrice`` took, and they change the answer, so they
        # are passed through rather than dropped.
        cloud = "SECURE" if secure_cloud else "COMMUNITY"
        payload = rp(
            "GET",
            f"/catalog/gpus?include=AVAILABILITY&product=POD&count={gpu_count}&cloud={cloud}",
        )
        gpu_types = [g for g in _items(payload, "gpus") if g.get("id") == gpu_type_id]

        if not gpu_types:
            return {
                "success": True,
                "gpu_type_id": gpu_type_id,
                "available": False,
                "stock_status": None,
                "message": f"GPU type '{gpu_type_id}' not found",
            }

        gpu = gpu_types[0]
        # v2 reports an enum where v1 reported a free-text stock string that
        # was null when out; "NONE" is the out-of-stock value here.
        label = str(gpu.get("availability") or "").strip()
        stock_status = None if label.upper() in ("", "NONE") else label
        # ``maxUnreservedGpuCount`` has no v2 field; ``maxCount`` is the
        # per-tier ceiling, which is what bounds a request of this size.
        max_counts = gpu.get("maxCount") or {}
        max_gpu = int(max_counts.get(cloud.lower(), 0) or 0) if isinstance(max_counts, dict) else 0

        # Available = the catalog reports stock AND the tier permits a GPU.
        available = stock_status is not None and max_gpu > 0

        # ``available_gpu_counts`` is documented as the AVAILABLE
        # configurations, so it must not contradict ``available`` in the same
        # response. ``maxCount`` is a static per-tier CEILING and knows nothing
        # about stock, so deriving the list from it alone reported
        # ``available: false, stock_status: null, available_gpu_counts:
        # [1..8]`` — observed live for NVIDIA A100 80GB PCIe. A caller
        # trusting the list over the flag would pick a count for a GPU that
        # cannot be provisioned at any count.
        #
        # Empty when nothing is in stock is the reading that matches the name;
        # ``max_gpu_count`` still carries the ceiling for anyone who wants it.
        available_counts = list(range(1, max_gpu + 1)) if available else []

        return {
            "success": True,
            "gpu_type_id": gpu.get("id", gpu_type_id),
            "display_name": gpu.get("name", ""),
            "memory_gb": gpu.get("memory"),
            "stock_status": stock_status,
            "available": available,
            "max_gpu_count": max_gpu,
            "available_gpu_counts": available_counts,
            # v2 groups prices by tier under ``price`` and renames the two
            # cloud flags. There is no v2 equivalent of the GraphQL spot bid
            # (``minimumBidPrice``), so the community-tier price — the only
            # sub-secure figure v2 publishes — stands in for it; the key is
            # kept so callers reading it do not break.
            "secure_price": (gpu.get("price") or {}).get("secure"),
            "spot_price": (gpu.get("price") or {}).get("community"),
            "secure_cloud": bool(gpu.get("secure", False)),
            "community_cloud": bool(gpu.get("community", False)),
        }

    except Exception as e:
        # Error flows back via response; ability middleware logs the call at
        # INFO. Caller decides escalation — no double-log at ERROR here.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Check GPU instance availability via GraphQL")
    parser.add_argument(
        "--gpu-type-id", required=True, help="GPU type ID (e.g. 'NVIDIA RTX A4500')"
    )
    parser.add_argument("--gpu-count", type=int, default=1, help="Number of GPUs needed")
    parser.add_argument(
        "--community",
        action="store_true",
        help="Check Community Cloud instead of Secure",
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    params = {
        "gpu_type_id": args.gpu_type_id,
        "gpu_count": args.gpu_count,
        "secure_cloud": not args.community,
    }
    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(
            SERVER_NAME_GET_INSTANCE_AVAILABILITY,
            params,
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_get_instance_availability(**params)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        name = result.get("display_name") or result["gpu_type_id"]
        mem = result.get("memory_gb") or "?"
        stock = result.get("stock_status") or "Unavailable"
        avail = "YES" if result["available"] else "NO"
        max_gpu = result.get("max_gpu_count", 0)
        price = result.get("secure_price")
        spot = result.get("spot_price")

        print(f"  GPU:       {name} ({mem}GB VRAM)")
        print(f"  Available: {avail} (stock: {stock})")
        print(f"  Max GPUs:  {max_gpu}")
        if result.get("available_gpu_counts"):
            print(f"  Configs:   {result['available_gpu_counts']}")
        if price is not None:
            print(f"  Price:     ${price}/hr (on-demand)")
        if spot is not None:
            print(f"  Spot:      ${spot}/hr (min bid)")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
