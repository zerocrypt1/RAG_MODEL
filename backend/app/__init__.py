"""
app/__init__.py
Flask application factory.
All extensions are created here and initialised inside create_app()
so they can be imported by routes/services without circular imports.
"""

import os
import redis as redis_lib
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_cors import CORS
from flask_migrate import Migrate
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

# ── Extension singletons (not yet bound to an app) ──────────────────────────
db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()
migrate = Migrate()

# Redis is a plain client – we store it in a module-level variable
# and expose a helper so routes can import it cleanly.
_redis_client: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    """Return the shared Redis client (raises if not initialised)."""
    if _redis_client is None:
        raise RuntimeError("Redis client has not been initialised yet.")
    return _redis_client


# ── Application factory ─────────────────────────────────────────────────────
def create_app() -> Flask:
    app = Flask(__name__)

    # ── Core config ──────────────────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///rag_app.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,          # detect stale connections
        "pool_recycle": 300,
    }

    # ── JWT config ────────────────────────────────────────────────────────────
    app.config["JWT_SECRET_KEY"] = os.environ["JWT_SECRET_KEY"]
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 86_400       # 24 h
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 2_592_000   # 30 days
    app.config["JWT_TOKEN_LOCATION"] = ["headers"]
    app.config["JWT_HEADER_NAME"] = "Authorization"
    app.config["JWT_HEADER_TYPE"] = "Bearer"

    # ── Mail config ───────────────────────────────────────────────────────────
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    app.config["MAIL_USE_SSL"] = False
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get(
        "MAIL_DEFAULT_SENDER", "noreply@ragapp.com"
    )

    # ── AWS / S3 config ───────────────────────────────────────────────────────
    app.config["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID", "")
    app.config["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    app.config["AWS_S3_BUCKET"] = os.environ.get("AWS_S3_BUCKET", "rag-pdf-bucket")
    app.config["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")

    # ── Upload limits ─────────────────────────────────────────────────────────
    app.config["MAX_CONTENT_LENGTH"] = int(
        os.environ.get("MAX_CONTENT_LENGTH", 52_428_800)
    )  # 50 MB

    # ── Misc ──────────────────────────────────────────────────────────────────
    app.config["FRONTEND_URL"] = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    # ── Initialise extensions ─────────────────────────────────────────────────
    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    # CORS – allow the React dev server and production domain
    CORS(
        app,
        origins=[app.config["FRONTEND_URL"]],
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    global _redis_client
    redis_password = os.environ.get("REDIS_PASSWORD") or None
    _redis_client = redis_lib.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        password=redis_password,
        db=0,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    # ── JWT error handlers ────────────────────────────────────────────────────
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_data):
        from flask import jsonify
        return jsonify({"error": "Token has expired", "code": "token_expired"}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        from flask import jsonify
        return jsonify({"error": "Invalid token", "code": "invalid_token"}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        from flask import jsonify
        return jsonify({"error": "Authorization token required", "code": "authorization_required"}), 401

    # ── Register blueprints ───────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.pdf import pdf_bp
    from app.routes.chat import chat_bp
    from app.routes.history import history_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(pdf_bp, url_prefix="/api/pdf")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(history_bp, url_prefix="/api/history")

    # ── Health-check endpoint ─────────────────────────────────────────────────
    @app.get("/api/health")
    def health():
        from flask import jsonify
        redis_ok = False
        try:
            _redis_client.ping()
            redis_ok = True
        except Exception:
            pass
        return jsonify({"status": "ok", "redis": redis_ok}), 200

    # ── Create DB tables (idempotent for SQLite / first run) ──────────────────
    with app.app_context():
        db.create_all()

    return app