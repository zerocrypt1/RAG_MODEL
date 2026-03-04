"""
app/routes/auth.py
Authentication endpoints
"""

import os
import secrets
import datetime
import logging

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
)

from flask_mail import Message as MailMessage
from werkzeug.security import generate_password_hash, check_password_hash
import requests as http_requests

from app import db, mail
from app import get_redis
from app.models import User

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────
# EMAIL SENDER
# ─────────────────────────────────────────────

def _send_email(subject: str, recipients: list[str], html_body: str) -> bool:
    """
    Send email safely.
    Fix: explicitly sets sender.
    """

    try:

        sender = current_app.config.get(
            "MAIL_DEFAULT_SENDER",
            os.getenv("MAIL_DEFAULT_SENDER", "noreply@ragpdf.ai")
        )

        msg = MailMessage(
            subject=subject,
            sender=sender,
            recipients=recipients,
            html=html_body
        )

        mail.send(msg)

        logger.info("Email sent to %s", recipients)

        return True

    except Exception as exc:
        logger.error("Email send error: %s", exc)
        return False


# ─────────────────────────────────────────────
# HTML TEMPLATES
# ─────────────────────────────────────────────

def _verification_html(name: str, link: str) -> str:
    return f"""
    <html>
    <body style="font-family:Arial;padding:30px;background:#f4f4f4">
        <div style="background:white;padding:40px;border-radius:10px">
            <h2>Verify your email</h2>
            <p>Hi {name},</p>
            <p>Click the button below to verify your email.</p>

            <a href="{link}"
               style="background:#6366f1;color:white;padding:12px 20px;
               border-radius:6px;text-decoration:none;font-weight:bold;">
               Verify Email
            </a>

            <p>This link expires in 24 hours.</p>
        </div>
    </body>
    </html>
    """


def _reset_html(name: str, link: str) -> str:
    return f"""
    <html>
    <body style="font-family:Arial;padding:30px;background:#f4f4f4">
        <div style="background:white;padding:40px;border-radius:10px">
            <h2>Password Reset</h2>
            <p>Hi {name},</p>
            <p>Click below to reset your password.</p>

            <a href="{link}"
               style="background:#6366f1;color:white;padding:12px 20px;
               border-radius:6px;text-decoration:none;font-weight:bold;">
               Reset Password
            </a>

            <p>This link expires in 1 hour.</p>
        </div>
    </body>
    </html>
    """


# ─────────────────────────────────────────────
# JWT TOKEN CREATION
# ─────────────────────────────────────────────

def _issue_token(user: User) -> str:

    token = create_access_token(identity=user.id)

    try:
        get_redis().setex(f"session:{user.id}", 86400, user.email)
    except Exception as exc:
        logger.warning("Redis cache write failed: %s", exc)

    return token


# ─────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────

@auth_bp.post("/register")
def register():

    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if not email or not password or not name:
        return jsonify({"error": "name, email and password are required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Account already exists"}), 409

    verification_token = secrets.token_urlsafe(48)

    user = User(
        email=email,
        name=name,
        password_hash=generate_password_hash(password),
        verification_token=verification_token,
        is_verified=False,
    )

    db.session.add(user)
    db.session.commit()

    frontend_url = current_app.config["FRONTEND_URL"]

    verify_link = f"{frontend_url}/verify-email?token={verification_token}"

    _send_email(
        subject="Verify your account",
        recipients=[email],
        html_body=_verification_html(name, verify_link),
    )

    return jsonify({
        "message": "Registration successful. Please verify your email."
    }), 201


# ─────────────────────────────────────────────
# VERIFY EMAIL
# ─────────────────────────────────────────────

