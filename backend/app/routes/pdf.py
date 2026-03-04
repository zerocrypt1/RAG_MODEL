"""
app/routes/pdf.py
PDF management endpoints:
  POST   /api/pdf/upload          – upload a PDF (multipart/form-data)
  GET    /api/pdf/list            – list all PDFs for current user
  GET    /api/pdf/status/<id>     – polling endpoint for processing status
  DELETE /api/pdf/<id>            – delete PDF + S3 object + vector store
  GET    /api/pdf/<id>/download   – presigned S3 download URL

Upload flow
-----------
1. File received → validated → uploaded to AWS S3 (async-safe)
2. PDF saved to a temp file on disk
3. Background thread calls rag_service.process_pdf()
4. PDF record updated to "ready" (or "failed") when done
5. Frontend polls /status/<id> every 3 s
"""

import os
import threading
import tempfile
import logging
import uuid

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from app import db
from app import get_redis
from app.models import PDF, User
from app.services import s3_service, rag_service

logger = logging.getLogger(__name__)
pdf_bp = Blueprint("pdf", __name__)

_ALLOWED_EXTENSIONS = {"pdf"}
_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


# ── Helpers ───────────────────────────────────────────────────────────────────

def _allowed(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS
    )


def _set_status_cache(pdf_id: str, status: str) -> None:
    try:
        get_redis().setex(f"pdf:status:{pdf_id}", 3_600, status)
    except Exception:
        pass


def _get_status_cache(pdf_id: str) -> str | None:
    try:
        return get_redis().get(f"pdf:status:{pdf_id}")
    except Exception:
        return None


# ── Background processing ─────────────────────────────────────────────────────

def _process_in_background(pdf_id: str, local_path: str, app) -> None:
    """
    Called in a daemon thread.
    Runs rag_service.process_pdf() and updates the DB record.
    The `app` object is passed so we can push an application context.
    """
    with app.app_context():
        pdf: PDF | None = None
        try:
            pdf = db.session.get(PDF, pdf_id)
            if not pdf:
                logger.error("[PDF] Background: record %s not found in DB", pdf_id)
                return

            pdf.status = "processing"
            db.session.commit()
            _set_status_cache(pdf_id, "processing")

            result = rag_service.process_pdf(local_path, pdf_id)

            pdf.status = "ready"
            pdf.page_count = result["page_count"]
            pdf.chunk_count = result["chunk_count"]
            pdf.vector_store_id = result["vector_store_id"]

            from datetime import datetime
            pdf.processed_at = datetime.utcnow()

            db.session.commit()
            _set_status_cache(pdf_id, "ready")
            logger.info("[PDF] %s processed: %d pages / %d chunks", pdf_id, result["page_count"], result["chunk_count"])

        except Exception as exc:
            logger.exception("[PDF] Processing failed for %s: %s", pdf_id, exc)
            if pdf:
                pdf.status = "failed"
                pdf.error_message = str(exc)
                db.session.commit()
            _set_status_cache(pdf_id, "failed")
        finally:
            if os.path.isfile(local_path):
                os.remove(local_path)
                logger.debug("[PDF] Removed temp file %s", local_path)


# ── Routes ────────────────────────────────────────────────────────────────────

@pdf_bp.post("/upload")
@jwt_required()
def upload_pdf():
    user_id = get_jwt_identity()

    # ── Validate file presence ────────────────────────────────────────────────
    if "file" not in request.files:
        return jsonify({"error": "No file field in request (expected field name: 'file')"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed(file.filename):
        return jsonify({"error": "Only PDF files are accepted (.pdf)"}), 400

    # ── Check file size ───────────────────────────────────────────────────────
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    if size == 0:
        return jsonify({"error": "Uploaded file is empty"}), 400
    if size > _MAX_FILE_BYTES:
        return jsonify({"error": f"File is too large (max {_MAX_FILE_BYTES // 1024 // 1024} MB)"}), 413

    # ── Build a unique ID and S3 key ──────────────────────────────────────────
    pdf_id = str(uuid.uuid4())
    original_name = secure_filename(file.filename)
    s3_key = f"pdfs/{user_id}/{pdf_id}/{original_name}"

    # ── Upload to S3 ──────────────────────────────────────────────────────────
    try:
        s3_url = s3_service.upload_pdf(file, s3_key)
    except Exception as exc:
        logger.error("[PDF] S3 upload failed: %s", exc)
        return jsonify({"error": f"Storage upload failed: {exc}"}), 502

    # ── Persist DB record ─────────────────────────────────────────────────────
    pdf = PDF(
        id=pdf_id,
        user_id=user_id,
        original_name=original_name,
        filename=f"{pdf_id}.pdf",
        file_size=size,
        s3_key=s3_key,
        s3_url=s3_url,
        status="pending",
    )
    db.session.add(pdf)
    db.session.commit()
    _set_status_cache(pdf_id, "pending")

    # ── Save temp copy for processing ─────────────────────────────────────────
    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, f"{pdf_id}.pdf")
    file.seek(0)
    file.save(local_path)

    # ── Kick off background processing ───────────────────────────────────────
    app = current_app._get_current_object()
    t = threading.Thread(
        target=_process_in_background,
        args=(pdf_id, local_path, app),
        daemon=True,
        name=f"rag-worker-{pdf_id[:8]}",
    )
    t.start()

    return jsonify({
        "message": "PDF uploaded successfully. Processing has started.",
        "pdf": pdf.to_dict(),
    }), 201


@pdf_bp.get("/list")
@jwt_required()
def list_pdfs():
    user_id = get_jwt_identity()
    pdfs = (
        PDF.query
        .filter_by(user_id=user_id)
        .order_by(PDF.created_at.desc())
        .all()
    )
    return jsonify({"pdfs": [p.to_dict() for p in pdfs], "total": len(pdfs)})


@pdf_bp.get("/status/<string:pdf_id>")
@jwt_required()
def get_status(pdf_id: str):
    user_id = get_jwt_identity()

    # Return from cache if available (avoids DB hit on every poll)
    cached = _get_status_cache(pdf_id)

    pdf = PDF.query.filter_by(id=pdf_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "PDF not found"}), 404

    status = cached or pdf.status
    return jsonify({"status": status, "pdf": pdf.to_dict()})


@pdf_bp.delete("/<string:pdf_id>")
@jwt_required()
def delete_pdf(pdf_id: str):
    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=pdf_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "PDF not found"}), 404

    errors: list[str] = []

    # Delete from S3
    try:
        s3_service.delete_object(pdf.s3_key)
    except Exception as exc:
        errors.append(f"S3 delete: {exc}")
        logger.warning("[PDF] S3 delete failed for %s: %s", pdf_id, exc)

    # Delete vector store
    if pdf.vector_store_id:
        try:
            rag_service.delete_store(pdf.vector_store_id)
        except Exception as exc:
            errors.append(f"Vector store delete: {exc}")
            logger.warning("[PDF] Vector store delete failed for %s: %s", pdf_id, exc)

    # Clear cache
    try:
        get_redis().delete(f"pdf:status:{pdf_id}")
    except Exception:
        pass

    # Remove from DB (cascades to chat sessions + messages)
    db.session.delete(pdf)
    db.session.commit()

    response = {"message": "PDF deleted successfully"}
    if errors:
        response["warnings"] = errors
    return jsonify(response)


@pdf_bp.get("/<string:pdf_id>/download")
@jwt_required()
def download_url(pdf_id: str):
    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=pdf_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "PDF not found"}), 404

    try:
        url = s3_service.get_presigned_url(pdf.s3_key, expiry_seconds=1_800)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"url": url, "expires_in": 1_800})