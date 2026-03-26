"""Tests for health, auth, and admin routes."""


class TestHealth:

    def test_health(self, client):
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert data['database'] == 'connected'


class TestAuth:

    def test_login_page(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200

    def test_login_success(self, db, client):
        from app.models.user import User
        user = User(username='admin', role='admin')
        user.set_password('testpass')
        db.session.add(user)
        db.session.commit()

        resp = client.post('/login', data={'username': 'admin', 'password': 'testpass'})
        assert resp.status_code == 302  # redirect to dashboard

    def test_login_failure(self, db, client):
        resp = client.post('/login', data={'username': 'bad', 'password': 'bad'})
        assert resp.status_code == 200  # stays on login page

    def test_logout(self, logged_in_client):
        resp = logged_in_client.get('/logout')
        assert resp.status_code == 302
        # Dashboard should now redirect to login
        dash = logged_in_client.get('/dashboard')
        assert dash.status_code == 302


class TestAdmin:

    def test_dashboard_requires_login(self, client):
        resp = client.get('/dashboard')
        assert resp.status_code == 302  # redirect to login

    def test_dashboard_logged_in(self, logged_in_client, db):
        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 200


class TestErrorFormat:

    def test_404_json(self, client):
        resp = client.get('/api/nonexistent')
        assert resp.status_code == 404
        data = resp.get_json()
        assert 'error' in data
        assert 'code' in data
