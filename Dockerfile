FROM python:3.12-alpine

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[bots]" 2>/dev/null || pip install --no-cache-dir -e .

# Copy application code
COPY nano_analytics/ nano_analytics/
COPY static/ static/
COPY templates/ templates/

# Create the data directory (will be overridden by volume mount)
RUN mkdir -p /data

ENV DB_PATH=/data/analytics.db
ENV PORT=8000

EXPOSE 8000

# Use 2 sync workers — correct for SQLite + WAL mode
CMD ["sh", "-c", "gunicorn 'nano_analytics:create_app()' --bind 0.0.0.0:${PORT} --workers 2 --timeout 30 --access-logfile -"]
