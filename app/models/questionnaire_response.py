import uuid
from datetime import datetime, timezone
from app import db


class QuestionnaireResponse(db.Model):
    __tablename__ = 'questionnaire_responses'

    id = db.Column(db.Integer, primary_key=True)
    response_guid = db.Column(db.String(36), nullable=False, unique=True,
                              default=lambda: str(uuid.uuid4()))
    form_guid = db.Column(db.String(36), nullable=False, index=True)
    form_version = db.Column(db.Integer, nullable=False)
    patient_guid = db.Column(db.String(36), nullable=False, index=True)
    assignment_guid = db.Column(db.String(36), nullable=True, index=True)
    fhir_json = db.Column(db.JSON, nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'response_guid': self.response_guid,
            'form_guid': self.form_guid,
            'form_version': self.form_version,
            'patient_guid': self.patient_guid,
            'assignment_guid': self.assignment_guid,
            'fhir_json': self.fhir_json,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
        }
