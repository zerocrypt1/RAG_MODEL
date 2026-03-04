"""
app/routes/chat.py
RAG chat endpoints:
  POST /api/chat/session                         – create a new chat session for a PDF
  POST /api/chat/message                         – send a question, get RAG answer
  GET  /api/chat/session/<id>/messages           – load all messages in a session
  GET  /api/chat/sessions                        – list all sessions for current user
  DELETE /api/chat/session/<id>                  – delete a session and all its messages

History caching strategy
-------------------------
The last 20 messages of each session are cached in Redis (key: chat:history:<session_id>)
as a JSON array.  On every successful send-message the cache is refreshed.
On session load the DB is the source of truth; cache is written-through.
"""

import json
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app import get_redis
from app.models import PDF, ChatSession, Message
from app.services import rag_service

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)

_HISTORY_CACHE_TTL = 3_600   # 1 hour
_HISTORY_WINDOW = 20          # keep last N messages in cache


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(session_id: str) -> str:
    return f"chat:history:{session_id}"


def _read_history_cache(session_id: str) -> list | None:
    try:
        raw = get_redis().get(_cache_key(session_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _write_history_cache(session_id: str, history: list) -> None:
    try:
        get_redis().setex(
            _cache_key(session_id),
            _HISTORY_CACHE_TTL,
            json.dumps(history[-_HISTORY_WINDOW:]),
        )
    except Exception:
        pass


def _invalidate_cache(session_id: str) -> None:
    try:
        get_redis().delete(_cache_key(session_id))
    except Exception:
        pass


def _build_history_from_db(session_id: str) -> list[dict]:
    """Load all messages from DB and return as [{role, content}]."""
    messages = (
        Message.query
        .filter_by(session_id=session_id)
        .order_by(Message.created_at)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in messages]


# ── Routes ────────────────────────────────────────────────────────────────────

@chat_bp.post("/session")
@jwt_required()
def create_session():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    pdf_id = data.get("pdf_id", "").strip()

    if not pdf_id:
        return jsonify({"error": "pdf_id is required"}), 400

    # Verify the PDF belongs to the user and is ready
    pdf = PDF.query.filter_by(id=pdf_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "PDF not found"}), 404

    if pdf.status == "processing" or pdf.status == "pending":
        return jsonify({
            "error": "PDF is still being processed. Please wait a moment and try again.",
            "status": pdf.status,
        }), 400

    if pdf.status == "failed":
        return jsonify({
            "error": "PDF processing failed. Please re-upload the document.",
            "status": pdf.status,
        }), 400

    if pdf.status != "ready":
        return jsonify({"error": f"PDF status is '{pdf.status}', cannot start chat"}), 400

    # Check the vector store actually exists on disk
    if not pdf.vector_store_id or not rag_service.store_exists(pdf.vector_store_id):
        return jsonify({
            "error": "Vector store not found for this PDF. Please re-upload the document."
        }), 400

    session = ChatSession(
        user_id=user_id,
        pdf_id=pdf_id,
        title=f"Chat about {pdf.original_name}",
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        "message": "Chat session created",
        "session": session.to_dict(),
        "pdf": pdf.to_dict(),
    }), 201


@chat_bp.post("/message")
@jwt_required()
def send_message():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    session_id = data.get("session_id", "").strip()
    question = (data.get("question") or "").strip()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not question:
        return jsonify({"error": "question cannot be empty"}), 400
    if len(question) > 2_000:
        return jsonify({"error": "Question is too long (max 2000 characters)"}), 400

    # Verify session belongs to user
    session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "Chat session not found"}), 404

    # Verify PDF is still ready
    pdf = PDF.query.get(session.pdf_id)
    if not pdf or pdf.status != "ready":
        return jsonify({
            "error": "The associated PDF is no longer available or is not ready."
        }), 400

    # ── Fetch history (cache-first) ───────────────────────────────────────────
    history = _read_history_cache(session_id)
    if history is None:
        history = _build_history_from_db(session_id)
        _write_history_cache(session_id, history)

    # ── Save user message ─────────────────────────────────────────────────────
    user_msg = Message(
        session_id=session_id,
        role="user",
        content=question,
    )
    db.session.add(user_msg)
    db.session.flush()   # get the ID without full commit

    # ── RAG query ─────────────────────────────────────────────────────────────
    try:
        result = rag_service.query(
            vector_store_id=pdf.vector_store_id,
            question=question,
            chat_history=history,
        )
    except FileNotFoundError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("[Chat] RAG query failed: %s", exc)
        return jsonify({"error": "Failed to get an answer. Please try again."}), 500

    # ── Save assistant message ────────────────────────────────────────────────
    assistant_msg = Message(
        session_id=session_id,
        role="assistant",
        content=result["answer"],
        sources=result["sources"],
        latency_ms=result.get("latency_ms"),
    )
    db.session.add(assistant_msg)

    # Update session title from first question
    if session.message_count == 0:
        title = question[:80] + ("…" if len(question) > 80 else "")
        session.title = title

    db.session.commit()

    # ── Update history cache ──────────────────────────────────────────────────
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": result["answer"]})
    _write_history_cache(session_id, history)

    return jsonify({
        "answer": result["answer"],
        "sources": result["sources"],
        "latency_ms": result.get("latency_ms"),
        "user_message_id": user_msg.id,
        "assistant_message_id": assistant_msg.id,
    })


@chat_bp.get("/session/<string:session_id>/messages")
@jwt_required()
def get_messages(session_id: str):
    user_id = get_jwt_identity()

    session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "Chat session not found"}), 404

    messages = (
        Message.query
        .filter_by(session_id=session_id)
        .order_by(Message.created_at)
        .all()
    )

    pdf = PDF.query.get(session.pdf_id)

    return jsonify({
        "session": session.to_dict(),
        "pdf": pdf.to_dict() if pdf else None,
        "messages": [m.to_dict() for m in messages],
    })


@chat_bp.get("/sessions")
@jwt_required()
def get_sessions():
    user_id = get_jwt_identity()

    sessions = (
        ChatSession.query
        .filter_by(user_id=user_id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )

    result = []
    for s in sessions:
        pdf = PDF.query.get(s.pdf_id)
        d = s.to_dict()
        d["pdf_name"] = pdf.original_name if pdf else "Unknown"
        result.append(d)

    return jsonify({"sessions": result, "total": len(result)})


@chat_bp.delete("/session/<string:session_id>")
@jwt_required()
def delete_session(session_id: str):
    user_id = get_jwt_identity()

    session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "Chat session not found"}), 404

    _invalidate_cache(session_id)
    db.session.delete(session)
    db.session.commit()

    return jsonify({"message": "Chat session deleted successfully"})