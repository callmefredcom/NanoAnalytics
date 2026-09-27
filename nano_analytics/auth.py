import os
import functools
from flask import request, jsonify


def _get_token_map():
    """Return a dict mapping token -> site (or None for global tokens).
    
    Supports:
    - API_TOKEN (single token, backward compatible) - global
    - API_TOKENS (comma-separated list of tokens) - global
    - API_TOKEN_<SITE> (per-site tokens, e.g., API_TOKEN_EXAMPLE_COM=abc123)
    """
    token_map = {}
    
    # Single token (backward compatible) - global
    single = os.environ.get("API_TOKEN", "").strip()
    if single:
        token_map[single] = None
    
    # Comma-separated list - global
    multi = os.environ.get("API_TOKENS", "").strip()
    if multi:
        for t in multi.split(","):
            t = t.strip()
            if t:
                token_map[t] = None
    
    # Per-site tokens: API_TOKEN_<SITE>=token
    for key, value in os.environ.items():
        if key.startswith("API_TOKEN_") and value.strip():
            # Extract site from key (e.g., API_TOKEN_EXAMPLE_COM -> example.com)
            site_key = key[10:]  # Remove 'API_TOKEN_'
            # Convert underscores to dots for domain format
            site = site_key.lower().replace('_', '.')
            token_map[value.strip()] = site
    
    return token_map


def require_token(f):
    """Decorator that enforces Bearer token authentication with per-site isolation."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token_map = _get_token_map()
        auth_header = request.headers.get("Authorization", "")
        incoming = auth_header.removeprefix("Bearer ").strip()
        
        if not token_map or incoming not in token_map:
            return jsonify({"error": "unauthorized"}), 401
        
        # Store allowed site in request context for route handlers
        request.token_site = token_map[incoming]
        return f(*args, **kwargs)
    return decorated


def get_valid_tokens():
    """Return list of valid tokens for API introspection."""
    return list(_get_token_map().keys())