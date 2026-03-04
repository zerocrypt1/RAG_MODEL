"""
app/routes/auth.py
Authentication endpoints:
  POST /api/auth/register        – email + password sign-up
  POST /api/auth/verify-email    – click-link email verification
  POST /api/auth/login           – email + password login
  POST /api/auth/google          – Google OAuth (access-token flow)
  POST /api/auth/forgot-password – request password-reset email
  POST /api/auth/reset-password  – set new password via token
  GET  /api/auth/me              – return current user (JWT required)
  POST /api/auth/logout          – invalidate server-side session
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


# ── Internal helpers ──────────────────────────────────────────────────────────

def _send_email(subject: str, recipients: list[str], html_body: str) -> bool:
    """Send an email, return True on success, False on failure."""
    try:
        msg = MailMessage(subject=subject, recipients=recipients, html=html_body)
        mail.send(msg)
        return True
    except Exception as exc:
        logger.error("Email send error: %s", exc)
        return False


def _verification_html(name: str, link: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f4f8; margin: 0; padding: 32px; }}
        .card {{ background: #fff; max-width: 520px; margin: 0 auto; border-radius: 12px;
                 padding: 40px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
        h2 {{ color: #6366f1; margin-bottom: 8px; }}
        p  {{ color: #444; line-height: 1.6; }}
        .btn {{ display: inline-block; background: linear-gradient(135deg,#6366f1,#8b5cf6);
                color: #fff; padding: 13px 28px; border-radius: 8px;
                text-decoration: none; font-weight: 700; margin: 20px 0; }}
        small {{ color: #999; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2>📄 RAG PDF — Verify your email</h2>
        <p>Hi <strong>{name}</strong>,</p>
        <p>Thanks for signing up! Click the button below to verify your email address.</p>
        <a href="{link}" class="btn">Verify Email Address</a>
        <p><small>This link expires in 24 hours. If you didn't create an account, you can ignore this email.</small></p>
      </div>
    </body>
    </html>
    """


