"""
test_image_gen.py -- Quick test to verify your Gemini API key works for image generation.

Usage:
    python test_image_gen.py

Requires GEMINI_API_KEY in your .env file (or as an environment variable).
"""

import os
import sys
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(override=True)

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    print("[FAIL] GEMINI_API_KEY not found!")
    print("       Set it in your .env file:  GEMINI_API_KEY=your-key-here")
    sys.exit(1)

print(f"[OK] API key found: {API_KEY[:8]}...{API_KEY[-4:]}")
print()

# --- Step 1: Test basic text generation ---
print("=" * 50)
print("Step 1: Testing basic text generation...")
print("=" * 50)

client = genai.Client(api_key=API_KEY)

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say 'Hello! Your API key is working!' in exactly those words.",
    )
    print(f"[OK] Text response: {response.text.strip()}")
except Exception as e:
    print(f"[FAIL] Text generation failed: {e}")
    sys.exit(1)

# --- Step 2: Test image generation ---
print()
print("=" * 50)
print("Step 2: Testing image generation...")
print("=" * 50)

IMAGE_MODEL = "gemini-2.5-flash-image"
image_found = False

try:
    print(f"   Model: {IMAGE_MODEL}")
    print(f"   Prompt: 'A beautiful golden necklace on a white background'")
    print(f"   Sending request...")

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents="Generate an image of a beautiful golden necklace on a clean white background.",
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    # Check if we got an image back
    text_found = False

    for part in response.parts:
        if part.inline_data is not None:
            image_found = True
            img_data = part.inline_data.data
            img_mime = part.inline_data.mime_type

            # Save the test image
            ext = "png" if "png" in img_mime else "jpg"
            output_path = os.path.join(os.path.dirname(__file__), f"test_output.{ext}")
            with open(output_path, "wb") as f:
                f.write(img_data)

            print(f"[OK] Image generated successfully!")
            print(f"     Format: {img_mime}")
            print(f"     Size: {len(img_data):,} bytes")
            print(f"     Saved to: {output_path}")

        elif part.text:
            text_found = True
            print(f"     Text response: {part.text.strip()[:200]}")

    if not image_found:
        print(f"[WARN] No image in response (text only). Model may not support image output.")
        print(f"       This could mean:")
        print(f"       - The model doesn't have image generation enabled for your key")
        print(f"       - Quota is exhausted for image generation")

except Exception as e:
    err = str(e)
    if "429" in err or "RESOURCE_EXHAUSTED" in err:
        print(f"[FAIL] QUOTA EXHAUSTED for {IMAGE_MODEL}")
        print(f"       Your key is valid but you've hit the rate/quota limit.")
    elif "403" in err or "PERMISSION_DENIED" in err:
        print(f"[FAIL] PERMISSION DENIED for {IMAGE_MODEL}")
        print(f"       Your key doesn't have access to this model.")
    elif "404" in err or "NOT_FOUND" in err:
        print(f"[FAIL] MODEL NOT FOUND: {IMAGE_MODEL}")
        print(f"       This model may not be available in your region.")
    else:
        print(f"[FAIL] Image generation failed: {e}")

print()
print("=" * 50)
print("Done! SUCCESS!" if image_found else "Done.")
print("=" * 50)
