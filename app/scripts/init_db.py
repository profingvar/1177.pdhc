#!/usr/bin/env python3
"""Initialize database tables."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app import create_app, db

app = create_app()
with app.app_context():
    db.create_all()
    print("Database tables created.")
