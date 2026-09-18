#!/usr/bin/env python
"""
Image Generation & Editing (nano_banana) — OpenRouter images API.

Generate or edit images via OpenRouter's dedicated images endpoint
(/api/v1/images) on the two Gemini "Nano Banana" tiers: the flash tier
(google/gemini-3.1-flash-image-preview / Nano Banana 2) by default, or
``--model pro`` for google/gemini-3-pro-image-preview (Nano Banana Pro) — with
aspect-ratio and 1K/2K/4K resolution control. Routes through the ability server.

Two billing paths:
  * PAID (default) — OpenRouter, on the flash tier (Nano Banana 2, ~$0.067/image
    @1K); ``--model pro`` selects Nano Banana Pro (~$0.134/image @1K-2K). The
    exact charge is read back from OpenRouter's ``usage.cost`` per call.
  * FREE (``--free``, or ``AII_FREE_TOOLS=1``) — Cloudflare Workers AI
    (FLUX / SDXL) inside the account's 10,000-neuron daily free allocation,
    recorded at a hard $0. The Gemini tiers have no free image path, so this is
    the only genuinely $0 route. Generation only; editing needs the paid path.

Usage (CLI):
    python concept_fig_gen.py -p "Bar chart..." -o ./fig.jpg
    python concept_fig_gen.py -p "Bar chart..." --style neurips
    python concept_fig_gen.py --edit input.jpg -p "Make it blue" -o out.jpg

Usage (direct):
    from concept_fig_gen import core_concept_fig_gen
    result = core_concept_fig_gen(prompt="...", output_path="./fig.jpg")
    result = core_concept_fig_gen(prompt="Make it blue", input_image="in.jpg", output_path="out.jpg")
"""

