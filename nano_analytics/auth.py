import os
import functools
from flask import request, jsonify


def require_token(f):
    """Decorator that enforces Bearer token authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = os.environ.get("API_TOKEN", "")
        auth_header = request.headers.get("Authorization", "")
        incoming = auth_header.removeprefix("Bearer ").strip()
        if not token or incoming != token:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated
