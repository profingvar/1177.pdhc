"""API key authentication for webhook and assignment endpoints."""
import functools
from flask import request, jsonify, current_app
from app.models.api_key import ApiKey


def require_api_key(f):
    """Require a valid API key via X-API-Key header."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key', '')

        configured_key = current_app.config.get('API_KEY')
        if configured_key and api_key == configured_key:
            return f(*args, **kwargs)

        if api_key:
            key_record = ApiKey.validate_key(api_key)
            if key_record:
                return f(*args, **kwargs)

        return jsonify(error="Unauthorized", message="Valid API key required", code=401), 401

    return decorated
