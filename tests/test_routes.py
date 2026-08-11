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
        # pdhc_keyauth login takes an api_key (not username/password).
        from pdhc_keyauth.auth import _get_models
        User, Key, _Log, kdb = _get_models()
        user = User(username='admin', role='admin')
        kdb.session.add(user)
        kdb.session.commit()
        key, raw = Key.create(user_guid=user.guid)
        kdb.session.add(key)
        kdb.session.commit()

        resp = client.post('/login', data={'api_key': raw})
        assert resp.status_code == 302  # redirect to dashboard

    def test_login_failure(self, db, client):
        resp = client.post('/login', data={'api_key': 'pdhc_not-a-real-key'})
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
