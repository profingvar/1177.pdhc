from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from app.config import Config

db = SQLAlchemy()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    CORS(app, origins=app.config.get('ALLOWED_ORIGINS', ['*']))

    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.assignments import assignments_bp
    from app.routes.webhook import webhook_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(assignments_bp, url_prefix='/api/assignments')
    app.register_blueprint(webhook_bp, url_prefix='/api/webhook')

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(error="Bad Request", message=str(e.description), code=400), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify(error="Unauthorized", message="Authentication required", code=401), 401

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="Not Found", message=str(e.description), code=404), 404

    @app.errorhandler(409)
    def conflict(e):
        return jsonify(error="Conflict", message=str(e.description), code=409), 409

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify(error="Internal Server Error", message="An unexpected error occurred", code=500), 500

    return app
