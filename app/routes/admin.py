"""Admin UI — dashboard, assignment overview, settings, user and key management."""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, request as flask_request, redirect, url_for, flash, current_app, session
import requests as http_requests
from app import db
from app.routes.auth import login_required
from app.models.assignment import Assignment
from app.models.questionnaire_response import QuestionnaireResponse
from app.models.user import User
from app.models.api_key import ApiKey
from sqlalchemy import func

logger = logging.getLogger(__name__)

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


@admin_bp.route('/assignments')
@login_required
def assignments_list():
    status_filter = flask_request.args.get('status', '').strip() or None
    show_all = flask_request.args.get('show_all', '') == '1'
    page = flask_request.args.get('page', 1, type=int)
    per_page = 50

    query = Assignment.query.order_by(Assignment.assigned_at.desc())
    if not show_all:
        query = query.filter(Assignment.archived == False)
    if status_filter:
        query = query.filter_by(status=status_filter)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'assignments_list.html',
        assignments=pagination.items,
        pagination=pagination,
        status_filter=status_filter or '',
        show_all=show_all,
    )


@admin_bp.route('/assignments/<guid>/archive', methods=['POST'])
@login_required
def archive_assignment(guid):
    assignment = Assignment.query.filter_by(assignment_guid=guid).first_or_404()
    assignment.archived = not assignment.archived
    db.session.commit()
    label = 'archived' if assignment.archived else 'unarchived'
    flash(f'Assignment {label}.', 'success')
    return redirect(flask_request.referrer or url_for('admin.assignments_list'))


@admin_bp.route('/assignments/<guid>')
@login_required
def assignment_detail(guid):
    """Open an assignment and render its questionnaire form."""
    assignment = Assignment.query.filter_by(assignment_guid=guid).first_or_404()

    # Mark pending → opened on first view
    if assignment.status == 'pending':
        assignment.status = 'opened'
        db.session.commit()

    # Load response if completed
    response = None
    answer_lookup = {}
    if assignment.response_guid:
        response = QuestionnaireResponse.query.filter_by(
            response_guid=assignment.response_guid
        ).first()
        if response and response.fhir_json:
            for resp_item in response.fhir_json.get('item', []):
                answers = resp_item.get('answer', [])
                if answers:
                    a = answers[0]
                    # Extract the value regardless of type
                    val = (
                        a.get('valueString')
                        or a.get('valueInteger')
                        or a.get('valueDecimal')
                        or a.get('valueDate')
                        or a.get('valueDateTime')
                    )
                    if a.get('valueCoding'):
                        val = a['valueCoding'].get('code')
                    if a.get('valueBoolean') is not None:
                        val = 'true' if a['valueBoolean'] else 'false'
                    if val is not None:
                        answer_lookup[resp_item['linkId']] = str(val)

    questionnaire = assignment.questionnaire_fhir
    items = questionnaire.get('item', [])
    is_readonly = assignment.status in ('completed', 'expired', 'cancelled')

    # Pre-process FHIR extensions into a flat lookup for template use
    item_meta = _extract_item_meta(items)

    return render_template(
        'assignment_form.html',
        assignment=assignment,
        questionnaire=questionnaire,
        items=items,
        response=response,
        answer_lookup=answer_lookup,
        is_readonly=is_readonly,
        item_meta=item_meta,
    )


