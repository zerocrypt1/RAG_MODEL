"""
app/routes/chat.py

RAG chat endpoints — v2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  POST   /api/chat/session                    – create session for a document
  POST   /api/chat/message                    – send Q, get RAG/web/memory answer
  POST   /api/chat/free                       – free chat (no document needed)
  POST   /api/chat/memory                     – query across ALL docs + chat history
  GET    /api/chat/session/<id>/messages      – load session messages
  GET    /api/chat/sessions                   – list all sessions
  DELETE /api/chat/session/<id>               – delete session

Modes supported in /api/chat/message:
  "document"  – RAG over the session's uploaded file  (default)
  "web"       – DuckDuckGo web search answer
  "memory"    – search across ALL files + chat history

History caching:
  Last 20 messages cached in Redis (chat:history:<session_id>, TTL 1h).
  DB is source of truth; cache is write-through.

After every assistant reply the session is persisted to the memory index
(./chat_history/<session_id>.json) so it becomes searchable by memory RAG.
"""

import json
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db, get_redis
from app.models import PDF, ChatSession, Message
from app.services import rag_service
from app.services.memory_rag_service import (
    query_memory,
    index_chat_session,
)

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)

_HISTORY_CACHE_TTL = 3_600
_HISTORY_WINDOW    = 20


# ─────────────────────────────────────────────
# CACHE HELPERS
# ─────────────────────────────────────────────

def _cache_key(session_id: str) -> str:
    return f"chat:history:{session_id}"


def _read_cache(session_id: str) -> list | None:
    try:
        raw = get_redis().get(_cache_key(session_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _write_cache(session_id: str, history: list) -> None:
    try:
        get_redis().setex(
            _cache_key(session_id),
            _HISTORY_CACHE_TTL,
            json.dumps(history[-_HISTORY_WINDOW:]),
        )
    except Exception:
        pass


def _del_cache(session_id: str) -> None:
    try:
        get_redis().delete(_cache_key(session_id))
    except Exception:
        pass


def _history_from_db(session_id: str) -> list[dict]:
    msgs = (
        Message.query
        .filter_by(session_id=session_id)
        .order_by(Message.created_at)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in msgs]


# ─────────────────────────────────────────────
# PERSIST SESSION → MEMORY INDEX
# ─────────────────────────────────────────────

def _sync_to_memory(session: ChatSession, history: list) -> None:
    """
    Write this chat session to disk so memory_rag_service can search it.
    Runs inline (fast, just JSON write) — no thread needed.
    """
    try:
        index_chat_session(
            session_id=str(session.id),
            title=session.title or "Chat",
            messages=history,
        )
    except Exception as e:
        logger.warning("[Chat] Memory sync failed: %s", e)


# ─────────────────────────────────────────────
# CREATE SESSION
# ─────────────────────────────────────────────

@chat_bp.post("/session")
@jwt_required()
def create_session():
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    # Support both pdf_id and file_id
    file_id = (data.get("file_id") or data.get("pdf_id") or "").strip()
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    pdf = PDF.query.filter_by(id=file_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "File not found"}), 404

    if pdf.status in ("processing", "pending"):
        return jsonify({
            "error": "File is still being processed. Please wait.",
            "status": pdf.status,
        }), 400

    if pdf.status == "failed":
        return jsonify({
            "error": "File processing failed. Please re-upload.",
            "status": pdf.status,
        }), 400

    if pdf.status != "ready":
        return jsonify({"error": f"File status is '{pdf.status}', cannot chat"}), 400

    if not pdf.vector_store_id or not rag_service.store_exists(pdf.vector_store_id):
        return jsonify({"error": "Vector store missing. Please re-upload the file."}), 400

    session = ChatSession(
        user_id=user_id,
        pdf_id=file_id,
        title=f"Chat about {pdf.original_name}",
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        "message": "Chat session created",
        "session": session.to_dict(),
        "pdf":     pdf.to_dict(),
    }), 201


# ─────────────────────────────────────────────
# SEND MESSAGE  (document / web / memory modes)
# ─────────────────────────────────────────────

