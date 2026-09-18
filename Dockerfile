# Production Dockerfile for GridWise Energy Optimization Service
# BUP CSE Fest 2026 Hackathon · Online Preliminary
FROM python:3.11-slim

# Set environment variables (no secret credentials)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code, tests, and sample reference files
COPY app/ app/
COPY tests/ tests/
COPY BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json .

# Expose the documented service port
EXPOSE 8000

# Healthcheck to verify readiness
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Start the service binding to 0.0.0.0:8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
