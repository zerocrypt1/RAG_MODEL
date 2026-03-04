"""
app/services/memory_rag_service.py

Cross-Document Memory RAG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lets users query across ALL uploaded documents and past
chat history at once — not just one file at a time.

Features:
• Merges every FAISS vector store into one mega-index
• Indexes chat history as searchable documents
• Returns ranked answers with source attribution
• Remembers which file/session each chunk came from
"""

import os
import json
import logging
import time
from pathlib import Path
from typing import Optional

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain.chains import RetrievalQA

logger = logging.getLogger(__name__)

_VECTOR_STORE_DIR = Path(os.environ.get("VECTOR_STORE_DIR",  "./vector_stores"))
_MEMORY_INDEX_DIR = Path(os.environ.get("MEMORY_INDEX_DIR", "./memory_index"))
_CHAT_HISTORY_DIR = Path(os.environ.get("CHAT_HISTORY_DIR", "./chat_history"))

_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "mistral")
_OLLAMA_URL      = os.environ.get("OLLAMA_URL",   "http://localhost:11434")

_TOP_K = 5

# ── Singletons ────────────────────────────────────────────────────────────────
_embeddings_model  = None
_llm_model         = None
_merged_store      = None   # in-memory merged FAISS index
_merged_store_mtime = 0     # rebuild when new files appear


# ─────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────

def _emb():
    global _embeddings_model
    if _embeddings_model is None:
        _embeddings_model = HuggingFaceEmbeddings(model_name=_EMBEDDING_MODEL)
    return _embeddings_model


def _llm():
    global _llm_model
    if _llm_model is None:
        _llm_model = Ollama(
            model=_OLLAMA_MODEL, base_url=_OLLAMA_URL,
            temperature=0.3, num_ctx=4096, num_thread=8, timeout=120
        )
    return _llm_model


def _store_mtime() -> float:
    """Return the latest modification time across all vector store subdirs."""
    if not _VECTOR_STORE_DIR.exists():
        return 0.0
    times = [p.stat().st_mtime for p in _VECTOR_STORE_DIR.iterdir() if p.is_dir()]
    return max(times, default=0.0)


def _chat_docs_from_history() -> list[Document]:
    """
    Convert saved chat-history JSON files into Documents so they
    become searchable in the memory index.
    """
    docs = []
    if not _CHAT_HISTORY_DIR.exists():
        return docs

    for fpath in _CHAT_HISTORY_DIR.glob("*.json"):
        try:
            data     = json.loads(fpath.read_text())
            session  = data.get("session_id", fpath.stem)
            title    = data.get("title", "Chat session")
            messages = data.get("messages", [])

            # Group consecutive user+assistant pairs into one chunk
            i = 0
            while i < len(messages):
                m = messages[i]
                if m.get("role") == "user":
                    q = m.get("content", "").strip()
                    a = ""
                    if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant":
                        a = messages[i + 1].get("content", "").strip()
                        i += 2
                    else:
                        i += 1

                    if q:
                        text = f"Q: {q}\nA: {a}" if a else f"Q: {q}"
                        docs.append(Document(
                            page_content=text,
                            metadata={
                                "source_type": "chat",
                                "session_id":  session,
                                "title":       title,
                                "page":        "chat",
                            }
                        ))
                else:
                    i += 1
        except Exception as e:
            logger.warning("[Memory] Could not load chat file %s: %s", fpath, e)

    logger.info("[Memory] Loaded %d chat chunks from history", len(docs))
    return docs


def _build_merged_index() -> Optional[FAISS]:
    """
    Merge all individual FAISS stores + chat history into one index.
    Rebuilt only when vector stores have changed.
    """
    global _merged_store, _merged_store_mtime

    current_mtime = _store_mtime()
    if _merged_store is not None and current_mtime <= _merged_store_mtime:
        return _merged_store  # cache still valid

    logger.info("[Memory] Rebuilding merged index…")

    emb      = _emb()
    all_docs = []

    # ── 1. Load every document vector store ───────────────────────────────
    if _VECTOR_STORE_DIR.exists():
        for store_dir in _VECTOR_STORE_DIR.iterdir():
            if not store_dir.is_dir():
                continue
            try:
                store = FAISS.load_local(
                    str(store_dir), emb,
                    allow_dangerous_deserialization=True
                )
                # Extract raw documents from the docstore
                raw_docs = list(store.docstore._dict.values())
                for doc in raw_docs:
                    doc.metadata.setdefault("source_type", "document")
                    doc.metadata.setdefault("store_id",    store_dir.name)
                all_docs.extend(raw_docs)
                logger.debug("[Memory] Loaded %d chunks from %s", len(raw_docs), store_dir.name)
            except Exception as e:
                logger.warning("[Memory] Skipping store %s: %s", store_dir.name, e)

    # ── 2. Add chat history chunks ─────────────────────────────────────────
    all_docs.extend(_chat_docs_from_history())

    if not all_docs:
        logger.info("[Memory] No documents to index yet")
        _merged_store      = None
        _merged_store_mtime = current_mtime
        return None

    _merged_store       = FAISS.from_documents(all_docs, emb)
    _merged_store_mtime = current_mtime
    logger.info("[Memory] Merged index built: %d total chunks", len(all_docs))
    return _merged_store


