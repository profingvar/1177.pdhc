#!/usr/bin/env python3
"""Bootstrap admin user from config."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app import create_app, db
from app.models.user import User

app = create_app()
with app.app_context():
    username = app.config.get('BOOTSTRAP_ADMIN_USER', 'admin')
    password = app.config.get('BOOTSTRAP_ADMIN_PASSWORD', 'change-me')

    existing = User.query.filter_by(username=username).first()
    if existing:
        print(f"User '{username}' already exists.")
    else:
        user = User(username=username, role='admin')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Admin user '{username}' created.")
