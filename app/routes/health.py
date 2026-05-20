from flask import Blueprint, jsonify
from app import db

health_bp = Blueprint('health', __name__)


@health_bp.route('/api/health')
def health_check():
    db_status = 'connected'
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        db_status = 'disconnected'

    resp = jsonify(status='ok', database=db_status)
    # Ticket #70 / CLAUDE.md §10: let www.pdhc.se/services.html read the JSON
    # body cross-origin so it can drive real status/DB dots. Specific origin +
    # Vary: Origin (not "*") keeps future Allow-Credentials spec-compliant.
    resp.headers['Access-Control-Allow-Origin'] = 'https://www.pdhc.se'
    resp.headers['Access-Control-Allow-Methods'] = 'GET'
    resp.headers['Vary'] = 'Origin'
    resp.headers['Cache-Control'] = 'no-store'
    return resp
