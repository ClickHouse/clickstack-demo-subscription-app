# Use Python 3.13 slim image as base
FROM python:3.13.5-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=flask_app.py \
    FLASK_ENV=production

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Install opentelemtery-bootstrap for auto-instrumentation
RUN opentelemetry-bootstrap --action=install

# Copy application code
COPY flask_app.py .

# Copy static files
COPY static/ static/
COPY templates/ templates/

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

# Run the application
CMD ["opentelemetry-instrument", "python", "flask_app.py"]
