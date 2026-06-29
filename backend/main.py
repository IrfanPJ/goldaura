"""
main.py — Flask backend for AI Jewelry Virtual Try-On & Styling App
Endpoints:
  POST /try-on         — virtual jewelry try-on
  POST /generate-style — gold-weight based full styling
  GET  /dataset        — list all jewelry items
  GET  /outputs/<name> — serve generated images
"""

import os
import sys
import uuid
import io

# Ensure backend/ is on the path so Vercel can find sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

from nanobanana import generate_tryon
from styler import select_jewelry_set, load_dataset

# ── App setup ────────────────────────────────────────────────────
# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
OUTPUTS_DIR = "/tmp/outputs" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "outputs")
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

def _image_to_b64(image: Image.Image) -> str:
    """Encode PIL image as base64 PNG string."""
    import base64
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def _save_result(image: Image.Image) -> str:
    """Save result image and return filename."""
    filename = f"result_{uuid.uuid4().hex[:8]}.png"
    filepath = os.path.join(OUTPUTS_DIR, filename)
    image.save(filepath, format="PNG")
    return filename


# ── Endpoints ────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def root():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>", methods=["GET"])
def serve_frontend(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
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
    Virtual Try-On endpoint (single item).
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
        tryon = generate_tryon(
            base_image=image_pil,
            jewelry_items=[{**jewelry_item, "path": jewelry_item["image"]}],
        )
    except ValueError as e:
        return jsonify({"detail": str(e)}), 422

    result = tryon["image"]
    filename = _save_result(result)
    return jsonify({
        "success": True,
        "result_image": f"/outputs/{filename}",
        "result_image_b64": _image_to_b64(result),
        "jewelry_applied": jewelry_item,
        "skipped_items": tryon["skipped"],
        "visible_parts": tryon["visible_parts"],
        "attempts": tryon.get("attempts", 1),
    })


@app.route("/try-on-multi", methods=["POST"])
def try_on_multi():
    """
    Multi-item Virtual Try-On endpoint.
    Accepts comma-separated jewelry_ids and applies them sequentially.
    """
    if "image" not in request.files or "jewelry_ids" not in request.form:
        return jsonify({"detail": "Missing image or jewelry_ids"}), 400
        
    image_file = request.files["image"]
    jewelry_ids = [jid.strip() for jid in request.form["jewelry_ids"].split(",") if jid.strip()]
    
    if not jewelry_ids:
        return jsonify({"detail": "No jewelry items selected."}), 400
    
    # Load dataset and find all jewelry items
    dataset = load_dataset()
    dataset_map = {item["id"]: item for item in dataset}
    
    items_to_apply = []
    for jid in jewelry_ids:
        item = dataset_map.get(jid)
        if item is None:
            return jsonify({"detail": f"Jewelry item '{jid}' not found."}), 404
        items_to_apply.append(item)
    
    # Read uploaded image
    file_bytes = image_file.read()
    image_pil = _read_upload_image(file_bytes)
    if image_pil is None:
        return jsonify({"detail": "Invalid image file."}), 400
    
    # Apply all jewelry items at once
    jewelry_items_payload = [{**item, "path": item["image"]} for item in items_to_apply]
    
    try:
        tryon = generate_tryon(
            base_image=image_pil,
            jewelry_items=jewelry_items_payload,
        )
    except ValueError as e:
        return jsonify({"detail": str(e)}), 422

    result = tryon["image"]
    applied_items = tryon["applied"]
    filename = _save_result(result)
    return jsonify({
        "success": True,
        "result_image": f"/outputs/{filename}",
        "result_image_b64": _image_to_b64(result),
        "applied_items": applied_items,
        "skipped_items": tryon["skipped"],
        "visible_parts": tryon["visible_parts"],
        "total_applied": len(applied_items),
        "total_requested": len(items_to_apply),
        "attempts": tryon.get("attempts", 1),
    })


@app.route("/suggest-pairs", methods=["GET"])
def suggest_pairs():
    """
    Auto-suggest complementary jewelry pairings.
    Given selected item IDs (comma-separated), suggest items from other types
    and necklaces of different lengths for layering.
    """
    selected_ids = request.args.get("selected", "")
    selected_ids = [sid.strip() for sid in selected_ids.split(",") if sid.strip()]
    
    dataset = load_dataset()
    dataset_map = {item["id"]: item for item in dataset}
    
    selected_items = [dataset_map[sid] for sid in selected_ids if sid in dataset_map]
    selected_types = set(item["type"] for item in selected_items)
    selected_lengths = set(item.get("length") for item in selected_items if item.get("length"))
    
    suggestions = []
    
    # 1. Suggest necklaces of different lengths for layering
    for item in dataset:
        if item["id"] in selected_ids:
            continue
        if item["type"] == "necklace":
            item_length = item.get("length", "")
            if "necklace" in selected_types and item_length in selected_lengths:
                continue  # Skip same-length necklaces
            suggestions.append({**item, "reason": f"Layer with different length ({item_length})"})
        elif item["type"] not in selected_types:
            # Suggest one of each missing type
            suggestions.append({**item, "reason": f"Complete your look with {item['type']}"})
    
    # Deduplicate: keep max 2 suggestions per type
    from collections import defaultdict
    by_type = defaultdict(list)
    for s in suggestions:
        by_type[s["type"]].append(s)
    
    final = []
    for t, items in by_type.items():
        final.extend(items[:3])  # Max 3 per type
    
    return jsonify(final)


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
        
    # Apply all styling items at once
    jewelry_items_payload = [{**item, "path": item["image"]} for item in styling_result["selected_items"]]
    
    try:
        tryon = generate_tryon(
            base_image=image_pil,
            jewelry_items=jewelry_items_payload,
        )
    except ValueError as e:
        return jsonify({"detail": str(e)}), 422

    result = tryon["image"]
    applied_items = tryon["applied"]
    filename = _save_result(result)
    return jsonify({
        "success": True,
        "result_image": f"/outputs/{filename}",
        "result_image_b64": _image_to_b64(result),
        "distribution": styling_result["distribution"],
        "selected_items": applied_items,
        "skipped_items": tryon["skipped"],
        "visible_parts": tryon["visible_parts"],
        "total_weight_requested": styling_result["total_weight_requested"],
        "total_weight_actual": styling_result["total_weight_actual"],
        "attempts": tryon.get("attempts", 1),
    })

if __name__ == "__main__":
    app.run(port=8000, debug=True)
