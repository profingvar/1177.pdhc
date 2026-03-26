import uuid
import hashlib
from datetime import datetime, timezone
from app import db


class ApiKey(db.Model):
    __tablename__ = 'api_keys'

    id = db.Column(db.Integer, primary_key=True)
    key_hash = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    scope = db.Column(db.String(50), nullable=False, default='webhook')
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.String(255), nullable=True)

    @staticmethod
    def hash_key(raw_key):
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @staticmethod
    def generate_key():
        return str(uuid.uuid4())

    @classmethod
    def create(cls, name, scope='webhook', created_by=None, expires_at=None):
        raw_key = cls.generate_key()
        key = cls(
            key_hash=cls.hash_key(raw_key),
            name=name,
            scope=scope,
            created_by=created_by,
            expires_at=expires_at,
        )
        return key, raw_key

    @classmethod
    def validate_key(cls, raw_key):
        key_hash = cls.hash_key(raw_key)
        api_key = cls.query.filter_by(key_hash=key_hash, is_active=True).first()
        if api_key is None:
            return None
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            return None
        return api_key
