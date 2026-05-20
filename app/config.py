import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

_app_dir = Path(__file__).resolve().parent
_env_candidates = [_app_dir / '.env', _app_dir.parent / '.env']
for _candidate in _env_candidates:
    if _candidate.exists():
        load_dotenv(_candidate)
        break
else:
    load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql+psycopg://forms_user:forms_dev_password@localhost:9037/forms_1177'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    API_KEY = os.environ.get('API_KEY', 'dev-api-key')
    ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:9036').split(',')

    # Bootstrap admin credentials
    BOOTSTRAP_ADMIN_USER = os.environ.get('BOOTSTRAP_ADMIN_USER', 'admin')
    BOOTSTRAP_ADMIN_PASSWORD = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', 'change-me-on-first-deploy')

    # Outbound: completed QuestionnaireResponses dispatched to gateway.pdhc
    GATEWAY_URL = os.environ.get('GATEWAY_URL', 'https://gateway.pdhc.se')
    GATEWAY_PROVIDER_TOKEN = os.environ.get('GATEWAY_PROVIDER_TOKEN', '')
