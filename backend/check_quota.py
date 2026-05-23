"""Quick script to check which Gemini models still have free-tier quota."""

import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

# All models from your account
IMAGE_MODELS = [
    # Image-capable models
    "gemini-2.5-flash-image",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image-preview",
    "nano-banana-pro-preview",
    # General models (may support image output)
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    # Image generation models
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
]

print("=" * 60)
print("Checking free-tier quota for image-capable models...")
print("=" * 60)

for model in IMAGE_MODELS:
    try:
        response = client.models.generate_content(
            model=model,
            contents="Say hello in one word.",
        )
        print(f"\n[OK] {model}")
        print(f"     Status: AVAILABLE (quota remaining)")
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            print(f"\n[EXHAUSTED] {model}")
            print(f"     Status: QUOTA EXHAUSTED (limit: 0)")
        elif "404" in err or "NOT_FOUND" in err:
            print(f"\n[NOT FOUND] {model}")
            print(f"     Status: MODEL NOT AVAILABLE")
        elif "403" in err or "PERMISSION_DENIED" in err:
            print(f"\n[DENIED] {model}")
            print(f"     Status: PERMISSION DENIED")
        else:
            print(f"\n[ERROR] {model}")
            print(f"     Status: {err[:150]}")

print("\n" + "=" * 60)
print("Done!")