import argparse
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# .env files are loaded as FALLBACKS only — an explicitly-set process env var
# (e.g. the OPENROUTER_API_KEY the RunPod deployment injects via AII_ENV_B64, or the
# pod's deploy-time-refreshed repo .env) MUST win. This previously used
# override=True on the skill-local .env, which let a stale key frozen into the
# Docker image at build time silently shadow the live deployment key. Repo .env
# is loaded first (it is refreshed every deploy), so neither file can clobber an
# already-resolved key.
load_dotenv(Path(__file__).resolve().parents[4] / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


# Paid path routes through OpenRouter's dedicated images API (/api/v1/images)
# rather than the native google-genai SDK — one key, one endpoint, both Gemini
# image tiers, with resolution/aspect params and the billed cost returned inline.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"

# =============================================================================
# FREE VARIANT — Cloudflare Workers AI text-to-image
# =============================================================================
# Gemini has NO free tier for image generation: ai.google.dev/gemini-api/docs/
# pricing lists "Not available" for every image model (gemini-2.5-flash-image,
# gemini-3-pro-image, gemini-3.1-flash-image/-lite, all Imagen 4 variants). So
# on the $0 backend the paid path is the single biggest line on the bill — a
# measured free-tier run came to $1.03, of which $0.8084 was six figures at
# $0.134 each, with $0 of LLM spend underneath it.
#
# Cloudflare Workers AI serves text-to-image on the SAME free 10,000-neuron/day
# account budget the free LLM pool already uses, with credentials already
# present. Probed live 2026-08-01: both models below answer
# "you have used up your daily free allocation of 10,000 neurons" when the
# budget is spent, which is what confirms they draw on the FREE allocation
# rather than a paid plan.
_FREE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
# Different architecture on purpose: if FLUX is unavailable for this account the
# fallback should not share its failure mode.
_FREE_FALLBACK_MODEL = "@cf/bytedance/stable-diffusion-xl-lightning"
_FREE_STEPS = 4  # schnell/lightning are few-step distilled models

# SECOND free provider. Both Cloudflare models draw on ONE 10,000-neuron daily
# account budget shared with the free LLM pool, so when a day's runs spend it
# there is nothing left to fail over to — image generation stopped while the LLM
# side kept working, because that side has 22 families across 8 providers and
# this had one. Hugging Face's free ``hf-inference`` provider serves this model
# on the HF_TOKEN the repo already holds (verified live: 200, image/jpeg, 53KB).
# Its other image models are gone — hf-inference answers 410 "deprecated" for
# FLUX and SDXL — so this is the one that works, not a preference.
_FREE_HF_MODEL = "stabilityai/stable-diffusion-3-medium-diffusers"
_FREE_HF_URL = "https://router.huggingface.co/hf-inference/models"
#: Free-variant pixel budget per ``image_size``. Cloudflare takes explicit
#: width/height rather than Gemini's named sizes, and caps at 2048.
_FREE_SIZE_PX = {"1K": 1024, "2K": 1536, "4K": 2048}


def free_credentials() -> tuple[str, str]:
    """``(api_token, account_id)`` for Workers AI, or ``("", "")``.

    Env first so a deployment can inject them, then the gitignored free-router
    key store that the LLM pool already reads — the free image path should not
    need its own secret plumbing.
    """
    token = os.environ.get("CLOUDFLARE_API_KEY", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if token and account:
        return token, account
    try:
        from aii_lib.free_router.keys import load_free_tier_keys

        stored = load_free_tier_keys()
    except Exception:  # standalone use without aii_lib on the path
        return token, account
    return token or stored.get("cloudflare", ""), account or stored.get("cloudflare_account_id", "")


def hf_token() -> str:
    """Token for the Hugging Face free inference provider, or ``""``."""
    return os.environ.get("HF_TOKEN", "") or os.environ.get("HUGGINGFACE_TOKEN", "")


def _free_enabled(explicit: bool | None) -> bool:
    """Whether THIS call should use the free variant.

    An explicit argument always wins (the agent passing ``--free`` or the
    ability's ``free=`` parameter). Otherwise the harness decides via
    ``AII_FREE_TOOLS``, which the pipeline sets for runs on the $0 backend —
    so a free run cannot silently spend on images just because a prompt forgot
    to ask.
    """
    if explicit is not None:
        return explicit
    return os.environ.get("AII_FREE_TOOLS", "").strip().lower() in ("1", "true", "yes", "on")


def _to_multiple_of_64(value: float) -> int:
    """Nearest multiple of 64 — the granularity diffusion backends accept."""
    return round(value / 64.0) * 64


def _call_free_api(
    prompt: str, aspect_ratio: str, image_size: str, budget_seconds: float | None = None
) -> tuple[dict | None, str, float]:
    """Generate on Workers AI. Returns ``(result, last_error)``.

    Mirrors ``_call_api``'s contract so the caller branches once and the save /
    return path is shared.
    """
    import requests

    # Credentials are NOT gated here: an HF-only setup (HF_TOKEN but no
    # Cloudflare account) is valid and must reach the Hugging Face lane below.
    # The per-lane `if token and account:` gate and the `if not lanes:` check
    # produce the correct combined error when nothing is configured.
    token, account = free_credentials()

    side = _FREE_SIZE_PX.get((image_size or "1K").upper(), 1024)
    width, height = side, side
    try:
        w_ratio, h_ratio = (float(x) for x in (aspect_ratio or "1:1").split(":"))
    except ValueError:
        w_ratio = h_ratio = 1.0  # unparseable ratio -> square, which is always valid
    # A zero or negative side is unparseable too, not a ratio: "1:0" once
    # divided out to a 1024x256 letterbox — a shape the caller never asked for,
    # from a string that means nothing. It joins the fallback above rather than
    # raising, because the raise used to land in this function's own `except`
    # two lines below, so its message could never reach anybody. Skipping the
    # division is also what keeps ZeroDivisionError off the table.
    if w_ratio > 0 and h_ratio > 0:
        # ROUND to the nearest multiple of 64, not down to it. Flooring is
        # one-directional, so every ratio it could not hit exactly came out
        # too wide: 21:9 wants 438 px and got 384 — a 2.67:1 canvas, 14.3%
        # off, laid out about a tenth shorter than the column it was sized
        # for. Rounding puts it at 448 (2.0% off).
        #
        # Which ratios come out EXACT depends on the size, and 2K is the odd
        # one out. A 16:9 needs side*9/16 to be a whole number of 64s, so the
        # side has to be a multiple of 1024 — 1K (1024) and 4K (2048) are,
        # and 2K (1536) is not: 1536*9/16 is 864, exactly 13.5 sixty-fours.
        # Half-to-even rounding sends that to 896, so 2K draws 16:9 at 1536x896
        # — 1.714 against 1.778, 3.6% off — and 9:16 at 3.7% off. 1:1, 4:3 and
        # 3:4 stay exact at every size because their factors divide 64 cleanly.
        # `_FREE_SIZE_PX` is what would have to change to fix that, and moving
        # 2K would move every figure already generated at it, so the numbers
        # are stated here and pinned by a test rather than quietly wrong.
        if w_ratio >= h_ratio:
            height = max(256, _to_multiple_of_64(side * h_ratio / w_ratio))
        else:
            width = max(256, _to_multiple_of_64(side * w_ratio / h_ratio))

    # Lanes in order. The two Cloudflare models share ONE account budget, so a
    # 429 skips the rest of Cloudflare — but must NOT end the walk, or a spent
    # daily allocation would take image generation down for the day when a
    # different free provider is sitting right there.
    deadline = time.monotonic() + float(budget_seconds or DEFAULT_TIMEOUT)
    lanes: list[tuple[str, str]] = []
    if token and account:
        lanes += [("cloudflare", _FREE_MODEL), ("cloudflare", _FREE_FALLBACK_MODEL)]
    hf = hf_token()
    if hf:
        lanes.append(("hf", _FREE_HF_MODEL))
    if not lanes:
        return (
            None,
            "no free image credentials (a Cloudflare account, or HF_TOKEN / "
            "HUGGINGFACE_TOKEN — either name works)",
            0.0,
        )

    last_error = ""
    cloudflare_exhausted = False
    # The deadline is one budget for the whole walk, not per lane. Breaking
    # only the attempt loop sent it into the NEXT lane, which re-ran the same
    # check and wrapped the message it had just written: three lanes produced
    # the one sentence three times, 281 characters nested inside itself, and
    # named the last lane rather than the one the time actually ran out on.
    out_of_time = False
    for provider, model in lanes:
        if provider == "cloudflare" and cloudflare_exhausted:
            continue
        for attempt in range(1, MAX_RETRIES + 1):
            remaining = deadline - time.monotonic()
            if remaining < _MIN_ATTEMPT_SECONDS:
                total = budget_seconds or DEFAULT_TIMEOUT
                last_error = (
                    f"the {total:.0f}s budget has {remaining:.0f}s left, under the "
                    f"{_MIN_ATTEMPT_SECONDS:.0f}s an attempt needs — stopped on "
                    f"{provider}. Last error: {last_error or 'none'}"
                )
                out_of_time = True
                break
            timeout = min(DEFAULT_TIMEOUT, remaining)
            try:
                if provider == "cloudflare":
                    resp = requests.post(
                        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "prompt": prompt,
                            "steps": _FREE_STEPS,
                            "width": width,
                            "height": height,
                        },
                        timeout=timeout,
                    )
                else:
                    # Same width/height the Cloudflare lane computes. Sending
                    # the prompt alone made this lane return a 1024x1024 image
                    # whatever was asked for, while the result dict went on
                    # reporting the REQUESTED ratio — a 21:9 request answered
                    # with a square, labelled "21:9". 21:9 is the ratio the
                    # pipeline prescribes for its architecture figure, and this
                    # lane is where every one of them lands once the daily
                    # Cloudflare allocation is spent.
                    resp = requests.post(
                        f"{_FREE_HF_URL}/{model}",
                        headers={"Authorization": f"Bearer {hf}"},
                        json={"inputs": prompt, "parameters": {"width": width, "height": height}},
                        timeout=timeout,
                    )
            except Exception as e:  # network/DNS/timeout
                last_error = f"{provider}: {type(e).__name__}: {e}"
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)
                continue

            if resp.status_code != 200:
                last_error = f"{provider} HTTP {resp.status_code}: {resp.text[:160]}"
                if provider == "cloudflare" and (
                    resp.status_code == 429 or "daily free allocation" in resp.text
                ):
                    # Account-wide and per-day: retrying, or trying Cloudflare's
                    # other model, cannot help. Move to the next PROVIDER.
                    cloudflare_exhausted = True
                    break
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)
                continue

            img_bytes = _extract_free_image(resp)
            if img_bytes:
                return (
                    {
                        "img_bytes": img_bytes,
                        "model": f"{provider}:{model}",
                        "attempts": attempt,
                        "text_content": "",
                    },
                    "",
                    0.0,
                )
            # Include the body, as the non-200 branch above already does. A
            # provider error wrapped in a 200 ("no such model", an exhausted
            # allocation) was reported only as "no image data", so a request
            # that could never succeed was indistinguishable from a transient
            # blank and was retried five more times.
            last_error = f"{provider}: 200 but no image: {resp.text[:160]}"
            # The allocation message arrives in a 200 as readily as in a 429 —
            # this branch is where a provider error wrapped in a 200 lands, and
            # the exhaustion notice is exactly that. Checking it only on the
            # non-200 path left the walk trying Cloudflare's SECOND model
            # against an account-wide budget with nothing in it; both lanes
            # share one allocation, which is why this flag exists at all.
            if provider == "cloudflare" and "daily free allocation" in resp.text:
                cloudflare_exhausted = True
                break
            # ...and back off before trying again, which the other two failure
            # paths above already do. Three attempts back-to-back against a
            # provider that just answered without an image is not a retry
            # policy, it is the same request three times.
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
        if out_of_time:
            break
    return None, last_error or "free image generation failed", 0.0


