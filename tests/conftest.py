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
    """Create admin user and log in."""
    from app.models.user import User
    user = User(username='admin', role='admin')
    user.set_password('testpass')
    db.session.add(user)
    db.session.commit()

    client.post('/login', data={'username': 'admin', 'password': 'testpass'})
    return client
