import os
import functools
from flask import request, jsonify


def _get_valid_tokens():
    """Return a set of valid API tokens from environment variables.
    
    Supports:
    - API_TOKEN (single token, backward compatible)
    - API_TOKENS (comma-separated list of tokens)
    - API_TOKEN_<SITE> (per-site tokens, e.g., API_TOKEN_EXAMPLE_COM=abc123)
    """
    tokens = set()
    
    # Single token (backward compatible)
    single = os.environ.get("API_TOKEN", "").strip()
    if single:
        tokens.add(single)
    
    # Comma-separated list
    multi = os.environ.get("API_TOKENS", "").strip()
    if multi:
        for t in multi.split(","):
            t = t.strip()
            if t:
                tokens.add(t)
    
    # Per-site tokens: API_TOKEN_<SITE>=token
    for key, value in os.environ.items():
        if key.startswith("API_TOKEN_") and value.strip():
            tokens.add(value.strip())
    
    return tokens


def require_token(f):
    """Decorator that enforces Bearer token authentication."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        valid_tokens = _get_valid_tokens()
        auth_header = request.headers.get("Authorization", "")
        incoming = auth_header.removeprefix("Bearer ").strip()
        if not valid_tokens or incoming not in valid_tokens:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def get_valid_tokens():
    """Return list of valid tokens for API introspection."""
    return list(_get_valid_tokens())
