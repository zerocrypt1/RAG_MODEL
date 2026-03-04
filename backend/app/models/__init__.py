"""
app/models/__init__.py
All SQLAlchemy ORM models.

Changes from original (all additive — no existing columns removed/renamed):
  PDF model:
    + file_type      (String 100, nullable)  — mime type e.g. "image/png", "application/pdf"
    + language       (String 10,  nullable)  — detected language of last interaction

  Message model:
    + language       (String 10,  nullable)  — detected language of this message
    + mode           (String 20,  nullable)  — "document" | "web" | "memory" | "chat"
    + input_type     (String 10,  nullable)  — "text" | "voice"

  to_dict() on both models updated to include new fields.
  Everything else is identical to the original.
"""

import uuid
from datetime import datetime

from app import db


# ── Helper ───────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


# ── User ─────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)

    # password_hash is NULL for Google-only accounts
    password_hash = db.Column(db.String(256), nullable=True)

    name = db.Column(db.String(100), nullable=False)
    avatar_url = db.Column(db.String(500), nullable=True)

    # Google OAuth
    google_id = db.Column(db.String(100), unique=True, nullable=True, index=True)

    # Email verification
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_token = db.Column(db.String(128), nullable=True, index=True)

    # Password reset
    reset_token = db.Column(db.String(128), nullable=True, index=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    pdfs = db.relationship(
        "PDF", back_populates="owner", lazy="dynamic", cascade="all, delete-orphan"
    )
    chat_sessions = db.relationship(
        "ChatSession", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "is_verified": self.is_verified,
            "has_password": self.password_hash is not None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<User {self.email}>"


# ── PDF ───────────────────────────────────────────────────────────────────────
# NOTE: Still named "PDF" and table "pdfs" — no renaming so existing data
#       and foreign keys are untouched. New columns are all nullable so
#       existing rows are unaffected.

class PDF(db.Model):
    __tablename__ = "pdfs"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # File metadata — ORIGINAL columns (unchanged)
    original_name = db.Column(db.String(255), nullable=False)
    filename      = db.Column(db.String(255), nullable=False)
    file_size     = db.Column(db.BigInteger,  nullable=True)
    page_count    = db.Column(db.Integer,     nullable=True)

    # ── NEW: mime type so the UI can show the right icon ─────────────────────
    # e.g. "application/pdf", "image/png", "application/vnd.openxmlformats..."
    # Defaults to "application/pdf" to keep old rows consistent.
    file_type = db.Column(db.String(100), nullable=True, default="application/pdf")

    # AWS S3 — ORIGINAL columns (unchanged)
    s3_key = db.Column(db.String(500),  nullable=False)
    s3_url = db.Column(db.String(1000), nullable=False)

    # Processing status: pending | processing | ready | failed — ORIGINAL (unchanged)
    status        = db.Column(db.String(20), default="pending", nullable=False, index=True)
    error_message = db.Column(db.Text, nullable=True)

    # FAISS vector store — ORIGINAL columns (unchanged)
    vector_store_id = db.Column(db.String(36), nullable=True)
    chunk_count     = db.Column(db.Integer,    nullable=True)

    # Timestamps — ORIGINAL (unchanged)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)

    # Relationships — ORIGINAL (unchanged)
    owner = db.relationship("User", back_populates="pdfs")
    chat_sessions = db.relationship(
        "ChatSession", back_populates="pdf", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            # ── original fields ────────────────────────────────────────────
            "id":               self.id,
            "original_name":    self.original_name,
            "filename":         self.filename,
            "file_size":        self.file_size,
            "page_count":       self.page_count,
            "status":           self.status,
            "error_message":    self.error_message,
            "chunk_count":      self.chunk_count,
            "s3_url":           self.s3_url,
            "created_at":       self.created_at.isoformat(),
            "processed_at":     self.processed_at.isoformat() if self.processed_at else None,
            # ── new fields ─────────────────────────────────────────────────
            "file_type":        self.file_type or "application/pdf",
        }

    def __repr__(self) -> str:
        return f"<PDF {self.original_name} [{self.status}]>"


# ── ChatSession ───────────────────────────────────────────────────────────────

class ChatSession(db.Model):
    __tablename__ = "chat_sessions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pdf_id = db.Column(
        db.String(36), db.ForeignKey("pdfs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    user = db.relationship("User", back_populates="chat_sessions")
    pdf  = db.relationship("PDF",  back_populates="chat_sessions")
    messages = db.relationship(
        "Message", back_populates="session", lazy="dynamic", cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    @property
    def message_count(self) -> int:
        return self.messages.count()

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "pdf_id":        self.pdf_id,
            "title":         self.title or "Untitled Chat",
            "message_count": self.message_count,
            "created_at":    self.created_at.isoformat(),
            "updated_at":    self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<ChatSession {self.id}>"


# ── Message ────────────────────────────────────────────────────────────────────

class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    session_id = db.Column(
        db.String(36), db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # "user" or "assistant" — ORIGINAL (unchanged)
    role    = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text,       nullable=False)

    # JSON list of source dicts — ORIGINAL (unchanged)
    sources = db.Column(db.JSON, nullable=True)

    # LLM latency — ORIGINAL (unchanged)
    latency_ms = db.Column(db.Integer, nullable=True)

    # ── NEW: metadata about how/why this message was generated ───────────────
    # Detected language: "english" | "hindi" | "hinglish"
    language   = db.Column(db.String(10), nullable=True)

    # Which mode produced the answer: "document" | "web" | "memory" | "chat"
    mode       = db.Column(db.String(20), nullable=True)

    # How the user sent the message: "text" | "voice"
    input_type = db.Column(db.String(10), nullable=True, default="text")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = db.relationship("ChatSession", back_populates="messages")

    def to_dict(self) -> dict:
        return {
            # ── original fields ────────────────────────────────────────────
            "id":         self.id,
            "session_id": self.session_id,
            "role":       self.role,
            "content":    self.content,
            "sources":    self.sources or [],
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat(),
            # ── new fields ─────────────────────────────────────────────────
            "language":   self.language,
            "mode":       self.mode,
            "input_type": self.input_type or "text",
        }

    def __repr__(self) -> str:
        return f"<Message [{self.role}] in session {self.session_id}>"