"""Authentication — simple session login + API key auth."""
import functools
from flask import (
    Blueprint, request, jsonify, redirect, session,
    url_for, current_app, render_template, flash,
)
from app.models.api_key import ApiKey

auth_bp = Blueprint('auth', __name__)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(fn):
    """Redirect to login if no session."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        return fn(*args, **kwargs)
    return wrapper


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


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user'):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        from app.models.user import User
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user'] = {'username': user.username, 'role': user.role}
            session.permanent = True
            return redirect(url_for('admin.dashboard'))

        flash('Invalid username or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('auth.login'))
