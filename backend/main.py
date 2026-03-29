"""
main.py — Flask backend for AI Jewelry Virtual Try-On & Styling App
Endpoints:
  POST /try-on         — virtual jewelry try-on
  POST /generate-style — gold-weight based full styling
  GET  /dataset        — list all jewelry items
  GET  /outputs/<name> — serve generated images
"""

import os
import uuid
import io
from PIL import Image
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

from nanobanana import generate_tryon
from styler import select_jewelry_set, load_dataset, DIFFUSION_PROMPTS

# ── App setup ────────────────────────────────────────────────────
# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
# CORS — allow frontend dev server
CORS(app)


# ── Helper ───────────────────────────────────────────────────────

def _read_upload_image(file_bytes: bytes) -> Image.Image:
    """Convert uploaded file bytes to a PIL Image."""
    try:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        return img
    except Exception:
        return None

def _save_result(image: Image.Image) -> str:
    """Save result image and return filename."""
    filename = f"result_{uuid.uuid4().hex[:8]}.png"
    filepath = os.path.join(OUTPUTS_DIR, filename)
    image.save(filepath, format="PNG")
    return filename


# ── Endpoints ────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def root():
    return app.send_static_file("index.html")

@app.route("/<path:path>", methods=["GET"])
def serve_frontend(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return app.send_static_file(path)
    return jsonify({"detail": "Not found"}), 404

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/dataset", methods=["GET"])
def get_dataset():
    """Return all jewelry items from dataset."""
    items = load_dataset()
    return jsonify(items)

@app.route("/outputs/<filename>", methods=["GET"])
def get_output(filename):
    """Serve a generated output image."""
    filepath = os.path.join(OUTPUTS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"detail": "Image not found."}), 404
    return send_file(filepath, mimetype="image/png")

@app.route("/assets/<path:subpath>", methods=["GET"])
def get_asset(subpath):
    """Serve static asset files."""
    return send_from_directory(ASSETS_DIR, subpath)

@app.route("/try-on", methods=["POST"])
def try_on():
    """
    Virtual Try-On endpoint.
    """
    if "image" not in request.files or "jewelry_id" not in request.form:
        return jsonify({"detail": "Missing image or jewelry_id"}), 400
        
    image_file = request.files["image"]
    jewelry_id = request.form["jewelry_id"]
    
    # Load dataset and find jewelry item
    dataset = load_dataset()
    jewelry_item = next((j for j in dataset if j["id"] == jewelry_id), None)
    if jewelry_item is None:
        return jsonify({"detail": f"Jewelry item '{jewelry_id}' not found."}), 404
        
    # Read uploaded image
    file_bytes = image_file.read()
    image_pil = _read_upload_image(file_bytes)
    if image_pil is None:
        return jsonify({"detail": "Invalid image file."}), 400
        
    # Apply Nano Banana processing
    try:
        result = generate_tryon(
            base_image=image_pil,
            jewelry_item_path=jewelry_item["image"],
            jewelry_type=jewelry_item["type"],
            fallback_prompt=DIFFUSION_PROMPTS["try_on"]
        )
    except ValueError as e:
        return jsonify({"detail": str(e)}), 422
        
    # Save and return
    filename = _save_result(result)
    return jsonify({
        "success": True,
        "result_image": f"/outputs/{filename}",
        "jewelry_applied": jewelry_item,
        "diffusion_prompt": DIFFUSION_PROMPTS["try_on"],
    })


@app.route("/generate-style", methods=["POST"])
def generate_style():
    """
    AI Styling endpoint.
    """
    if "image" not in request.files or "total_grams" not in request.form:
        return jsonify({"detail": "Missing image or total_grams"}), 400
        
    image_file = request.files["image"]
    total_grams = float(request.form["total_grams"])
    
    if total_grams <= 0 or total_grams > 500:
        return jsonify({"detail": "Gold weight must be between 1 and 500 grams."}), 400
        
    # Select jewelry set based on weight
    styling_result = select_jewelry_set(total_grams)
    
    # Read uploaded image
    file_bytes = image_file.read()
    image_pil = _read_upload_image(file_bytes)
    if image_pil is None:
        return jsonify({"detail": "Invalid image file."}), 400
        
    current_image = image_pil.copy()
    applied_items = []
    
    for item in styling_result["selected_items"]:
        try:
            current_image = generate_tryon(
                base_image=current_image,
                jewelry_item_path=item["image"],
                jewelry_type=item["type"],
                fallback_prompt=DIFFUSION_PROMPTS["full_styling"]
            )
            applied_items.append(item)
        except ValueError:
            # Skip items if Gemini refuses or fails
            continue
            
    # Save and return
    filename = _save_result(current_image)
    return jsonify({
        "success": True,
        "result_image": f"/outputs/{filename}",
        "distribution": styling_result["distribution"],
        "selected_items": applied_items,
        "total_weight_requested": styling_result["total_weight_requested"],
        "total_weight_actual": styling_result["total_weight_actual"],
        "diffusion_prompt": DIFFUSION_PROMPTS["full_styling"],
        "negative_prompt": DIFFUSION_PROMPTS["negative"],
    })

if __name__ == "__main__":
    app.run(port=8000, debug=True)
