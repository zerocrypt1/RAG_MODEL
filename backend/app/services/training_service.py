"""
app/services/training_service.py

Self-Training Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Builds a custom training dataset from:
  • Uploaded PDFs / images / Word / Excel (chunked text)
  • Chat history (Q&A pairs)
  • Manual Q&A pairs you add yourself

Then trains / adapts the model in two ways:

  1. OLLAMA MODELFILE  (fast, no GPU needed)
     Injects your knowledge into the model's system prompt
     via a custom Ollama Modelfile — zero hardware cost.

  2. HUGGINGFACE JSONL EXPORT  (full fine-tune)
     Exports a standard instruction-tuning JSONL file
     compatible with trl / LoRA / QLoRA pipelines.
     You can upload this to HuggingFace AutoTrain or run
     locally with `trl sft` on a GPU machine.

Directory layout:
  ./training_data/
    dataset.jsonl          ← HuggingFace-ready training file
    dataset_meta.json      ← stats about the dataset
    custom_qa.json         ← manually added Q&A pairs
  ./trained_models/
    <model_name>/
      Modelfile            ← Ollama custom model definition
      system_prompt.txt    ← extracted system knowledge
"""

import os
import re
import json
import shutil
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_VECTOR_STORE_DIR  = Path(os.environ.get("VECTOR_STORE_DIR",   "./vector_stores"))
_CHAT_HISTORY_DIR  = Path(os.environ.get("CHAT_HISTORY_DIR",   "./chat_history"))
_TRAINING_DATA_DIR = Path(os.environ.get("TRAINING_DATA_DIR",  "./training_data"))
_TRAINED_MODEL_DIR = Path(os.environ.get("TRAINED_MODEL_DIR",  "./trained_models"))

_BASE_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
_OLLAMA_URL        = os.environ.get("OLLAMA_URL",   "http://localhost:11434")

_DATASET_FILE     = _TRAINING_DATA_DIR / "dataset.jsonl"
_META_FILE        = _TRAINING_DATA_DIR / "dataset_meta.json"
_CUSTOM_QA_FILE   = _TRAINING_DATA_DIR / "custom_qa.json"


# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

