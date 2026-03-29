# 💎 GoldAura — AI Jewelry Virtual Try-On & Styling App

An MVP web application that lets users virtually try on gold jewelry using AI-powered body landmark detection, and get smart styling recommendations based on gold weight.

## Features

### 🪞 Virtual Try-On
- Upload a portrait/body photo
- Select a jewelry piece (necklace, earring, bangle, ring)
- AI validates body part visibility using **MediaPipe**
- Raw photo + jewelry image are sent directly to the **Nano Banana (Gemini)** model for realistic dual-image generation
- Download the result

### ⚖️ AI Gold Styling
- Upload a full-body photo
- Input total gold weight (e.g., 100g)
- AI distributes weight: 40% necklace, 35% bangles, 15% earrings, 10% rings
- Selects best-matching items from dataset
- Composites all jewelry onto the photo

---

## Tech Stack

| Layer      | Technology                         |
|------------|------------------------------------|
| Frontend   | Vanilla HTML, CSS, JavaScript      |
| Backend    | Python Flask                       |
| AI/Vision  | MediaPipe Pose & Face Mesh         |
| Image      | OpenCV + Pillow (alpha compositing) |
| Assets     | Transparent PNG jewelry images      |

---

## Folder Structure

```
jewellery/
├── backend/
│   ├── main.py              # Flask app & endpoints
│   ├── overlay.py           # Jewelry overlay engine (MediaPipe)
│   ├── styler.py            # Gold weight distribution & selection
│   ├── requirements.txt     # Python dependencies
│   ├── assets/              # Transparent PNG jewelry assets
│   │   ├── necklaces/
│   │   ├── earrings/
│   │   ├── bangles/
│   │   └── rings/
│   ├── dataset/
│   │   └── jewelry.json     # Jewelry metadata
│   └── outputs/             # Generated result images
├── frontend/
│   ├── index.html           # Landing page
│   ├── tryon.html           # Virtual Try-On page
│   ├── styling.html         # AI Gold Styling page
│   ├── styles.css           # Global styles (dark + gold theme)
│   ├── app.js               # API integrations & UI logic
│   └── README.md
└── README.md
```

---

## Run Locally

### Prerequisites
- **Python 3.9+** with pip
- **Node.js 18+** with npm
- **Gemini API Key** (set as `GEMINI_API_KEY` environment variable)

### 1. Start Full Application

You can start **both the backend and frontend simultaneously** by double-clicking the `run.bat` file in the root directory, or by running:

```bash
.\run.bat
```

This will start the Flask server which now also serves the frontend!

The app will be available at: **http://localhost:8000**



---

## API Endpoints

| Method | Endpoint           | Description                    |
|--------|--------------------|--------------------------------|
| GET    | `/`                | Health check                   |
| GET    | `/dataset`         | List all jewelry items         |
| GET    | `/health`          | Health status                  |
| POST   | `/try-on`          | Virtual try-on (image + ID)    |
| POST   | `/generate-style`  | AI styling (image + grams)     |
| GET    | `/outputs/{name}`  | Serve generated result images  |

---

## Diffusion Model Prompts (for enhancement)

**Try-On:**
```
"A realistic photo of a person wearing elegant gold jewelry, natural indoor lighting, photorealistic, high detail, smooth skin, professional portrait"
```

**Full Styling:**
```
"A realistic photo of a person wearing a complete set of traditional Indian gold jewelry including necklace, earrings, bangles, and rings, natural lighting, photorealistic, high detail, 8k resolution, studio portrait"
```

**Negative Prompt:**
```
"blurry, low quality, distorted, cartoon, anime, painting, drawing, sketch, unrealistic"
```

---

## Constraints
- This is an **MVP** — uses 2D overlay approximation, not 3D modeling
- Overlay quality depends on MediaPipe landmark detection accuracy
- Best results with clear, well-lit photos where body landmarks are visible
- Jewelry PNG assets are synthetic/generated — replace with real product photos for production
