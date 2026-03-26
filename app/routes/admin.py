"""Admin UI — dashboard with assignment overview."""
from flask import Blueprint, render_template
from app import db
from app.routes.auth import login_required
from app.models.assignment import Assignment
from app.models.questionnaire_response import QuestionnaireResponse
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
def index():
    return render_template('login.html')


@admin_bp.route('/dashboard')
@login_required
def dashboard():
    pending = db.session.query(func.count(Assignment.id)).filter_by(status='pending').scalar() or 0
    opened = db.session.query(func.count(Assignment.id)).filter_by(status='opened').scalar() or 0
    completed = db.session.query(func.count(Assignment.id)).filter_by(status='completed').scalar() or 0
    total_responses = db.session.query(func.count(QuestionnaireResponse.id)).scalar() or 0

    return render_template('dashboard.html',
                           pending=pending,
                           opened=opened,
                           completed=completed,
                           total_responses=total_responses)
