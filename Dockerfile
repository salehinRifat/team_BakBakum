# Production Dockerfile for GridWise Energy Optimization Service
# BUP CSE Fest 2026 Hackathon
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and reference files
COPY app/ app/
COPY BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json .

# Expose service port
EXPOSE 8000

# Healthcheck for container orchestrators and judge harness
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Start the service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
