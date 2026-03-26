"""Tests for POST /api/webhook/inbound — ServiceRequest from request.pdhc.se."""
import copy
from app.models.assignment import Assignment


SAMPLE_QUESTIONNAIRE = {
    'resourceType': 'Questionnaire',
    'id': 'a8451918-c7fa-42e2-849a-77c79c1f374a',
    'title': 'Testing procedure',
    'status': 'draft',
    'version': '1',
    'item': [
        {
            'linkId': '16d06f0c-622a-4efc-b886-6e8df5f52dcd',
            'text': 'Hur \u00e4r din ledsm\u00e4rta?',
            'type': 'choice',
            'repeats': False,
            'required': False,
            'answerOption': [
                {'valueCoding': {'code': '43656', 'display': 'h\u00f6g', 'system': 'https://plan.pdhc.se'}},
                {'valueCoding': {'code': '656554', 'display': 'medel', 'system': 'https://plan.pdhc.se'}},
                {'valueCoding': {'code': '567768987', 'display': 'l\u00e5g', 'system': 'https://plan.pdhc.se'}},
            ],
        },
    ],
}

SAMPLE_SERVICE_REQUEST = {
    'resourceType': 'ServiceRequest',
    'id': '56e0083e-a41b-43d7-b054-3c1984937e6f',
    'status': 'draft',
    'intent': 'order',
    'priority': 'routine',
    'authoredOn': '2026-03-26T20:32:50.523595',
    'code': {'text': 'All koll'},
    'subject': {
        'display': 'Per Bergstr\u00f6m',
        'reference': 'Patient/8bb57ce2-b24c-4371-8ff9-4eb04374ecda',
    },
    'contained': [
        {
            'resourceType': 'Patient',
            'id': '8bb57ce2-b24c-4371-8ff9-4eb04374ecda',
            'birthDate': '1978-06-11',
            'gender': 'male',
            'name': [{'family': 'Bergstr\u00f6m', 'given': ['Per'], 'use': 'official'}],
        },
        {
            'resourceType': 'CarePlan',
            'id': 'careplan-56e0083e',
            'status': 'active',
            'intent': 'plan',
            'title': 'All koll',
            'subject': {'reference': 'Patient/8bb57ce2-b24c-4371-8ff9-4eb04374ecda'},
            'activity': [{
                'detail': {
                    'status': 'not-started',
                    'scheduledTiming': {'repeat': {'frequency': 1, 'period': 30.0, 'periodUnit': 'd'}},
                },
            }],
        },
        SAMPLE_QUESTIONNAIRE,
    ],
}


def _payload(**overrides):
    p = copy.deepcopy(SAMPLE_SERVICE_REQUEST)
    p.update(overrides)
    return p


class TestWebhookInbound:

    def test_requires_api_key(self, client, db):
        resp = client.post('/api/webhook/inbound', json=_payload())
        assert resp.status_code == 401

    def test_success(self, client, db, auth_headers):
        resp = client.post('/api/webhook/inbound', json=_payload(), headers=auth_headers)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['received'] is True
        assert data['assignments_created'] == 1
        assert data['patient_guid'] == '8bb57ce2-b24c-4371-8ff9-4eb04374ecda'

    def test_assignment_stored(self, client, db, auth_headers):
        client.post('/api/webhook/inbound', json=_payload(), headers=auth_headers)
        a = Assignment.query.first()
        assert a is not None
        assert a.form_guid == 'a8451918-c7fa-42e2-849a-77c79c1f374a'
        assert a.form_version == 1
        assert a.status == 'pending'
        assert a.questionnaire_fhir['item'][0]['type'] == 'choice'

    def test_multiple_questionnaires(self, client, db, auth_headers):
        payload = _payload()
        second_q = copy.deepcopy(SAMPLE_QUESTIONNAIRE)
        second_q['id'] = 'bbbb1111-2222-3333-4444-555566667777'
        second_q['version'] = '2'
        payload['contained'].append(second_q)
        resp = client.post('/api/webhook/inbound', json=payload, headers=auth_headers)
        assert resp.get_json()['assignments_created'] == 2

    def test_wrong_resource_type(self, client, db, auth_headers):
        resp = client.post('/api/webhook/inbound', json={'resourceType': 'Patient'}, headers=auth_headers)
        assert resp.status_code == 400

    def test_missing_patient(self, client, db, auth_headers):
        payload = _payload()
        payload['contained'] = [SAMPLE_QUESTIONNAIRE]
        resp = client.post('/api/webhook/inbound', json=payload, headers=auth_headers)
        assert resp.status_code == 400
        assert 'Patient' in resp.get_json()['message']

    def test_missing_questionnaire(self, client, db, auth_headers):
        payload = _payload()
        payload['contained'] = [c for c in payload['contained'] if c['resourceType'] != 'Questionnaire']
        resp = client.post('/api/webhook/inbound', json=payload, headers=auth_headers)
        assert resp.status_code == 400
        assert 'Questionnaire' in resp.get_json()['message']

    def test_no_json(self, client, db, auth_headers):
        resp = client.post('/api/webhook/inbound', data='bad', content_type='text/plain', headers=auth_headers)
        assert resp.status_code == 400


class TestAssignmentsAPI:

    def test_list_requires_patient(self, client, db, auth_headers):
        resp = client.get('/api/assignments', headers=auth_headers)
        assert resp.status_code == 400

    def test_list_empty(self, client, db, auth_headers):
        resp = client.get('/api/assignments?patient_guid=none', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['total'] == 0

    def test_get_not_found(self, client, db, auth_headers):
        resp = client.get('/api/assignments/00000000-0000-0000-0000-000000000000', headers=auth_headers)
        assert resp.status_code == 404

    def test_cancel(self, client, db, auth_headers):
        # Create via webhook
        client.post('/api/webhook/inbound', json=_payload(), headers=auth_headers)
        a = Assignment.query.first()

        resp = client.post(f'/api/assignments/{a.assignment_guid}/cancel', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'cancelled'

    def test_cancel_completed_fails(self, client, db, auth_headers):
        client.post('/api/webhook/inbound', json=_payload(), headers=auth_headers)
        a = Assignment.query.first()
        a.status = 'completed'
        db.session.commit()

        resp = client.post(f'/api/assignments/{a.assignment_guid}/cancel', headers=auth_headers)
        assert resp.status_code == 409

    def test_queryable_after_webhook(self, client, db, auth_headers):
        client.post('/api/webhook/inbound', json=_payload(), headers=auth_headers)
        resp = client.get(
            '/api/assignments?patient_guid=8bb57ce2-b24c-4371-8ff9-4eb04374ecda',
            headers=auth_headers,
        )
        assert resp.get_json()['total'] == 1
