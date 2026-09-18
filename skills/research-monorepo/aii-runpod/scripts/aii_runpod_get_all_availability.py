#!/usr/bin/env python
"""RunPod Get ALL Instance Availability — one GraphQL call, whole fallback chain.

A single GraphQL round-trip returns the stock of *every* GPU type and *every*
CPU flavor for one ``(data_center, cloud)`` pair:

  * GPU: ``gpuTypes.lowestPrice.stockStatus`` ("High"/"Medium"/"Low"/null)
  * CPU: ``dataCenters.cpuAvailability {{ cpuFlavorId, available }}``

This replaces N per-entry ``get_instance_availability`` calls with one (~0.85s
for 47 GPUs + 6 CPU flavors, ~6x faster than walking the chain) and — unlike the
GPU-only ``get_instance_availability`` — also covers CPU flavors, which DO have
an availability signal (``available`` bool), contrary to older notes.

Empirically validated: predicted-available instances create successfully and
land a host in ~1s; predicted-unavailable ones fail fast at create (HTTP 500).

Usage (via ability server):
    python aii_runpod_get_all_availability.py --data-center EU-RO-1
    python aii_runpod_get_all_availability.py --data-center EU-RO-1 --json
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
    SERVER_NAME_GET_ALL_AVAILABILITY,
    _items,
    rp,
)

# =============================================================================
# Core: get_all_availability
# =============================================================================


@aii_ability(
    name="aii_runpod__get_all_availability",
    description="Batched GPU+CPU availability for a data center (one GraphQL call).",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=5,
    check_env="check_env.sh",
)
def core_runpod_get_all_availability(
    data_center: str = "", secure_cloud: bool = True, gpu_count: int = 1
) -> dict:
    """Fetch stock for every GPU type + CPU flavor from the v2 catalog.

    Args:
        data_center: DC id to scope availability to (e.g. "EU-RO-1"). When
            empty, GPU stock is global and CPU stock is merged across DCs.
        secure_cloud: Whether to query Secure Cloud GPU stock (default: True).
        gpu_count: GPU count for the GPU stock query (default: 1).

    Returns:
        Dict with:
          - success: bool
          - data_center: echoed DC id
          - gpu: ``{gpu_type_id: stock_status}`` ("" when out of stock)
          - cpu: ``{cpu_flavor_id: available_bool}``
    """
    # Normalise string "false"/"true" from CLI
    if isinstance(secure_cloud, str):
        secure_cloud = secure_cloud.lower() not in ("false", "0", "no")

    try:
        # Two v2 calls, because v2 split into two catalogs what v1 answered in
        # one question — and NEITHER alone reproduces it:
        #
        #  * ``/catalog/gpus`` is the only endpoint taking ``count`` and
        #    ``cloud``, but it is global and cannot be scoped to a DC.
        #  * ``/catalog/datacenters`` is per-DC and carries BOTH availability
        #    maps, but takes neither ``count`` nor ``cloud``.
        #
        # v1's ``gpuTypes.lowestPrice`` took ``gpuCount``, ``secureCloud`` AND
        # ``dataCenterId`` together. So a GPU counts as in stock only where the
        # two readings AGREE — that reproduces v1, whose single answer was
        # already false if any one constraint failed. A GPU the DC does not
        # OFFER at all (9 of 48 are offered in EU-RO-1) keeps its global
        # reading rather than being vetoed: absence is very likely a real
        # structural no, but it is the kind of no this codebase declines to
        # trust the stock signal for.
        #
        # This is the deploy-side ``RunPodAPI.get_all_availability``'s mirror
        # and the two must not answer differently; changes belong in both.
        cloud = "SECURE" if secure_cloud else "COMMUNITY"
        gpu_payload = rp(
            "GET",
            f"/catalog/gpus?include=AVAILABILITY&product=POD&count={gpu_count}&cloud={cloud}",
        )
        payload = rp("GET", "/catalog/datacenters?include=GPU_AVAILABILITY,CPU_AVAILABILITY")

        def _stock(entry: dict) -> str:
            """v2's enum -> v1's stock string. ``NONE`` must become ``""``.

            Callers read a non-empty string as provisionable, so passing
            ``"NONE"`` through unmapped would report every out-of-stock GPU as
            available and invert the signal.
            """
            label = str(entry.get("availability") or "").strip()
            return "" if label.upper() in ("", "NONE") else label

        dc_gpu: dict[str, str] = {}
        cpu: dict[str, bool] = {}
        for dc in _items(payload, "dataCenters"):
            if data_center and dc.get("id") != data_center:
                continue
            for g in dc.get("gpuAvailability") or []:
                key = g.get("id")
                if key:
                    # When unscoped, stock in ANY DC wins.
                    dc_gpu[key] = dc_gpu.get(key) or _stock(g)
            for c in dc.get("cpuAvailability") or []:
                # v2 keys CPU entries by ``id`` (was ``cpuFlavorId``) and
                # reports the same enum as GPUs instead of a boolean.
                flavor = c.get("id")
                if flavor:
                    # When unscoped, an available flavor in ANY DC wins.
                    cpu[flavor] = bool(_stock(c)) or cpu.get(flavor, False)

        gpu: dict[str, str] = {}
        for g in _items(gpu_payload, "gpus"):
            key = g.get("id")
            if not key:
                continue
            gpu[key] = (_stock(g) and dc_gpu[key]) if key in dc_gpu else _stock(g)

        return {
            "success": True,
            "data_center": data_center,
            "secure_cloud": secure_cloud,
            "gpu": gpu,
            "cpu": cpu,
        }

    except Exception as e:
        # Error flows back via response; ability middleware logs the call at
        # INFO. Callers fail open (treat missing data as "attempt it"), so a
        # failure here never blocks a launch — no double-log at ERROR.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Batched GPU+CPU availability for a data center")
    parser.add_argument("--data-center", default="", help="DC id (e.g. 'EU-RO-1')")
    parser.add_argument("--gpu-count", type=int, default=1, help="GPU count for stock query")
    parser.add_argument("--community", action="store_true", help="Query Community Cloud GPU stock")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    params = {
        "data_center": args.data_center,
        "secure_cloud": not args.community,
        "gpu_count": args.gpu_count,
    }
    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_GET_ALL_AVAILABILITY, params, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server).
        result = core_runpod_get_all_availability(**params)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        gpu = result.get("gpu", {})
        cpu = result.get("cpu", {})
        gpu_in = [k for k, v in gpu.items() if v]
        cpu_in = [k for k, v in cpu.items() if v]
        print(f"  Data center: {result.get('data_center') or '(global)'}")
        print(f"  GPU types:   {len(gpu_in)}/{len(gpu)} in stock")
        for k in gpu_in:
            print(f"    [stock] {k} ({gpu[k]})")
        print(f"  CPU flavors: {len(cpu_in)}/{len(cpu)} available")
        for k in sorted(cpu):
            print(f"    [{'ok ' if cpu[k] else 'no '}] {k}")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
