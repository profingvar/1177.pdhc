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

    return jsonify(status='ok', database=db_status)
