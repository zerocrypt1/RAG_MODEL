"""
app/routes/file.py

File management endpoints (PDF · Image · Word · Excel):

  POST   /api/file/upload          – upload any supported file
  GET    /api/file/list            – list all files for current user
  GET    /api/file/status/<id>     – get processing status
  DELETE /api/file/<id>            – delete file + vector store
  GET    /api/file/<id>/download   – presigned S3 download URL

Backward-compat aliases kept under /api/pdf/* as well.
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
from app.models import PDF                     # reuse existing PDF model
from app.services import s3_service, rag_service
from app.services.memory_rag_service import invalidate_cache as invalidate_memory_cache

logger = logging.getLogger(__name__)

file_bp = Blueprint("file", __name__)
pdf_bp  = file_bp   # backward-compat alias registered separately in app factory

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

_ALLOWED_EXTENSIONS = {
    "pdf",
    "png", "jpg", "jpeg", "webp", "bmp", "tiff",
    "doc", "docx",
    "xls", "xlsx",
    "csv",
    "txt",
}

_MIME_TO_EXT = {
    "application/pdf":                                                              "pdf",
    "image/png":                                                                    "png",
    "image/jpeg":                                                                   "jpg",
    "image/webp":                                                                   "webp",
    "image/bmp":                                                                    "bmp",
    "image/tiff":                                                                   "tiff",
    "application/msword":                                                           "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":     "docx",
    "application/vnd.ms-excel":                                                     "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":           "xlsx",
    "text/csv":                                                                     "csv",
    "text/plain":                                                                   "txt",
}

_MAX_FILE_BYTES = 50 * 1024 * 1024   # 50 MB

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _allowed(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in _ALLOWED_EXTENSIONS


def _ext_from_mime(mime: str) -> str:
    return _MIME_TO_EXT.get(mime, "")


def _set_status(pdf_id: str, status: str):
    try:
        get_redis().setex(f"pdf:status:{pdf_id}", 3600, status)
    except Exception:
        pass


def _get_status(pdf_id: str) -> str | None:
    try:
        val = get_redis().get(f"pdf:status:{pdf_id}")
        return val.decode() if val else None
    except Exception:
        return None


# ─────────────────────────────────────────────
# BACKGROUND PROCESSING
# ─────────────────────────────────────────────

def _process_in_background(file_id: str, local_path: str, app):
    """
    Run rag_service.process_file() in a daemon thread.
    Updates PDF record status + invalidates memory index cache.
    """
    with app.app_context():
        pdf = None
        try:
            pdf = db.session.get(PDF, file_id)
            if not pdf:
                logger.error("[File] Record not found: %s", file_id)
                return

            pdf.status = "processing"
            db.session.commit()
            _set_status(file_id, "processing")

            # ── Core ingestion ─────────────────────────────────────────────
            result = rag_service.process_file(local_path, file_id)

            pdf.status          = "ready"
            pdf.page_count      = result["page_count"]
            pdf.chunk_count     = result["chunk_count"]
            pdf.vector_store_id = result["vector_store_id"]

            from datetime import datetime
            pdf.processed_at = datetime.utcnow()
            db.session.commit()
            _set_status(file_id, "ready")

            # Invalidate memory RAG so it picks up the new doc
            invalidate_memory_cache()

            logger.info("[File] %s processed (%d pages)", file_id, result["page_count"])

        except Exception as exc:
            logger.exception("[File] Processing failed: %s", exc)
            if pdf:
                pdf.status        = "failed"
                pdf.error_message = str(exc)[:500]
                db.session.commit()
            _set_status(file_id, "failed")

        finally:
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass


# ─────────────────────────────────────────────
# UPLOAD
# ─────────────────────────────────────────────

@file_bp.post("/upload")
@jwt_required()
def upload_file():
    user_id = get_jwt_identity()

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f        = request.files["file"]
    filename = f.filename or ""

    if not filename:
        return jsonify({"error": "No file selected"}), 400

    # ── Extension check ────────────────────────────────────────────────────
    if not _allowed(filename):
        return jsonify({
            "error": "Unsupported file type. Allowed: PDF, CSV, TXT, PNG/JPG/WebP, Word (.doc/.docx), Excel (.xls/.xlsx)"
        }), 400

    # ── Size check ─────────────────────────────────────────────────────────
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)

    if size == 0:
        return jsonify({"error": "Empty file"}), 400
    if size > _MAX_FILE_BYTES:
        return jsonify({"error": "File too large (max 50 MB)"}), 413

    # ── Determine extension ────────────────────────────────────────────────
    ext = filename.rsplit(".", 1)[-1].lower()
    if not ext:
        ext = _ext_from_mime(f.mimetype or "")

    file_id       = str(uuid.uuid4())
    safe_name     = secure_filename(filename)
    local_fname   = f"{file_id}.{ext}"
    s3_key        = f"files/{user_id}/{file_id}/{safe_name}"

    # ── Save locally for processing ────────────────────────────────────────
    tmp_dir    = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, local_fname)
    f.save(local_path)

    # ── Upload to S3 ───────────────────────────────────────────────────────
    try:
        with open(local_path, "rb") as fh:
            s3_url = s3_service.upload_pdf(fh, s3_key)
    except Exception as exc:
        logger.error("[File] S3 upload failed: %s", exc)
        return jsonify({"error": str(exc)}), 500

    # ── DB record ──────────────────────────────────────────────────────────
    # Reusing the PDF model; original_name stores real filename
    pdf = PDF(
        id            = file_id,
        user_id       = user_id,
        original_name = safe_name,
        filename      = local_fname,
        file_size     = size,
        file_type     = f.mimetype or f"application/{ext}",
        s3_key        = s3_key,
        s3_url        = s3_url,
        status        = "pending",
    )
    db.session.add(pdf)
    db.session.commit()
    _set_status(file_id, "pending")

    # ── Background processing ──────────────────────────────────────────────
    app = current_app._get_current_object()
    threading.Thread(
        target=_process_in_background,
        args=(file_id, local_path, app),
        daemon=True,
    ).start()

    return jsonify({
        "message": "File uploaded. Processing started.",
        "file":    pdf.to_dict(),
        "pdf":     pdf.to_dict(),   # backward-compat
    }), 201


# ─────────────────────────────────────────────
# LIST
# ─────────────────────────────────────────────

@file_bp.get("/list")
@jwt_required()
def list_files():
    user_id = get_jwt_identity()

    files = (
        PDF.query
        .filter_by(user_id=user_id)
        .order_by(PDF.created_at.desc())
        .all()
    )

    return jsonify({
        "files": [f.to_dict() for f in files],
        "pdfs":  [f.to_dict() for f in files],   # backward-compat
        "total": len(files),
    })


# ─────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────

@file_bp.get("/status/<string:file_id>")
@jwt_required()
def get_status(file_id):
    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=file_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "File not found"}), 404

    cached = _get_status(file_id)
    return jsonify({
        "status": cached or pdf.status,
        "file":   pdf.to_dict(),
        "pdf":    pdf.to_dict(),
    })


# ─────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────

@file_bp.delete("/<string:file_id>")
@jwt_required()
def delete_file(file_id):
    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=file_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "File not found"}), 404

    # S3
    try:
        s3_service.delete_object(pdf.s3_key)
    except Exception as e:
        logger.warning("[File] S3 delete failed: %s", e)

    # Vector store
    if pdf.vector_store_id:
        try:
            rag_service.delete_store(pdf.vector_store_id)
        except Exception:
            pass

    # Redis
    try:
        get_redis().delete(f"pdf:status:{file_id}")
    except Exception:
        pass

    # Invalidate merged memory index
    invalidate_memory_cache()

    db.session.delete(pdf)
    db.session.commit()

    return jsonify({"message": "File deleted successfully"})


# ─────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────

@file_bp.get("/<string:file_id>/download")
@jwt_required()
def download_url(file_id):
    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=file_id, user_id=user_id).first()
    if not pdf:
        return jsonify({"error": "File not found"}), 404

    try:
        url = s3_service.get_presigned_url(pdf.s3_key, expiry_seconds=1800)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"url": url, "expires_in": 1800})