# ─────────────────────────────────────────────
# LANGUAGE HELPERS  (re-used from rag_service)
# ─────────────────────────────────────────────

def _lang_rule(lang: str) -> str:
    if lang == "hinglish":
        return (
            "══ REPLY IN HINGLISH ONLY ══\n"
            "User Hinglish mein baat kar raha hai.\n"
            "Hindi fillers (yaar, bhai, toh, hai, matlab) + English words use karo.\n"
            "Example — Q: 'purani file mein kya tha?' "
            "A: 'Haan bhai, us file mein page 3 pe financial data tha! 📄'"
        )
    if lang == "hindi":
        return (
            "══ SIRF HINDI MEIN JAWAB DO ══\n"
            "User ne Hindi mein likha hai. Devanagari script use karo."
        )
    return "Reply in friendly, conversational English."


_MEMORY_PROMPT = PromptTemplate(
    input_variables=["context", "question", "lang_rule"],
    template="""You are a smart AI assistant with memory of all uploaded documents and past chats.

{lang_rule}

Use ONLY the context below to answer. Mention the source (document name or chat session) when possible.
If the answer spans multiple sources, summarize all relevant parts.
If not found anywhere, say so honestly.

Context from memory:
{context}

Question: {question}

Answer:"""
)


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def query_memory(
    question:    str,
    lang:        str = "english",
    top_k:       int = _TOP_K,
) -> dict:
    """
    Search across ALL documents + chat history and return a synthesized answer.
    """
    start = time.monotonic()

    store = _build_merged_index()

    if store is None:
        return {
            "answer":     "Koi document ya chat history nahi mili abhi. Pehle kuch upload karo! 📎",
            "sources":    [],
            "latency_ms": 0,
            "mode":       "memory",
        }

    # Similarity search
    docs_scores = store.similarity_search_with_score(question, k=top_k)

    if not docs_scores:
        return {
            "answer":     "Hmm, kuch relevant nahi mila memory mein. Try a different question?",
            "sources":    [],
            "latency_ms": int((time.monotonic() - start) * 1000),
            "mode":       "memory",
        }

    # Build context string
    context_parts = []
    sources       = []
    seen_sources  = set()

    for doc, score in docs_scores:
        src_type  = doc.metadata.get("source_type", "document")
        store_id  = doc.metadata.get("store_id",    doc.metadata.get("session_id", "unknown"))
        page      = doc.metadata.get("page", 0)
        src_label = f"[{src_type.upper()}] {store_id}"

        context_parts.append(f"{src_label}:\n{doc.page_content}")

        src_key = f"{src_type}:{store_id}:{page}"
        if src_key not in seen_sources:
            seen_sources.add(src_key)
            sources.append({
                "type":     src_type,
                "store_id": store_id,
                "page":     page if src_type == "document" else "chat",
                "content":  doc.page_content[:180].strip(),
                "score":    round(float(score), 3),
            })

    context   = "\n\n---\n\n".join(context_parts)
    lang_rule = _lang_rule(lang)

    # Fill prompt manually (no chain needed for this one)
    prompt = _MEMORY_PROMPT.format(
        context=context, question=question, lang_rule=lang_rule
    )

    try:
        answer = _llm().invoke(prompt).strip()
    except Exception as e:
        logger.error("[Memory] LLM error: %s", e)
        answer = "LLM se answer nahi aaya. Ollama chal raha hai? 🤔"

    sources.sort(key=lambda s: s["score"])

    return {
        "answer":     answer,
        "sources":    sources,
        "latency_ms": int((time.monotonic() - start) * 1000),
        "mode":       "memory",
        "language":   lang,
    }


def index_chat_session(session_id: str, title: str, messages: list) -> bool:
    """
    Persist a chat session to disk so it gets picked up by the memory index.
    Call this after every chat turn.
    """
    global _merged_store   # invalidate cache
    _CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    data = {"session_id": session_id, "title": title, "messages": messages}
    fpath = _CHAT_HISTORY_DIR / f"{session_id}.json"

    try:
        fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        _merged_store = None   # force rebuild next query
        return True
    except Exception as e:
        logger.error("[Memory] Could not save chat session: %s", e)
        return False


def list_memory_sources() -> dict:
    """Return a summary of everything in the memory index."""
    sources = {"documents": [], "chats": []}

    if _VECTOR_STORE_DIR.exists():
        for d in _VECTOR_STORE_DIR.iterdir():
            if d.is_dir():
                meta_file = d / "metadata.json"
                if meta_file.exists():
                    try:
                        sources["documents"].append(json.loads(meta_file.read_text()))
                    except Exception:
                        sources["documents"].append({"store_id": d.name})
                else:
                    sources["documents"].append({"store_id": d.name})

    if _CHAT_HISTORY_DIR.exists():
        for f in _CHAT_HISTORY_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                sources["chats"].append({
                    "session_id": data.get("session_id", f.stem),
                    "title":      data.get("title", "Untitled"),
                    "msg_count":  len(data.get("messages", [])),
                })
            except Exception:
                pass

    return sources


def invalidate_cache():
    """Force the merged index to rebuild on next query."""
    global _merged_store
    _merged_store = None