#: The first bytes of the formats a free lane can legitimately return. PNG and
#: JPEG are what the Stable Diffusion and FLUX lanes stream; WebP is included
#: because Cloudflare has served it before and it is a real image either way.
_IMAGE_SIGNATURES = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF8")


def _looks_like_an_image(data: bytes | None) -> bool:
    """True when ``data`` actually begins like an image file.

    The lanes that stream raw bytes are identified by their content-type, and
    a content-type is what the SERVER says, not what it sent. A 200 carrying
    an HTML error page, a plain-text rate-limit notice or an XML fault was
    handed back as image bytes and written to ``fig.jpg`` verbatim, reported
    as a success with a byte count. Measured: a 41-byte "502 Bad Gateway"
    page came back as a 41-byte image.

    Magic bytes rather than a library: Pillow is an optional import here (it
    is used only to read back the dimensions) and this has to work without it.
    """
    if not data:
        return False
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return any(data.startswith(signature) for signature in _IMAGE_SIGNATURES)


def _extract_free_image(resp) -> bytes | None:
    """Pull image bytes out of a Workers AI response.

    The two model families answer differently and both are supported rather
    than assumed: FLUX returns JSON with a base64 ``result.image``, while the
    Stable Diffusion lanes stream raw PNG bytes.

    Whatever the route, the bytes are checked to BE an image before they are
    returned — see ``_looks_like_an_image``. A lane that answers 200 with an
    error page is a lane that failed, and the walk should move to the next
    one rather than save the page as a figure.
    """
    content_type = (resp.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            body = resp.json()
        except ValueError:
            return None
        # The same guard the paid extractor carries: a 200 body that is valid
        # JSON but not an object (null, a list, a bare string from a proxy)
        # raised AttributeError straight out of the retry loop, taking down the
        # untried HuggingFace lane with it.
        if not isinstance(body, dict):
            return None
        payload = body.get("result") or {}
        encoded = payload.get("image") if isinstance(payload, dict) else None
        if not encoded:
            return None
        try:
            decoded = base64.b64decode(encoded)
        except Exception:
            return None
        return decoded if _looks_like_an_image(decoded) else None
    raw = resp.content or None
    return raw if _looks_like_an_image(raw) else None


SERVER_NAME = "aii_concept_fig_gen__generate"
DEFAULT_TIMEOUT = 180.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0

#: Below this much budget left there is no point starting another attempt —
#: an image generation that answers at all answers in tens of seconds, and a
#: request abandoned mid-flight still costs whatever the provider charged for
#: starting it.
_MIN_ATTEMPT_SECONDS = 15.0

log = logging.getLogger("aii-concept-fig-gen")

# OpenRouter image-model slugs for the two PAID tiers.
MODEL = "google/gemini-3-pro-image-preview"  # "pro" — Nano Banana Pro
FALLBACK_MODEL = "google/gemini-3.1-flash-image-preview"  # "flash" — Nano Banana 2

# Two user-selectable PAID tiers, both served through OpenRouter's images API
# (the free Cloudflare/HF path ignores this — free-vs-paid is a separate axis).
# "flash" (Nano Banana 2) is the default: the same Gemini image family at
# roughly half the price of "pro" (Nano Banana Pro). Slugs verified against
# OpenRouter's /api/v1/images/models catalog.
MODEL_TIERS = {"pro": MODEL, "flash": FALLBACK_MODEL}


def _resolve_model(model: str | None) -> str:
    """Map a friendly tier ('pro'/'flash') or a raw model id to a model id."""
    if not model:
        return FALLBACK_MODEL
    return MODEL_TIERS.get(model.lower(), model)


#: The palette every DATA figure in the same paper is drawn from — seaborn's
#: ``colorblind``, which aii-data-fig-gen applies to all 55 of its chart
#: types. Named here so a paper's concept diagrams belong to the same set
#: rather than to whatever the image model felt like, and so the hero figure
#: — always a concept figure — gets the colourblind safety the data figures
#: were given deliberately. Red-versus-green is called out separately: it is
#: the one pairing that carries meaning for most readers and none for the
#: ~8% of men with a red-green deficiency.
NEURIPS_PALETTE = "#0173B2 blue, #DE8F05 amber, #029E73 green, #CC78BC pink, #949494 grey"

NEURIPS_STYLE = (
    "Clean white background, no borders or decorative elements. "
    "Sans-serif font labels (Helvetica/Arial style), clearly readable at print size. "
    "Properly formatted axes with labeled tick marks. "
    "Minimal gridlines (light gray, dotted if needed). "
    "No 3D effects, no shadows, no gradients. "
    f"Use only these colours, so the figure matches the paper's data figures: {NEURIPS_PALETTE}. "
    "Never let red versus green be the only thing that distinguishes two elements — "
    "give them different shapes, labels or positions as well. "
    "Proportions suitable for a two-column NeurIPS paper layout."
)

VALID_ASPECT_RATIOS = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
]