def _ensure_dirs():
    for d in [_TRAINING_DATA_DIR, _TRAINED_MODEL_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# DATASET SOURCES
# ─────────────────────────────────────────────

def _load_document_chunks() -> list[dict]:
    """
    Pull text chunks out of every FAISS vector store.
    Returns list of {"text": str, "source": str, "type": "document"}
    """
    items = []

    if not _VECTOR_STORE_DIR.exists():
        return items

    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from langchain_community.vectorstores import FAISS

        emb = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    except ImportError:
        logger.error("[Train] langchain not installed")
        return items

    for store_dir in _VECTOR_STORE_DIR.iterdir():
        if not store_dir.is_dir():
            continue
        try:
            store    = FAISS.load_local(
                str(store_dir), emb,
                allow_dangerous_deserialization=True
            )
            raw_docs = list(store.docstore._dict.values())
            for doc in raw_docs:
                text = doc.page_content.strip()
                if len(text) > 50:   # skip tiny fragments
                    items.append({
                        "text":   text,
                        "source": store_dir.name,
                        "type":   "document",
                        "page":   doc.metadata.get("page", 0),
                    })
            logger.info("[Train] %d chunks from doc store '%s'", len(raw_docs), store_dir.name)
        except Exception as e:
            logger.warning("[Train] Skip store %s: %s", store_dir.name, e)

    return items


def _load_chat_pairs() -> list[dict]:
    """
    Load Q&A pairs from all saved chat sessions.
    Returns list of {"question": str, "answer": str, "source": str, "type": "chat"}
    """
    pairs = []

    if not _CHAT_HISTORY_DIR.exists():
        return pairs

    for fpath in _CHAT_HISTORY_DIR.glob("*.json"):
        try:
            data     = json.loads(fpath.read_text())
            session  = data.get("session_id", fpath.stem)
            messages = data.get("messages", [])

            i = 0
            while i < len(messages) - 1:
                m = messages[i]
                if m.get("role") == "user":
                    q = m["content"].strip()
                    if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                        a = messages[i + 1]["content"].strip()
                        if q and a and len(a) > 20:
                            pairs.append({
                                "question": q,
                                "answer":   a,
                                "source":   session,
                                "type":     "chat",
                            })
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1
        except Exception as e:
            logger.warning("[Train] Skip chat file %s: %s", fpath, e)

    logger.info("[Train] %d Q&A pairs from chat history", len(pairs))
    return pairs


def _load_custom_qa() -> list[dict]:
    """Load manually added Q&A pairs."""
    if not _CUSTOM_QA_FILE.exists():
        return []
    try:
        data = json.loads(_CUSTOM_QA_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ─────────────────────────────────────────────
# DATASET BUILDER
# ─────────────────────────────────────────────

def _chunk_to_instruction(chunk: dict) -> dict:
    """
    Convert a raw document chunk into an instruction-tuning example.
    Uses a simple "Explain this passage" template.
    """
    text = chunk["text"]
    src  = chunk["source"]
    return {
        "instruction": f"Based on the following text from '{src}', answer questions accurately and helpfully.",
        "input":       text[:600],
        "output":      f"This passage from '{src}' covers: {text[:300]}...",
        "source":      src,
        "type":        "document_chunk",
    }


def _qa_to_instruction(pair: dict) -> dict:
    """Convert a Q&A pair into an instruction-tuning example."""
    return {
        "instruction": pair["question"],
        "input":       "",
        "output":      pair["answer"],
        "source":      pair.get("source", "chat"),
        "type":        pair.get("type", "chat"),
    }


def build_dataset() -> dict:
    """
    Collect all sources → build JSONL dataset.
    Returns stats dict.
    """
    _ensure_dirs()
    logger.info("[Train] Building dataset…")

    examples      = []
    doc_chunks    = _load_document_chunks()
    chat_pairs    = _load_chat_pairs()
    custom_pairs  = _load_custom_qa()

    # Document chunks → instruction format
    for chunk in doc_chunks:
        examples.append(_chunk_to_instruction(chunk))

    # Chat history → instruction format
    for pair in chat_pairs:
        examples.append(_qa_to_instruction(pair))

    # Custom Q&A (highest quality — user-curated)
    for pair in custom_pairs:
        examples.append(_qa_to_instruction(pair))

    # Deduplicate by instruction text
    seen  = set()
    dedup = []
    for ex in examples:
        key = ex["instruction"][:120]
        if key not in seen:
            seen.add(key)
            dedup.append(ex)

    # Write JSONL
    with open(_DATASET_FILE, "w", encoding="utf-8") as f:
        for ex in dedup:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Write metadata
    meta = {
        "built_at":     datetime.utcnow().isoformat(),
        "total":        len(dedup),
        "from_docs":    len(doc_chunks),
        "from_chat":    len(chat_pairs),
        "from_custom":  len(custom_pairs),
        "dataset_file": str(_DATASET_FILE),
    }
    _META_FILE.write_text(json.dumps(meta, indent=2))

    logger.info("[Train] Dataset ready: %d examples", len(dedup))
    return meta


def get_dataset_stats() -> dict:
    """Return metadata about the current dataset without rebuilding it."""
    if not _META_FILE.exists():
        return {"total": 0, "built_at": None, "from_docs": 0, "from_chat": 0, "from_custom": 0}
    try:
        return json.loads(_META_FILE.read_text())
    except Exception:
        return {}


# ─────────────────────────────────────────────
# OLLAMA MODELFILE TRAINING  (Fast — no GPU)
# ─────────────────────────────────────────────

def _build_knowledge_block(max_chars: int = 12_000) -> str:
    """
    Extract the most important text from the dataset to embed
    directly into the Ollama system prompt.
    Prioritises chat Q&A (highest signal) then document chunks.
    """
    blocks   = []
    used     = 0
    examples = []

    if _DATASET_FILE.exists():
        with open(_DATASET_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    examples.append(json.loads(line))
                except Exception:
                    pass

    # Sort: chat > custom > document  (chat Q&A most useful for persona)
    priority = {"chat": 0, "custom": 0, "document_chunk": 1}
    examples.sort(key=lambda x: priority.get(x.get("type", "document_chunk"), 2))

    for ex in examples:
        if ex.get("type") in ("chat", "custom"):
            block = f"Q: {ex['instruction']}\nA: {ex['output']}"
        else:
            block = f"Context: {ex['input'][:300]}"

        if used + len(block) > max_chars:
            break

        blocks.append(block)
        used += len(block)

    return "\n\n".join(blocks)


def create_ollama_model(model_name: str, description: str = "") -> dict:
    """
    Create a custom Ollama model by writing a Modelfile that:
    1. Is based on the base Mistral model
    2. Injects a system prompt with all your knowledge
    3. Sets a friendly, human-like persona

    Then calls `ollama create` to register it locally.
    Returns {"success": bool, "model_name": str, "modelfile_path": str, ...}
    """
    import subprocess

    _ensure_dirs()

    # Build dataset first if it doesn't exist
    if not _DATASET_FILE.exists():
        build_dataset()

    knowledge = _build_knowledge_block()
    model_dir = _TRAINED_MODEL_DIR / model_name
    model_dir.mkdir(parents=True, exist_ok=True)

    # ── System prompt ──────────────────────────────────────────────────────
    system_prompt = f"""You are a smart, warm, and friendly AI assistant — like a knowledgeable best friend.

You have been trained on a custom knowledge base that includes uploaded documents, images, PDFs, and past conversation history.

PERSONALITY:
- Friendly, warm, and conversational — never robotic
- You understand Hindi, Hinglish, and English
- In Hinglish: mix English words with Hindi fillers (yaar, bhai, toh, hai, matlab)
- Give concise but complete answers
- Reference page numbers or sources when you know them
- Use light humor when appropriate

YOUR CUSTOM KNOWLEDGE BASE:
{'=' * 60}
{knowledge if knowledge else '(No documents uploaded yet — answer from general knowledge)'}
{'=' * 60}

{f'ABOUT THIS ASSISTANT: {description}' if description else ''}

When answering:
1. Check if the question relates to anything in the knowledge base above
2. If yes — use that information and cite the source
3. If no — answer from general knowledge, and say so
4. Always match the user's language (Hindi → Hindi, Hinglish → Hinglish, English → English)"""

    # ── Modelfile ──────────────────────────────────────────────────────────
    # Escape backticks in system prompt to avoid breaking the heredoc
    safe_system = system_prompt.replace('"""', "'''")

    modelfile_content = f"""FROM {_BASE_OLLAMA_MODEL}

PARAMETER temperature 0.3
PARAMETER num_ctx 4096
PARAMETER num_thread 8
PARAMETER top_k 40
PARAMETER top_p 0.9

SYSTEM \"\"\"
{safe_system}
\"\"\"
"""

    modelfile_path    = model_dir / "Modelfile"
    system_prompt_path = model_dir / "system_prompt.txt"

    modelfile_path.write_text(modelfile_content)
    system_prompt_path.write_text(system_prompt)

    logger.info("[Train] Modelfile written to %s", modelfile_path)

    # ── Run `ollama create` ────────────────────────────────────────────────
    result = subprocess.run(
        ["ollama", "create", model_name, "-f", str(modelfile_path)],
        capture_output=True, text=True, timeout=120
    )

    success = result.returncode == 0

    if success:
        logger.info("[Train] Ollama model '%s' created successfully", model_name)
    else:
        logger.error("[Train] ollama create failed:\n%s", result.stderr)

    return {
        "success":       success,
        "model_name":    model_name,
        "modelfile_path": str(modelfile_path),
        "knowledge_chars": len(knowledge),
        "stdout":        result.stdout[:500] if result.stdout else "",
        "stderr":        result.stderr[:500] if not success else "",
        "created_at":    datetime.utcnow().isoformat(),
    }


def list_trained_models() -> list[dict]:
    """List all models created by this service."""
    models = []
    if not _TRAINED_MODEL_DIR.exists():
        return models

    for d in _TRAINED_MODEL_DIR.iterdir():
        if not d.is_dir():
            continue
        mf = d / "Modelfile"
        sp = d / "system_prompt.txt"
        models.append({
            "name":          d.name,
            "modelfile":     str(mf) if mf.exists() else None,
            "has_knowledge": sp.exists(),
            "created_at":    datetime.fromtimestamp(d.stat().st_mtime).isoformat(),
        })

    return sorted(models, key=lambda m: m["created_at"], reverse=True)


def delete_trained_model(model_name: str) -> dict:
    """Delete a trained model (local files + Ollama registry)."""
    import subprocess

    model_dir = _TRAINED_MODEL_DIR / model_name
    if model_dir.exists():
        shutil.rmtree(model_dir)

    result = subprocess.run(
        ["ollama", "rm", model_name],
        capture_output=True, text=True, timeout=30
    )

    return {
        "deleted":   True,
        "ollama_ok": result.returncode == 0,
    }


# ─────────────────────────────────────────────
# HUGGINGFACE JSONL EXPORT
# ─────────────────────────────────────────────

def export_hf_dataset(output_path: Optional[str] = None) -> dict:
    """
    Export the dataset in HuggingFace instruction-tuning format.
    Compatible with: trl SFT, AutoTrain, LoRA, QLoRA.

    Format per line:
    {"prompt": "...", "completion": "..."}

    Also writes an alpaca-style version:
    {"instruction": ..., "input": ..., "output": ...}
    """
    _ensure_dirs()

    if not _DATASET_FILE.exists():
        build_dataset()

    out_dir    = Path(output_path) if output_path else _TRAINING_DATA_DIR
    hf_path    = out_dir / "hf_dataset.jsonl"
    alpaca_path = out_dir / "alpaca_dataset.jsonl"

    hf_lines     = []
    alpaca_lines = []

    with open(_DATASET_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                ex = json.loads(line)
            except Exception:
                continue

            instruction = ex.get("instruction", "")
            inp         = ex.get("input", "")
            output      = ex.get("output", "")

            if not instruction or not output:
                continue

            # HuggingFace prompt/completion format
            prompt = (
                f"### Instruction:\n{instruction}\n\n"
                f"### Input:\n{inp}\n\n" if inp else
                f"### Instruction:\n{instruction}\n\n"
            )
            prompt += "### Response:\n"

            hf_lines.append(json.dumps({
                "prompt":     prompt,
                "completion": output,
            }, ensure_ascii=False))

            # Alpaca format
            alpaca_lines.append(json.dumps({
                "instruction": instruction,
                "input":       inp,
                "output":      output,
            }, ensure_ascii=False))

    hf_path.write_text("\n".join(hf_lines), encoding="utf-8")
    alpaca_path.write_text("\n".join(alpaca_lines), encoding="utf-8")

    return {
        "hf_path":      str(hf_path),
        "alpaca_path":  str(alpaca_path),
        "total_examples": len(hf_lines),
        "exported_at":  datetime.utcnow().isoformat(),
        "train_command": (
            "trl sft "
            f"--model_name_or_path mistralai/Mistral-7B-v0.1 "
            f"--dataset_path {hf_path} "
            "--dataset_text_field prompt "
            "--output_dir ./fine_tuned_model "
            "--num_train_epochs 3 "
            "--per_device_train_batch_size 4 "
            "--use_peft --lora_r 16 --lora_alpha 32"
        )
    }


# ─────────────────────────────────────────────
# CUSTOM Q&A MANAGEMENT
# ─────────────────────────────────────────────

def add_custom_qa(question: str, answer: str, source: str = "manual") -> dict:
    """Add a manually curated Q&A pair to the training data."""
    _ensure_dirs()

    pairs = _load_custom_qa()
    pairs.append({
        "question":   question,
        "answer":     answer,
        "source":     source,
        "type":       "custom",
        "added_at":   datetime.utcnow().isoformat(),
    })

    _CUSTOM_QA_FILE.write_text(
        json.dumps(pairs, ensure_ascii=False, indent=2)
    )

    return {"total_custom": len(pairs), "added": True}


def list_custom_qa() -> list[dict]:
    """Return all manually added Q&A pairs."""
    return _load_custom_qa()


def delete_custom_qa(index: int) -> dict:
    """Delete a custom Q&A pair by index."""
    pairs = _load_custom_qa()
    if 0 <= index < len(pairs):
        removed = pairs.pop(index)
        _CUSTOM_QA_FILE.write_text(json.dumps(pairs, ensure_ascii=False, indent=2))
        return {"deleted": True, "item": removed}
    return {"deleted": False, "error": "Index out of range"}