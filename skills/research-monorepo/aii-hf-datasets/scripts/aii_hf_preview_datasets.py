#!/usr/bin/env python
"""
HuggingFace Dataset Preview Tool

Preview a dataset's metadata and sample rows.

Usage:
    python aii_hf_preview_datasets.py openai/gsm8k
    python aii_hf_preview_datasets.py glue --config mrpc --split validation
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# .env is loaded as a FALLBACK only — an already-set process env var (e.g. the
# token the RunPod deployment injects, or the pod's deploy-time-refreshed repo
# .env) MUST win. load_dotenv never overrides an existing var, so the repo-root
# .env (the single source of truth for API keys) wins over the skill-local one.
load_dotenv(Path(__file__).resolve().parents[4] / ".env")  # repo-root — wins
load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # skill-local fallback

# Sibling module. These scripts are invoked by absolute path
# (`$PY $SKILL_DIR/scripts/<name>.py`), so Python puts this directory on
# sys.path itself and no path manipulation is needed. The name carries the
# skill's own prefix because every skill's scripts share ONE bare-name
# namespace in the ability server: a plain `_endpoints` in two bundles
# resolves to whichever loaded first, and the second skill's imports fail.
from _aii_hf_endpoints import ROWS_URL

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


SERVER_NAME = "aii_hf_datasets__preview_datasets"
CONNECTION_TIMEOUT = 180  # seconds

# =============================================================================
# Core Logic (used by server handler)
# =============================================================================

HF_TOKEN = os.environ.get("HF_TOKEN", "")

# Global HfApi instance for session reuse
_hf_api = None


def init_preview_dataset():
    """Initialize HuggingFace environment for preview."""
    global _hf_api
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["HF_DATASETS_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["HF_HUB_VERBOSITY"] = "error"
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(CONNECTION_TIMEOUT)

    from huggingface_hub.utils import disable_progress_bars

    disable_progress_bars()

    import logging

    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub.repocard").setLevel(logging.ERROR)
    logging.getLogger("datasets").setLevel(logging.ERROR)

    # Pre-import to cache
    from datasets import load_dataset
    from huggingface_hub import HfApi

    # Create global HfApi instance for session reuse
    _hf_api = HfApi()

    # Warmup API connection
    try:
        _hf_api.dataset_info("dair-ai/emotion")
        # Pinned to a commit so the warmup fetches the same bytes every time.
        ds = load_dataset(
            "dair-ai/emotion",
            split="train",
            streaming=True,
            revision="cab853a1dbdf4c42c2b3ef2173804746df8825fe",
        )
        next(iter(ds))
    except Exception:
        pass


@aii_ability(
    name="aii_hf_datasets__preview_datasets",
    description="Preview a HuggingFace dataset's metadata and sample rows.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_preview_dataset",
    check_env="check_env.sh",
)
def core_preview_dataset(
    dataset_id: str = "",
    config: str | None = None,
    split: str = "train",
    num_rows: int = 5,
    revision: str | None = None,
) -> dict:
    """
    Preview a HuggingFace dataset - metadata and sample rows.

    Args:
        dataset_id: HuggingFace dataset ID (e.g., "openai/gsm8k")
        config: Dataset configuration/subset name (optional)
        split: Split to preview (default: train)
        num_rows: Number of sample rows (default: 5, max: 20)
        revision: Git revision of the dataset repo to read (a commit SHA pins
            the bytes; default is the Hub's current main)

    Returns:
        Dict with metadata and sample rows
    """
    from concurrent.futures import ThreadPoolExecutor

    from datasets import get_dataset_config_names, load_dataset
    from huggingface_hub import DatasetCard
    from huggingface_hub.utils import RepositoryNotFoundError

    if not dataset_id or not dataset_id.strip():
        return {"success": False, "error": "dataset_id is required"}

    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(CONNECTION_TIMEOUT)

    def truncate(text, max_len=500):
        if not text:
            return ""
        text = str(text)
        return (
            text[:max_len] + f"... (+{len(text) - max_len} chars)" if len(text) > max_len else text
        )

    def truncate_value(value, max_array=3, max_str=200):
        # Handle None and primitives
        if value is None:
            return None
        if isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value[:max_str] + "..." if len(value) > max_str else value
        if isinstance(value, bytes):
            return f"<bytes: {len(value)} bytes>"
        if isinstance(value, list):
            return [truncate_value(v) for v in value[:max_array]]
        if isinstance(value, tuple):
            return [truncate_value(v) for v in value[:max_array]]
        if isinstance(value, dict):
            return {str(k): truncate_value(v) for k, v in list(value.items())[:max_array]}
        # Handle numpy/PIL/other objects
        type_name = type(value).__name__
        if hasattr(value, "shape"):  # numpy array
            return f"<{type_name}: shape={value.shape}>"
        if hasattr(value, "size") and hasattr(value, "mode"):  # PIL Image
            return f"<{type_name}: size={value.size}, mode={value.mode}>"
        # Fallback: convert to string
        try:
            s = str(value)
            return s[:max_str] + "..." if len(s) > max_str else s
        except Exception:
            return f"<{type_name}>"

    result = {
        "success": True,
        "dataset_id": dataset_id,
        "config": config,
        "split": split,
    }
    global _hf_api
    api = _hf_api  # Reuse global session

    # Fetch metadata in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_info = executor.submit(api.dataset_info, dataset_id)
        future_card = executor.submit(DatasetCard.load, dataset_id)
        future_configs = executor.submit(get_dataset_config_names, dataset_id)

        try:
            info = future_info.result()
            result["downloads"] = getattr(info, "downloads", 0)
            result["likes"] = getattr(info, "likes", 0)
            if getattr(info, "created_at", None):
                result["created_at"] = str(info.created_at)[:10]
            if getattr(info, "last_modified", None):
                result["last_modified"] = str(info.last_modified)[:10]
            if getattr(info, "tags", None):
                result["tags"] = info.tags
        except RepositoryNotFoundError:
            return {"success": False, "error": f"Dataset '{dataset_id}' not found"}
        except Exception:
            pass

        try:
            card = future_card.result()
            if card and card.text:
                result["description"] = truncate(card.text, 500)
        except Exception:
            pass

        try:
            config_names = future_configs.result()
            if config_names:
                result["configs"] = config_names
        except Exception:
            config_names = []

    # Determine config
    actual_config = config or (config_names[0] if config_names else None)
    result["config"] = actual_config

    # Load sample rows. Try HF Datasets Server /rows endpoint first — it
    # returns pre-converted JSON rows directly, no script execution. Falls
    # back to streaming ``load_dataset`` only when the server can't serve
    # this dataset (uncovered, gated, or HF-side conversion failure).
    rows, columns = _try_datasets_server_rows(
        dataset_id, actual_config, split, num_rows, truncate_value
    )
    if rows is not None:
        result["columns"] = columns
        result["sample_rows"] = rows
        result["num_sample_rows"] = len(rows)
        result["sample_source"] = "datasets-server-rows"
        return result

    try:
        from datasets import load_dataset

        load_kwargs = {"path": dataset_id, "split": split, "streaming": True}
        if actual_config:
            load_kwargs["name"] = actual_config

        ds = load_dataset(**load_kwargs, revision=revision)
        rows, columns = [], []
        for i, row in enumerate(ds):
            if i >= num_rows:
                break
            rows.append(truncate_value(dict(row)))
            if i == 0:
                columns = list(row.keys())

        result["columns"] = columns
        result["sample_rows"] = rows
        result["num_sample_rows"] = len(rows)
        result["sample_source"] = "load_dataset"
    except Exception as e:
        result["sample_error"] = str(e)
        result["success"] = False

    return result


def _try_datasets_server_rows(
    dataset_id: str,
    config: str | None,
    split: str,
    num_rows: int,
    truncate_value,
) -> tuple[list, list] | tuple[None, None]:
    """Fetch sample rows from HF Datasets Server's /rows endpoint.

    Returns:
      (rows, columns) on success — rows are already truncated by ``truncate_value``.
      (None, None) if the endpoint can't serve this dataset (uncovered,
      gated without auth, or HF-side conversion failure). Caller should
      fall back to ``load_dataset``.

    Bypasses script-execution entirely: ``datasets>=3`` refuses ``<repo>.py``
    loaders, but the same data is reachable via this REST endpoint as long
    as HF has auto-converted the dataset (the typical case).
    """
    import httpx

    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"
    params = {
        "dataset": dataset_id,
        "split": split,
        "offset": 0,
        "length": min(num_rows, 100),  # /rows caps at 100 per call
    }
    if config:
        params["config"] = config
    try:
        resp = httpx.get(
            ROWS_URL,
            params=params,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
        return None, None
    if resp.status_code != 200:
        return None, None
    try:
        body = resp.json()
    except Exception:
        return None, None
    raw_rows = body.get("rows") or []
    if not raw_rows:
        return None, None
    # /rows returns [{"row_idx": int, "row": {...}, "truncated_cells": [...]}]
    cleaned = [truncate_value(item.get("row", {})) for item in raw_rows]
    columns = list(raw_rows[0].get("row", {}).keys()) if raw_rows else []
    return cleaned, columns


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Preview a HuggingFace dataset")
    parser.add_argument("dataset_id", help="HuggingFace dataset ID")
    parser.add_argument("--config", default="", help="Dataset configuration")
    parser.add_argument("--split", default="train", help="Split to preview")
    parser.add_argument("--num-rows", type=int, default=5, help="Number of sample rows")
    parser.add_argument(
        "--revision", default=None, help="Dataset repo revision (commit SHA pins it)"
    )
    args = parser.parse_args()

    params = {
        "dataset_id": args.dataset_id,
        "config": args.config,
        "split": args.split,
        "num_rows": args.num_rows,
        "revision": args.revision,
    }

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME, params)
    except Exception:
        result = None

    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        init_preview_dataset()
        result = core_preview_dataset(**params)

    if result.get("success"):
        print(f"\n{'=' * 60}")
        print(f"Dataset: {result['dataset_id']}")
        print(f"{'=' * 60}")
        if result.get("downloads") is not None:
            print(f"Downloads: {result['downloads']:,} | Likes: {result.get('likes', 0)}")
        if result.get("description"):
            print(f"\nDescription: {result['description']}")
        if result.get("configs"):
            print(f"\nConfigs: {', '.join(result['configs'][:10])}")
        print(f"\n--- Sample Rows ({result['split']}) ---")
        if result.get("columns"):
            print(f"Columns: {', '.join(result['columns'][:15])}")
        for i, row in enumerate(result.get("sample_rows", []), 1):
            print(f"\nRow {i}:")
            for k, v in row.items():
                v_str = str(v)[:200] + "..." if len(str(v)) > 200 else str(v)
                print(f"  {k}: {v_str}")
    else:
        print(f"Error: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
