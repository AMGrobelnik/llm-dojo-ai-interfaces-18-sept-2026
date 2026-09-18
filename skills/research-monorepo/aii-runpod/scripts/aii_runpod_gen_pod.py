#!/usr/bin/env python
"""
RunPod Pod Creation — create a CPU/GPU pod, wait for container ready.

Closely mirrors gen_runpod.sh: finds template, finds/creates volume,
creates pod, waits for container ready via GraphQL (runtime.uptimeInSeconds > 0
+ machine.podHostId for SSH username).

Supports both orchestrator pods (lookup by name) and worker pods (direct IDs).

Usage (via ability server):
    # Orchestrator pod (lookup by name):
    python aii_runpod_gen_pod.py --pod-name aii_orchestrator
    python aii_runpod_gen_pod.py --pod-name my-pod --template-name my-tpl --cpu-flavor cpu3m --vcpu 8

    # Worker pod (direct IDs, skip wait):
    python aii_runpod_gen_pod.py --pod-name aii_worker_x --template-id abc123 --volume-id vol456 --skip-wait
    python aii_runpod_gen_pod.py --pod-name gpu-worker --template-id abc --gpu-type-id "NVIDIA RTX A4500"
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


# Shared helpers from the template script (same process, same sys.path)
from aii_runpod_gen_template import (
    DEFAULT_TIMEOUT,
    SERVER_NAME_CREATE_POD,
    _find_by_name,
    _items,
    rp,
)
from loguru import logger

# =============================================================================
# Core: create_pod
# =============================================================================


@aii_ability(
    name="aii_runpod__gen_pod",
    description="Create a RunPod pod (CPU or GPU), optionally wait for container ready.",
    check_env="check_env.sh",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=3,
    # Pod creation is NOT idempotent — never blanket-retry it. A
    # transient-looking failure can arrive AFTER the pod exists (the
    # ready-wait below returns "Timeout waiting for pod ready" WITH a
    # ``pod_id``), so the default worker-side retry would re-run the whole
    # handler and create duplicate same-named pods that keep billing: the
    # retry loop returns only the LAST result, dropping earlier pod_ids,
    # and preflight/CLI pods have no name-based reaper to sweep strays.
    # Callers own recovery (e.g. GPU-type fallback iteration) with full
    # context instead.
    retries=0,
)
def core_runpod_create_pod(
    pod_name: str = "",
    image: str = "<author>/aii_pipeline:latest",
    data_center: str = "EU-RO-1",
    disk_gb: int = 40,
    cloud_type: str = "SECURE",
    template_id: str = "",
    template_name: str = "aii_orchestrator",
    volume_id: str = "",
    # REST v2 requires an explicit mount path for a network volume ("no
    # default — must be specified explicitly"), where v1 inferred one.
    # Defaulted to ``execution.runpod.volume_mount_path``, the value every
    # deployment config carries and the templates are built from.
    volume_mount_path: str = "/research-monorepo/aii_data",
    # Empty by default = ATTACH NO VOLUME. This used to default to
    # ``aii_pipeline_data_eu``, which cannot match anything: the real volume is
    # hyphenated (``aii-pipeline-data-eu``) and ``_find_by_name`` is an exact
    # match with no normalisation. So the lookup could only ever MISS and fall
    # through to the create branch below, minting a fresh ``volume_size_gb``
    # (1 TB, ~$70/month) volume on every call that omitted a volume. A default
    # whose only reachable outcome is an orphan is not a default; it is a bill.
    # Callers that want the production volume pass ``volume_id`` (what every
    # production path does — ``runpod_backend.py`` reads it from config) or the
    # correctly-spelled name.
    volume_name: str = "",
    volume_size_gb: int = 1000,
    cpu_flavor: str = "cpu3g",
    vcpu: int = 4,
    gpu_type_id: str = "",
    gpu_count: int = 1,
    docker_start_cmd: str = "",
    ports: str = "",
    skip_wait: bool = False,
    wait_timeout: int = 600,
    env: dict | None = None,
) -> dict:
    """Create a RunPod pod (CPU or GPU), optionally wait for container ready."""
    # ``pod_name`` has no default at the ability level so an empty-body
    # POST returns 422 instead of silently spawning a pod with the legacy
    # ``aii_orchestrator`` default. CLI keeps its argparse default.
    if not pod_name:
        return {"success": False, "error": "pod_name is required"}
    env = env or {}

    try:
        # --- Resolve template ---
        if not template_id:
            all_templates = _items(rp("GET", "/templates"), "templates")
            template = _find_by_name(all_templates, template_name)
            if not template:
                return {
                    "success": False,
                    "error": f"Template '{template_name}' not found. Create it first.",
                }
            template_id = template["id"]
            logger.info(f"Template: {template_name} ({template_id})")
        else:
            logger.info(f"Template: {template_id} (direct)")

        # --- Resolve volume ---
        # An empty ``volume_name`` (with no explicit ``volume_id``) means
        # "attach no network volume" — for ephemeral pods (e.g. the preflight
        # healthcheck) that only need container disk. Without this guard the
        # name lookup below falls through to CREATE a fresh ``volume_size_gb``
        # volume on every call that omits a volume, silently leaking 1 TB
        # volumes (the legacy default name ``aii_pipeline_data_eu`` also never
        # matches the real hyphenated ``aii-pipeline-data-eu``, so the lookup
        # could never reuse the production volume anyway).
        if volume_id:
            logger.info(f"Volume: {volume_id} (direct)")
        elif volume_name:
            all_volumes = _items(rp("GET", "/network-volumes"), "networkVolumes")
            volume = _find_by_name(all_volumes, volume_name)
            if volume:
                volume_id = volume["id"]
                logger.info(f"Volume: {volume_name} ({volume_id})")
            else:
                logger.info(f"Creating volume: {volume_name} ({volume_size_gb}GB)...")
                result = rp(
                    "POST",
                    "/network-volumes",
                    {
                        "name": volume_name,
                        "size": volume_size_gb,
                        # ``dataCenter``, NOT the pod's ``dataCenterId``. The
                        # two objects genuinely spell it differently in v2 — a
                        # Pod still reports ``dataCenterId``, a NetworkVolume
                        # requires ``dataCenter`` — so this is not a rename
                        # that was missed twice but a real asymmetry.
                        #
                        # It cannot fail quietly: v2 rejects unknown fields, so
                        # the old spelling made every volume create a 422 that
                        # named BOTH halves of the mistake at once —
                        # "missing property 'dataCenter'" and "additional
                        # properties 'dataCenterId' not allowed" (probed with
                        # size 0, which is refused before anything is billed).
                        "dataCenter": data_center,
                    },
                )
                volume_id = result.get("id", "")
                if not volume_id:
                    return {
                        "success": False,
                        "error": f"Failed to create volume: {result}",
                    }
                logger.info(f"Created volume: {volume_name} ({volume_id})")
        else:
            logger.info("No network volume (volume_name empty) — container disk only")

        # --- Build pod request body ---
        if gpu_type_id:
            # GPU pod
            logger.info(f"Creating GPU pod: {pod_name} ({gpu_type_id} x{gpu_count})...")
            body = {
                "name": pod_name,
                "image": image,
                "gpu": {"id": gpu_type_id, "count": gpu_count},
                "disk": disk_gb,
                "cloud": cloud_type,
            }
        else:
            # CPU pod
            logger.info(f"Creating CPU pod: {pod_name} ({cpu_flavor} x{vcpu}vCPU)...")
            body = {
                "name": pod_name,
                "image": image,
                "cpu": {"id": cpu_flavor, "vcpuCount": vcpu},
                "disk": disk_gb,
                "cloud": cloud_type,
            }

        # Common fields. REST v2 renamed most of the create body and validates
        # strictly — it rejects an unrecognised field rather than ignoring it,
        # so the v1 names would have failed every create outright:
        #
        #   imageName -> image            containerDiskInGb -> disk
        #   cloudType -> cloud            computeType -> implied by cpu/gpu
        #   gpuTypeIds+gpuCount -> gpu{}  cpuFlavorIds+vcpuCount -> cpu{}
        #   networkVolumeId -> mounts.network[]   dockerStartCmd -> args
        body["dataCenterIds"] = [data_center]
        if volume_id:
            # v2's NetworkMount documents "no default — must be specified
            # explicitly" for the path, where v1 inferred it.
            body["mounts"] = {"network": [{"volumeId": volume_id, "path": volume_mount_path}]}
        if template_id:
            body["templateId"] = template_id
        if docker_start_cmd:
            body["args"] = json.dumps({"cmd": ["bash", "-c", docker_start_cmd]})
        if ports:
            body["ports"] = [p.strip() for p in ports.split(",")]
        if env:
            body["env"] = env

        # --- Create pod ---
        pod_result = rp("POST", "/pods", body)
        pod_id = pod_result.get("id", "")
        if not pod_id:
            return {"success": False, "error": f"Failed to create pod: {pod_result}"}
        cost = pod_result.get("cost", pod_result.get("costPerHr", "?"))
        logger.info(f"Created pod: {pod_name} ({pod_id}, ${cost}/hr)")

        # --- Skip wait mode (for worker pods) ---
        if skip_wait:
            return {
                "success": True,
                "pod_id": pod_id,
                "pod_name": pod_name,
                "cost_per_hr": cost,
                "volume_id": volume_id,
                "template_id": template_id,
                "message": f"Pod created: {pod_name} ({pod_id}, ${cost}/hr)",
            }

        # --- Wait for container ready (REST v2) ---
        # Was a GraphQL poll for ``runtime.uptimeInSeconds`` +
        # ``machine.podHostId``, which REST v1 lacked. v2 carries the uptime
        # under ``runtime.uptime`` (and nulls ``runtime`` entirely unless the
        # pod is RUNNING), and — better than the old reconstruction — hands
        # back the finished proxy SSH command, so the host id no longer has to
        # be dug out and re-assembled into one.
        logger.info("Waiting for pod container to be ready...")

        ssh_command = ""
        start = time.monotonic()
        while time.monotonic() - start < wait_timeout:
            try:
                pod_data = rp("GET", f"/pods/{pod_id}")
                pod_data = pod_data if isinstance(pod_data, dict) else {}
                status = str(pod_data.get("status") or "")
                uptime = int((pod_data.get("runtime") or {}).get("uptime") or 0)
                proxy = (pod_data.get("ssh") or {}).get("proxy") or {}

                if status in ("EXITED", "ERROR", "TERMINATED"):
                    return {
                        "success": False,
                        "error": f"Pod entered terminal state: {status}",
                        "pod_id": pod_id,
                    }

                # Same two conditions as before: the container is up AND the
                # pod has been placed. ``proxy.command`` is populated only
                # once RunPod has a host to route to, so it stands in for the
                # old non-empty ``podHostId`` check.
                if uptime > 0 and proxy.get("command"):
                    ssh_command = str(proxy["command"])
                    break

                elapsed = int(time.monotonic() - start)
                logger.debug(f"/health poll: status={status}, uptime={uptime} ({elapsed}s)")

            except Exception as e:
                logger.debug(f"pod poll error (non-fatal): {e}")

            time.sleep(5)
        else:
            return {
                "success": False,
                "error": f"Timeout waiting for pod ready ({wait_timeout}s)",
                "pod_id": pod_id,
            }

        elapsed = int(time.monotonic() - start)
        worker_url = f"https://{pod_id}-8080.proxy.runpod.net"

        logger.info(f"Pod ready: {pod_name} ({pod_id}, ${cost}/hr) in {elapsed}s")
        logger.info(f"SSH: {ssh_command}")

        return {
            "success": True,
            "pod_id": pod_id,
            "pod_name": pod_name,
            "cost_per_hr": cost,
            "ssh_command": ssh_command,
            # v2's proxy username — the identity the command above connects as,
            # and the direct replacement for GraphQL's ``machine.podHostId``.
            "ssh_host": ssh_command.split(" ")[1].split("@")[0] if "@" in ssh_command else "",
            "worker_url": worker_url,
            "volume_id": volume_id,
            "template_id": template_id,
            "wait_seconds": elapsed,
            "message": f"Pod ready: {pod_name} ({pod_id}, ${cost}/hr)",
        }

    except Exception as e:
        # "No instances available" / transient 5xx surface here every attempt.
        # Callers iterate fallback GPU types — logging ERROR per attempt would
        # falsely escalate recovered failures. Error flows back via the
        # response; ability middleware logs the call at INFO.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI (calls ability server endpoint)
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Create a RunPod pod")
    parser.add_argument("--pod-name", default="aii_orchestrator", help="Pod name")
    parser.add_argument(
        "--template-name", default="aii_orchestrator", help="Template name (must exist)"
    )
    parser.add_argument(
        "--template-id", default="", help="Template ID directly (skips name lookup)"
    )
    parser.add_argument(
        "--volume-name",
        default="",
        help="Network volume name (default: none — attach no volume)",
    )
    parser.add_argument("--volume-id", default="", help="Volume ID directly (skips name lookup)")
    parser.add_argument(
        "--volume-size-gb", type=int, default=1000, help="Volume size GB if creating"
    )
    parser.add_argument("--data-center", default="EU-RO-1", help="Data center ID")
    parser.add_argument(
        "--cpu-flavor", default="cpu3g", help="CPU flavor (cpu3g, cpu3m, cpu5g, ...)"
    )
    parser.add_argument("--vcpu", type=int, default=4, help="vCPU count")
    parser.add_argument("--gpu-type-id", default="", help="GPU type ID (enables GPU mode)")
    parser.add_argument("--gpu-count", type=int, default=1, help="Number of GPUs")
    parser.add_argument("--disk-gb", type=int, default=40, help="Container disk GB")
    parser.add_argument("--image", default="<author>/aii_pipeline:latest", help="Docker image")
    parser.add_argument(
        "--docker-start-cmd", default="", help="Override container start command (CMD)"
    )
    parser.add_argument("--ports", default="", help="Port config (e.g. '8080/http')")
    parser.add_argument(
        "--env-json",
        default="",
        help='Extra env vars as JSON object (e.g. \'{"KEY":"val"}\')',
    )
    parser.add_argument(
        "--skip-wait", action="store_true", help="Return immediately after creation"
    )
    parser.add_argument(
        "--wait-timeout", type=int, default=600, help="Max seconds to wait for ready"
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    payload = {
        "pod_name": args.pod_name,
        "template_name": args.template_name,
        "volume_name": args.volume_name,
        "volume_size_gb": args.volume_size_gb,
        "data_center": args.data_center,
        "cpu_flavor": args.cpu_flavor,
        "vcpu": args.vcpu,
        "disk_gb": args.disk_gb,
        "image": args.image,
        "wait_timeout": args.wait_timeout,
    }
    if args.template_id:
        payload["template_id"] = args.template_id
    if args.volume_id:
        payload["volume_id"] = args.volume_id
    if args.gpu_type_id:
        payload["gpu_type_id"] = args.gpu_type_id
        payload["gpu_count"] = args.gpu_count
    if args.docker_start_cmd:
        payload["docker_start_cmd"] = args.docker_start_cmd
    if args.ports:
        payload["ports"] = args.ports
    if args.skip_wait:
        payload["skip_wait"] = True
    if args.env_json:
        payload["env"] = json.loads(args.env_json)

    # Pod creation waits for container ready (image pull ~300s).
    # Override both the HTTP client timeout and server-side timeout.
    pod_timeout = max(args.wait_timeout + 60, DEFAULT_TIMEOUT)
    payload["_timeout"] = pod_timeout
    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_CREATE_POD, payload, timeout=pod_timeout)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        # ``_timeout`` is a transport-only key (HTTP/server timeout), not a
        # core_runpod_create_pod parameter — drop it before the local call.
        core_payload = {k: v for k, v in payload.items() if k != "_timeout"}
        result = core_runpod_create_pod(**core_payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        print(
            f"  [OK]   Pod: {result['pod_name']} ({result['pod_id']}, ${result['cost_per_hr']}/hr)"
        )
        if result.get("ssh_command"):
            print(f"  [INFO] SSH: {result['ssh_command']}")
        if result.get("worker_url"):
            print(f"  [INFO] Worker URL: {result['worker_url']}")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