@admin_bp.route('/assignments/<guid>/submit', methods=['POST'])
@login_required
def assignment_submit(guid):
    """Submit answers for an assignment questionnaire."""
    assignment = Assignment.query.filter_by(assignment_guid=guid).first_or_404()

    if assignment.status == 'completed':
        flash('This assignment has already been completed.', 'error')
        return redirect(url_for('admin.assignment_detail', guid=guid))

    if assignment.status not in ('pending', 'opened'):
        flash(f'Cannot submit — assignment is {assignment.status}.', 'error')
        return redirect(url_for('admin.assignments_list'))

    questionnaire = assignment.questionnaire_fhir
    items = questionnaire.get('item', [])

    # Build FHIR QuestionnaireResponse items
    response_items = _build_response_items(items, flask_request.form)

    # Check required fields
    for item in items:
        if item.get('required') and item.get('type') != 'display':
            link_id = item.get('linkId')
            raw = flask_request.form.get(f'item_{link_id}', '').strip()
            if not raw:
                flash(f'Required: {item.get("text", link_id)}', 'error')
                return redirect(url_for('admin.assignment_detail', guid=guid))

    fhir_response = {
        'resourceType': 'QuestionnaireResponse',
        'questionnaire': assignment.form_guid,
        'status': 'completed',
        'authored': datetime.now(timezone.utc).isoformat(),
        'subject': {'reference': f'Patient/{assignment.patient_guid}'},
        'item': response_items,
    }
    if assignment.request_guid:
        fhir_response['basedOn'] = [{'reference': f'ServiceRequest/{assignment.request_guid}'}]

    qr = QuestionnaireResponse(
        form_guid=assignment.form_guid,
        form_version=assignment.form_version,
        patient_guid=assignment.patient_guid,
        assignment_guid=assignment.assignment_guid,
        fhir_json=fhir_response,
    )
    db.session.add(qr)
    db.session.flush()

    assignment.status = 'completed'
    assignment.completed_at = datetime.now(timezone.utc)
    assignment.response_guid = qr.response_guid
    db.session.commit()

    # Dispatch to gateway.pdhc if auth context is present
    _dispatch_to_gateway(assignment, fhir_response)

    flash('Response submitted.', 'success')
    return redirect(url_for('admin.assignment_detail', guid=guid))


def _dispatch_to_gateway(assignment, fhir_qr):
    """Fire-and-forget dispatch of a QuestionnaireResponse to gateway.pdhc."""
    if not (assignment.grant_token and assignment.contract_guid
            and assignment.organisation_guid and assignment.request_guid):
        return  # Auth context not available — push not configured for this assignment

    gateway_url = current_app.config.get('GATEWAY_URL', '').rstrip('/')
    gateway_token = current_app.config.get('GATEWAY_PROVIDER_TOKEN', '')
    if not gateway_url or not gateway_token:
        logger.warning('GATEWAY_URL or GATEWAY_PROVIDER_TOKEN not configured — skipping dispatch')
        return

    report_body = {
        'patient_guid': assignment.patient_guid,
        'contract_guid': assignment.contract_guid,
        'organisation_guid': assignment.organisation_guid,
        'grant_token': assignment.grant_token,
        'expires_at': assignment.grant_expires_at.isoformat() if assignment.grant_expires_at else None,
        'report_payload': fhir_qr,
    }
    try:
        resp = http_requests.post(
            f'{gateway_url}/api/v1/provider/report/{assignment.request_guid}',
            headers={
                'Content-Type': 'application/fhir+json',
                'X-Provider-Token': gateway_token,
            },
            json=report_body,
            timeout=15,
        )
        if resp.status_code not in (200, 201, 202):
            logger.warning('Gateway rejected QR: HTTP %d — %s', resp.status_code, resp.text[:200])
        else:
            logger.info('QR dispatched to gateway for SR %s', assignment.request_guid)
    except http_requests.RequestException as e:
        logger.warning('Gateway unreachable during QR dispatch: %s', e)


def _extract_item_meta(items):
    """Walk FHIR Questionnaire items and extract extension metadata into a flat dict.

    Returns {linkId: {unit, min, max, anchor_low, anchor_high, code, code_system, repeats}} .
    """
    meta = {}
    for item in items:
        link_id = item.get('linkId')
        if not link_id:
            continue

        m = {}
        # FHIR extensions — units, min/max, anchors, itemControl
        for ext in item.get('extension', []):
            url = ext.get('url', '')
            if url.endswith('/questionnaire-unit'):
                vc = ext.get('valueCoding', {})
                m['unit'] = vc.get('display') or vc.get('code') or ''
            elif url.endswith('/minValue'):
                m['min'] = ext.get('valueDecimal') or ext.get('valueInteger')
            elif url.endswith('/maxValue'):
                if 'valueString' in ext:
                    m['anchor_high'] = ext['valueString']
                else:
                    m['max'] = ext.get('valueDecimal') or ext.get('valueInteger')
            elif url.endswith('/questionnaire-sliderStepValue'):
                m['step'] = ext.get('valueInteger') or ext.get('valueDecimal')
                if ext.get('valueString'):
                    m['anchor_low'] = ext['valueString']
            elif url.endswith('/questionnaire-itemControl'):
                vcc = ext.get('valueCodeableConcept', {})
                for coding in vcc.get('coding', []):
                    if coding.get('code') == 'slider':
                        m['is_slider'] = True

        # Code reference (canonical concept)
        codes = item.get('code', [])
        if codes:
            c = codes[0]
            m['code'] = c.get('code', '')
            m['code_system'] = c.get('system', '')
            m['code_display'] = c.get('display', '')

        # Repeats flag (multiple choice)
        if item.get('repeats'):
            m['repeats'] = True

        if m:
            meta[link_id] = m

        # Recurse into groups
        if item.get('type') == 'group':
            meta.update(_extract_item_meta(item.get('item', [])))

    return meta


