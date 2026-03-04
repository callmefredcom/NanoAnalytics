import logging


class _FilterActive(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return "/api/active" not in msg


# Suppress noisy polling endpoint from access logs
logging.getLogger("gunicorn.access").addFilter(_FilterActive())
