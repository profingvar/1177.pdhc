"""Assignments API — query and manage assignments."""
import logging
import uuid
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, abort, current_app
import requests as http_requests
from app import db
from app.models.assignment import Assignment
from app.models.questionnaire_response import QuestionnaireResponse
from app.routes.auth import require_api_key

logger = logging.getLogger(__name__)

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


@assignments_bp.route('/<assignment_guid>/submit', methods=['POST'])
@require_api_key
def submit_assignment(assignment_guid):
    """POST /api/assignments/<guid>/submit — submit a completed QuestionnaireResponse.

    Body: {"items": [{"linkId": "q1", "text": "...", "answer": [{"valueString": "..."}]}]}

    Builds a FHIR R5 QuestionnaireResponse, stores it locally, then dispatches
    it to gateway.pdhc via POST /api/v1/provider/report/<service_request_guid>.
    """
    assignment = Assignment.query.filter_by(assignment_guid=assignment_guid).first()
    if not assignment:
        abort(404, description=f'Assignment {assignment_guid} not found')
    if assignment.status in ('completed', 'cancelled', 'expired'):
        abort(409, description=f'Assignment is already {assignment.status}')

    body = request.get_json(silent=True) or {}
    items = body.get('items', [])

    # Build FHIR R5 QuestionnaireResponse
    response_guid = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    qr = {
        'resourceType': 'QuestionnaireResponse',
        'id': response_guid,
        'questionnaire': assignment.form_guid,
        'status': 'completed',
        'subject': {'reference': f'Patient/{assignment.patient_guid}'},
        'authored': now_iso,
        'author': {'reference': f'Patient/{assignment.patient_guid}'},
        'item': items,
    }
    if assignment.request_guid:
        qr['basedOn'] = [{'reference': f'ServiceRequest/{assignment.request_guid}'}]

    # Persist locally
    qr_record = QuestionnaireResponse(
        response_guid=response_guid,
        form_guid=assignment.form_guid,
        form_version=assignment.form_version,
        patient_guid=assignment.patient_guid,
        assignment_guid=assignment_guid,
        fhir_json=qr,
    )
    db.session.add(qr_record)

    assignment.status = 'completed'
    assignment.completed_at = datetime.now(timezone.utc)
    assignment.response_guid = response_guid
    db.session.flush()

    # Dispatch to gateway.pdhc if auth context is available
    gateway_status = 'skipped'
    gateway_error = None
    if assignment.grant_token:
        gateway_url = current_app.config.get('GATEWAY_URL', '').rstrip('/')
        gateway_token = current_app.config.get('GATEWAY_PROVIDER_TOKEN', '')
        sr_guid = assignment.request_guid

        if gateway_url and gateway_token and sr_guid:
            # Minimal payload — gateway derives org_guid from PAT, contract_guid from grant
            report_body = {
                'patient_guid': assignment.patient_guid,
                'grant_token': assignment.grant_token,
                'status': 'completed',
                'report_payload': qr,
            }
            try:
                resp = http_requests.post(
                    f'{gateway_url}/api/v1/provider/report/{sr_guid}',
                    headers={
                        'Content-Type': 'application/fhir+json',
                        'X-Provider-Token': gateway_token,
                    },
                    json=report_body,
                    timeout=15,
                )
                gateway_status = 'delivered' if resp.status_code in (200, 201, 202) else 'failed'
                if resp.status_code not in (200, 201, 202):
                    gateway_error = f'HTTP {resp.status_code}: {resp.text[:200]}'
                    logger.warning('Gateway rejected QR submission: %s', gateway_error)
            except http_requests.RequestException as e:
                gateway_status = 'failed'
                gateway_error = str(e)
                logger.warning('Gateway unreachable during QR submission: %s', e)
        else:
            gateway_status = 'not_configured'

    db.session.commit()

    result = {
        'assignment_guid': assignment_guid,
        'response_guid': response_guid,
        'status': 'completed',
        'gateway_status': gateway_status,
    }
    if gateway_error:
        result['gateway_error'] = gateway_error
    return jsonify(result), 201


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