def _build_response_items(items, form_data):
    """Walk questionnaire items and build FHIR response items from form data."""
    result = []
    for item in items:
        link_id = item.get('linkId')
        item_type = item.get('type', 'string')

        if item_type == 'display':
            continue

        # Handle groups — recurse into nested items
        if item_type == 'group':
            nested = _build_response_items(item.get('item', []), form_data)
            if nested:
                result.append({
                    'linkId': link_id,
                    'text': item.get('text', ''),
                    'item': nested,
                })
            continue

        raw = form_data.get(f'item_{link_id}', '').strip()
        if not raw:
            continue

        answer = _make_answer(item_type, raw, item.get('answerOption', []))
        if answer:
            result.append({
                'linkId': link_id,
                'text': item.get('text', ''),
                'answer': [answer],
            })

    return result


def _make_answer(item_type, raw, answer_options):
    """Convert a raw form value into a FHIR answer dict."""
    if item_type == 'choice':
        for opt in answer_options:
            coding = opt.get('valueCoding', {})
            if coding.get('code') == raw:
                return {'valueCoding': coding}
        return {'valueString': raw}
    elif item_type in ('string', 'text'):
        return {'valueString': raw}
    elif item_type == 'integer':
        try:
            return {'valueInteger': int(raw)}
        except ValueError:
            return {'valueString': raw}
    elif item_type == 'decimal':
        try:
            return {'valueDecimal': float(raw)}
        except ValueError:
            return {'valueString': raw}
    elif item_type == 'boolean':
        return {'valueBoolean': raw == 'true'}
    elif item_type == 'date':
        return {'valueDate': raw}
    elif item_type == 'dateTime':
        return {'valueDateTime': raw}
    else:
        return {'valueString': raw}


# ---------------------------------------------------------------------------
# Settings hub
# ---------------------------------------------------------------------------

@admin_bp.route('/settings')
@login_required
def settings():
    return render_template('settings.html')


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@admin_bp.route('/settings/users')
@login_required
def users_list():
    users = User.query.order_by(User.created_at).all()
    return render_template('users.html', users=users)


@admin_bp.route('/settings/users/create', methods=['POST'])
@login_required
def user_create():
    username = flask_request.form.get('username', '').strip()
    password = flask_request.form.get('password', '')
    confirm  = flask_request.form.get('confirm', '')
    role     = flask_request.form.get('role', 'admin')

    if not username or not password:
        flash('Username and password are required.', 'error')
        return redirect(url_for('admin.users_list'))
    if password != confirm:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('admin.users_list'))
    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
        return redirect(url_for('admin.users_list'))
    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'error')
        return redirect(url_for('admin.users_list'))

    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f'User "{username}" created.', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/settings/users/<int:user_id>/set-password', methods=['POST'])
