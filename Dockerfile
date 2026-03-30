FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Set working directory to backend
WORKDIR /app/backend

# Expose HF Spaces default port
EXPOSE 7860

# Run with gunicorn for production (no timeout limit)
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:7860", "--timeout", "300", "--workers", "1"]
