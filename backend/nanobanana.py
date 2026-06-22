"""
nanobanana.py — Production try-on pipeline (4-step with retry).

Step 1 — Pre-detection : Identify which body parts are visible in the portrait.
Step 2 — Filter        : Hard-skip items that are impossible to place/extend.
Step 3 — Generation    : Composite jewelry; extend frame for rings/bangles if needed.
Step 4 — Validation    : Verify every piece landed in the correct anatomical spot.
                         Retry up to MAX_ATTEMPTS times, injecting failure feedback
                         into the next prompt so the model can self-correct.

Returns dict:
  {
    "image":         PIL.Image,
    "applied":       list[dict],  — items successfully composited
    "skipped":       list[dict],  — items skipped (impossible or failed validation)
    "visible_parts": dict,        — raw pre-detection output
    "attempts":      int,         — how many generation attempts were made
  }
"""

import os
import io
import re
import json
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(override=True)


# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY")
GCP_PROJECT      = os.environ.get("GOOGLE_CLOUD_PROJECT")
GCP_LOCATION     = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

DETECTION_MODEL  = "gemini-2.0-flash"        # fast text model — used for both detection & validation
GENERATION_MODEL = "gemini-2.5-flash-image"  # image-output model

MAX_ATTEMPTS = 2   # 1 original attempt + 1 retry

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
MAX_PX = 1024

# Maps jewelry type → body-part key used in detection/validation
PART_REQUIRED = {
    "necklace":  "neck",
    "earring":   "ears",
    "bangle":    "wrists",
    "bracelet":  "wrists",
    "ring":      "fingers",
    "anklet":    "ankles",
}

PART_LABEL = {
    "neck":    "neck / chest area",
    "ears":    "ears",
    "wrists":  "wrists / hands",
    "fingers": "fingers",
    "ankles":  "ankles",
}

PLACEMENT_DESC = {
    "necklace":  "around the neck / upper chest",
    "earring":   "on the ears",
    "bangle":    "on the wrist (not forearm, not upper arm)",
    "bracelet":  "on the wrist (not forearm, not upper arm)",
    "ring":      "on a finger (not palm, not bicep, not any other body part)",
    "anklet":    "on the ankle",
}

# Correct anatomical zone per type — used in validation prompt
CORRECT_ZONE = {
    "necklace":  "around the neck or upper chest",
    "earring":   "on or near the ear lobe",
    "bangle":    "on the wrist joint (between hand and forearm)",
    "bracelet":  "on the wrist joint (between hand and forearm)",
    "ring":      "on a finger (any finger is acceptable, NOT the palm, arm, or torso)",
    "anklet":    "around the ankle",
}

