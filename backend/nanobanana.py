"""
nanobanana.py — Gemini image-edit integration for jewelry try-on.

Sends the user's original photo + jewelry PNG(s) to Gemini and instructs
it to edit the photo in-place: preserve the person exactly, only add jewelry.
"""

import os
import io
import sys
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

def log(msg):
    """Print with flush so logs appear immediately in Flask debug mode."""
    print(f"[NanoBanana] {msg}", flush=True)

load_dotenv(override=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-3-pro-image-preview"
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
MAX_PX = 1024  # resize large images before sending to stay within token limits


def _to_bytes(img: Image.Image, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, format="JPEG", quality=92)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def _resize_if_large(img: Image.Image) -> Image.Image:
    w, h = img.size
    if max(w, h) > MAX_PX:
        scale = MAX_PX / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def generate_tryon(
    base_image: Image.Image,
    jewelry_items: list,   # list of {"path": str, "type": str}
) -> Image.Image:
    """
    Edit base_image to add all jewelry_items using Gemini image generation.
    Returns the edited PIL Image (RGB).

    Raises ValueError on API failure.
    Returns base_image if GEMINI_API_KEY is not set.
    """
    log(f"=== Try-On Request ===")
    log(f"Model: {MODEL}")
    log(f"Jewelry items: {[item['type'] for item in jewelry_items]}")

    if not GEMINI_API_KEY:
        log("WARNING: GEMINI_API_KEY not set — returning original image.")
        return base_image

    log("API key found, creating client...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    # ── Prepare base image ─────────────────────────────────────────
    base_resized = _resize_if_large(base_image)
    base_part = types.Part.from_bytes(
        data=_to_bytes(base_resized, "JPEG"),
        mime_type="image/jpeg",
    )

    # ── Prepare jewelry images ─────────────────────────────────────
    jewelry_parts = []
    jewelry_type_labels = []
    for item in jewelry_items:
        full_path = os.path.join(ASSETS_DIR, item["path"])
        jewel_pil = Image.open(full_path).convert("RGBA")
        jewel_pil = _resize_if_large(jewel_pil)
        jewelry_parts.append(
            types.Part.from_bytes(
                data=_to_bytes(jewel_pil, "PNG"),
                mime_type="image/png",
            )
        )
        jewelry_type_labels.append(item["type"])

    jewelry_list = ", ".join(jewelry_type_labels)

    # Placement map so the model knows where each piece belongs
    placement = {
        "necklace": "around the neck",
        "earring":  "on the ears",
        "bangle":   "on the wrist",
        "ring":     "on a finger",
        "bracelet": "on the wrist",
        "anklet":   "on the ankle",
    }
    placement_instructions = "; ".join(
        f"{t} → {placement.get(t, 'correct position')}"
        for t in jewelry_type_labels
    )

    # ── Prompt — anchored firmly to editing the original photo ──────
    prompt = (
        f"EDIT this photo. Do NOT create a new image. Do NOT regenerate the person.\n\n"
        f"I am giving you:\n"
        f"  Image 1: The ORIGINAL photo — this is what you must edit.\n"
        f"  Image 2+: Transparent PNG(s) of {jewelry_list} jewelry pieces.\n\n"
        f"YOUR ONLY TASK: Overlay the provided {jewelry_list} onto the ORIGINAL photo (Image 1).\n"
        f"Place each piece at its correct position: {placement_instructions}.\n\n"
        f"CRITICAL EDITING RULES:\n"
        f"1. START from the EXACT original photo (Image 1) as your base canvas.\n"
        f"2. The person's face, skin, hair, eyes, expression, body, pose, and clothing "
        f"must remain COMPLETELY UNCHANGED — identical to Image 1.\n"
        f"3. The background, lighting, colors, and composition must stay EXACTLY the same.\n"
        f"4. ONLY add the jewelry — blend it naturally with matching lighting, shadows, and reflections.\n"
        f"5. The result should look like the person was actually wearing the jewelry when the photo was taken.\n"
        f"6. CLOTHING INTERACTION: If a garment (collar, apron strap, sleeve, scarf) naturally "
        f"overlaps the jewelry area, let it overlap realistically — the clothing stays on top of "
        f"the jewelry exactly as it would in real life. Do NOT remove or alter clothing.\n"
        f"7. NECKLACE: It should sit on the skin of the neck/chest, going under any collar or strap "
        f"that crosses over it, emerging naturally at the sides.\n"
        f"8. Do NOT change anything else. No new person. No new background. No style changes.\n"
    )

    contents = [base_part, *jewelry_parts, types.Part.from_text(text=prompt)]

    log(f"Sending request to Gemini ({MODEL})...")
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        log("Response received from Gemini!")

        # Extract the first image part from the response
        for part in response.parts:
            if part.inline_data is not None:
                log("Image found in response - SUCCESS!")
                return Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")

        # No image in response — likely a permissions issue
        log("ERROR: No image in response")
        raise ValueError(
            f"Gemini returned no image. Your API key may not have access to "
            f"'{MODEL}'. Ensure your API key has access to image generation in Google AI Studio and retry."
        )

    except Exception as exc:
        log(f"ERROR: {exc}")
        raise ValueError(f"Gemini API Error: {exc}")
