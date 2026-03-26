"""Tests for database models."""
import uuid
from app.models.assignment import Assignment
from app.models.questionnaire_response import QuestionnaireResponse
from app.models.user import User
from app.models.api_key import ApiKey


SAMPLE_Q = {'resourceType': 'Questionnaire', 'status': 'draft', 'item': []}


class TestAssignmentModel:

    def test_create(self, db):
        a = Assignment(
            patient_guid=str(uuid.uuid4()),
            form_guid=str(uuid.uuid4()),
            form_version=1,
            questionnaire_fhir=SAMPLE_Q,
        )
        db.session.add(a)
        db.session.commit()
        assert a.id is not None
        assert len(a.assignment_guid) == 36
        assert a.status == 'pending'

    def test_to_dict(self, db):
        a = Assignment(
            patient_guid='p1', form_guid='f1', form_version=1,
            questionnaire_fhir=SAMPLE_Q, request_guid='r1',
        )
        db.session.add(a)
        db.session.commit()
        d = a.to_dict()
        assert d['patient_guid'] == 'p1'
        assert d['questionnaire_fhir']['resourceType'] == 'Questionnaire'

    def test_to_summary_omits_fhir(self, db):
        a = Assignment(
            patient_guid='p1', form_guid='f1', form_version=1,
            questionnaire_fhir=SAMPLE_Q,
        )
        db.session.add(a)
        db.session.commit()
        s = a.to_summary()
        assert 'questionnaire_fhir' not in s


class TestQuestionnaireResponseModel:

    def test_create(self, db):
        resp = QuestionnaireResponse(
            form_guid=str(uuid.uuid4()), form_version=1,
            patient_guid=str(uuid.uuid4()),
            fhir_json={'resourceType': 'QuestionnaireResponse'},
        )
        db.session.add(resp)
        db.session.commit()
        assert resp.id is not None
        assert len(resp.response_guid) == 36

    def test_to_dict(self, db):
        resp = QuestionnaireResponse(
            form_guid='f1', form_version=1, patient_guid='p1',
            assignment_guid='a1',
            fhir_json={'resourceType': 'QuestionnaireResponse'},
        )
        db.session.add(resp)
        db.session.commit()
        d = resp.to_dict()
        assert d['assignment_guid'] == 'a1'


class TestUserModel:

    def test_create_and_auth(self, db):
        user = User(username='testuser', role='admin')
        user.set_password('secret')
        db.session.add(user)
        db.session.commit()
        assert user.check_password('secret')
        assert not user.check_password('wrong')


class TestApiKeyModel:

    def test_create_and_validate(self, db):
        key, raw = ApiKey.create(name='test-key', scope='webhook')
        db.session.add(key)
        db.session.commit()
        assert ApiKey.validate_key(raw) is not None

    def test_invalid_key(self, db):
        assert ApiKey.validate_key('nonexistent') is None

    def test_revoked_key(self, db):
        key, raw = ApiKey.create(name='revoked')
        key.is_active = False
        db.session.add(key)
        db.session.commit()
        assert ApiKey.validate_key(raw) is None