def _reset_html(name: str, link: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f4f8; margin: 0; padding: 32px; }}
        .card {{ background: #fff; max-width: 520px; margin: 0 auto; border-radius: 12px;
                 padding: 40px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
        h2 {{ color: #6366f1; margin-bottom: 8px; }}
        p  {{ color: #444; line-height: 1.6; }}
        .btn {{ display: inline-block; background: linear-gradient(135deg,#6366f1,#8b5cf6);
                color: #fff; padding: 13px 28px; border-radius: 8px;
                text-decoration: none; font-weight: 700; margin: 20px 0; }}
        small {{ color: #999; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2>🔑 Password Reset Request</h2>
        <p>Hi <strong>{name}</strong>,</p>
        <p>We received a request to reset your password. Click the button below — this link expires in 1 hour.</p>
        <a href="{link}" class="btn">Reset My Password</a>
        <p><small>If you did not request a password reset, you can safely ignore this email.</small></p>
      </div>
    </body>
    </html>
    """


def _issue_token(user: User) -> str:
    """Create a JWT and cache the user session in Redis."""
    token = create_access_token(identity=user.id)
    try:
        get_redis().setex(f"session:{user.id}", 86_400, user.email)
    except Exception as exc:
        logger.warning("Redis cache write failed: %s", exc)
    return token


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    # Validation
    if not email or not password or not name:
        return jsonify({"error": "name, email and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if len(name) < 2:
        return jsonify({"error": "Name must be at least 2 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    # Create user
    verification_token = secrets.token_urlsafe(48)
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        name=name,
        verification_token=verification_token,
        is_verified=False,
    )
    db.session.add(user)
    db.session.commit()

    # Send verification email
    frontend_url = current_app.config["FRONTEND_URL"]
    verify_link = f"{frontend_url}/verify-email?token={verification_token}"
    _send_email(
        subject="Verify your RAG PDF account",
        recipients=[email],
        html_body=_verification_html(name, verify_link),
    )

    logger.info("New user registered: %s", email)
    return jsonify({
        "message": "Registration successful. Please check your email to verify your account.",
        "user_id": user.id,
    }), 201


@auth_bp.post("/verify-email")
def verify_email():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()

    if not token:
        return jsonify({"error": "Verification token is required"}), 400

    user = User.query.filter_by(verification_token=token).first()
    if not user:
        return jsonify({"error": "Invalid or expired verification token"}), 400

    user.is_verified = True
    user.verification_token = None
    db.session.commit()

    access_token = _issue_token(user)
    logger.info("Email verified for: %s", user.email)
    return jsonify({
        "message": "Email verified successfully. You are now logged in.",
        "token": access_token,
        "user": user.to_dict(),
    })


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=email).first()

    # Generic message to prevent user enumeration
    invalid_msg = "Invalid email or password"

    if not user:
        return jsonify({"error": invalid_msg}), 401

    if not user.password_hash:
        return jsonify({
            "error": "This account uses Google Sign-In. Please log in with Google."
        }), 401

    if not check_password_hash(user.password_hash, password):
        return jsonify({"error": invalid_msg}), 401

    if not user.is_verified:
        return jsonify({
            "error": "Please verify your email address before logging in.",
            "code": "email_not_verified",
        }), 403

    access_token = _issue_token(user)
    logger.info("User logged in: %s", email)
    return jsonify({"token": access_token, "user": user.to_dict()})


@auth_bp.post("/google")
def google_login():
    """
    Frontend sends the Google OAuth access token.
    We call the Google UserInfo endpoint to verify it and get the user profile.
    """
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token") or data.get("credential")

    if not access_token:
        return jsonify({"error": "Google access_token is required"}), 400

    # Fetch user profile from Google
    try:
        resp = http_requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return jsonify({"error": "Failed to verify Google token"}), 401

        info = resp.json()
    except Exception as exc:
        logger.error("Google userinfo error: %s", exc)
        return jsonify({"error": "Google authentication failed"}), 401

    google_id = info.get("sub")
    email = (info.get("email") or "").lower().strip()
    name = info.get("name") or email.split("@")[0]
    avatar_url = info.get("picture", "")
    email_verified = info.get("email_verified", False)

    if not google_id or not email:
        return jsonify({"error": "Could not retrieve profile from Google"}), 401

    if not email_verified:
        return jsonify({"error": "Google account email is not verified"}), 401

    # Find or create user
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            # Merge Google ID into existing email account
            user.google_id = google_id
            if not user.avatar_url:
                user.avatar_url = avatar_url
            user.is_verified = True
        else:
            # Brand-new user via Google
            user = User(
                email=email,
                name=name,
                google_id=google_id,
                avatar_url=avatar_url,
                is_verified=True,
            )
            db.session.add(user)

    db.session.commit()
    access_token_jwt = _issue_token(user)
    logger.info("Google login: %s", email)
    return jsonify({"token": access_token_jwt, "user": user.to_dict()})


@auth_bp.post("/forgot-password")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "email is required"}), 400

    # Always return the same message to prevent enumeration
    user = User.query.filter_by(email=email).first()
    if user and user.password_hash:
        reset_token = secrets.token_urlsafe(48)
        user.reset_token = reset_token
        user.reset_token_expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        db.session.commit()

        frontend_url = current_app.config["FRONTEND_URL"]
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"
        _send_email(
            subject="Reset your RAG PDF password",
            recipients=[email],
            html_body=_reset_html(user.name, reset_link),
        )
        logger.info("Password reset requested for: %s", email)

    return jsonify({
        "message": "If an account with that email exists, a reset link has been sent."
    })


@auth_bp.post("/reset-password")
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    new_password = data.get("password") or ""

    if not token or not new_password:
        return jsonify({"error": "token and password are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expiry:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    if datetime.datetime.utcnow() > user.reset_token_expiry:
        return jsonify({"error": "This reset link has expired. Please request a new one."}), 400

    user.password_hash = generate_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.session.commit()

    logger.info("Password reset for: %s", user.email)
    return jsonify({"message": "Password reset successfully. You can now log in."})


@auth_bp.get("/me")
@jwt_required()
def get_me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.to_dict()})


@auth_bp.post("/logout")
@jwt_required()
def logout():
    user_id = get_jwt_identity()
    try:
        get_redis().delete(f"session:{user_id}")
    except Exception:
        pass
    return jsonify({"message": "Logged out successfully"})