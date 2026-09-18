"""Shared OpenRouter API endpoint declared once for this skill bundle.

The three sibling scripts (``aii_or_call_llms.py``, ``aii_or_get_llm_params.py``,
``aii_or_search_llms.py``) import from here instead of each repeating the
``https://openrouter.ai`` literal — see the ``endpoint-urls-once`` hook.

Leading underscore keeps this out of ability discovery's import-as-ability
scan (``discovery.py`` skips ``_*.py``), while remaining a normal sibling
import: the scripts' own directory is on ``sys.path`` whether they run as a
standalone script or get imported by the ability server, so a plain
``from _openrouter_api import ...`` resolves in both contexts.
"""

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
MODELS_URL = f"{OPENROUTER_API_BASE}/models"
RESPONSES_URL = f"{OPENROUTER_API_BASE}/responses"
