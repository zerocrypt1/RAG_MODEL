"""
app/routes/training.py

Self-training & dataset management endpoints:

  POST   /api/training/build-dataset      – collect all sources → JSONL dataset
  GET    /api/training/stats              – dataset stats (no rebuild)
  POST   /api/training/create-model       – create custom Ollama model
  GET    /api/training/models             – list trained models
  DELETE /api/training/models/<name>      – delete a trained model
  POST   /api/training/export-hf          – export HuggingFace-ready JSONL
  POST   /api/training/custom-qa          – add a custom Q&A pair
  GET    /api/training/custom-qa          – list all custom Q&A pairs
  DELETE /api/training/custom-qa/<idx>    – delete a custom Q&A pair by index
"""

import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.training_service import (
    build_dataset,
    get_dataset_stats,
    create_ollama_model,
    list_trained_models,
    delete_trained_model,
    export_hf_dataset,
    add_custom_qa,
    list_custom_qa,
    delete_custom_qa,
)

logger = logging.getLogger(__name__)
training_bp = Blueprint("training", __name__)


# ─────────────────────────────────────────────
# BUILD DATASET
# ─────────────────────────────────────────────

@training_bp.post("/build-dataset")
@jwt_required()
def api_build_dataset():
    """
    Scan all vector stores + chat history + custom Q&A and
    write a JSONL training dataset to ./training_data/dataset.jsonl.

    Response:
      { total, from_docs, from_chat, from_custom, built_at, dataset_file }
    """
    try:
        meta = build_dataset()
        return jsonify(meta), 200
    except Exception as exc:
        logger.exception("[Training] build_dataset failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────
# DATASET STATS
# ─────────────────────────────────────────────

@training_bp.get("/stats")
@jwt_required()
def api_stats():
    """
    Return metadata about the current dataset without rebuilding it.
    """
    try:
        return jsonify(get_dataset_stats()), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────
# CREATE OLLAMA MODEL
# ─────────────────────────────────────────────

@training_bp.post("/create-model")
@jwt_required()
def api_create_model():
    """
    Build dataset → write Modelfile → run `ollama create`.

    Request body:
      { "model_name": "my-buddy-ai", "description": "optional text" }

    Response:
      { success, model_name, modelfile_path, knowledge_chars, stdout, created_at }
    """
    data        = request.get_json(silent=True) or {}
    model_name  = (data.get("model_name")  or "").strip().lower()
    description = (data.get("description") or "").strip()

    if not model_name:
        return jsonify({"error": "model_name is required"}), 400

    # Basic sanity check — Ollama model names: lowercase alphanumeric + dash/underscore
    import re
    if not re.match(r"^[a-z0-9][a-z0-9\-_]{0,63}$", model_name):
        return jsonify({
            "error": "model_name must be lowercase alphanumeric with dashes/underscores only"
        }), 400

    try:
        result = create_ollama_model(model_name, description)
        status = 200 if result["success"] else 500
        return jsonify(result), status
    except Exception as exc:
        logger.exception("[Training] create_model failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────
# LIST / DELETE TRAINED MODELS
# ─────────────────────────────────────────────

@training_bp.get("/models")
@jwt_required()
def api_list_models():
    try:
        return jsonify({"models": list_trained_models()}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@training_bp.delete("/models/<string:model_name>")
@jwt_required()
def api_delete_model(model_name: str):
    if not model_name:
        return jsonify({"error": "model_name is required"}), 400
    try:
        result = delete_trained_model(model_name)
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────
# EXPORT HUGGINGFACE DATASET
# ─────────────────────────────────────────────

@training_bp.post("/export-hf")
@jwt_required()
def api_export_hf():
    """
    Export the dataset in HuggingFace prompt/completion + Alpaca format.
    Also returns the ready-to-run trl SFT command.
    """
    try:
        result = export_hf_dataset()
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("[Training] export_hf failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────
# CUSTOM Q&A
# ─────────────────────────────────────────────

@training_bp.post("/custom-qa")
@jwt_required()
def api_add_custom_qa():
    """
    Add a manually curated Q&A pair to the training data.

    Request body:
      { "question": "...", "answer": "...", "source": "manual" }
    """
    data     = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    answer   = (data.get("answer")   or "").strip()
    source   = (data.get("source")   or "manual").strip()

    if not question:
        return jsonify({"error": "question is required"}), 400
    if not answer:
        return jsonify({"error": "answer is required"}), 400

    try:
        result = add_custom_qa(question, answer, source)
        return jsonify(result), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@training_bp.get("/custom-qa")
@jwt_required()
def api_list_custom_qa():
    try:
        pairs = list_custom_qa()
        return jsonify({"pairs": pairs, "total": len(pairs)}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@training_bp.delete("/custom-qa/<int:idx>")
@jwt_required()
def api_delete_custom_qa(idx: int):
    try:
        result = delete_custom_qa(idx)
        if not result.get("deleted"):
            return jsonify(result), 404
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500