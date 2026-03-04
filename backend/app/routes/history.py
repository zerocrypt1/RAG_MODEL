"""
app/routes/history.py
Chat history & statistics endpoints:
  GET /api/history/          – paginated list of chat sessions with last message
  GET /api/history/search    – full-text search across message content
  GET /api/history/stats     – aggregate counts for the current user
"""

import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from app.models import ChatSession, Message, PDF

logger = logging.getLogger(__name__)
history_bp = Blueprint("history", __name__)

_DEFAULT_PER_PAGE = 10
_MAX_PER_PAGE = 50


@history_bp.get("/")
@jwt_required()
def get_history():
    user_id = get_jwt_identity()

    # ── Pagination params ─────────────────────────────────────────────────────
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = min(
            _MAX_PER_PAGE,
            max(1, int(request.args.get("per_page", _DEFAULT_PER_PAGE))),
        )
    except (ValueError, TypeError):
        per_page = _DEFAULT_PER_PAGE

    # ── Paginated sessions ────────────────────────────────────────────────────
    pagination = (
        ChatSession.query
        .filter_by(user_id=user_id)
        .order_by(ChatSession.updated_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    items = []
    for session in pagination.items:
        pdf = PDF.query.get(session.pdf_id)

        # Last message in this session
        last_msg = (
            Message.query
            .filter_by(session_id=session.id)
            .order_by(Message.created_at.desc())
            .first()
        )

        entry = session.to_dict()
        entry["pdf_name"] = pdf.original_name if pdf else "Unknown PDF"
        entry["pdf_status"] = pdf.status if pdf else "unknown"
        entry["last_message"] = (
            (last_msg.content[:150] + "…" if len(last_msg.content) > 150 else last_msg.content)
            if last_msg else None
        )
        entry["last_message_role"] = last_msg.role if last_msg else None
        items.append(entry)

    return jsonify({
        "history": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "total_pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        },
    })


@history_bp.get("/search")
@jwt_required()
def search_history():
    user_id = get_jwt_identity()
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"results": [], "query": ""}), 200

    if len(query) > 200:
        return jsonify({"error": "Search query is too long (max 200 characters)"}), 400

    # Full-text search across message content (ILIKE for Postgres/SQLite)
    matches = (
        Message.query
        .join(ChatSession, Message.session_id == ChatSession.id)
        .filter(
            ChatSession.user_id == user_id,
            Message.content.ilike(f"%{query}%"),
        )
        .order_by(Message.created_at.desc())
        .limit(30)
        .all()
    )

    # Group by session for a cleaner response
    seen_sessions: dict[str, dict] = {}
    for msg in matches:
        sid = msg.session_id
        if sid not in seen_sessions:
            session = ChatSession.query.get(sid)
            pdf = PDF.query.get(session.pdf_id) if session else None
            seen_sessions[sid] = {
                "session_id": sid,
                "session_title": session.title if session else "Unknown",
                "pdf_name": pdf.original_name if pdf else "Unknown PDF",
                "matching_messages": [],
            }

        # Highlight the match with surrounding context
        content = msg.content
        idx = content.lower().find(query.lower())
        if idx != -1:
            start = max(0, idx - 60)
            end = min(len(content), idx + len(query) + 60)
            snippet = ("…" if start > 0 else "") + content[start:end] + ("…" if end < len(content) else "")
        else:
            snippet = content[:120] + "…"

        seen_sessions[sid]["matching_messages"].append({
            "message_id": msg.id,
            "role": msg.role,
            "snippet": snippet,
            "created_at": msg.created_at.isoformat(),
        })

    return jsonify({
        "results": list(seen_sessions.values()),
        "query": query,
        "total_matches": len(matches),
    })


@history_bp.get("/stats")
@jwt_required()
def get_stats():
    user_id = get_jwt_identity()

    total_pdfs = PDF.query.filter_by(user_id=user_id).count()
    total_sessions = ChatSession.query.filter_by(user_id=user_id).count()

    # Total messages across all sessions owned by this user
    total_messages = (
        Message.query
        .join(ChatSession, Message.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .count()
    )

    # Ready PDFs
    ready_pdfs = PDF.query.filter_by(user_id=user_id, status="ready").count()

    # PDFs by status
    status_counts_raw = (
        PDF.query
        .filter_by(user_id=user_id)
        .with_entities(PDF.status, func.count(PDF.id))
        .group_by(PDF.status)
        .all()
    )
    pdf_by_status = {row[0]: row[1] for row in status_counts_raw}

    return jsonify({
        "total_pdfs": total_pdfs,
        "ready_pdfs": ready_pdfs,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "pdf_by_status": pdf_by_status,
    })