VALID_IMAGE_SIZES = ["1K", "2K", "4K"]


# =============================================================================
# Cost accounting
# =============================================================================
# OpenRouter returns the exact billed charge for each image as ``usage.cost`` in
# the response, and that is the source of truth (see ``_extract_openrouter_image``).
# This table is only a FALLBACK estimate for the rare response with no usage
# block — figures track OpenRouter's per-image rates (which mirror Google's):
#   google/gemini-3-pro-image-preview:     1K/2K = $0.134, 4K = $0.24  (input img $0.0011)
#   google/gemini-3.1-flash-image-preview: 1K = $0.067, 2K = $0.101, 4K = $0.15 (input img $0.0006)
_IMAGE_OUTPUT_PRICE_USD = {
    MODEL: {"1K": 0.134, "2K": 0.134, "4K": 0.24},
    FALLBACK_MODEL: {"1K": 0.067, "2K": 0.101, "4K": 0.15},
}
# Per-input-image surcharge (edit mode sends one reference image).
_INPUT_IMAGE_PRICE_USD = {MODEL: 0.0011, FALLBACK_MODEL: 0.0006}


def gemini_image_cost_usd(*, model: str, image_size: str, num_input_images: int = 0) -> float:
    """USD for one Gemini image gen/edit at the given model + resolution.

    Cost depends on the model that actually produced the image (the skill
    falls back from Pro to Flash) and the output resolution; edit mode adds a
    small per-input-image surcharge.
    """
    table = _IMAGE_OUTPUT_PRICE_USD.get(model, _IMAGE_OUTPUT_PRICE_USD[MODEL])
    size = (image_size or "1K").upper()
    output = table.get(size, table.get("1K", 0.134))
    surcharge = _INPUT_IMAGE_PRICE_USD.get(model, 0.0011) * max(0, num_input_images)
    return round(output + surcharge, 6)


def record_external_cost(cost_usd, *, tool: str, **meta) -> None:
    """Append this call's $ to the per-task cost ledger (``AII_COST_LEDGER``).

    No-op when the env var is unset (standalone use) or cost is missing.
    Best-effort — a telemetry write must never break the tool's real result.
    The agent backend that spawned this subprocess reads the ledger back at
    summary time and folds the total into the run's external_tool_cost.
    """
    ledger = os.environ.get("AII_COST_LEDGER")
    if not ledger or cost_usd is None:
        return
    rec = {"ts": time.time(), "tool": tool, "cost_usd": float(cost_usd), **meta}
    try:
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


# =============================================================================
# OpenRouter images client
# =============================================================================
# Stateless HTTP — no persistent client object. The paid path POSTs to
# OpenRouter's dedicated images endpoint with OPENROUTER_API_KEY.