@chat_bp.post("/message")
@jwt_required()
def send_message():
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    session_id = (data.get("session_id") or "").strip()
    question   = (data.get("question")   or "").strip()
    mode       = (data.get("mode")       or "document").strip()   # document | web | memory
    input_type = data.get("input_type", "text")                   # text | voice

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not question:
        return jsonify({"error": "question cannot be empty"}), 400
    if len(question) > 2_000:
        return jsonify({"error": "Question too long (max 2000 chars)"}), 400
    if mode not in ("document", "web", "memory"):
        return jsonify({"error": "mode must be 'document', 'web', or 'memory'"}), 400

    # Verify session ownership
    session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "Chat session not found"}), 404

    # ── Fetch history ──────────────────────────────────────────────────────
    history = _read_cache(session_id)
    if history is None:
        history = _history_from_db(session_id)
        _write_cache(session_id, history)

    # ── Detect language ────────────────────────────────────────────────────
    lang = rag_service.detect_language(question)

    # ── Save user message ──────────────────────────────────────────────────
    user_msg = Message(
        session_id = session_id,
        role       = "user",
        content    = question,
    )
    db.session.add(user_msg)
    db.session.flush()

    # ── Route to correct service ───────────────────────────────────────────
    try:
        if mode == "memory":
            result = query_memory(question, lang=lang)

        elif mode == "web":
            from app.services.web_search_service import web_answer
            from app.services.rag_service import _llm
            result = web_answer(question, _llm(), lang)

        else:
            # document mode
            pdf = PDF.query.get(session.pdf_id)
            if not pdf or pdf.status != "ready":
                return jsonify({"error": "File is no longer available."}), 400

            result = rag_service.query(
                vector_store_id = pdf.vector_store_id,
                question        = question,
                chat_history    = history,
                mode            = "document",
            )

    except Exception as exc:
        db.session.rollback()
        logger.exception("[Chat] Query failed: %s", exc)
        return jsonify({"error": "Failed to get answer. Please try again."}), 500

    # ── Save assistant message ─────────────────────────────────────────────
    asst_msg = Message(
        session_id = session_id,
        role       = "assistant",
        content    = result["answer"],
        sources    = result.get("sources"),
        latency_ms = result.get("latency_ms"),
    )
    db.session.add(asst_msg)

    # Update session title from first question
    if session.message_count == 0:
        session.title = question[:80] + ("…" if len(question) > 80 else "")

    db.session.commit()

    # ── Update history cache ───────────────────────────────────────────────
    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": result["answer"]})
    _write_cache(session_id, history)

    # ── Sync to memory index ───────────────────────────────────────────────
    _sync_to_memory(session, history)

    return jsonify({
        "answer":               result["answer"],
        "sources":              result.get("sources", []),
        "language":             result.get("language", lang),
        "mode":                 result.get("mode", mode),
        "latency_ms":           result.get("latency_ms"),
        "user_message_id":      user_msg.id,
        "assistant_message_id": asst_msg.id,
        "message_id":           asst_msg.id,
    })


# ─────────────────────────────────────────────
# FREE CHAT  (no document, no session needed)
# ─────────────────────────────────────────────

@chat_bp.post("/free")
@jwt_required()
def free_chat():
    """
    Pure conversational AI — no document attached.
    Hindi / Hinglish / English auto-detected.
    History is passed in the request body (stateless from server's view).
    """
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    question   = (data.get("question") or "").strip()
    history    = data.get("history", [])      # [{role, content}, ...]
    input_type = data.get("input_type", "text")

    if not question:
        return jsonify({"error": "question cannot be empty"}), 400
    if len(question) > 2_000:
        return jsonify({"error": "Question too long (max 2000 chars)"}), 400

    lang = rag_service.detect_language(question)

    try:
        result = rag_service.query(
            vector_store_id = "",           # ignored in chat mode
            question        = question,
            chat_history    = history,
            mode            = "chat",
        )
    except Exception as exc:
        logger.exception("[FreeChat] Failed: %s", exc)
        return jsonify({"error": "Failed to get answer. Please try again."}), 500

    return jsonify({
        "answer":     result["answer"],
        "sources":    [],
        "language":   result.get("language", lang),
        "mode":       "chat",
        "latency_ms": result.get("latency_ms"),
    })


# ─────────────────────────────────────────────
# MEMORY QUERY  (dedicated endpoint)
# ─────────────────────────────────────────────

@chat_bp.post("/memory")
@jwt_required()
def memory_query():
    """
    Search across ALL uploaded documents + ALL past chat sessions.
    No specific session or document needed.
    """
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question cannot be empty"}), 400

    lang = rag_service.detect_language(question)

    try:
        result = query_memory(question, lang=lang)
    except Exception as exc:
        logger.exception("[Memory] Query failed: %s", exc)
        return jsonify({"error": "Memory search failed. Please try again."}), 500

    return jsonify({
        "answer":     result["answer"],
        "sources":    result.get("sources", []),
        "language":   result.get("language", lang),
        "mode":       "memory",
        "latency_ms": result.get("latency_ms"),
    })


# ─────────────────────────────────────────────
# GET MESSAGES
# ─────────────────────────────────────────────

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
        "session":  session.to_dict(),
        "pdf":      pdf.to_dict() if pdf else None,
        "messages": [m.to_dict() for m in messages],
    })


# ─────────────────────────────────────────────
# LIST SESSIONS
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# DELETE SESSION
# ─────────────────────────────────────────────

@chat_bp.delete("/session/<string:session_id>")
@jwt_required()
def delete_session(session_id: str):
    user_id = get_jwt_identity()

    session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not session:
        return jsonify({"error": "Chat session not found"}), 404

    _del_cache(session_id)
    db.session.delete(session)
    db.session.commit()

    return jsonify({"message": "Chat session deleted successfully"})