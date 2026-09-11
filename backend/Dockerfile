FROM python:3.11-alpine

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies.
# Note: pango/cairo/gdk-pixbuf/shared-mime-info support WeasyPrint PDF generation.
RUN apk upgrade --no-cache && \
    apk add --no-cache \
    bash \
    postgresql-client \
    tesseract-ocr \
    tesseract-ocr-data-eng \
    pango \
    cairo \
    gdk-pixbuf \
    glib \
    harfbuzz \
    shared-mime-info

# Copy and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade "pip>=26.1.2" "setuptools>=83.0.0" "wheel>=0.46.2" "jaraco.context>=6.1.0" && \
    rm -f /usr/local/lib/python3.11/site-packages/pip/_vendor/bom.cdx.json
RUN pip install --no-cache-dir -e ".[dev]"

# Copy application code
COPY . .

# Copy and make startup script executable
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh && ls -la /app/start.sh

# Create necessary directories
RUN mkdir -p /app/static /app/media /app/logs \
    /app/runtime/document-intelligence/artifacts \
    /app/runtime/bdr/storage \
    /app/runtime/bdr/restore

# Create non-root user for security
RUN addgroup -S appuser && \
    adduser -S -D -H -u 1000 -G appuser appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port for Django
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
