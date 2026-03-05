"""
app/services/memory_rag_service.py

Advanced Cross-Document Memory RAG

Priority:
1. Chat memory
2. Stored documents
3. LLM reasoning
4. Web search fallback
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

from app.services.web_search_service import web_answer

logger = logging.getLogger(__name__)

VECTOR_DIR = Path(os.environ.get("VECTOR_STORE_DIR", "./vector_stores"))
CHAT_DIR = Path(os.environ.get("CHAT_HISTORY_DIR", "./chat_history"))

# ------------------------------------------------
# CONFIG
# ------------------------------------------------

EMBED_MODEL = "BAAI/bge-small-en-v1.5"

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

TOP_K_CHAT = 3
TOP_K_DOC = 3

THRESHOLD = 0.35

_embeddings = None
_llm = None
_doc_index = None
_chat_index = None


# ------------------------------------------------
# EMBEDDINGS
# ------------------------------------------------

def emb():
    global _embeddings

    if _embeddings is None:
        logger.info("[Memory] Loading embedding model")

        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL
        )

    return _embeddings


# ------------------------------------------------
# LLM
# ------------------------------------------------

def llm():
    global _llm

    if _llm is None:

        logger.info("[Memory] Connecting to Ollama")

        _llm = Ollama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
            temperature=0.2,
            num_ctx=2048,
            num_thread=8,
            num_predict=300
        )

    return _llm


# ------------------------------------------------
# CHAT MEMORY LOADER
# ------------------------------------------------

def load_chat_documents():

    docs = []

    if not CHAT_DIR.exists():
        return docs

    for f in CHAT_DIR.glob("*.json"):

        try:

            data = json.loads(f.read_text())

            session = data.get("session_id", f.stem)

            messages = data.get("messages", [])

            i = 0

            while i < len(messages):

                m = messages[i]

                if m.get("role") == "user":

                    q = m.get("content", "")
                    a = ""

                    if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                        a = messages[i + 1]["content"]
                        i += 2
                    else:
                        i += 1

                    text = f"User: {q}\nAssistant: {a}"

                    docs.append(
                        Document(
                            page_content=text,
                            metadata={
                                "source": "chat",
                                "session": session
                            }
                        )
                    )

                else:
                    i += 1

        except Exception as e:

            logger.warning("[Memory] Chat load error %s", e)

    return docs


# ------------------------------------------------
# BUILD CHAT INDEX
# ------------------------------------------------

def build_chat_index():

    global _chat_index

    docs = load_chat_documents()

    if not docs:
        _chat_index = None
        return None

    _chat_index = FAISS.from_documents(
        docs,
        emb()
    )

    return _chat_index


# ------------------------------------------------
# BUILD DOCUMENT INDEX
# ------------------------------------------------

def build_doc_index():

    global _doc_index

    docs = []

    if VECTOR_DIR.exists():

        for d in VECTOR_DIR.iterdir():

            if not d.is_dir():
                continue

            try:

                store = FAISS.load_local(
                    str(d),
                    emb(),
                    allow_dangerous_deserialization=True
                )

                raw_docs = list(store.docstore._dict.values())

                for doc in raw_docs:

                    doc.metadata.setdefault("source", "document")
                    doc.metadata.setdefault("store", d.name)

                docs.extend(raw_docs)

            except Exception as e:

                logger.warning("[Memory] Skipping store %s: %s", d.name, e)

    if not docs:

        _doc_index = None
        return None

    _doc_index = FAISS.from_documents(
        docs,
        emb()
    )

    return _doc_index


# ------------------------------------------------
# PROMPT
# ------------------------------------------------

PROMPT = PromptTemplate(

    input_variables=["context", "question"],

    template="""

You are a smart AI assistant.

Rules:
1. Use ONLY the context below.
2. If the answer is not present reply exactly:
   "This information is not present in memory or documents."
3. Never guess.

Context:
{context}

