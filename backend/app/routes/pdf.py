"""
app/routes/pdf.py

PDF management endpoints:

POST   /api/pdf/upload
GET    /api/pdf/list
GET    /api/pdf/status/<id>
DELETE /api/pdf/<id>
GET    /api/pdf/<id>/download
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
from app.models import PDF
from app.services import s3_service, rag_service

logger = logging.getLogger(__name__)
pdf_bp = Blueprint("pdf", __name__)

_ALLOWED_EXTENSIONS = {"pdf"}
_MAX_FILE_BYTES = 50 * 1024 * 1024


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _allowed(filename: str):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS
    )


def _set_status_cache(pdf_id: str, status: str):

    try:
        get_redis().setex(f"pdf:status:{pdf_id}", 3600, status)
    except Exception:
        pass


def _get_status_cache(pdf_id: str):

    try:
        val = get_redis().get(f"pdf:status:{pdf_id}")
        if val:
            return val.decode()
    except Exception:
        pass

    return None


# ─────────────────────────────────────────────
# Background processing
# ─────────────────────────────────────────────

def _process_in_background(pdf_id: str, local_path: str, app):

    with app.app_context():

        pdf = None

        try:

            pdf = db.session.get(PDF, pdf_id)

            if not pdf:
                logger.error("PDF record not found %s", pdf_id)
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

            logger.info(
                "PDF %s processed (%s pages)",
                pdf_id,
                result["page_count"],
            )

        except Exception as e:

            logger.exception("PDF processing failed")

            if pdf:
                pdf.status = "failed"
                pdf.error_message = str(e)
                db.session.commit()

            _set_status_cache(pdf_id, "failed")

        finally:

            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass


# ─────────────────────────────────────────────
# Upload PDF
# ─────────────────────────────────────────────
@pdf_bp.post("/upload")
@jwt_required()
def upload_pdf():

    user_id = get_jwt_identity()

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed(file.filename):
        return jsonify({"error": "Only PDF files allowed"}), 400

    # check file size
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    if size == 0:
        return jsonify({"error": "Empty file"}), 400

    if size > _MAX_FILE_BYTES:
        return jsonify({"error": "File too large"}), 413

    pdf_id = str(uuid.uuid4())
    original_name = secure_filename(file.filename)

    s3_key = f"pdfs/{user_id}/{pdf_id}/{original_name}"

    # ─────────────────────────────
    # SAVE FILE LOCALLY FIRST
    # ─────────────────────────────

    tmp_dir = tempfile.mkdtemp()
    local_path = os.path.join(tmp_dir, f"{pdf_id}.pdf")

    file.save(local_path)

    # ─────────────────────────────
    # UPLOAD TO S3 USING LOCAL FILE
    # ─────────────────────────────

    try:

        with open(local_path, "rb") as f:
            s3_url = s3_service.upload_pdf(f, s3_key)

    except Exception as exc:

        logger.error("S3 upload failed %s", exc)

        return jsonify({"error": str(exc)}), 500

    # ─────────────────────────────
    # SAVE DB RECORD
    # ─────────────────────────────

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

    # ─────────────────────────────
    # START RAG PROCESSING
    # ─────────────────────────────

    app = current_app._get_current_object()

    thread = threading.Thread(
        target=_process_in_background,
        args=(pdf_id, local_path, app),
        daemon=True
    )

    thread.start()

    return jsonify({

        "message": "PDF uploaded successfully. Processing started.",
        "pdf": pdf.to_dict()

    }), 201


# ─────────────────────────────────────────────
# List PDFs
# ─────────────────────────────────────────────

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

    return jsonify({

        "pdfs": [p.to_dict() for p in pdfs],
        "total": len(pdfs)

    })


# ─────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────

@pdf_bp.get("/status/<string:pdf_id>")
@jwt_required()
def get_status(pdf_id):

    user_id = get_jwt_identity()

    cached = _get_status_cache(pdf_id)

    pdf = PDF.query.filter_by(
        id=pdf_id,
        user_id=user_id
    ).first()

    if not pdf:
        return jsonify({"error": "PDF not found"}), 404

    return jsonify({

        "status": cached or pdf.status,
        "pdf": pdf.to_dict()

    })


# ─────────────────────────────────────────────
# Delete PDF
# ─────────────────────────────────────────────

@pdf_bp.delete("/<string:pdf_id>")
@jwt_required()
def delete_pdf(pdf_id):

    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(
        id=pdf_id,
        user_id=user_id
    ).first()

    if not pdf:
        return jsonify({"error": "PDF not found"}), 404

    try:
        s3_service.delete_object(pdf.s3_key)
    except Exception as e:
        logger.warning("S3 delete failed %s", e)

    if pdf.vector_store_id:

        try:
            rag_service.delete_store(pdf.vector_store_id)
        except Exception:
            pass

    try:
        get_redis().delete(f"pdf:status:{pdf_id}")
    except Exception:
        pass

    db.session.delete(pdf)
    db.session.commit()

    return jsonify({

        "message": "PDF deleted successfully"

    })


# ─────────────────────────────────────────────
# Download URL
# ─────────────────────────────────────────────

@pdf_bp.get("/<string:pdf_id>/download")
@jwt_required()
def download_url(pdf_id):

    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(
        id=pdf_id,
        user_id=user_id
    ).first()

    if not pdf:
        return jsonify({"error": "PDF not found"}), 404

    try:

        url = s3_service.get_presigned_url(
            pdf.s3_key,
            expiry_seconds=1800
        )

    except Exception as e:

        return jsonify({"error": str(e)}), 500

    return jsonify({

        "url": url,
        "expires_in": 1800

    })