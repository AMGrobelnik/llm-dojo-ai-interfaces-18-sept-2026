#!/usr/bin/env python
"""
RunPod Get Templates — list all templates, optionally filtered by name prefix.

Usage (via ability server):
    python aii_runpod_get_templates.py
    python aii_runpod_get_templates.py --prefix aii_worker_

The prefix in that example is UNDERSCORED, and the distinction is not
cosmetic. TWO parallel template families live on the account:

    aii_worker_{gpu,cpu_heavy,cpu_light}   <author>/aii_pipeline:<sha>
    aii-worker-{gpu,cpu-heavy,cpu-light}   <author>/aii-pipeline:latest

Only the underscored set is live — those names come from ``execute_env``'s
``templates:`` block, and the deploy repins them onto the deploy SHA. Nothing
in this repo references the hyphenated set; it appears to predate the current
naming, along with its separate ``aii-pipeline`` image repo.

So the hyphenated prefix this example used to show does not fail loudly — it
returns THREE templates, which is the trap. An empty result would read as "no
such templates"; three plausible-looking hits read as success while pointing
at an unreferenced, ``:latest``-pinned set. Measured: ``--prefix
aii-worker-`` -> 3, ``--prefix aii_worker_`` -> 3, disjoint.

The stale set is left alone rather than reaped. Unlike the ``aii_hc_tpl_*``
healthcheck leftovers — a code-defined test prefix with an obvious owner —
these are not clearly disposable and may be a deliberate route back to the
``:latest`` images.

**How stale, measured 2026-08-25 — this is the part that bears on that
"deliberate route" reading.** Both hyphenated repos' ``:latest`` are from
**2026-05-13**, i.e. **103.2 days** old, against 0.3 days for the underscored
pair:

    <author>/aii-pipeline:latest    2026-05-13    103.2 days
    <author>/aii-server:latest      2026-05-13    103.2 days
    <author>/aii_pipeline:latest    2026-08-24      0.3 days
    <author>/aii_server:latest      2026-08-24      0.3 days

An escape hatch onto a 3.4-month-old image is not much of an escape hatch, so
"deliberate route back" is weaker than it looks; nothing has moved those tags
in a quarter of a year. The templates cost nothing (RunPod bills pods and
volumes, not templates), so this is not urgent — but the reason for KEEPING
them should be re-examined rather than inherited, and that is an owner call,
which is why they are still here.

Note the failure mode this produces is the quiet one: the lookup SUCCEEDS.
A pod created from ``aii-worker-gpu`` pulls a real, resolvable image and runs
103-day-old code. A name that resolves to stale infrastructure is worse than
one that 404s, because nothing anywhere reports an error.
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
    SERVER_NAME_GET_TEMPLATES,
    _items,
    rp,
)

# =============================================================================
# Core: get_templates
# =============================================================================


@aii_ability(
    name="aii_runpod__get_templates",
    description="List RunPod templates, optionally filtered by name prefix.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=5,
    check_env="check_env.sh",
)
def core_runpod_get_templates(prefix: str = "") -> dict:
    """List RunPod templates, optionally filtered by name prefix."""

    try:
        # v2 wraps collections ({"templates": [...]}) where v1 answered a bare list.
        # Iterating the dict yields KEYS, so the next .get() raises
        # AttributeError on a str — a silent, total failure of this ability.
        all_templates = _items(rp("GET", "/templates"), "templates")

        if prefix:
            all_templates = [t for t in all_templates if (t.get("name") or "").startswith(prefix)]

        templates = []
        for t in all_templates:
            templates.append(
                {
                    "id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "image": t.get("image", t.get("imageName", "")),
                    # v2 renamed both of these, and neither reported it: a
                    # missing key reads as None, which looks like "this
                    # template sets no disk / no start command" rather than
                    # like a bug. Confirmed against a live template, whose
                    # keys are exactly {allowedCudaVersions, args, category,
                    # disk, env, id, image, mounts, name, ports, public,
                    # registry, serverless, startJupyter, startSsh} — no
                    # containerDiskInGb, no dockerStartCmd, and no volumeInGb
                    # either (a v2 template carries no volume; the mount comes
                    # from the POD's mounts.network).
                    "container_disk_gb": t.get("disk"),
                    "ports": t.get("ports"),
                    # v2 serves this as a JSON STRING (e.g. '{}' or
                    # '{"cmd":[...]}'), not the bare command v1 gave.
                    "docker_start_cmd": t.get("args"),
                    "env": t.get("env"),
                }
            )

        return {"success": True, "templates": templates, "count": len(templates)}

    except Exception as e:
        # Error flows back via response; ability middleware logs the call at
        # INFO. Caller decides escalation — no double-log at ERROR here.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="List RunPod templates")
    parser.add_argument("--prefix", default="", help="Filter by name prefix")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    payload = {}
    if args.prefix:
        payload["prefix"] = args.prefix

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_GET_TEMPLATES, payload, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_get_templates(**payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        templates = result.get("templates", [])
        if not templates:
            print("  [INFO] No templates found")
        else:
            for t in templates:
                print(f"  {t['id']:<14} {t['name']:<30} {t.get('image', '')}")
            print(f"  [OK]   {len(templates)} template(s)")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
