"""
app/routes/file.py

File management endpoints

POST   /api/file/upload
GET    /api/file/list
GET    /api/file/status/<id>
DELETE /api/file/<id>
GET    /api/file/<id>/download
"""

import os
import uuid
import tempfile
import threading
import logging

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from app import db, get_redis
from app.models import PDF
from app.services import s3_service, rag_service
from app.services.memory_rag_service import invalidate_cache as invalidate_memory_cache

logger = logging.getLogger(__name__)

file_bp = Blueprint("file", __name__)
pdf_bp = file_bp   # backward compatibility

# ------------------------------------------------
# CONFIG
# ------------------------------------------------

_ALLOWED_EXTENSIONS = {
    "pdf",
    "png","jpg","jpeg","webp","bmp","tiff",
    "doc","docx",
    "xls","xlsx",
    "csv",
    "txt",
}

_MAX_FILE_BYTES = 50 * 1024 * 1024


# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def _allowed(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".",1)[-1].lower()
    return ext in _ALLOWED_EXTENSIONS


def _set_status(file_id: str, status: str):
    try:
        get_redis().setex(f"pdf:status:{file_id}",3600,status)
    except Exception:
        pass


def _get_status(file_id: str):
    try:
        v = get_redis().get(f"pdf:status:{file_id}")
        return v.decode() if v else None
    except Exception:
        return None


# ------------------------------------------------
# BACKGROUND PROCESS
# ------------------------------------------------

def _process_in_background(file_id: str, local_path: str, app):

    with app.app_context():

        pdf = None

        try:

            pdf = db.session.get(PDF,file_id)

            if not pdf:
                logger.error("[File] DB record missing")
                return

            pdf.status = "processing"
            db.session.commit()

            _set_status(file_id,"processing")

            # ------------------------------
            # RAG INGESTION
            # ------------------------------
            result = rag_service.process_file(local_path,file_id)

            pdf.status          = "ready"
            pdf.page_count      = result["page_count"]
            pdf.chunk_count     = result["chunk_count"]
            pdf.vector_store_id = result["vector_store_id"]

            from datetime import datetime
            pdf.processed_at = datetime.utcnow()

            db.session.commit()

            _set_status(file_id,"ready")

            # IMPORTANT
            invalidate_memory_cache()

            logger.info("[File] processed %s pages=%s",file_id,result["page_count"])

        except Exception as e:

            logger.exception("[File] processing failed")

            if pdf:
                pdf.status = "failed"
                pdf.error_message = str(e)[:500]
                db.session.commit()

            _set_status(file_id,"failed")

        finally:

            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass


# ------------------------------------------------
# UPLOAD
# ------------------------------------------------

@file_bp.post("/upload")
@jwt_required()
def upload_file():

    user_id = get_jwt_identity()

    if "file" not in request.files:
        return jsonify({"error":"No file uploaded"}),400

    f = request.files["file"]

    filename = f.filename or ""

    if not filename:
        return jsonify({"error":"No file selected"}),400

    if not _allowed(filename):
        return jsonify({"error":"Unsupported file type"}),400

    # check size
    f.seek(0,os.SEEK_END)
    size = f.tell()
    f.seek(0)

    if size == 0:
        return jsonify({"error":"Empty file"}),400

    if size > _MAX_FILE_BYTES:
        return jsonify({"error":"File too large"}),413

    ext = filename.rsplit(".",1)[-1].lower()

    file_id = str(uuid.uuid4())

    safe_name = secure_filename(filename)

    local_name = f"{file_id}.{ext}"

    s3_key = f"files/{user_id}/{file_id}/{safe_name}"

    tmp_dir = tempfile.mkdtemp()

    local_path = os.path.join(tmp_dir,local_name)

    f.save(local_path)

    # ------------------------------
    # S3 upload
    # ------------------------------

    try:

        with open(local_path,"rb") as fh:
            s3_url = s3_service.upload_pdf(fh,s3_key)

    except Exception as e:

        logger.error("[File] S3 upload failed")

        return jsonify({"error":str(e)}),500


    pdf = PDF(
        id=file_id,
        user_id=user_id,
        original_name=safe_name,
        filename=local_name,
        file_size=size,
        file_type=f.mimetype or f"application/{ext}",
        s3_key=s3_key,
        s3_url=s3_url,
        status="pending"
    )

    db.session.add(pdf)
    db.session.commit()

    _set_status(file_id,"pending")

    app = current_app._get_current_object()

    threading.Thread(
        target=_process_in_background,
        args=(file_id,local_path,app),
        daemon=True
    ).start()

    return jsonify({
        "message":"File uploaded. Processing started.",
        "file":pdf.to_dict()
    }),201


# ------------------------------------------------
# LIST FILES
# ------------------------------------------------

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
        "files":[f.to_dict() for f in files],
        "total":len(files)
    })


# ------------------------------------------------
# STATUS
# ------------------------------------------------

@file_bp.get("/status/<string:file_id>")
@jwt_required()
def get_status(file_id):

    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=file_id,user_id=user_id).first()

    if not pdf:
        return jsonify({"error":"File not found"}),404

    cached = _get_status(file_id)

    return jsonify({
        "status":cached or pdf.status,
        "file":pdf.to_dict()
    })


# ------------------------------------------------
# DELETE
# ------------------------------------------------

@file_bp.delete("/<string:file_id>")
@jwt_required()
def delete_file(file_id):

    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=file_id,user_id=user_id).first()

    if not pdf:
        return jsonify({"error":"File not found"}),404

    try:
        s3_service.delete_object(pdf.s3_key)
    except Exception:
        pass

    if pdf.vector_store_id:
        try:
            rag_service.delete_store(pdf.vector_store_id)
        except Exception:
            pass

    try:
        get_redis().delete(f"pdf:status:{file_id}")
    except Exception:
        pass

    invalidate_memory_cache()

    db.session.delete(pdf)
    db.session.commit()

    return jsonify({"message":"File deleted"})


# ------------------------------------------------
# DOWNLOAD
# ------------------------------------------------

@file_bp.get("/<string:file_id>/download")
@jwt_required()
def download_url(file_id):

    user_id = get_jwt_identity()

    pdf = PDF.query.filter_by(id=file_id,user_id=user_id).first()

    if not pdf:
        return jsonify({"error":"File not found"}),404

    try:
        url = s3_service.get_presigned_url(pdf.s3_key,expiry_seconds=1800)
    except Exception as e:
        return jsonify({"error":str(e)}),500

    return jsonify({
        "url":url,
        "expires_in":1800
    })