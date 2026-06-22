"""
nanobanana.py — Two-step Gemini pipeline for jewelry virtual try-on.

Step 1 — Detection:  Analyze the portrait to find which body parts are
                     visible (neck, ears, wrists, fingers, ankles).
Step 2 — Generation: Apply only the jewelry whose placement area is visible.

Returns a dict:
  {
    "image":         PIL.Image  — edited result,
    "applied":       list[dict] — items actually composited,
    "skipped":       list[dict] — items skipped with reason,
    "visible_parts": dict       — detection result for the UI,
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

GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY")
GCP_PROJECT     = os.environ.get("GOOGLE_CLOUD_PROJECT")
GCP_LOCATION    = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

DETECTION_MODEL  = "gemini-2.0-flash"          # fast, cheap — text output only
GENERATION_MODEL = "gemini-2.5-flash-image"    # image output

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
MAX_PX = 1024

# Maps jewelry type → body part key from detection
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
    "bangle":    "on the wrist",
    "bracelet":  "on the wrist",
    "ring":      "on a finger",
    "anklet":    "on the ankle",
}

# Items we can "extend" the frame for when not visible.
# The model will show the body part naturally at the frame edge.
# Anklets are excluded — showing ankles requires too much body extension.
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


def _image_part(img: Image.Image, fmt: str = "JPEG") -> types.Part:
    return types.Part.from_bytes(
        data=_to_bytes(img, fmt),
        mime_type=f"image/{'jpeg' if fmt == 'JPEG' else 'png'}",
    )


# ── Step 1: Body-part detection ───────────────────────────────────────────────

def _detect_visible_parts(portrait_part: types.Part, client: genai.Client) -> dict:
    """
    Ask Gemini to check which jewelry-relevant body regions are clearly visible.
    Returns e.g. {"neck": True, "ears": False, "wrists": True, "fingers": False, "ankles": False}
    Falls back to all-True if the model call fails, so generation always attempts.
    """
    prompt = (
        "Analyze this portrait photo carefully.\n"
        "For each body region below, answer true ONLY if it is clearly visible "
        "AND unobstructed enough to realistically place jewelry on it.\n\n"
        "Reply with ONLY a JSON object — no explanation, no markdown:\n"
        '{"neck": <bool>, "ears": <bool>, "wrists": <bool>, "fingers": <bool>, "ankles": <bool>}\n\n'
        "Definitions:\n"
        "• neck   — neck and upper chest clearly exposed for a necklace\n"
        "• ears   — at least one ear clearly visible for earrings\n"
        "• wrists — wrist/lower arm clearly visible for a bangle or bracelet\n"
        "• fingers — individual fingers clearly visible and identifiable for a ring "
        "  (a closed fist, pockets, or hands behind back = false)\n"
        "• ankles — ankles clearly visible for an anklet\n"
    )
    try:
        response = client.models.generate_content(
            model=DETECTION_MODEL,
            contents=[portrait_part, types.Part.from_text(text=prompt)],
        )
        raw = response.text.strip()
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
            log(f"Detection result: {result}")
            return result
        log(f"Detection parse failed (raw: {raw!r}), defaulting all True")
    except Exception as exc:
        log(f"Detection error: {exc} — defaulting all True")

    return {k: True for k in PART_LABEL}


# ── Step 2: Image generation ──────────────────────────────────────────────────

def _build_prompt(items: list[dict], visible: dict) -> str:
    """
    Build a context-aware prompt that tells the model exactly how to handle
    each jewelry item — including how to extend the frame for rings/bangles
    when hands are not in the original photo.
    """
    jewelry_list = ", ".join(i["type"] for i in items)

    # Build per-item placement instructions
    item_lines = []
    for item in items:
        t = item["type"]
        part_key = PART_REQUIRED.get(t, "neck")
        part_visible = visible.get(part_key, True)
        base = f"  • {t} → {PLACEMENT_DESC.get(t, 'correct position')}"

        if part_visible:
            item_lines.append(base)
        elif t in EXTENDABLE:
            # Hand/wrist not in frame — instruct the model to extend naturally
            item_lines.append(
                base + "\n"
                "    ↳ The hand/wrist is NOT currently in this photo. "
                "    Naturally extend the composition to show just enough of the "
                "    wrist or fingers at the lower edge of the frame — in a relaxed, "
                "    neutral pose. The skin tone, bone structure, and hand appearance "
                "    MUST match this specific person exactly (derive from their face, "
                "    neck, and any visible skin in Image 1). "
                "    The extension must look like the hand was always there — "
                "    no unnatural angles, floating limbs, or mismatched anatomy."
            )
        else:
            # Earrings when ears not visible, necklace when neck hidden, etc.
            item_lines.append(
                base + "\n"
                f"    ↳ The {PART_LABEL[part_key]} is not clearly visible. "
                "    Place the jewelry as best you can where it would naturally sit, "
                "    or omit it if placement would look unrealistic."
            )

    placement_block = "\n".join(item_lines)

    return (
        "EDIT this photo. Do NOT create a new image. Do NOT regenerate the person.\n\n"
        "You are given:\n"
        "  Image 1: The ORIGINAL photo — use this as your base canvas.\n"
        f"  Image 2+: Transparent PNG(s) of: {jewelry_list}.\n\n"
        f"TASK: Composite the provided jewelry onto Image 1.\n\n"
        f"PER-ITEM PLACEMENT INSTRUCTIONS:\n{placement_block}\n\n"
        "CORE RULES (never break):\n"
        "1. Image 1 is your base canvas — every pixel of the existing scene "
        "   (person's face, clothing, background, lighting) stays IDENTICAL.\n"
        "2. Only add jewelry and any minimal hand-extension described above.\n"
        "3. Match jewelry brightness, shadows, and reflections to the scene lighting in Image 1.\n"
        "4. If clothing (collar, strap, sleeve) crosses a jewelry area, "
        "   keep the clothing on top exactly as in real life.\n"
        "5. Any extended hand/wrist must be anatomically correct for this person — "
        "   same skin tone, proportions, and natural resting position.\n"
        "6. Final image must look like an unedited professional photograph — "
        "   no halos, seams, floating objects, or compositing artifacts.\n"
    )


def _extract_image(response) -> Image.Image | None:
    for part in response.parts:
        if part.inline_data is not None:
            return Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def generate_tryon(
    base_image: Image.Image,
    jewelry_items: list,   # list of {"path": str, "type": str, ...}
) -> dict:
    """
    Two-step pipeline: detect visible parts, then generate the try-on.

    Returns:
      {
        "image":         PIL.Image,
        "applied":       list[dict],  — items composited
        "skipped":       list[dict],  — items skipped (body part not visible)
        "visible_parts": dict,        — raw detection output
      }

    Raises ValueError on unrecoverable API errors.
    """
    log(f"=== Try-On Request ({len(jewelry_items)} items) ===")

    if not GEMINI_API_KEY and not GCP_PROJECT:
        log("WARNING: No credentials — returning original image.")
        return {
            "image": base_image,
            "applied": [],
            "skipped": [{**i, "reason": "API not configured"} for i in jewelry_items],
            "visible_parts": {},
        }

    client = _build_client()
    portrait_resized = _resize(base_image)
    portrait_part    = _image_part(portrait_resized, "JPEG")

    # ── Step 1: detect ───────────────────────────────────────────────
    log("Step 1: detecting visible body parts...")
    visible = _detect_visible_parts(portrait_part, client)

    # ── Step 2: filter ───────────────────────────────────────────────
    # Hard-skip: anklets when ankles not visible (extending the frame to show
    # full legs/ankles requires too drastic a composition change).
    # Everything else is passed to generation — rings/bangles get explicit
    # "extend the frame" instructions when hands are not in the photo.
    applicable, skipped = [], []
    for item in jewelry_items:
        part_key = PART_REQUIRED.get(item["type"], "neck")
        part_visible = visible.get(part_key, True)

        if not part_visible and item["type"] == "anklet":
            reason = "ankles not visible — frame extension not feasible"
            log(f"Hard-skip {item['type']}: {reason}")
            skipped.append({**item, "skip_reason": reason})
        else:
            applicable.append(item)

    log(f"Applicable: {[i['type'] for i in applicable]} | Hard-skipped: {[i['type'] for i in skipped]}")

    if not applicable:
        raise ValueError(
            "None of the selected jewelry can be applied to this photo. "
            f"Skipped: {', '.join(i['type'] for i in skipped)}. "
            "Try a different photo where the relevant body areas are visible."
        )

    # ── Step 3: load jewelry images ──────────────────────────────────
    jewelry_parts      = []
    jewelry_type_labels = []
    for item in applicable:
        full_path = os.path.join(ASSETS_DIR, item["path"])
        jewel_pil = Image.open(full_path).convert("RGBA")
        jewel_pil = _resize(jewel_pil)
        jewelry_parts.append(_image_part(jewel_pil, "PNG"))
        jewelry_type_labels.append(item["type"])

    # ── Step 4: generate ─────────────────────────────────────────────
    prompt   = _build_prompt(applicable, visible)
    contents = [portrait_part, *jewelry_parts, types.Part.from_text(text=prompt)]

    log(f"Step 2: generating with {GENERATION_MODEL}...")
    try:
        response = client.models.generate_content(
            model=GENERATION_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        result_image = _extract_image(response)
        if result_image is None:
            raise ValueError(
                f"Gemini returned no image for model '{GENERATION_MODEL}'. "
                "Ensure your API key has image generation access."
            )
        log("Generation SUCCESS")
        return {
            "image":         result_image,
            "applied":       applicable,
            "skipped":       skipped,
            "visible_parts": visible,
        }
    except Exception as exc:
        log(f"Generation ERROR: {exc}")
        raise ValueError(f"Gemini API error: {exc}")