def init_concept_fig_gen():
    """Validate the paid-path credential (ability-server ``worker_init`` hook)."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env or environment")
    log.info("OpenRouter images path ready")


def _extract_openrouter_image(resp) -> tuple[bytes | None, float | None]:
    """Return ``(image_bytes, cost_usd)`` from an OpenRouter /images response.

    The image comes back base64 in ``data[0].b64_json`` (or a ``data:`` URL);
    the exact billed charge is in ``usage.cost``.
    """
    try:
        payload = resp.json()
    except ValueError:
        return None, None
    # A 200 body that is valid JSON but not an object (null, a list, a bare
    # string from a proxy) would crash the .get() calls below; treat it as "no
    # image" so the retry loop handles it like any other empty response.
    if not isinstance(payload, dict):
        return None, None
    cost = (payload.get("usage") or {}).get("cost")
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        b64 = item.get("b64_json")
        if not b64:
            url = item.get("url") or (item.get("image_url") or {}).get("url", "")
            if isinstance(url, str) and url.startswith("data:"):
                b64 = url.split(",", 1)[1]
        if b64:
            try:
                return base64.b64decode(b64), cost
            except Exception:
                return None, cost
    return None, cost


def _call_api(
    prompt, aspect_ratio, image_size, model=MODEL, input_image_url=None, budget_seconds=None
):
    """Generate/edit via OpenRouter's images API, retries + Pro->Flash fallback.

    ``image_size`` (1K/2K/4K) maps to the ``resolution`` tier; an edit-mode
    source image rides along as a base64 data URL in ``image``. Returns
    ``(result_dict, last_error, spent_usd)`` — result_dict is None on failure,
    and ``spent_usd`` is what the provider reported charging WHETHER OR NOT an
    image came back, so a failure the caller pays for is still recorded.

    ``budget_seconds`` is the whole call's deadline, and the loop will not
    START an attempt it cannot finish inside it. Without that, the advertised
    budget was unreachable: three attempts per model across two models, each
    allowed ``DEFAULT_TIMEOUT`` (180 s), needs up to 1092 s, while the caller
    gives the ability server 180 s in total — so on slow responses the worker
    was cut off during attempt 2 of 6, the fallback model was never reached,
    and the caller saw a bare transport timeout rather than "the budget ran
    out". Fast failures — a connection error, a 5xx — still get every attempt,
    which is the case retries exist for.
    """
    import requests

    spent = 0.0
    deadline = time.monotonic() + float(budget_seconds or DEFAULT_TIMEOUT)

    base_body: dict = {"prompt": prompt}
    if aspect_ratio and aspect_ratio in VALID_ASPECT_RATIOS:
        base_body["aspect_ratio"] = aspect_ratio
    if image_size and image_size.upper() in VALID_IMAGE_SIZES:
        base_body["resolution"] = image_size.upper()
    if input_image_url:
        # OpenRouter's images API takes a reference/edit image via
        # ``input_references`` — an array of {type, image_url} objects, the same
        # shape chat-completions uses. A bare ``image`` field is silently
        # ignored, so the model regenerates from the prompt alone instead of
        # editing the supplied image (verified: a "change only the background"
        # edit returned a different figure entirely).
        base_body["input_references"] = [
            {"type": "image_url", "image_url": {"url": input_image_url}}
        ]

    last_error = ""
    # One budget for both models, so running out ends the walk. Breaking only
    # the attempt loop moved on to the fallback, which re-ran this check and
    # wrapped the message it had just written -- and logged "MODEL failed,
    # falling back" for a model that was never called at all.
    out_of_time = False
    for current_model in [model, FALLBACK_MODEL] if model != FALLBACK_MODEL else [FALLBACK_MODEL]:
        body = {**base_body, "model": current_model}
        for attempt in range(1, MAX_RETRIES + 1):
            remaining = deadline - time.monotonic()
            if remaining < _MIN_ATTEMPT_SECONDS:
                total = budget_seconds or DEFAULT_TIMEOUT
                last_error = (
                    f"the {total:.0f}s budget has {remaining:.0f}s left, under the "
                    f"{_MIN_ATTEMPT_SECONDS:.0f}s an attempt needs"
                    + (
                        f" — {current_model} was never tried. Raise --timeout."
                        if attempt == 1 and not last_error
                        else f", after {attempt - 1} attempt(s) on {current_model}."
                        f" Last error: {last_error or 'none'}"
                    )
                )
                out_of_time = True
                break
            timeout = min(DEFAULT_TIMEOUT, remaining)
            try:
                resp = requests.post(
                    OPENROUTER_IMAGES_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=timeout,
                )
            except Exception as e:  # network / DNS / timeout
                last_error = f"[{current_model}] {type(e).__name__}: {e}"
                log.warning(f"{current_model} attempt {attempt}/{MAX_RETRIES}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF**attempt)
                continue

            if resp.status_code != 200:
                last_error = f"[{current_model}] HTTP {resp.status_code}: {resp.text[:160]}"
                log.warning(f"{current_model} attempt {attempt}/{MAX_RETRIES}: {last_error}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF**attempt)
                continue

            img_bytes, cost = _extract_openrouter_image(resp)
            if img_bytes:
                return (
                    {
                        "img_bytes": img_bytes,
                        "text_content": "",
                        "model": current_model,
                        "attempts": attempt,
                        "cost_usd": (spent + (cost or 0.0)) or None,
                    },
                    None,
                    spent + (cost or 0.0),
                )

            # The provider answered 200 and priced it. Keep the charge — it is
            # owed whether or not an image came back, and dropping it
            # understated a run's external cost by the whole amount — and stop
            # asking: an imageless 200 is a refusal (quota, moderation, a bad
            # model id), not a blank that a retry fills in. Six identical
            # priced calls came to $0.60 for nothing.
            spent += cost or 0.0
            # And say what it carried, the way the HTTP-error branch does.
            # "response carried no image data" made a quota message, a
            # moderation block and a malformed payload the same sentence.
            last_error = f"[{current_model}] 200 but no image: {resp.text[:160]}"
            log.warning(f"{current_model} attempt {attempt}/{MAX_RETRIES}: {last_error}")
            if cost:
                break
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF**attempt)

        if out_of_time:
            break
        if current_model == MODEL:
            log.warning(f"{MODEL} failed, falling back to {FALLBACK_MODEL}")

    return None, last_error or "All attempts exhausted (both models)", spent


@aii_ability(
    name="aii_concept_fig_gen__generate",
    description="Generate or edit images via OpenRouter images API with aspect ratio and resolution control.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_concept_fig_gen",
    check_env="check_env.sh",
    # Image generation BILLS on every call, so it must never be blanket-
    # retried: a transient-looking failure can arrive after the provider has
    # already charged, and the cost ledger books the call once no matter how
    # many times the handler ran. With the default retries=3 a single timeout
    # buys up to four images and records one. Callers own recovery.
    retries=0,
)
def core_concept_fig_gen(
    prompt: str = "",
    output_path: str = "./generated_image.jpg",
    input_image: str | None = None,
    aspect_ratio: str = "16:9",
    image_size: str = "1K",
    negative_prompt: str | None = None,
    style: str | None = None,
    system_instruction: str | None = None,
    free: bool | None = None,
    model: str = "flash",
    budget_seconds: float | None = None,
) -> dict:
    """Generate or edit an image via Gemini API.

    Args:
        prompt: Image description or edit instruction.
        output_path: Where to save the image.
        input_image: Path to source image for editing (omit for generation).
        aspect_ratio: Canvas shape (e.g., '16:9', '4:3', '1:1').
        image_size: Resolution: '1K', '2K', '4K' (default: '1K').
        negative_prompt: Things to exclude from the image.
        style: Preset style ('neurips' appends academic style).
        system_instruction: System-level style guidance.
        free: Use the $0 Cloudflare Workers AI path instead of paid Gemini.
            ``None`` (default) defers to ``AII_FREE_TOOLS``, which the
            pipeline sets for runs on the free backend.
        model: Paid-path Gemini tier — 'flash' (Nano Banana 2, ~half cost,
            the default) or 'pro' (Nano Banana Pro). Ignored on the free path.

    Returns:
        Dict with success, output_path, model, dimensions, and metadata.
    """
    # ``.strip()``: a whitespace-only prompt is not empty to Python and went
    # all the way to the provider, which answered HTTP 400 — a paid round trip
    # to be told what this line already knew.
    if not prompt or not prompt.strip():
        return {"success": False, "error": "Prompt is required"}

    use_free = _free_enabled(free)
    # Workers AI takes a single prompt string with no image part, so editing
    # cannot be served for free. Refused HERE, before the source file is even
    # opened: the combination is invalid regardless of whether that file exists,
    # and reporting "input image not found" for it would send the caller after
    # the wrong problem.
    if use_free and input_image:
        return {
            "success": False,
            "error": "the free image variant cannot edit an existing image; use --paid to edit",
        }
    # Checked AFTER the free branch is resolved: the free path authenticates to
    # Cloudflare and must not be blocked by a missing Gemini key.
    if not use_free and not OPENROUTER_API_KEY:
        return {"success": False, "error": "OPENROUTER_API_KEY not set"}

    # Build full prompt. The images API takes a single prompt string (no separate
    # system/content parts), so any system instruction and the neurips style
    # prelude are folded into the prompt text.
    full_prompt = prompt
    if style == "neurips":
        full_prompt = f"{prompt}\n\nStyle: {NEURIPS_STYLE}"
    if negative_prompt:
        full_prompt = f"{full_prompt}\n\nAvoid: {negative_prompt}"
    if system_instruction:
        full_prompt = f"{system_instruction}\n\n{full_prompt}"
    elif style == "neurips":
        full_prompt = (
            "You are a scientific figure generator. Produce clean, "
            f"publication-ready charts and diagrams.\n\n{full_prompt}"
        )

    # Edit mode: the source image rides along as a base64 data URL in the
    # request's ``input_references`` field (built in ``_call_api``).
    input_image_url = None
    if input_image:
        import mimetypes

        img_path = Path(input_image)
        # ``is_file``, not ``exists``: a DIRECTORY exists, so a folder path
        # passed to --edit got past this and raised IsADirectoryError out of
        # read_bytes() below — a traceback where every other bad input here
        # gets a sentence naming the file.
        if not img_path.is_file():
            what = "is a directory" if img_path.is_dir() else "not found"
            return {"success": False, "error": f"Input image {what}: {input_image}"}
        mime, _ = mimetypes.guess_type(img_path.name)
        encoded = base64.b64encode(img_path.read_bytes()).decode()
        input_image_url = f"data:{mime or 'image/jpeg'};base64,{encoded}"

    # Generate
    if use_free:
        result, err, spent = _call_free_api(
            full_prompt, aspect_ratio, image_size, budget_seconds=budget_seconds
        )
    else:
        result, err, spent = _call_api(
            full_prompt,
            aspect_ratio,
            image_size,
            model=_resolve_model(model),
            input_image_url=input_image_url,
            budget_seconds=budget_seconds,
        )
    if result is None:
        # ``cost_usd`` rides on the FAILURE too. A 200 that reports a charge
        # and carries no image is money already owed; leaving it off the
        # failure dict meant main() skipped record_external_cost and the run's
        # external spend was understated by the whole amount.
        failed = {"success": False, "error": f"Generation failed: {err}"}
        if spent:
            # Carry WHAT WAS BOUGHT, not only how much. ``main`` fills the
            # ledger row from these keys, and the ones it could not find came
            # out as empty strings — so the same charge was attributable when
            # it produced an image and anonymous when it did not, which is the
            # row somebody reads to find out what the money went on. Both
            # values are already in scope; the success dict reports the same.
            #
            # No ``billing`` here on purpose: ``_call_free_api`` reports a hard
            # 0.0 on every failure, so ``if spent`` cannot be reached from the
            # free path, and ``main``'s "paid" default is already the only
            # right answer. A ``"free" if use_free else "paid"`` would read as
            # if it could go either way and never would.
            failed["cost_usd"] = spent
            failed["model"] = _resolve_model(model)
            failed["image_size"] = image_size
            failed["mode"] = "edit" if input_image else "generate"
        return failed

    # Save — Gemini always returns JPEG, so force .jpg suffix regardless of
    # what the caller requested (avoids JPEG-bytes-with-.png-extension files).
    img_bytes = result["img_bytes"]
    out_path = Path(output_path).with_suffix(".jpg")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(img_bytes)

    dimensions = ""
    try:
        from PIL import Image

        with Image.open(out_path) as img:
            dimensions = f"{img.width}x{img.height}"
    except Exception:
        pass

    mode = "edit" if input_image else "generate"
    return {
        "success": True,
        "output_path": str(out_path.resolve()),
        "mode": mode,
        "model": result["model"],
        "dimensions": dimensions,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "prompt_length": len(full_prompt),
        "image_bytes": len(img_bytes),
        "image_data": base64.b64encode(img_bytes).decode(),
        "attempts": result["attempts"],
        "text_response": result["text_content"][:200] if result["text_content"] else "",
        # ``out_path``, not ``output_path`` — the suffix was just rewritten to
        # .jpg, so echoing what the caller ASKED for names a file that is not
        # on disk. ``main`` rebuilds this line from its own save and so never
        # saw it; a direct ``core_concept_fig_gen`` caller (the second usage in
        # this module's docstring) reads it and goes looking for ``fig.png``.
        "output": f"Image saved: {out_path} ({len(img_bytes)} bytes, {dimensions})",
        # Self-reported external API cost — priced by the model that actually
        # produced the image (Pro vs Flash fallback) and the output resolution.
        # Single source of truth for this call's $; recorded into the run cost
        # ledger by ``main`` (see ``record_external_cost``).
        # The free path is served inside Cloudflare's daily free allocation, so
        # it reports a HARD ZERO rather than a rate-card valuation. Pricing it
        # from a table would put notional dollars on a run that was never
        # billed — the same mistake the free LLM pool had to unwind.
        "billing": "free" if use_free else "paid",
        # OpenRouter returns the exact billed charge inline (``usage.cost``);
        # fall back to the rate-card estimate only if a response omits it.
        "cost_usd": 0.0
        if use_free
        else (
            result["cost_usd"]
            if result.get("cost_usd") is not None
            else gemini_image_cost_usd(
                model=result["model"],
                image_size=image_size,
                num_input_images=1 if input_image else 0,
            )
        ),
    }


# =============================================================================
# CLI
# =============================================================================


def _server_may_have_started_work(exc: BaseException) -> bool:
    """Whether the ability server might already be generating this image.

    Only an HTTP-layer timeout qualifies. ``ability_client`` raises
    ``RuntimeError`` from an ``httpx.TimeoutException`` when the request
    reached the server and the answer did not come back — the one case where
    running the generation again buys a second image. A CONNECT timeout is
    excluded: nothing was ever delivered. Read off the exception chain rather
    than matched against message text, so a reworded error cannot silently
    turn a paid double-call back on.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx ships with the client
        return False
    cause = exc.__cause__
    return isinstance(cause, httpx.TimeoutException) and not isinstance(cause, httpx.ConnectTimeout)


