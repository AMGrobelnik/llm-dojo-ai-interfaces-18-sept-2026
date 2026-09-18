#!/usr/bin/env python
"""
RunPod Template Management — find or create a template by name.

Closely mirrors gen_template.sh: checks if template exists, creates if not,
verifies creation. Registered as ability server endpoint.

Usage (via ability server):
    python aii_runpod_gen_template.py --name aii_worker_cpu_light
    python aii_runpod_gen_template.py --name my-template --image myimg:latest --env-json '{"KEY":"val"}'
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


from aii_lib.runpod_endpoints import RUNPOD_REST_BASE
from loguru import logger

# =============================================================================
# Shared RunPod API helpers (used by all 3 scripts)
# =============================================================================

SERVER_NAME_TEMPLATE = "aii_runpod__gen_template"
SERVER_NAME_CREATE_POD = "aii_runpod__gen_pod"
SERVER_NAME_DEL_POD = "aii_runpod__del_pod"
SERVER_NAME_DEL_TEMPLATE = "aii_runpod__del_template"
SERVER_NAME_GET_PODS = "aii_runpod__get_pods"
SERVER_NAME_GET_TEMPLATES = "aii_runpod__get_templates"
SERVER_NAME_GET_VOLUMES = "aii_runpod__get_volumes"
SERVER_NAME_GET_POD_STATUS = "aii_runpod__get_pod_status"
SERVER_NAME_GET_INSTANCE_AVAILABILITY = "aii_runpod__get_instance_availability"
SERVER_NAME_GET_ALL_AVAILABILITY = "aii_runpod__get_all_availability"
DEFAULT_TIMEOUT = 300.0

# REST v2. v1 retires 2026-11-15 and GraphQL in early 2027, both announced
# when v2 went GA on 2026-08-18. v2 wraps collections (``{"templates": [...]}``
# where v1 answered a bare list) — see ``_items``.
REST_BASE = RUNPOD_REST_BASE

_session: requests.Session | None = None
_api_key: str = ""


def init_runpod() -> None:
    """Load RunPod API key from .env and create a requests session."""
    global _session, _api_key

    # Load .env (same logic as bash scripts)
    project_root = Path(__file__).resolve().parents[4]
    env_file = project_root / ".env"
    if not os.environ.get("RUNPOD_API_KEY") and env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("RUNPOD_API_KEY="):
                val = line.split("=", 1)[1].strip().strip("\"'")
                os.environ["RUNPOD_API_KEY"] = val
                break

    _api_key = os.environ.get("RUNPOD_API_KEY", "")
    if not _api_key:
        raise RuntimeError("RUNPOD_API_KEY not set (check .env or environment)")

    _session = requests.Session()
    _session.headers.update(
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key}",
        }
    )

    # Warmup — list templates to verify connectivity
    try:
        resp = _session.get(f"{REST_BASE}/templates", timeout=10)
        resp.raise_for_status()
        # ``len()`` on the v2 envelope counts its ONE key, so this always
        # said "1 templates" — a connectivity check that cannot notice an
        # empty account is not much of a check.
        logger.info(f"RunPod API connected ({len(_items(resp.json(), 'templates'))} templates)")
    except Exception as e:
        logger.warning(f"RunPod warmup failed (non-fatal): {e}")

    logger.info("RunPod tools initialized")


def rp(method: str, path: str, body: dict | None = None) -> dict | list:
    """Make an authenticated RunPod REST API request.

    Mirrors the rp() bash helper. Returns parsed JSON.
    Raises RuntimeError on 4xx/5xx.
    """
    global _session, _api_key
    if _session is None:
        init_runpod()

    url = f"{REST_BASE}{path}"
    resp = _session.request(method, url, json=body, timeout=30)
    if resp.status_code >= 400:
        error_text = resp.text[:500]
        raise RuntimeError(
            f"RunPod API error (HTTP {resp.status_code} {method} {path}): {error_text}"
        )
    if resp.status_code == 204:
        return {}
    return resp.json()


def _items(payload, key: str) -> list:
    """Unwrap a v2 collection response, tolerating a bare list."""
    if isinstance(payload, dict):
        return list(payload.get(key) or [])
    return list(payload or [])


def pod_readiness(pod_id: str) -> dict:
    """``{status, uptime, host_id}`` for a pod, from one v2 GET.

    Replaces the GraphQL query these scripts used for
    ``runtime.uptimeInSeconds`` + ``machine.podHostId``, which REST v1
    lacked. v2 carries the uptime under ``runtime.uptime`` and nulls
    ``runtime`` entirely unless the pod is RUNNING.

    v2 exposes NO machine identifier, so ``host_id`` reports PLACEMENT
    instead: empty while ``PROVISIONING`` ("pod is being allocated", i.e. no
    host yet), non-empty once allocated. That is the contract the callers
    actually use — they test it for emptiness to detect an out-of-stock
    flavor, never for its value.
    """
    pod = rp("GET", f"/pods/{pod_id}")
    if not isinstance(pod, dict):
        return {"status": "", "uptime": 0, "host_id": ""}
    status = str(pod.get("status") or "")
    uptime = int((pod.get("runtime") or {}).get("uptime") or 0)
    host_id = "" if status.upper() == "PROVISIONING" else str(pod.get("startedAt") or "")
    return {"status": status, "uptime": uptime, "host_id": host_id}


def _find_by_name(items: list[dict], name: str) -> dict | None:
    """Find an item by exact name in a list of dicts. Mirrors _find() bash helper."""
    for item in items:
        if item.get("name") == name:
            return item
    return None


# =============================================================================
# Core: ensure_template
# =============================================================================


@aii_ability(
    name="aii_runpod__gen_template",
    description="Find or create a RunPod template by name.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=3,
    check_env="check_env.sh",
    # spend-exempt: a template is metadata, not a billable resource — RunPod
    # meters pods and network volumes, never a template — and this handler is a
    # find-or-create keyed on ``name``, so a re-invocation returns the existing
    # template instead of provisioning a second one. The blanket result-retry
    # is therefore both free and idempotent here, and worth keeping: the only
    # failure it can see is a transport error on the two REST calls, which is
    # exactly what a retry is for.
)
def core_runpod_ensure_template(
    name: str = "",
    image: str = "<author>/aii_pipeline:latest",
    disk_gb: int = 40,
    start_cmd: str = "",
    ports: str = "",
    env_json: str = "{}",
    volume_mount_path: str = "",
) -> dict:
    """Find or create a RunPod template by name."""
    if not name:
        return {"success": False, "error": "--name is required"}

    try:
        # Parse env_json if it's a string
        if isinstance(env_json, str):
            env_dict = json.loads(env_json) if env_json else {}
        else:
            env_dict = env_json or {}

        # Check existing
        all_templates = _items(rp("GET", "/templates"), "templates")
        existing = _find_by_name(all_templates, name)
        if existing:
            return {
                "success": True,
                "template_id": existing["id"],
                "template_name": name,
                "created": False,
                "message": f"Template already exists: {name} ({existing['id']})",
            }

        # Build request body (mirrors bash gen_template.sh logic)
        # REST v2 body. The renames mirror the pod create's
        # (``imageName``->``image``, ``containerDiskInGb``->``disk``), plus two
        # that are specific to templates:
        #
        #  * ``dockerStartCmd`` (array) -> ``args`` (a JSON-encoded STRING —
        #    the shape v2 returns on a live pod, e.g.
        #    ``{"cmd":["bash","/research-monorepo/scripts/runpod/run_server.sh"]}``).
        #  * ``volumeMountPath`` is GONE. v2's ``TemplateMounts`` accepts only
        #    a ``persistent`` mount and rejects ``network`` with 422, and a
        #    persistent mount is disallowed on CPU pods anyway. Our volume is a
        #    NETWORK volume attached at pod-create time, so the path belongs
        #    there (``mounts.network[].path``) and the template carries none —
        #    which is exactly what the live templates already show
        #    (``mounts: {}``), so nothing is lost by dropping it here.
        body: dict = {
            "name": name,
            "image": image,
            "disk": disk_gb,
        }
        if env_dict:
            body["env"] = env_dict
        if start_cmd:
            # Accept list (passed directly) or string (wrapped in bash -c)
            cmd = start_cmd if isinstance(start_cmd, list) else ["bash", "-c", start_cmd]
            body["args"] = json.dumps({"cmd": cmd})
        if ports:
            body["ports"] = [p.strip() for p in ports.split(",")]
        if volume_mount_path:
            # Kept in the signature because callers still pass it and it is
            # still the right value — it just belongs to the POD now, not the
            # template. Said out loud rather than dropped silently, so a
            # caller that sets it learns where it took effect.
            logger.info(
                f"volume_mount_path={volume_mount_path!r} is not part of a v2 template; "
                "a network volume carries its mount path at pod-create time "
                "(mounts.network[].path) instead."
            )

        # Create template
        result = rp("POST", "/templates", body)
        template_id = result.get("id", "")
        if not template_id:
            return {"success": False, "error": f"No template ID in response: {result}"}

        # Verify template exists (mirrors bash verification step)
        all_templates = _items(rp("GET", "/templates"), "templates")
        verify = _find_by_name(all_templates, name)
        if not verify:
            return {
                "success": False,
                "error": "Template created but not found on verification",
            }

        return {
            "success": True,
            "template_id": template_id,
            "template_name": name,
            "created": True,
            "message": f"Template ready: {name} ({template_id})",
        }

    except Exception as e:
        # Recoverable conditions (transient API errors) flow back via the
        # response; ability middleware logs them at INFO. Caller decides
        # escalation — don't double-log at ERROR here.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI (calls ability server endpoint)
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Find or create a RunPod template")
    parser.add_argument("--name", required=True, help="Template name")
    parser.add_argument("--image", default="<author>/aii_pipeline:latest", help="Docker image")
    parser.add_argument("--disk-gb", type=int, default=40, help="Container disk GB")
    parser.add_argument("--start-cmd", default="", help="Docker start command")
    parser.add_argument("--ports", default="", help="Port config (e.g. '8080/http')")
    parser.add_argument("--env-json", default="{}", help="Env vars as JSON object")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    payload = {
        "name": args.name,
        "image": args.image,
        "disk_gb": args.disk_gb,
        "start_cmd": args.start_cmd,
        "ports": args.ports,
        "env_json": args.env_json,
    }

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_TEMPLATE, payload, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        init_runpod()
        result = core_runpod_ensure_template(**payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        action = "Created" if result.get("created") else "Found"
        print(f"  [OK]   {action} template: {result['template_name']} ({result['template_id']})")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
