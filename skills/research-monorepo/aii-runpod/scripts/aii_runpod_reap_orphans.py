#!/usr/bin/env python
"""
RunPod Reap Orphans — sweep leftover pods, templates and volumes by prefix.

Until now the only janitor lived inside the ability PREFLIGHT, so strays were
collected only when someone happened to run the preflight — and only for the
two things it creates. That is how 8 orphaned ``aii_hc_tpl_*`` templates
accumulated against 0 orphaned pods: the pod side had a janitor and the
template side did not, and nothing swept either on demand.

This is that sweep, for all three resource types, runnable whenever.

DRY-RUN BY DEFAULT, and that is the whole safety story. Deleting a pod, a
template or a volume is irreversible, and a prefix is a blunt instrument — the
production templates are ``aii_server`` / ``aii_orchestrator`` /
``aii_worker_*``, so a careless ``--prefix aii_`` would match every one of
them. So it lists what it WOULD delete and stops; ``--delete`` is required to
act, and ``--prefix`` is required always (there is no "sweep everything").

Usage (via ability server):
    python aii_runpod_reap_orphans.py --prefix aii_hc_            # report only
    python aii_runpod_reap_orphans.py --prefix aii_hc_ --delete   # act
    python aii_runpod_reap_orphans.py --prefix aii_hc_ --keep abc123
    python aii_runpod_reap_orphans.py --prefix aii_hc_ --kinds templates

``--keep`` exists for the case the preflight janitor solves with its run id:
sweeping while your OWN resource matches the prefix would delete the thing you
are using. Pass its id (or name) and it is spared.

VOLUMES ARE OPT-IN, unlike the other two. They are the only resource here that
bills by the GB, they routinely hold the data a run needs (``aii-pipeline-data-eu``
is 1000 GB of live pgdata), and unmounted does NOT mean unwanted. So
``--kinds`` defaults to pods+templates and a volume is only ever considered
when asked for by name.
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


from aii_runpod_gen_template import DEFAULT_TIMEOUT, _items, rp
from loguru import logger

SERVER_NAME_REAP_ORPHANS = "aii_runpod__reap_orphans"

#: ``(kind, list path, collection key, delete path template)``. The delete
#: paths are v2's: a pod is TERMINATED via its action route, while templates
#: and volumes are plain DELETE calls. Kept as data so adding a fourth resource
#: a row rather than a branch.
_KINDS = {
    "pods": ("/pods", "pods", "/pods/{id}"),
    "templates": ("/templates", "templates", "/templates/{id}"),
    "volumes": ("/network-volumes", "networkVolumes", "/network-volumes/{id}"),
}

#: Swept unless ``--kinds`` says otherwise. Volumes are excluded on purpose —
#: see the module docstring.
_DEFAULT_KINDS = ("pods", "templates")


def _matches(item: dict, prefix: str, keep: set[str]) -> bool:
    """Does this resource match the prefix and survive the keep-list?"""
    name = str(item.get("name") or "")
    rid = str(item.get("id") or "")
    if not name.startswith(prefix):
        return False
    return not (rid in keep or name in keep)


@aii_ability(
    name=SERVER_NAME_REAP_ORPHANS,
    description=(
        "Sweep leftover RunPod pods/templates/volumes whose name starts with a "
        "prefix. Reports by default; deletes only when asked."
    ),
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=3,
    check_env="check_env.sh",
)
def core_runpod_reap_orphans(
    prefix: str = "",
    delete: bool = False,
    kinds: str = "",
    keep: str = "",
) -> dict:
    """Find (and optionally delete) resources whose name starts with ``prefix``.

    Args:
        prefix: Required. Name prefix to match. No default — sweeping
            everything is never what anyone means.
        delete: Actually delete. Default False (report only).
        kinds: Comma-separated subset of pods,templates,volumes.
        keep: Comma-separated ids or names to spare.

    Returns:
        ``{success, prefix, deleted (bool), found: {kind: [...]}, counts,
        errors}``. ``found`` always lists what matched, whether or not
        anything was deleted, so a dry run and a real run report the same
        shape.
    """
    if not prefix:
        return {"success": False, "error": "--prefix is required (refusing to sweep everything)"}

    wanted = [k.strip() for k in (kinds or "").split(",") if k.strip()] or list(_DEFAULT_KINDS)
    unknown = [k for k in wanted if k not in _KINDS]
    if unknown:
        return {"success": False, "error": f"unknown kind(s) {unknown}; expected {sorted(_KINDS)}"}

    keep_set = {k.strip() for k in (keep or "").split(",") if k.strip()}
    found: dict[str, list] = {}
    errors: list[str] = []

    for kind in wanted:
        list_path, collection_key, delete_path = _KINDS[kind]
        try:
            items = _items(rp("GET", list_path), collection_key)
        except Exception as exc:  # one unreachable collection must not kill the sweep
            errors.append(f"list {kind}: {type(exc).__name__}: {exc}")
            logger.warning(f"reap_orphans: listing {kind} failed: {exc}")
            continue

        matched = [i for i in items if _matches(i, prefix, keep_set)]
        found[kind] = [{"id": i.get("id", ""), "name": i.get("name", "")} for i in matched]
        if not delete:
            continue

        for item in matched:
            rid = str(item.get("id") or "")
            try:
                if kind == "pods":
                    # v2 dropped the dedicated stop/terminate routes for one
                    # action endpoint; terminate is what frees the billing.
                    rp("POST", f"/pods/{rid}/action", {"action": "terminate"})
                else:
                    rp("DELETE", delete_path.format(id=rid))
                logger.info(f"reap_orphans: deleted {kind[:-1]} {rid} ({item.get('name')})")
            except Exception as exc:
                errors.append(f"delete {kind} {rid}: {type(exc).__name__}: {exc}")
                logger.warning(f"reap_orphans: deleting {rid} failed: {exc}")

    return {
        "success": True,
        "prefix": prefix,
        "deleted": bool(delete),
        "found": found,
        "counts": {k: len(v) for k, v in found.items()},
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep leftover RunPod resources by name prefix (reports unless --delete)."
    )
    parser.add_argument("--prefix", required=True, help="Name prefix to match")
    parser.add_argument(
        "--delete", action="store_true", help="Actually delete (default: report only)"
    )
    parser.add_argument(
        "--kinds",
        default="",
        help="Comma-separated: pods,templates,volumes (default pods,templates)",
    )
    parser.add_argument("--keep", default="", help="Comma-separated ids/names to spare")
    parser.add_argument("--json", action="store_true", help="Print raw JSON")
    args = parser.parse_args()

    payload = {
        "prefix": args.prefix,
        "delete": args.delete,
        "kinds": args.kinds,
        "keep": args.keep,
    }

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_REAP_ORPHANS, payload, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_reap_orphans(**payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if not result.get("success"):
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)

    total = sum(result.get("counts", {}).values())
    verb = "Deleted" if result.get("deleted") else "Would delete"
    for kind, items in (result.get("found") or {}).items():
        for item in items:
            print(f"  [{verb.upper()}] {kind[:-1]:9s} {item['id']:14s} {item['name']}")
    if not total:
        print(f"  [OK]   nothing matches '{result['prefix']}'")
    else:
        print(f"  [OK]   {verb.lower()} {total} resource(s) matching '{result['prefix']}'")
        if not result.get("deleted"):
            print("         re-run with --delete to act")
    for err in result.get("errors") or []:
        print(f"  [WARN] {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
