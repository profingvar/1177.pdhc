"""Assignments API — query and manage assignments."""
from flask import Blueprint, jsonify, request, abort
from app import db
from app.models.assignment import Assignment
from app.routes.auth import require_api_key

assignments_bp = Blueprint('assignments', __name__)


@assignments_bp.route('/<assignment_guid>', methods=['GET'])
@require_api_key
def get_assignment(assignment_guid):
    """GET /api/assignments/<guid> — fetch a single assignment."""
    assignment = Assignment.query.filter_by(assignment_guid=assignment_guid).first()
    if not assignment:
        abort(404, description=f'Assignment {assignment_guid} not found')
    return jsonify(assignment.to_dict())


@assignments_bp.route('', methods=['GET'])
@require_api_key
def list_assignments():
    """GET /api/assignments?patient_guid=...&status=...

    Query params:
        patient_guid:  filter by patient (required)
        status:        filter by status (optional)
        limit:         pagination limit (default 50)
        offset:        pagination offset (default 0)
    """
    patient_guid = request.args.get('patient_guid')
    if not patient_guid:
        abort(400, description='patient_guid query parameter is required')

    status_filter = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    query = Assignment.query.filter_by(patient_guid=patient_guid)
    if status_filter:
        query = query.filter_by(status=status_filter)

    total = query.count()
    assignments = (
        query
        .order_by(Assignment.assigned_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jsonify({
        'assignments': [a.to_summary() for a in assignments],
        'total': total,
        'limit': limit,
        'offset': offset,
        'has_more': (offset + limit) < total,
    })


@assignments_bp.route('/<assignment_guid>/cancel', methods=['POST'])
@require_api_key
def cancel_assignment(assignment_guid):
    """POST /api/assignments/<guid>/cancel — cancel a pending/opened assignment."""
    assignment = Assignment.query.filter_by(assignment_guid=assignment_guid).first()
    if not assignment:
        abort(404, description=f'Assignment {assignment_guid} not found')
    if assignment.status not in ('pending', 'opened'):
        abort(409, description=f'Cannot cancel assignment in status "{assignment.status}"')

    assignment.status = 'cancelled'
    db.session.commit()
    return jsonify(assignment.to_dict())
