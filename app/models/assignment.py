"""Assignment — inbound questionnaire assignment from request.pdhc.se."""
import uuid
from datetime import datetime, timezone
from app import db


class Assignment(db.Model):
    __tablename__ = 'assignments'

    id = db.Column(db.Integer, primary_key=True)
    assignment_guid = db.Column(
        db.String(36), nullable=False, unique=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Who: patient receiving the questionnaire
    patient_guid = db.Column(db.String(36), nullable=False, index=True)

    # What: the FHIR Questionnaire to render
    form_guid = db.Column(db.String(36), nullable=False, index=True)
    form_version = db.Column(db.Integer, nullable=False)
    questionnaire_fhir = db.Column(db.JSON, nullable=False)

    # Where from: traceability back to request.pdhc.se
    request_guid = db.Column(db.String(36), nullable=True, index=True)

    # Auth context for submitting responses back to gateway.pdhc
    grant_token = db.Column(db.String(128), nullable=True)
    contract_guid = db.Column(db.String(36), nullable=True, index=True)
    organisation_guid = db.Column(db.String(36), nullable=True, index=True)
    grant_expires_at = db.Column(db.DateTime, nullable=True)

    # Lifecycle: pending | opened | completed | expired | cancelled
    status = db.Column(db.String(20), nullable=False, default='pending')
    assigned_at = db.Column(
        db.DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Link to response once submitted
    response_guid = db.Column(db.String(36), nullable=True)

    # Archive flag
    archived = db.Column(db.Boolean, default=False, nullable=False, server_default='0')

    def to_dict(self):
        return {
            'assignment_guid': self.assignment_guid,
            'patient_guid': self.patient_guid,
            'form_guid': self.form_guid,
            'form_version': self.form_version,
            'questionnaire_fhir': self.questionnaire_fhir,
            'request_guid': self.request_guid,
            'contract_guid': self.contract_guid,
            'organisation_guid': self.organisation_guid,
            'grant_expires_at': self.grant_expires_at.isoformat() if self.grant_expires_at else None,
            'status': self.status,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'response_guid': self.response_guid,
        }

    def to_summary(self):
        return {
            'assignment_guid': self.assignment_guid,
            'patient_guid': self.patient_guid,
            'form_guid': self.form_guid,
            'form_version': self.form_version,
            'status': self.status,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
        }