@auth_bp.post("/verify-email")
def verify_email():

    data = request.get_json(silent=True) or {}
    token = data.get("token", "")

    if not token:
        return jsonify({"error": "Token required"}), 400

    user = User.query.filter_by(verification_token=token).first()

    if not user:
        return jsonify({"error": "Invalid token"}), 400

    user.is_verified = True
    user.verification_token = None

    db.session.commit()

    jwt_token = _issue_token(user)

    return jsonify({
        "token": jwt_token,
        "user": user.to_dict()
    })


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────

@auth_bp.post("/login")
def login():

    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    if not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.is_verified:
        return jsonify({"error": "Please verify your email"}), 403

    token = _issue_token(user)

    return jsonify({
        "token": token,
        "user": user.to_dict()
    })

# ─────────────────────────────────────────────
# GOOGLE LOGIN
# ─────────────────────────────────────────────

@auth_bp.route("/google", methods=["POST", "OPTIONS"])
def google_login():

    # CORS preflight support
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    data = request.get_json(silent=True) or {}

    access_token = data.get("access_token") or data.get("credential")

    if not access_token:
        return jsonify({"error": "Google access_token required"}), 400

    try:
        # Verify token with Google
        resp = http_requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

        if resp.status_code != 200:
            return jsonify({"error": "Invalid Google token"}), 401

        info = resp.json()

    except Exception as e:
        logger.error("Google auth failed: %s", e)
        return jsonify({"error": "Google authentication failed"}), 401

    google_id = info.get("sub")
    email = (info.get("email") or "").lower().strip()
    name = info.get("name") or email.split("@")[0]
    avatar = info.get("picture")

    if not google_id or not email:
        return jsonify({"error": "Invalid Google account"}), 401

    # Find user
    user = User.query.filter_by(google_id=google_id).first()

    if not user:

        # Check if email already exists
        user = User.query.filter_by(email=email).first()

        if user:
            user.google_id = google_id
            user.avatar_url = avatar
            user.is_verified = True

        else:
            user = User(
                email=email,
                name=name,
                google_id=google_id,
                avatar_url=avatar,
                is_verified=True
            )

            db.session.add(user)

    db.session.commit()

    token = _issue_token(user)

    return jsonify({
        "token": token,
        "user": user.to_dict()
    })

# ─────────────────────────────────────────────
# FORGOT PASSWORD
# ─────────────────────────────────────────────

@auth_bp.post("/forgot-password")
def forgot_password():

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    user = User.query.filter_by(email=email).first()

    if user:

        token = secrets.token_urlsafe(48)

        user.reset_token = token
        user.reset_token_expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

        db.session.commit()

        frontend_url = current_app.config["FRONTEND_URL"]

        link = f"{frontend_url}/reset-password?token={token}"

        _send_email(
            subject="Reset your password",
            recipients=[email],
            html_body=_reset_html(user.name, link),
        )

    return jsonify({
        "message": "If the email exists, a reset link has been sent."
    })


# ─────────────────────────────────────────────
# RESET PASSWORD
# ─────────────────────────────────────────────

@auth_bp.post("/reset-password")
def reset_password():

    data = request.get_json(silent=True) or {}

    token = data.get("token")
    password = data.get("password")

    user = User.query.filter_by(reset_token=token).first()

    if not user:
        return jsonify({"error": "Invalid token"}), 400

    if datetime.datetime.utcnow() > user.reset_token_expiry:
        return jsonify({"error": "Token expired"}), 400

    user.password_hash = generate_password_hash(password)

    user.reset_token = None
    user.reset_token_expiry = None

    db.session.commit()

    return jsonify({"message": "Password reset successful"})


# ─────────────────────────────────────────────
# CURRENT USER
# ─────────────────────────────────────────────

@auth_bp.get("/me")
@jwt_required()
def get_me():

    user_id = get_jwt_identity()

    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"user": user.to_dict()})


# ─────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────

@auth_bp.post("/logout")
@jwt_required()
def logout():

    user_id = get_jwt_identity()

    try:
        get_redis().delete(f"session:{user_id}")
    except Exception:
        pass

    return jsonify({"message": "Logged out"})