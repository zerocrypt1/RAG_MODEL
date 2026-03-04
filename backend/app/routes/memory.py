"""
app/routes/memory.py

Cross-document memory search endpoints:

  POST  /api/memory/query          – search ALL docs + chats, get synthesized answer
  GET   /api/memory/sources        – list everything in the memory index
  POST  /api/memory/index-session  – manually sync a chat session to memory index
  POST  /api/memory/rebuild        – force full index rebuild
"""

import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services import rag_service
from app.services.memory_rag_service import (
    query_memory,
    index_chat_session,
    list_memory_sources,
    invalidate_cache,
)

logger = logging.getLogger(__name__)
memory_bp = Blueprint("memory", __name__)


# ─────────────────────────────────────────────
# QUERY MEMORY
# ─────────────────────────────────────────────

@memory_bp.post("/query")
@jwt_required()
def query():
    """
    Ask a question that is answered by searching across every
    uploaded document AND every past chat session at once.

    Request body:
      { "question": "...", "lang": "hinglish" }   (lang is optional)

    Response:
      { "answer": "...", "sources": [...], "language": "...", "latency_ms": N }
    """
    data     = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    lang     = data.get("lang")   # optional override; auto-detected if absent

    if not question:
        return jsonify({"error": "question cannot be empty"}), 400
    if len(question) > 2_000:
        return jsonify({"error": "Question too long (max 2000 chars)"}), 400

    # Auto-detect language if not supplied
    if not lang:
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
        "latency_ms": result.get("latency_ms", 0),
    })


# ─────────────────────────────────────────────
# LIST SOURCES
# ─────────────────────────────────────────────

@memory_bp.get("/sources")
@jwt_required()
def sources():
    """
    Returns a summary of everything in the memory index:
      { "documents": [...], "chats": [...] }
    """
    try:
        data = list_memory_sources()
    except Exception as exc:
        logger.exception("[Memory] list_sources failed: %s", exc)
        return jsonify({"documents": [], "chats": []}), 200

    return jsonify(data)


# ─────────────────────────────────────────────
# INDEX SESSION (manual sync)
# ─────────────────────────────────────────────

@memory_bp.post("/index-session")
@jwt_required()
def index_session():
    """
    Manually persist a chat session into the memory index.
    The server calls this automatically after every message, but
    the client can also call it to force a sync.

    Request body:
      { "session_id": "...", "title": "...", "messages": [{role, content}, ...] }
    """
    data       = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    title      = (data.get("title")      or "Untitled").strip()
    messages   = data.get("messages", [])

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    ok = index_chat_session(session_id, title, messages)

    return jsonify({"indexed": ok, "session_id": session_id})


# ─────────────────────────────────────────────
# REBUILD INDEX
# ─────────────────────────────────────────────

@memory_bp.post("/rebuild")
@jwt_required()
def rebuild():
    """
    Force the merged memory index to fully rebuild on the next query.
    Useful after bulk uploads or imports.
    """
    invalidate_cache()
    return jsonify({"message": "Memory index will rebuild on next query."})