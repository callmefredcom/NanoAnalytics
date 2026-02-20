FROM python:3.12-alpine

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir flask gunicorn geoip2fast

# Copy application code
COPY nano_analytics/ nano_analytics/
COPY static/ static/
COPY templates/ templates/
COPY wsgi.py .

# Create the data directory (overridden by volume mount on Railway/Render/Fly)
RUN mkdir -p /data

ENV DB_PATH=/data/analytics.db
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 30 --access-logfile -"]
