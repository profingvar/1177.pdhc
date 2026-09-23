from flask import Blueprint, jsonify
from app import db

health_bp = Blueprint('health', __name__)


@health_bp.route('/api/health')
def health_check():
    db_status = 'connected'
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        db_status = 'unavailable'

    # CLAUDE.md §10 canonical health shape: status/database/service, and
    # HTTP 503 when degraded so services.html + monitoring see a real red.
    status = 'ok' if db_status == 'connected' else 'degraded'
    resp = jsonify(status=status, database=db_status, service='1177.pdhc')
    # Ticket #70 / CLAUDE.md §10: let www.pdhc.se/services.html read the JSON
    # body cross-origin so it can drive real status/DB dots. Specific origin +
    # Vary: Origin (not "*") keeps future Allow-Credentials spec-compliant.
    resp.headers['Access-Control-Allow-Origin'] = 'https://www.pdhc.se'
    resp.headers['Access-Control-Allow-Methods'] = 'GET'
    resp.headers['Vary'] = 'Origin'
    resp.headers['Cache-Control'] = 'no-store'
    return resp, 200 if status == 'ok' else 503
