"""
app/__init__.py
Flask application factory
"""

import os
import redis as redis_lib
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_cors import CORS
from flask_migrate import Migrate
from dotenv import load_dotenv

# Load env
load_dotenv()

# ─────────────────────────────────────────────
# Extensions
# ─────────────────────────────────────────────

db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()
migrate = Migrate()

_redis_client: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis not initialized")
    return _redis_client


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────

def create_app():

    app = Flask(__name__)

    # ─────────────────────────────────────────
    # BASIC CONFIG
    # ─────────────────────────────────────────

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "sqlite:///rag_app.db"
    )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300
    }

    # ─────────────────────────────────────────
    # JWT
    # ─────────────────────────────────────────

    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "jwt-secret")

    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 86400
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 2592000

    app.config["JWT_TOKEN_LOCATION"] = ["headers"]
    app.config["JWT_HEADER_NAME"] = "Authorization"
    app.config["JWT_HEADER_TYPE"] = "Bearer"

    # ─────────────────────────────────────────
    # MAIL
    # ─────────────────────────────────────────

    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

    # ─────────────────────────────────────────
    # AWS
    # ─────────────────────────────────────────

    app.config["AWS_ACCESS_KEY_ID"] = os.getenv("AWS_ACCESS_KEY_ID", "")
    app.config["AWS_SECRET_ACCESS_KEY"] = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    app.config["AWS_S3_BUCKET"] = os.getenv("AWS_S3_BUCKET", "rag-pdf-bucket")
    app.config["AWS_REGION"] = os.getenv("AWS_REGION", "us-east-1")

    # ─────────────────────────────────────────
    # Upload size
    # ─────────────────────────────────────────

    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

    # ─────────────────────────────────────────
    # FRONTEND
    # ─────────────────────────────────────────

    app.config["FRONTEND_URL"] = os.getenv(
        "FRONTEND_URL",
        "http://localhost:3000"
    )

    # ─────────────────────────────────────────
    # EXTENSIONS INIT
    # ─────────────────────────────────────────

    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    # ─────────────────────────────────────────
    # CORS (FIXED)
    # ─────────────────────────────────────────

    CORS(
        app,
        resources={r"/api/*": {"origins": "*"}},
        supports_credentials=True
    )

    # ─────────────────────────────────────────
    # REDIS
    # ─────────────────────────────────────────

    global _redis_client

    _redis_client = redis_lib.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        password=os.getenv("REDIS_PASSWORD"),
        db=0,
        decode_responses=True
    )

    # ─────────────────────────────────────────
    # JWT ERROR HANDLERS
    # ─────────────────────────────────────────

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return jsonify({
            "error": "Token expired"
        }), 401


    @jwt.invalid_token_loader
    def invalid_token(err):
        return jsonify({
            "error": "Invalid token"
        }), 401


    @jwt.unauthorized_loader
    def missing_token(err):
        return jsonify({
            "error": "Authorization token required"
        }), 401


    # ─────────────────────────────────────────
    # BLUEPRINTS
    # ─────────────────────────────────────────

    from app.routes.auth import auth_bp
    from app.routes.pdf import pdf_bp
    from app.routes.chat import chat_bp
    from app.routes.history import history_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(pdf_bp, url_prefix="/api/pdf")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(history_bp, url_prefix="/api/history")

    # optional modules

    try:
        from app.routes.file import file_bp
        app.register_blueprint(file_bp, url_prefix="/api/file")
    except Exception as e:
        print("file blueprint error:", e)

    try:
        from app.routes.memory import memory_bp
        app.register_blueprint(memory_bp, url_prefix="/api/memory")
    except Exception as e:
        print("memory blueprint error:", e)

    try:
        from app.routes.training import training_bp
        app.register_blueprint(training_bp, url_prefix="/api/training")
    except Exception as e:
        print("training blueprint error:", e)

    try:
        from app.routes.search import search_bp
        app.register_blueprint(search_bp, url_prefix="/api/search")
    except Exception as e:
        print("search blueprint error:", e)

    # ─────────────────────────────────────────
    # HEALTH CHECK
    # ─────────────────────────────────────────

    @app.route("/api/health")
    def health():

        redis_ok = False

        try:
            _redis_client.ping()
            redis_ok = True
        except Exception:
            pass

        return jsonify({
            "status": "ok",
            "redis": redis_ok
        })


    # ─────────────────────────────────────────
    # CREATE TABLES
    # ─────────────────────────────────────────

    with app.app_context():
        db.create_all()

    return app