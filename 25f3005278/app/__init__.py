"""Application factory and extension setup (MVC application configuration)."""
import os
from datetime import datetime

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-this-secret"),
        SQLALCHEMY_DATABASE_URI="sqlite:///emp.sqlite3",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)

    from . import models
    from .routes import admin_bp, auth_bp, examiner_bp, main_bp, student_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(examiner_bp, url_prefix="/examiner")
    app.register_blueprint(student_bp, url_prefix="/student")

    with app.app_context():
        # ORM creates the SQLite schema programmatically; no manual DB setup is needed.
        db.create_all()
        if not models.User.query.filter_by(role="admin").first():
            admin = models.User(
                name=os.environ.get("EMP_ADMIN_NAME", "Administrator"),
                email=os.environ.get("EMP_ADMIN_EMAIL", "admin@emp.local").lower(),
                password_hash=generate_password_hash(os.environ.get("EMP_ADMIN_PASSWORD", "Admin@123")),
                role="admin", approved=True, active=True,
                created_at=datetime.utcnow(),
            )
            db.session.add(admin)
            db.session.commit()
    return app