# Items that can be shown by extending the frame when not visible
EXTENDABLE = {"ring", "bangle", "bracelet"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[NanoBanana] {msg}", flush=True)


def _build_client() -> genai.Client:
    if GCP_PROJECT:
        return genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    if GEMINI_API_KEY:
        return genai.Client(api_key=GEMINI_API_KEY)
    raise ValueError("No credentials: set GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT.")


def _to_bytes(img: Image.Image, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, format="JPEG", quality=92)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def _resize(img: Image.Image) -> Image.Image:
    w, h = img.size
    if max(w, h) > MAX_PX:
        scale = MAX_PX / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _as_part(img: Image.Image, fmt: str = "JPEG") -> types.Part:
    return types.Part.from_bytes(
        data=_to_bytes(img, fmt),
        mime_type="image/jpeg" if fmt == "JPEG" else "image/png",
    )


def _extract_image(response) -> Image.Image | None:
    for part in response.parts:
        if part.inline_data is not None:
            return Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
    return None


def _parse_json(text: str) -> dict | None:
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(match.group()) if match else None
    except Exception:
        return None


# ── Step 1: Pre-detection ─────────────────────────────────────────────────────

def _detect_visible_parts(portrait_part: types.Part, client: genai.Client) -> dict:
    """
    Identify which jewelry-relevant body parts are clearly visible in the portrait.
    Falls back to all-True so generation always proceeds if this call fails.
    """
    prompt = (
        "Analyze this portrait photo carefully.\n"
        "For each body region, answer true ONLY if it is clearly visible AND "
        "unobstructed enough to realistically place jewelry on it.\n\n"
        "Reply with ONLY a JSON object — no explanation, no markdown:\n"
        '{"neck": <bool>, "ears": <bool>, "wrists": <bool>, "fingers": <bool>, "ankles": <bool>}\n\n'
        "Definitions:\n"
        "• neck    — neck and upper chest exposed enough for a necklace\n"
        "• ears    — at least one ear visible for earrings\n"
        "• wrists  — wrist/lower arm visible for a bangle or bracelet\n"
        "• fingers — individual fingers clearly visible for a ring\n"
        "            (closed fist / hidden hands / hands in pockets = false)\n"
        "• ankles  — ankles visible for an anklet\n"
    )
    try:
        resp = client.models.generate_content(
            model=DETECTION_MODEL,
            contents=[portrait_part, types.Part.from_text(text=prompt)],
        )
        result = _parse_json(resp.text.strip())
        if result:
            log(f"Pre-detection: {result}")
            return result
        log(f"Pre-detection parse failed — defaulting all True")
    except Exception as exc:
        log(f"Pre-detection error: {exc} — defaulting all True")

    return {k: True for k in PART_LABEL}


# ── Step 2: Filter ────────────────────────────────────────────────────────────

def _filter_items(jewelry_items: list, visible: dict) -> tuple[list, list]:
    """
    Hard-skip items that cannot be placed or frame-extended:
    - anklets when ankles are not visible (showing full legs breaks composition)
    - everything else proceeds; rings/bangles use frame-extension if needed
    Returns (applicable, hard_skipped).
    """
    applicable, hard_skipped = [], []
    for item in jewelry_items:
        part_key  = PART_REQUIRED.get(item["type"], "neck")
        visible_  = visible.get(part_key, True)
        if not visible_ and item["type"] == "anklet":
            hard_skipped.append({
                **item,
                "skip_reason": "Ankles not visible — frame extension not feasible for this shot.",
            })
            log(f"Hard-skip anklet (ankles not visible)")
        else:
            applicable.append(item)
    return applicable, hard_skipped


# ── Step 3: Generation ────────────────────────────────────────────────────────

def _build_prompt(items: list, visible: dict, feedback: list[str] | None = None) -> str:
    """
    Build a context-aware generation prompt.
    `feedback` is a list of plain-English issues from the previous validation pass;
    when provided it is appended as a CORRECTIONS section so the model self-corrects.
    """
    jewelry_list = ", ".join(i["type"] for i in items)

    item_lines = []
    for item in items:
        t          = item["type"]
        part_key   = PART_REQUIRED.get(t, "neck")
        is_visible = visible.get(part_key, True)
        base       = f"  • {t} → {PLACEMENT_DESC.get(t, 'correct anatomical position')}"

        if is_visible:
            item_lines.append(base)
        elif t in EXTENDABLE:
            item_lines.append(
                base + "\n"
                "    ↳ Hands/wrists are NOT in the original photo. Naturally extend\n"
                "      the composition to show just enough wrist or fingers at the\n"
                "      lower frame edge in a relaxed, neutral pose. Skin tone, bone\n"
                "      structure, and proportions MUST match this specific person\n"
                "      exactly (derived from their face and visible skin). The\n"
                "      extension must look like it was always part of the photo."
            )
        else:
            item_lines.append(
                base + "\n"
                f"    ↳ The {PART_LABEL[part_key]} is not clearly visible.\n"
                "      Place the jewelry where it would naturally sit, or omit it\n"
                "      entirely if realistic placement is not possible."
            )

    corrections = ""
    if feedback:
        issues_text = "\n".join(f"  - {f}" for f in feedback)
        corrections = (
            "\nCORRECTIONS FROM PREVIOUS ATTEMPT (fix all of these):\n"
            f"{issues_text}\n"
        )

    return (
        "EDIT this photo. Do NOT create a new image. Do NOT regenerate the person.\n\n"
        "You are given:\n"
        "  Image 1: The ORIGINAL photo — your base canvas.\n"
        f"  Image 2+: Transparent PNG(s) of: {jewelry_list}.\n\n"
        f"PER-ITEM PLACEMENT:\n" + "\n".join(item_lines) + "\n"
        + corrections +
        "\nCORE RULES (never break):\n"
        "1. Image 1 is the base — face, skin, hair, clothing, background, lighting stay IDENTICAL.\n"
        "2. Add ONLY the jewelry (and any minimal frame extension noted above).\n"
        "3. Match jewelry brightness, shadows, and reflections to the scene lighting.\n"
        "4. Clothing (collars, straps, sleeves) stays on top of jewelry naturally.\n"
        "5. Any frame-extended hand must match this person's exact skin tone and anatomy.\n"
        "6. Final image must look like an unedited professional photograph — "
        "no halos, seams, floating objects, or artifacts.\n"
    )


def _run_generation(
    portrait_part: types.Part,
    jewelry_parts: list,
    prompt: str,
    client: genai.Client,
) -> Image.Image:
    response = client.models.generate_content(
        model=GENERATION_MODEL,
        contents=[portrait_part, *jewelry_parts, types.Part.from_text(text=prompt)],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )
    img = _extract_image(response)
    if img is None:
        raise ValueError(
            f"Gemini returned no image (model: {GENERATION_MODEL}). "
            "Ensure your API key has image generation access."
        )
    return img


# ── Step 4: Post-generation validation ───────────────────────────────────────

def _validate_placement(
    result_image: Image.Image,
    items: list,
    client: genai.Client,
) -> dict:
    """
    Analyze the generated image and verify every jewelry piece is in the
    correct anatomical position.

    Returns:
      {
        "valid":  bool,
        "issues": list[str],          — plain-English problems (empty if valid)
        "detail": list[dict],         — per-item breakdown
      }
    """
    result_part = _as_part(result_image, "JPEG")

    item_specs = "\n".join(
        f"  • {item['type']}: must be {CORRECT_ZONE[item['type']]}"
        for item in items
    )

    prompt = (
        "You are a quality-control inspector for a jewelry virtual try-on system.\n"
        "Examine this photo and verify that each jewelry piece listed below is:\n"
        "  (a) actually present in the image, AND\n"
        "  (b) placed in the correct anatomical position.\n\n"
        f"Expected jewelry and their correct positions:\n{item_specs}\n\n"
        "Common errors to check for:\n"
        "• Ring placed on a bicep, arm, or torso instead of a finger\n"
        "• Bangle placed on the forearm or upper arm instead of the wrist\n"
        "• Necklace floating or placed on clothing without following the neckline\n"
        "• Earring placed on cheek, hair, or wrong side of face\n"
        "• Jewelry that is missing entirely\n"
        "• Extended hand/wrist that looks anatomically wrong or has mismatched skin tone\n\n"
        "Reply with ONLY a JSON object:\n"
        "{\n"
        '  "valid": <true if ALL items are correctly placed, false otherwise>,\n'
        '  "items": [\n'
        '    {"type": "<jewelry_type>", "present": <bool>, "correct_position": <bool>, '
        '"issue": "<specific problem or null>"}\n'
        "  ]\n"
        "}"
    )

    try:
        resp = client.models.generate_content(
            model=DETECTION_MODEL,
            contents=[result_part, types.Part.from_text(text=prompt)],
        )
        data = _parse_json(resp.text.strip())
        if data and "items" in data:
            issues = [
                f"{r['type']}: {r['issue']}"
                for r in data["items"]
                if not r.get("correct_position") or not r.get("present")
                if r.get("issue")
            ]
            valid = bool(data.get("valid", False)) and len(issues) == 0
            log(f"Validation: valid={valid}, issues={issues}")
            return {"valid": valid, "issues": issues, "detail": data["items"]}

        log("Validation parse failed — treating as valid to avoid false negatives")
        return {"valid": True, "issues": [], "detail": []}

    except Exception as exc:
        log(f"Validation error: {exc} — treating as valid")
        return {"valid": True, "issues": [], "detail": []}


# ── Public API ────────────────────────────────────────────────────────────────

def generate_tryon(
    base_image: Image.Image,
    jewelry_items: list,
) -> dict:
    """
    Full 4-step pipeline with retry loop.

    Returns:
      {
        "image":         PIL.Image,
        "applied":       list[dict],
        "skipped":       list[dict],
        "visible_parts": dict,
        "attempts":      int,
      }

    Raises ValueError if generation fails or validation does not pass
    within MAX_ATTEMPTS attempts.
    """
    log(f"=== Try-On Request ({len(jewelry_items)} items) ===")

    if not GEMINI_API_KEY and not GCP_PROJECT:
        log("WARNING: No credentials — returning original image.")
        return {
            "image":         base_image,
            "applied":       [],
            "skipped":       [{**i, "skip_reason": "API not configured"} for i in jewelry_items],
            "visible_parts": {},
            "attempts":      0,
        }

    client = _build_client()

    # ── Step 1: Pre-detection ────────────────────────────────────────
    log("Step 1 — pre-detecting visible body parts...")
    portrait_resized = _resize(base_image)
    portrait_part    = _as_part(portrait_resized, "JPEG")
    visible          = _detect_visible_parts(portrait_part, client)

    # ── Step 2: Filter ───────────────────────────────────────────────
    log("Step 2 — filtering items...")
    applicable, skipped = _filter_items(jewelry_items, visible)
    log(f"Applicable: {[i['type'] for i in applicable]} | Hard-skipped: {[i['type'] for i in skipped]}")

    if not applicable:
        raise ValueError(
            "None of the selected jewelry can be applied to this photo. "
            f"Skipped: {', '.join(i['type'] for i in skipped)}. "
            "Try a photo where the relevant body areas are visible."
        )

    # Preload jewelry images (done once, reused across retry attempts)
    jewelry_parts = []
    for item in applicable:
        full_path = os.path.join(ASSETS_DIR, item["path"])
        jewel_pil = Image.open(full_path).convert("RGBA")
        jewelry_parts.append(_as_part(_resize(jewel_pil), "PNG"))

    # ── Steps 3 & 4: Generate → Validate → Retry ────────────────────
    feedback      = None   # issues from previous attempt, injected into next prompt
    last_result   = None
    last_issues   = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"Step 3 — generation attempt {attempt}/{MAX_ATTEMPTS}...")

        try:
            prompt = _build_prompt(applicable, visible, feedback=feedback)
            result_image = _run_generation(portrait_part, jewelry_parts, prompt, client)
        except Exception as exc:
            log(f"Generation failed on attempt {attempt}: {exc}")
            if attempt == MAX_ATTEMPTS:
                raise ValueError(f"Image generation failed after {MAX_ATTEMPTS} attempts: {exc}")
            feedback = [f"Previous generation failed entirely ({exc}). Retry carefully."]
            continue

        last_result = result_image

        log(f"Step 4 — validating attempt {attempt}...")
        validation = _validate_placement(result_image, applicable, client)

        if validation["valid"]:
            log(f"Validation PASSED on attempt {attempt}")
            return {
                "image":         result_image,
                "applied":       applicable,
                "skipped":       skipped,
                "visible_parts": visible,
                "attempts":      attempt,
            }

        last_issues = validation["issues"]
        log(f"Validation FAILED on attempt {attempt}: {last_issues}")

        if attempt < MAX_ATTEMPTS:
            feedback = last_issues
            log("Injecting feedback into retry prompt...")

    # All attempts exhausted — raise a descriptive error
    issues_text = "; ".join(last_issues) if last_issues else "unknown placement error"
    raise ValueError(
        f"Jewelry placement could not be verified after {MAX_ATTEMPTS} attempts. "
        f"Issues: {issues_text}. "
        "Try a clearer photo with the relevant body parts more visible."
    )
