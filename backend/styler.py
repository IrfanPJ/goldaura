"""
styler.py — Gold Weight Based Jewelry Styling Selector
Given a total gold weight, distributes it across jewelry categories
and selects the best matching items from the dataset.
"""

import json
import os
from typing import Dict, List, Tuple

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset", "jewelry.json")

# ── Weight distribution ratios ───────────────────────────────────
DISTRIBUTION = {
    "necklace": 0.40,   # 40% of total weight
    "bangle": 0.35,     # 35% of total weight
    "earring": 0.15,    # 15% of total weight
    "ring": 0.10,       # 10% of total weight
}


def load_dataset() -> List[dict]:
    """Load jewelry dataset from JSON file."""
    with open(DATASET_PATH, "r") as f:
        return json.load(f)


def _find_best_match(items: List[dict], target_weight: float) -> dict | None:
    """
    Find the single item whose weight is closest to the target weight.
    Returns None if no items available.
    """
    if not items:
        return None
    return min(items, key=lambda item: abs(item["weight"] - target_weight))


def _find_combination(items: List[dict], target_weight: float) -> List[dict]:
    """
    Find a combination of items (with possible duplicates) that comes
    close to the target weight using a greedy approach.
    """
    if not items:
        return []

    selected = []
    remaining_weight = target_weight

    # Sort items by weight descending for greedy selection
    sorted_items = sorted(items, key=lambda x: x["weight"], reverse=True)

    while remaining_weight > 0:
        best = None
        best_diff = float("inf")

        for item in sorted_items:
            if item["weight"] <= remaining_weight + 2:  # Allow 2g tolerance
                diff = abs(remaining_weight - item["weight"])
                if diff < best_diff:
                    best = item
                    best_diff = diff

        if best is None:
            break

        selected.append(best)
        remaining_weight -= best["weight"]

        if remaining_weight <= 1:  # Close enough
            break

    return selected


def distribute_gold(total_grams: float) -> Dict[str, float]:
    """
    Distribute total gold weight across jewelry categories.
    Returns dict: {category: allocated_grams}
    """
    return {
        category: round(total_grams * ratio, 1)
        for category, ratio in DISTRIBUTION.items()
    }


def select_jewelry_set(total_grams: float) -> Dict[str, dict]:
    """
    Select a complete jewelry set based on total gold weight.

    Returns:
        {
            "distribution": {"necklace": 40.0, "bangle": 35.0, ...},
            "selected_items": [
                {"id": "necklace1", "type": "necklace", "weight": 35, ...},
                ...
            ],
            "total_weight_actual": 98,
            "total_weight_requested": 100
        }
    """
    dataset = load_dataset()
    distribution = distribute_gold(total_grams)

    # Group items by type
    items_by_type: Dict[str, List[dict]] = {}
    for item in dataset:
        t = item["type"]
        items_by_type.setdefault(t, []).append(item)

    selected_items = []

    for category, target_weight in distribution.items():
        available = items_by_type.get(category, [])
        if not available:
            continue

        # For bangles, try to find a combination (people wear multiple)
        if category == "bangle":
            combo = _find_combination(available, target_weight)
            selected_items.extend(combo)
        else:
            best = _find_best_match(available, target_weight)
            if best:
                selected_items.append(best)

    actual_weight = sum(item["weight"] for item in selected_items)

    return {
        "distribution": distribution,
        "selected_items": selected_items,
        "total_weight_actual": actual_weight,
        "total_weight_requested": total_grams,
    }


# ── Example prompts for diffusion model refinement ──────────────
DIFFUSION_PROMPTS = {
    "try_on": (
        "A realistic photo of a person wearing elegant gold jewelry, "
        "natural indoor lighting, photorealistic, high detail, "
        "smooth skin, professional portrait"
    ),
    "full_styling": (
        "A realistic photo of a person wearing a complete set of "
        "traditional Indian gold jewelry including necklace, earrings, "
        "bangles, and rings, natural lighting, photorealistic, "
        "high detail, 8k resolution, studio portrait"
    ),
    "negative": (
        "blurry, low quality, distorted, cartoon, anime, "
        "painting, drawing, sketch, unrealistic"
    ),
}
