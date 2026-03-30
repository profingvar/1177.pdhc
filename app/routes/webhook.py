"""Webhook — inbound ServiceRequest from request.pdhc.se."""
import logging
from flask import Blueprint, jsonify, request, abort
from app import db
from app.models.assignment import Assignment
from app.routes.auth import require_api_key

logger = logging.getLogger(__name__)

webhook_bp = Blueprint('webhook', __name__)


def _extract_contained(contained_list, resource_type):
    """Find a contained resource by resourceType."""
    for resource in contained_list:
        if resource.get('resourceType') == resource_type:
            return resource
    return None


def _extract_all_contained(contained_list, resource_type):
    """Find all contained resources of a given resourceType."""
    return [r for r in contained_list if r.get('resourceType') == resource_type]


@webhook_bp.route('/inbound', methods=['POST'])
@require_api_key
def inbound():
    """POST /api/webhook/inbound — receive a ServiceRequest from request.pdhc.se.

    Parses the FHIR ServiceRequest bundle, extracts contained Patient and
    Questionnaire resources, and creates one Assignment per Questionnaire.
    """
    data = request.get_json(silent=True)
    if not data:
        abort(400, description='JSON body required')

    # Unwrap Bundle → extract the ServiceRequest entry and delivery meta tags
    bundle_tags = {}
    if data.get('resourceType') == 'Bundle':
        for tag in data.get('meta', {}).get('tag', []):
            if tag.get('system') == 'https://pdhc.se/delivery':
                bundle_tags[tag['code']] = tag.get('display', '')

        sr_resource = None
        for entry in data.get('entry', []):
            res = entry.get('resource', entry)
            if res.get('resourceType') == 'ServiceRequest':
                sr_resource = res
                break
        if not sr_resource:
            abort(400, description='Bundle must contain a ServiceRequest resource')
        data = sr_resource

    if data.get('resourceType') != 'ServiceRequest':
        abort(400, description='resourceType must be "ServiceRequest"')

    contained = data.get('contained', [])
    if not contained:
        abort(400, description='ServiceRequest must include contained resources')

    # --- Extract Patient ---
    patient = _extract_contained(contained, 'Patient')
    if not patient:
        abort(400, description='ServiceRequest must contain a Patient resource')

    patient_guid = patient.get('id')
    if not patient_guid:
        abort(400, description='Contained Patient must have an id')

    # --- Extract Questionnaire(s) ---
    questionnaires = _extract_all_contained(contained, 'Questionnaire')
    if not questionnaires:
        abort(
            400,
            description='ServiceRequest must contain at least one Questionnaire resource. '
                        'request.pdhc.se should resolve and include the Questionnaire from plan.pdhc.se '
                        'before dispatching.',
        )

    # --- Extract metadata ---
    request_guid = data.get('id')

    # Parse grant_expires_at from bundle tags
    grant_expires_at = None
    expires_at_str = bundle_tags.get('expires_at', '')
    if expires_at_str:
        try:
            from datetime import datetime, timezone
            grant_expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            pass

    # --- Create one assignment per Questionnaire ---
    created = []
    for q in questionnaires:
        form_guid = q.get('id', '')
        if not form_guid:
            logger.warning('Skipping Questionnaire without id in ServiceRequest %s', request_guid)
            continue
        # Strip fhir_builder prefix (e.g. "questionnaire-<uuid>" → "<uuid>")
        if form_guid.startswith('questionnaire-'):
            form_guid = form_guid[len('questionnaire-'):]

        form_version_str = q.get('version', '1')
        try:
            form_version = int(form_version_str)
        except (ValueError, TypeError):
            form_version = 1

        assignment = Assignment(
            patient_guid=patient_guid,
            form_guid=form_guid,
            form_version=form_version,
            questionnaire_fhir=q,
            request_guid=request_guid,
            grant_token=bundle_tags.get('grant_token', '') or None,
            contract_guid=bundle_tags.get('contract_guid', '') or None,
            organisation_guid=bundle_tags.get('organisation_guid', '') or None,
            grant_expires_at=grant_expires_at,
        )
        db.session.add(assignment)
        created.append(assignment)

    if not created:
        abort(400, description='No valid Questionnaire resources found in contained')

    db.session.commit()

    logger.info(
        'Webhook: created %d assignment(s) from ServiceRequest %s for patient %s',
        len(created), request_guid, patient_guid,
    )

    return jsonify({
        'received': True,
        'service_request_id': request_guid,
        'patient_guid': patient_guid,
        'assignments_created': len(created),
        'assignments': [a.to_summary() for a in created],
    }), 201