Question:
{question}

Answer:
"""
)


# ------------------------------------------------
# CONTEXT BUILDER
# ------------------------------------------------

def build_context(results):

    texts = []
    seen = set()

    for doc, score in results:

        txt = doc.page_content.strip()

        if txt in seen:
            continue

        seen.add(txt)

        texts.append(txt)

    context = "\n\n".join(texts)

    return context[:3500]


# ------------------------------------------------
# MAIN QUERY
# ------------------------------------------------

def query_memory(question: str, lang: str = "english"):

    start = time.monotonic()

    greetings = ["hi","hello","hey"]

    if question.lower().strip() in greetings:
        return {
            "answer": llm().invoke(question),
            "sources": [],
            "mode": "chat",
            "language": lang
        }

    # ---------- CHAT MEMORY ----------

    chat_index = build_chat_index()

    if chat_index:

        chat_results = chat_index.similarity_search_with_score(
            question,
            k=TOP_K_CHAT
        )

        if chat_results and chat_results[0][1] < THRESHOLD:

            context = build_context(chat_results)

            prompt = PROMPT.format(
                context=context,
                question=question
            )

            answer = llm().invoke(prompt)

            return {
                "answer": answer,
                "sources": ["chat_memory"],
                "latency_ms": int((time.monotonic() - start) * 1000),
                "mode": "chat_memory",
                "language": lang
            }

    # ---------- DOCUMENT MEMORY ----------

    doc_index = build_doc_index()

    if doc_index:

        doc_results = doc_index.similarity_search_with_score(
            question,
            k=TOP_K_DOC
        )

        if doc_results and doc_results[0][1] < THRESHOLD:

            context = build_context(doc_results)

            prompt = PROMPT.format(
                context=context,
                question=question
            )

            answer = llm().invoke(prompt)

            return {
                "answer": answer,
                "sources": ["documents"],
                "latency_ms": int((time.monotonic() - start) * 1000),
                "mode": "documents",
                "language": lang
            }

    # ---------- LLM REASONING ----------

    try:

        answer = llm().invoke(question)

        if len(answer.strip()) > 20:

            return {
                "answer": answer,
                "sources": [],
                "mode": "llm_reasoning",
                "language": lang
            }

    except Exception as e:

        logger.warning("[Memory] LLM reasoning failed: %s", e)

    # ---------- WEB FALLBACK ----------

    return web_answer(question, llm(), lang)


# ------------------------------------------------
# SAVE CHAT SESSION
# ------------------------------------------------

def index_chat_session(session_id: str, title: str, messages: list) -> bool:

    global _chat_index

    CHAT_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "session_id": session_id,
        "title": title,
        "messages": messages,
    }

    fpath = CHAT_DIR / f"{session_id}.json"

    try:

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        _chat_index = None

        return True

    except Exception as e:

        logger.error("[Memory] Failed to save chat session: %s", e)

        return False


# ------------------------------------------------
# LIST MEMORY SOURCES
# ------------------------------------------------

def list_memory_sources():

    sources = {
        "documents": [],
        "chats": []
    }

    if VECTOR_DIR.exists():

        for d in VECTOR_DIR.iterdir():

            if d.is_dir():

                sources["documents"].append({
                    "store_id": d.name
                })

    if CHAT_DIR.exists():

        for f in CHAT_DIR.glob("*.json"):

            try:

                data = json.loads(f.read_text())

                sources["chats"].append({
                    "session_id": data.get("session_id", f.stem),
                    "title": data.get("title", "Untitled"),
                    "messages": len(data.get("messages", []))
                })

            except Exception:
                pass

    return sources

def invalidate_cache():
    """
    Reset memory indexes.
    Called when new files are uploaded so the system rebuilds indexes.
    """

    global _doc_index
    global _chat_index

    _doc_index = None
    _chat_index = None

    logger.info("[Memory] Cache invalidated")

    