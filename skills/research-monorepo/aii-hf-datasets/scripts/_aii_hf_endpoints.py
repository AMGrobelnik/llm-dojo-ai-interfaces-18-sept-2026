"""HuggingFace datasets-server URLs for this skill, declared once.

The three scripts here each called the same host on a different path and each
spelled the host out for itself. One home per provider means a move of the
host, or of one of these paths, is a single edit.

A sibling module rather than an import from ``aii_lib``: these scripts run
standalone (they guard their ``aii_lib`` import with ``try/except
ImportError``), so a shared declaration has to travel inside the bundle.
The leading underscore keeps the ability discovery pass from importing it as
a script — it registers nothing.
"""

#: Dataset-viewer API root. Serves precomputed metadata about a Hub dataset:
#: whether the parquet conversion landed, the parquet shard listing, and row
#: samples. Distinct from the Hub API on ``huggingface.co``.
BASE_URL = "https://datasets-server.huggingface.co"

#: Conversion probe — reports ``preview``/``viewer`` for a dataset id, which is
#: what says whether the rest of this API will answer for it at all.
IS_VALID_URL = f"{BASE_URL}/is-valid"

#: Parquet shard listing per config and split, used to download a dataset
#: without pulling it through the ``datasets`` library.
PARQUET_URL = f"{BASE_URL}/parquet"

#: Row sampler. Caps at 100 rows per call, which is why the preview script
#: pages rather than asking for everything at once.
ROWS_URL = f"{BASE_URL}/rows"
