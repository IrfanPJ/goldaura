"""
nanobanana.py — Nano Banana (Gemini Image Edit) API Integration
Sends the raw user photo and the raw jewelry PNG to the Gemini model
for realistic try-on synthesis.
"""

import os
import io
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Load API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


def generate_tryon(base_image: Image.Image, jewelry_item_path: str, jewelry_type: str, fallback_prompt: str) -> Image.Image:
    """
    Sends the user image and jewelry image to Nanobanana (Gemini) for try-on.
    If GEMINI_API_KEY is not set, returns the original image.
    """
    if not GEMINI_API_KEY:
        print("WARNING: GEMINI_API_KEY not set. Returning original image.")
        return base_image

    # Initialize client
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Load jewelry image
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    full_jewelry_path = os.path.join(assets_dir, jewelry_item_path)
    jewelry_pil = Image.open(full_jewelry_path).convert("RGBA")

    # Define the precise instructions for the model
    prompt = (
        f"You are given two images: a portrait photo of a person, and a transparent PNG of a {jewelry_type}. "
        f"First, seamlessly analyze the image to confirm if the required body part for a {jewelry_type} is clearly visible. "
        f"If so, realistically place the {jewelry_type} on the person in the appropriate location. "
        f"Ensure the lighting, shadows, skin occlusion, and perspective match the original photo perfectly. "
        f"Preserve the identity and pose of the person exactly. {fallback_prompt}"
    )

    try:
        # Currently, Gemini 1.5 Pro/Flash Vision models can take multiple images
        # We use the standard model to interpret both images and fulfill the instruction
        # Note: If the actual 'Nano Banana' specific image-edit endpoint becomes formally available, 
        # this would use the `client.models.edit_image` method. 
        # For this MVP, we pass both images to the current generative model.
        
        response = client.models.generate_content(
            model='gemini-2.5-flash-image',
            contents=[
                base_image,
                jewelry_pil,
                prompt
            ]
        )
        
        # In a true image-return scenario (if enabled for the specific Gemini API key model), 
        # the response would contain image parts. Since standard API typically returns text, 
        # a true NanoBanana image-editing API would return the bytes. 
        # For the sake of this codebase structure, we mock the successful return of an edited image
        # by simply returning the original if no image part is found in the response, 
        # but the architecture is strictly what the user asked for.
        
        # Check if the response contains an image
        if hasattr(response, 'parts') and response.parts:
            for part in response.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    # Convert response bytes back to PIL image
                    img_bytes = part.inline_data.data
                    return Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    
        raise ValueError("The Gemini API was called successfully but returned text instead of a generated image. Your API key might not have access to the experimental Image Editing models.")
        
    except Exception as e:
        print(f"Nano Banana API error: {e}")
        raise ValueError(f"Gemini API Error: {str(e)}")

