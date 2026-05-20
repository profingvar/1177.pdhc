"""Tests for the assignment form: open, render, submit, complete."""
import pytest
from app.models.assignment import Assignment
from app.models.questionnaire_response import QuestionnaireResponse


SAMPLE_QUESTIONNAIRE = {
    'resourceType': 'Questionnaire',
    'id': 'form-001',
    'title': 'Smärtbedömning',
    'status': 'active',
    'version': '1',
    'item': [
        {
            'linkId': 'q1',
            'text': 'Hur är din ledsmärta?',
            'type': 'choice',
            'required': True,
            'answerOption': [
                {'valueCoding': {'code': 'high', 'display': 'Hög', 'system': 'https://plan.pdhc.se'}},
                {'valueCoding': {'code': 'medium', 'display': 'Medel', 'system': 'https://plan.pdhc.se'}},
                {'valueCoding': {'code': 'low', 'display': 'Låg', 'system': 'https://plan.pdhc.se'}},
            ],
        },
        {
            'linkId': 'q2',
            'text': 'Beskriv dina symptom',
            'type': 'text',
            'required': False,
        },
        {
            'linkId': 'q3',
            'text': 'Har du feber?',
            'type': 'boolean',
            'required': False,
        },
        {
            'linkId': 'q4',
            'text': 'Ålder',
            'type': 'integer',
            'required': False,
        },
    ],
}


def _create_assignment(db, status='pending', questionnaire=None):
    a = Assignment(
        patient_guid='patient-001',
        form_guid='form-001',
        form_version=1,
        questionnaire_fhir=questionnaire or SAMPLE_QUESTIONNAIRE,
        request_guid='req-001',
        status=status,
    )
    db.session.add(a)
    db.session.commit()
    return a


class TestAssignmentDetail:

    def test_opens_pending_assignment(self, logged_in_client, db):
        a = _create_assignment(db, status='pending')
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        assert resp.status_code == 200
        assert 'Smärtbedömning' in resp.data.decode('utf-8')
        # Should have been marked opened
        db.session.refresh(a)
        assert a.status == 'opened'

    def test_renders_choice_options(self, logged_in_client, db):
        a = _create_assignment(db)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'Hög' in html
        assert 'Medel' in html
        assert 'Låg' in html

    def test_renders_text_field(self, logged_in_client, db):
        a = _create_assignment(db)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'Beskriv dina symptom' in html
        assert 'textarea' in html

    def test_renders_boolean_field(self, logged_in_client, db):
        a = _create_assignment(db)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'Har du feber?' in html
        assert 'value="true"' in html

    def test_renders_integer_field(self, logged_in_client, db):
        a = _create_assignment(db)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'type="number"' in html

    def test_404_for_unknown_guid(self, logged_in_client, db):
        resp = logged_in_client.get('/assignments/nonexistent')
        assert resp.status_code == 404

    def test_completed_shows_readonly(self, logged_in_client, db):
        a = _create_assignment(db, status='completed')
        # Create a response
        qr = QuestionnaireResponse(
            form_guid='form-001',
            form_version=1,
            patient_guid='patient-001',
            assignment_guid=a.assignment_guid,
            fhir_json={
                'resourceType': 'QuestionnaireResponse',
                'item': [
                    {'linkId': 'q1', 'text': 'Smärta', 'answer': [
                        {'valueCoding': {'code': 'high', 'display': 'Hög'}}
                    ]},
                ],
            },
        )
        db.session.add(qr)
        db.session.flush()
        a.response_guid = qr.response_guid
        db.session.commit()

        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'Completed' in html
        assert 'Hög' in html
        # No submit button
        assert 'Submit response' not in html