def main():
    parser = argparse.ArgumentParser(
        description="Generate or edit images via OpenRouter images API (ability server)",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        required=True,
        help="Image description or edit instruction",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./generated_image.jpg",
        help="Output file path (default: ./generated_image.jpg). Always saved as .jpg regardless of suffix.",
    )
    parser.add_argument(
        "--edit",
        default=None,
        metavar="INPUT_IMAGE",
        help="Edit an existing image (provide path to source image)",
    )
    parser.add_argument(
        "--aspect-ratio",
        default="16:9",
        choices=VALID_ASPECT_RATIOS,
        help="Canvas aspect ratio (default: 16:9)",
    )
    parser.add_argument(
        "--image-size",
        default="1K",
        choices=VALID_IMAGE_SIZES,
        help="Image resolution (default: 1K)",
    )
    parser.add_argument(
        "--negative-prompt",
        default=None,
        help="Things to exclude from the image",
    )
    parser.add_argument(
        "--style",
        default=None,
        choices=["neurips"],
        help="Preset style (neurips = academic paper style)",
    )
    parser.add_argument(
        "--system",
        default=None,
        dest="system_instruction",
        help="System instruction for style guidance",
    )
    parser.add_argument(
        "--model",
        default="flash",
        choices=["pro", "flash"],
        help=(
            "Paid tier (via OpenRouter): 'flash' = Nano Banana 2 "
            "(gemini-3.1-flash-image-preview, ~half cost, default); 'pro' = "
            "Nano Banana Pro (gemini-3-pro-image-preview). Ignored with --free."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=(
            f"Ability-server call timeout in seconds (default: {DEFAULT_TIMEOUT:.0f}). "
            f"The image request itself uses a fixed {DEFAULT_TIMEOUT:.0f}s timeout."
        ),
    )
    free_group = parser.add_mutually_exclusive_group()
    free_group.add_argument(
        "--free",
        dest="free",
        action="store_true",
        default=None,
        help="Generate on Cloudflare Workers AI at $0 instead of paid Gemini",
    )
    free_group.add_argument(
        "--paid",
        dest="free",
        action="store_false",
        help="Force the paid Gemini path even on a free-tier run",
    )

    args = parser.parse_args()

    payload = {
        "prompt": args.prompt,
        "output_path": args.output,
        "aspect_ratio": args.aspect_ratio,
        "image_size": args.image_size,
        "negative_prompt": args.negative_prompt,
        "style": args.style,
        "system_instruction": args.system_instruction,
        # Resolved HERE, in the only process that can see the answer.
        # AII_FREE_TOOLS is set on the AGENT's environment by whichever backend
        # is running the task (repl_driver spawns the CLI with it; the
        # openhands backend puts it in its own os.environ), and this CLI is a
        # subprocess of that agent. The ability server is a SEPARATE,
        # long-lived process reached over HTTP, so a null on the wire was
        # answered by whatever environment that process happened to start with
        # — and the default invocation on a $0 run, the one SKILL.md tells
        # agents to use, bought paid images. --free/--paid always transmitted
        # fine because they are booleans; only the default was lost.
        "free": _free_enabled(args.free),
        "model": args.model,
        # The same deadline the in-process path passes. Without it on the wire
        # the worker planned its retries against the 180 s default whatever
        # ``--timeout`` said, so the two paths disagreed in both directions:
        # a raised timeout bought no extra attempts, and a LOWERED one left
        # the worker still buying them after the caller had stopped waiting.
        "budget_seconds": args.timeout,
    }
    if args.edit:
        payload["input_image"] = args.edit

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME, payload, timeout=args.timeout)
    except ImportError:
        # No ability server in this environment at all — the standalone case
        # the fallback below exists for.
        log.info("no ability server available; generating in-process")
    except Exception as exc:
        if _server_may_have_started_work(exc):
            # ability_client refuses to retry an HTTP timeout precisely so the
            # caller does not re-issue a generation that may still be running.
            # This caller re-issued it anyway, silently, and the provider
            # charged for both — the failure did not appear in stdout, stderr
            # or the ledger.
            log.exception("ability server may still be generating; not re-issuing")
            print(json.dumps({"success": False, "error": f"ability server: {exc}"}, indent=2))
            sys.exit(1)
        # The server never took the work: not running, refusing the
        # connection, or answering 401/403/404. In-process is the documented
        # standalone path, so take it — but SAY so. A bare ``except
        # Exception: result = None`` hid a credential-scope problem behind a
        # figure that looked like it came from the server.
        log.warning(f"ability server unusable ({type(exc).__name__}: {exc}); generating in-process")

    if result is None:
        # Standalone fallback: run the core logic locally (no ability server
        # needed). No init gate here — core_concept_fig_gen validates the
        # paid-path key itself and correctly allows a FREE run without it, which
        # init_concept_fig_gen (a paid-only worker hook) would wrongly block.
        # ``--timeout`` is the caller's whole deadline, so it is also the
        # retry budget: without it the loop would happily plan six attempts of
        # 180 s each inside a 180 s wait. It rides in ``payload`` now, so both
        # this path and the ability server get the same number.
        result = core_concept_fig_gen(**payload)

    # Record this generation's external API $ into the agent's per-task cost
    # ledger (no-op when run standalone). ``cost_usd`` comes back from
    # ``core_concept_fig_gen`` whether it ran locally or via the ability
    # server. Written on a FAILURE that still cost money as well as on
    # success: a 200 that reports a charge and carries no image is money
    # already owed, and gating this on success alone left the run's external
    # spend understated by the whole amount. The ``or`` keeps the hard $0 a
    # successful free run records — "served inside a free allocation", which a
    # falsy cost alone could not say.
    if result.get("success") or result.get("cost_usd"):
        record_external_cost(
            result.get("cost_usd"),
            tool=SERVER_NAME,
            model=result.get("model", ""),
            image_size=result.get("image_size", ""),
            mode=result.get("mode", ""),
            # Marks WHY the figure was $0 — served inside a free allocation,
            # not "we failed to price it". A bare 0.00 cannot say that.
            billing=result.get("billing", "paid"),
        )

    if result.get("success"):
        # Save image locally from base64 data returned by ability server.
        # Gemini always returns JPEG, so force .jpg suffix regardless of
        # what the caller requested (avoids JPEG-bytes-with-.png-extension files).
        image_data = result.get("image_data")
        if image_data:
            out = Path(args.output).with_suffix(".jpg")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(image_data))
            result["output_path"] = str(out.resolve())
            result["output"] = (
                f"Image saved: {out} ({result.get('image_bytes', '?')} bytes, {result.get('dimensions', '')})"
            )

        # Print metadata (exclude large base64 blob from output)
        display = {k: v for k, v in result.items() if k != "image_data"}
        print(display.get("output", ""))
        print(json.dumps(display, indent=2))
    else:
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
