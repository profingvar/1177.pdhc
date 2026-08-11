import pytest
from app import create_app, db as _db
from app.config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'
    API_KEY = 'test-api-key'
    BOOTSTRAP_ADMIN_USER = 'admin'
    BOOTSTRAP_ADMIN_PASSWORD = 'testpass'
    GATEKEEPER_URL = 'https://gatekeeper.pdhc.se'
    GATEKEEPER_TOKEN = ''


@pytest.fixture(scope='session')
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {'X-API-Key': 'test-api-key'}


@pytest.fixture
def logged_in_client(client, db):
    """Create a keyauth admin user and set the session pdhc_keyauth reads.

    1177's local User model + username/password login were removed; admin auth
    is now pdhc_keyauth (session['keyauth_user'] → KeyauthUser lookup by guid).
    """
    from pdhc_keyauth.auth import _get_models
    User, _Key, _Log, kdb = _get_models()
    user = User(username='admin', role='admin')
    kdb.session.add(user)
    kdb.session.commit()
    payload = {'guid': user.guid, 'username': user.username, 'role': user.role}
    with client.session_transaction() as sess:
        sess['keyauth_user'] = payload
    return client