@login_required
def user_set_password(user_id):
    user = User.query.get_or_404(user_id)
    password = flask_request.form.get('password', '')
    confirm  = flask_request.form.get('confirm', '')

    if not password:
        flash('Password is required.', 'error')
    elif password != confirm:
        flash('Passwords do not match.', 'error')
    elif len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
    else:
        user.set_password(password)
        db.session.commit()
        # If changing own password, force re-login
        if session.get('user', {}).get('username') == user.username:
            session.pop('user', None)
            flash('Password updated. Please log in again.', 'success')
            return redirect(url_for('auth.login'))
        flash(f'Password updated for "{user.username}".', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/settings/users/<int:user_id>/delete', methods=['POST'])
@login_required
def user_delete(user_id):
    user = User.query.get_or_404(user_id)
    if session.get('user', {}).get('username') == user.username:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users_list'))
    if User.query.count() <= 1:
        flash('Cannot delete the last admin account.', 'error')
        return redirect(url_for('admin.users_list'))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{username}" deleted.', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/settings/change-password', methods=['POST'])
@login_required
def change_own_password():
    """Change the currently logged-in user's password."""
    current  = flask_request.form.get('current_password', '')
    password = flask_request.form.get('password', '')
    confirm  = flask_request.form.get('confirm', '')
    next_url = flask_request.form.get('next', url_for('admin.settings'))

    me = User.query.filter_by(username=session['user']['username']).first()
    if not me or not me.check_password(current):
        flash('Current password is incorrect.', 'error')
        return redirect(next_url)
    if password != confirm:
        flash('New passwords do not match.', 'error')
        return redirect(next_url)
    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
        return redirect(next_url)

    me.set_password(password)
    db.session.commit()
    session.pop('user', None)
    flash('Password changed. Please log in again.', 'success')
    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------

@admin_bp.route('/settings/api-keys')
@login_required
def api_keys_list():
    keys = ApiKey.query.order_by(ApiKey.created_at.desc()).all()
    return render_template('api_keys.html', keys=keys)


@admin_bp.route('/settings/api-keys/create', methods=['POST'])
@login_required
def api_key_create():
    name  = flask_request.form.get('name', '').strip()
    scope = flask_request.form.get('scope', 'webhook')
    if not name:
        flash('A name is required.', 'error')
        return redirect(url_for('admin.api_keys_list'))

    key_obj, raw_key = ApiKey.create(
        name=name,
        scope=scope,
        created_by=session.get('user', {}).get('username'),
    )
    db.session.add(key_obj)
    db.session.commit()
    flash(f'API key "{name}" created. Copy it now — it will not be shown again: {raw_key}', 'success')
    return redirect(url_for('admin.api_keys_list'))


@admin_bp.route('/settings/api-keys/<int:key_id>/revoke', methods=['POST'])
@login_required
def api_key_revoke(key_id):
    key = ApiKey.query.get_or_404(key_id)
    key.is_active = False
    db.session.commit()
    flash(f'API key "{key.name}" revoked.', 'success')
    return redirect(url_for('admin.api_keys_list'))


@admin_bp.route('/settings/api-keys/<int:key_id>/delete', methods=['POST'])
@login_required
def api_key_delete(key_id):
    key = ApiKey.query.get_or_404(key_id)
    db.session.delete(key)
    db.session.commit()
    flash(f'API key "{key.name}" deleted.', 'success')
    return redirect(url_for('admin.api_keys_list'))


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@admin_bp.route('/settings/cleanup', methods=['GET'])
@login_required
def cleanup():
    counts = {
        'pending':   Assignment.query.filter_by(status='pending').count(),
        'opened':    Assignment.query.filter_by(status='opened').count(),
        'completed': Assignment.query.filter_by(status='completed').count(),
        'expired':   Assignment.query.filter_by(status='expired').count(),
        'cancelled': Assignment.query.filter_by(status='cancelled').count(),
        'responses': QuestionnaireResponse.query.count(),
    }
    counts['assignments_total'] = sum(
        counts[s] for s in ('pending', 'opened', 'completed', 'expired', 'cancelled')
    )
    return render_template('cleanup.html', counts=counts)


@admin_bp.route('/settings/cleanup/assignments', methods=['POST'])
@login_required
def cleanup_assignments():
    status = flask_request.form.get('status', '')
    confirm = flask_request.form.get('confirm', '')
    if confirm != 'DELETE':
        flash('Type DELETE to confirm.', 'error')
        return redirect(url_for('admin.cleanup'))

    valid = ('pending', 'opened', 'completed', 'expired', 'cancelled', 'all')
    if status not in valid:
        flash('Invalid status.', 'error')
        return redirect(url_for('admin.cleanup'))

    q = Assignment.query
    if status != 'all':
        q = q.filter_by(status=status)
    deleted = q.delete(synchronize_session=False)
    db.session.commit()
    flash(f'Deleted {deleted} assignment(s).', 'success')
    return redirect(url_for('admin.cleanup'))


@admin_bp.route('/settings/cleanup/responses', methods=['POST'])
@login_required
def cleanup_responses():
    confirm = flask_request.form.get('confirm', '')
    if confirm != 'DELETE':
        flash('Type DELETE to confirm.', 'error')
        return redirect(url_for('admin.cleanup'))

    deleted = QuestionnaireResponse.query.delete(synchronize_session=False)
    db.session.commit()
    flash(f'Deleted {deleted} response(s).', 'success')
    return redirect(url_for('admin.cleanup'))
