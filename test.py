import os
import cv2
import numpy as np

# Create a dummy image
img = np.zeros((400, 400, 3), dtype=np.uint8)
# Add some fake "landmarks" so mediapipe doesn't immediately fail
# Actually we can just pass an image and see what error it generates.
# Let's import main and call the function directly
from backend.nanobanana import generate_tryon

print("Testing generate_tryon directly...")
try:
    res = generate_tryon(img, "necklaces/necklace1.png", "necklace", "test prompt")
    print("Shape:", res.shape)
except Exception as e:
    print("Error:", e)