class TestAssignmentSubmit:

    def test_submit_choice_answer(self, logged_in_client, db):
        a = _create_assignment(db, status='opened')
        resp = logged_in_client.post(
            f'/assignments/{a.assignment_guid}/submit',
            data={'item_q1': 'medium', 'item_q2': '', 'item_q3': '', 'item_q4': ''},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db.session.refresh(a)
        assert a.status == 'completed'
        assert a.response_guid is not None

        qr = QuestionnaireResponse.query.filter_by(assignment_guid=a.assignment_guid).first()
        assert qr is not None
        assert qr.fhir_json['resourceType'] == 'QuestionnaireResponse'
        items = qr.fhir_json['item']
        assert any(
            i['linkId'] == 'q1' and i['answer'][0]['valueCoding']['code'] == 'medium'
            for i in items
        )

    def test_submit_with_text_and_boolean(self, logged_in_client, db):
        a = _create_assignment(db, status='opened')
        resp = logged_in_client.post(
            f'/assignments/{a.assignment_guid}/submit',
            data={
                'item_q1': 'low',
                'item_q2': 'Ont i knäet sedan veckan',
                'item_q3': 'true',
                'item_q4': '45',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        qr = QuestionnaireResponse.query.filter_by(assignment_guid=a.assignment_guid).first()
        items = {i['linkId']: i for i in qr.fhir_json['item']}
        assert items['q2']['answer'][0]['valueString'] == 'Ont i knäet sedan veckan'
        assert items['q3']['answer'][0]['valueBoolean'] is True
        assert items['q4']['answer'][0]['valueInteger'] == 45

    def test_submit_requires_required_field(self, logged_in_client, db):
        a = _create_assignment(db, status='opened')
        resp = logged_in_client.post(
            f'/assignments/{a.assignment_guid}/submit',
            data={'item_q1': ''},  # q1 is required
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db.session.refresh(a)
        assert a.status == 'opened'  # Not completed

    def test_submit_already_completed(self, logged_in_client, db):
        a = _create_assignment(db, status='completed')
        resp = logged_in_client.post(
            f'/assignments/{a.assignment_guid}/submit',
            data={'item_q1': 'high'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Should not create a second response
        count = QuestionnaireResponse.query.filter_by(assignment_guid=a.assignment_guid).count()
        assert count == 0

    def test_submit_cancelled_blocked(self, logged_in_client, db):
        a = _create_assignment(db, status='cancelled')
        resp = logged_in_client.post(
            f'/assignments/{a.assignment_guid}/submit',
            data={'item_q1': 'high'},
            follow_redirects=True,
        )
        db.session.refresh(a)
        assert a.status == 'cancelled'

    def test_submit_skips_optional_empty_fields(self, logged_in_client, db):
        a = _create_assignment(db, status='opened')
        resp = logged_in_client.post(
            f'/assignments/{a.assignment_guid}/submit',
            data={'item_q1': 'high', 'item_q2': '', 'item_q3': '', 'item_q4': ''},
            follow_redirects=True,
        )
        qr = QuestionnaireResponse.query.filter_by(assignment_guid=a.assignment_guid).first()
        link_ids = [i['linkId'] for i in qr.fhir_json['item']]
        assert 'q1' in link_ids
        assert 'q2' not in link_ids  # empty optional skipped


RICH_QUESTIONNAIRE = {
    'resourceType': 'Questionnaire',
    'id': 'form-002',
    'title': 'Blodtryckskontroll',
    'description': 'Daglig uppföljning av blodtryck och smärta.',
    'status': 'active',
    'version': '1',
    'item': [
        {
            'linkId': 'bp-sys',
            'text': 'Systoliskt blodtryck',
            'type': 'decimal',
            'required': True,
            'code': [{'system': 'http://loinc.org', 'code': '8480-6', 'display': 'Systolic BP'}],
            'extension': [
                {'url': 'http://hl7.org/fhir/StructureDefinition/minValue', 'valueDecimal': 60},
                {'url': 'http://hl7.org/fhir/StructureDefinition/maxValue', 'valueDecimal': 250},
                {'url': 'http://hl7.org/fhir/StructureDefinition/questionnaire-unit',
                 'valueCoding': {'display': 'mmHg'}},
            ],
        },
        {
            'linkId': 'pain',
            'text': 'Smärtskattning',
            'type': 'integer',
            'required': True,
            'extension': [
                {'url': 'http://hl7.org/fhir/StructureDefinition/minValue', 'valueInteger': 0},
                {'url': 'http://hl7.org/fhir/StructureDefinition/maxValue', 'valueInteger': 10},
                {'url': 'http://hl7.org/fhir/StructureDefinition/questionnaire-sliderStepValue',
                 'valueString': 'Ingen smärta'},
                {'url': 'http://hl7.org/fhir/StructureDefinition/maxValue',
                 'valueString': 'Värsta tänkbara'},
            ],
        },
    ],
}


class TestRichRendering:

    def test_renders_unit_suffix(self, logged_in_client, db):
        a = _create_assignment(db, questionnaire=RICH_QUESTIONNAIRE)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'mmHg' in html

    def test_renders_range_hint(self, logged_in_client, db):
        a = _create_assignment(db, questionnaire=RICH_QUESTIONNAIRE)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert '60' in html
        assert '250' in html

    def test_renders_slider_for_anchored_integer(self, logged_in_client, db):
        a = _create_assignment(db, questionnaire=RICH_QUESTIONNAIRE)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'type="range"' in html
        assert 'Ingen smärta' in html

    def test_renders_code_reference(self, logged_in_client, db):
        a = _create_assignment(db, questionnaire=RICH_QUESTIONNAIRE)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert '8480-6' in html

    def test_renders_description(self, logged_in_client, db):
        a = _create_assignment(db, questionnaire=RICH_QUESTIONNAIRE)
        resp = logged_in_client.get(f'/assignments/{a.assignment_guid}')
        html = resp.data.decode('utf-8')
        assert 'Daglig uppföljning' in html

    def test_submit_slider_value(self, logged_in_client, db):
        a = _create_assignment(db, status='opened', questionnaire=RICH_QUESTIONNAIRE)
        resp = logged_in_client.post(
            f'/assignments/{a.assignment_guid}/submit',
            data={'item_bp-sys': '120.5', 'item_pain': '7'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        qr = QuestionnaireResponse.query.filter_by(assignment_guid=a.assignment_guid).first()
        items = {i['linkId']: i for i in qr.fhir_json['item']}
        assert items['bp-sys']['answer'][0]['valueDecimal'] == 120.5
        assert items['pain']['answer'][0]['valueInteger'] == 7

    def test_extract_item_meta(self):
        from app.routes.admin import _extract_item_meta
        meta = _extract_item_meta(RICH_QUESTIONNAIRE['item'])
        assert meta['bp-sys']['unit'] == 'mmHg'
        assert meta['bp-sys']['min'] == 60
        assert meta['bp-sys']['max'] == 250
        assert meta['bp-sys']['code'] == '8480-6'
        assert meta['pain']['anchor_low'] == 'Ingen smärta'
        assert meta['pain']['anchor_high'] == 'Värsta tänkbara'


class TestAssignmentListLink:

    def test_list_links_to_detail(self, logged_in_client, db):
        a = _create_assignment(db)
        resp = logged_in_client.get('/assignments')
        assert a.assignment_guid[:12].encode() in resp.data
        assert f'/assignments/{a.assignment_guid}'.encode() in resp.data
