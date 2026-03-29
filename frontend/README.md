# GoldAura Frontend

This is a lightweight, pure HTML/CSS/JS frontend for the GoldAura Virtual Try-On API.
It requires no build steps or Node.js environment.

## Getting Started

1. Make sure your Python backend is running on `http://localhost:8000`.
2. Simply double-click `index.html` to open the app in your web browser. 
3. (Optional) For a better experience, serve the directory via a simple HTTP server:
   ```bash
   python -m http.server 3000
   ```
   Then navigate to `http://localhost:3000`.

## Files
- `index.html` - Landing page with marketing copy and navigation.
- `tryon.html` - Virtual Try-On interface featuring image upload and interactive jewelry selection grid.
- `styling.html` - AI Gold Styling interface featuring weight sliders and dynamic distribution visualization.
- `styles.css` - Global CSS styling containing the dark mode theme, glassmorphism cards, and gold accents.
- `app.js` - Client-side logic for API requests to the FastAPI backend, state management, and DOM manipulation.
