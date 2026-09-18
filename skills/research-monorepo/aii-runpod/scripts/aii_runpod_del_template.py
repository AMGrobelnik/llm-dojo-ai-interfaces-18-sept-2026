#!/usr/bin/env python
"""
RunPod Delete Template — delete a template by name or ID.

Usage (via ability server):
    python aii_runpod_del_template.py --name aii_test_lifecycle
    python aii_runpod_del_template.py --template-id abc123
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


# Shared helpers from the template script
from aii_runpod_gen_template import (
    DEFAULT_TIMEOUT,
    SERVER_NAME_DEL_TEMPLATE,
    _find_by_name,
    _items,
    rp,
)
from loguru import logger

# =============================================================================
# Core: del_template
# =============================================================================


@aii_ability(
    name="aii_runpod__del_template",
    description="Delete a RunPod template by name or ID.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_runpod",
    max_workers=3,
    check_env="check_env.sh",
)
def core_runpod_del_template(name: str = "", template_id: str = "") -> dict:
    """Delete a RunPod template by name or ID.

    Args:
        name: Template name to delete (optional).
        template_id: Template ID to delete directly (optional, takes precedence).
        At least one must be provided.

    Returns:
        Dict with success, template_deleted, template_name, template_id, message.
    """

    if not name and not template_id:
        return {"success": False, "error": "Provide name or template_id"}

    try:
        # Resolve template_id from name if needed
        resolved_id = template_id
        display_name = name or template_id
        if not resolved_id and name:
            all_templates = _items(rp("GET", "/templates"), "templates")
            template = _find_by_name(all_templates, name)
            if not template:
                return {
                    "success": True,
                    "template_deleted": False,
                    "message": f"No template found: {name}",
                }
            resolved_id = template["id"]

        # Delete template
        logger.info(f"Deleting template: {display_name} ({resolved_id})...")
        rp("DELETE", f"/templates/{resolved_id}")

        # Verify template is gone
        all_templates = _items(rp("GET", "/templates"), "templates")
        if name:
            check = _find_by_name(all_templates, name)
        else:
            check = any(t.get("id") == resolved_id for t in all_templates)

        if check:
            return {
                "success": False,
                "template_deleted": False,
                "error": f"Template still exists after deletion: {display_name}",
            }

        logger.info(f"Template deleted: {display_name} ({resolved_id})")
        return {
            "success": True,
            "template_deleted": True,
            "template_name": name,
            "template_id": resolved_id,
            "message": f"Template deleted: {display_name} ({resolved_id})",
        }

    except Exception as e:
        # Recoverable conditions (template-in-use 500, transient API errors)
        # flow back via the response; the ability middleware logs them at
        # INFO. Don't double-log at ERROR — caller decides escalation.
        return {"success": False, "error": str(e)}


# =============================================================================
# CLI (calls ability server endpoint)
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Delete a RunPod template")
    parser.add_argument("--name", default="", help="Template name to delete")
    parser.add_argument("--template-id", default="", help="Template ID to delete directly")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if not args.name and not args.template_id:
        parser.error("Provide --name or --template-id")

    payload = {}
    if args.name:
        payload["name"] = args.name
    if args.template_id:
        payload["template_id"] = args.template_id

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME_DEL_TEMPLATE, payload, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None
    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        result = core_runpod_del_template(**payload)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("success"):
        if result.get("template_deleted"):
            print(f"  [OK]   {result['message']}")
        else:
            print(f"  [INFO] {result['message']}")
    else:
        print(f"  [FAIL] {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
