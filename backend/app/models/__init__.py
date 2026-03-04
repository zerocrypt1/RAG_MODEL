"""
app/models/__init__.py
All SQLAlchemy ORM models.
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

    # ── Serialisation ─────────────────────────────────────────────────────────

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

class PDF(db.Model):
    __tablename__ = "pdfs"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # File metadata
    original_name = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)   # sanitised name stored in S3
    file_size = db.Column(db.BigInteger, nullable=True)    # bytes
    page_count = db.Column(db.Integer, nullable=True)

    # AWS S3
    s3_key = db.Column(db.String(500), nullable=False)
    s3_url = db.Column(db.String(1000), nullable=False)

    # Processing status: pending | processing | ready | failed
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    error_message = db.Column(db.Text, nullable=True)

    # FAISS vector store
    vector_store_id = db.Column(db.String(36), nullable=True)
    chunk_count = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    owner = db.relationship("User", back_populates="pdfs")
    chat_sessions = db.relationship(
        "ChatSession", back_populates="pdf", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "original_name": self.original_name,
            "filename": self.filename,
            "file_size": self.file_size,
            "page_count": self.page_count,
            "status": self.status,
            "error_message": self.error_message,
            "chunk_count": self.chunk_count,
            "s3_url": self.s3_url,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
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
    pdf = db.relationship("PDF", back_populates="chat_sessions")
    messages = db.relationship(
        "Message", back_populates="session", lazy="dynamic", cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    @property
    def message_count(self) -> int:
        return self.messages.count()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pdf_id": self.pdf_id,
            "title": self.title or "Untitled Chat",
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
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

    # "user" or "assistant"
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)

    # JSON list of source dicts: [{page: int, content: str}, ...]
    sources = db.Column(db.JSON, nullable=True)

    # How long the LLM took to respond (ms) – useful for monitoring
    latency_ms = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = db.relationship("ChatSession", back_populates="messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "sources": self.sources or [],
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Message [{self.role}] in session {self.session_id}>"