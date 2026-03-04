"""
app/services/rag_service.py
Full Retrieval-Augmented Generation pipeline using:
  • LangChain (document loading, splitting, chain)
  • OpenAI Embeddings (text-embedding-ada-002)
  • FAISS (local vector store, persisted to disk)
  • ChatOpenAI GPT-3.5 / GPT-4

Public API
----------
process_pdf(pdf_path, pdf_id)   →  dict   build & save vector store
query(vector_store_id, question, history)  →  dict   RAG answer + sources
delete_store(vector_store_id)   →  None   remove from disk
store_exists(vector_store_id)   →  bool
"""

import os
import shutil
import logging
import time
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage, AIMessage

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_VECTOR_STORE_DIR = Path(os.environ.get("VECTOR_STORE_DIR", "/tmp/vector_stores"))
_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
_OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")

# Chunking strategy
_CHUNK_SIZE = 1_000
_CHUNK_OVERLAP = 200

# Retrieval
_TOP_K = 4


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ensure_dir() -> None:
    _VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _store_path(vector_store_id: str) -> Path:
    return _VECTOR_STORE_DIR / vector_store_id


def _embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        openai_api_key=_OPENAI_API_KEY,
        model=_OPENAI_EMBEDDING_MODEL,
    )


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        openai_api_key=_OPENAI_API_KEY,
        model_name=_OPENAI_MODEL,
        temperature=0.2,
        max_tokens=1_024,
        request_timeout=60,
    )


# ── System prompt ─────────────────────────────────────────────────────────────
_CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(
    """Given the following conversation history and a follow-up question,
rephrase the follow-up question to be a standalone question.
If it is already a standalone question, return it as-is.

Chat History:
{chat_history}

Follow-Up Question: {question}

Standalone Question:"""
)

_QA_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""You are an expert assistant helping users understand PDF documents.
Use ONLY the context below to answer the question accurately and concisely.
If the answer is not found in the context, say: "I couldn't find that information in this document."
Always reference specific page numbers when possible (e.g. "According to page 3…").

Context from document:
{context}

Question: {question}

Detailed Answer:""",
)


# ── Public API ─────────────────────────────────────────────────────────────────

def process_pdf(pdf_path: str, pdf_id: str) -> dict:
    """
    Load a PDF, split it into chunks, create OpenAI embeddings, and save a
    FAISS index to disk.

    Parameters
    ----------
    pdf_path : str
        Absolute local path to the PDF file.
    pdf_id : str
        Unique identifier – used as the folder name for the vector store.

    Returns
    -------
    dict
        {
            "page_count": int,
            "chunk_count": int,
            "vector_store_id": str,
        }

    Raises
    ------
    FileNotFoundError
        If the PDF does not exist at the given path.
    Exception
        Propagated from LangChain / OpenAI on any processing error.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found at {pdf_path!r}")

    _ensure_dir()
    logger.info("[RAG] Processing %s (id=%s)", pdf_path, pdf_id)

    # 1. Load ──────────────────────────────────────────────────────────────────
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()
    page_count = len(pages)
    logger.info("[RAG] Loaded %d pages", page_count)

    # 2. Split ─────────────────────────────────────────────────────────────────
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(pages)

    # Enrich metadata so we can show page citations in the UI
    for i, chunk in enumerate(chunks):
        chunk.metadata.setdefault("page", 0)         # PyPDFLoader sets this
        chunk.metadata["chunk_index"] = i
        chunk.metadata["pdf_id"] = pdf_id

    chunk_count = len(chunks)
    logger.info("[RAG] Created %d chunks", chunk_count)

    # 3. Embed + index ─────────────────────────────────────────────────────────
    logger.info("[RAG] Building FAISS index…")
    embeddings = _embeddings()
    vector_store = FAISS.from_documents(chunks, embeddings)

    # 4. Persist ───────────────────────────────────────────────────────────────
    store_path = _store_path(pdf_id)
    vector_store.save_local(str(store_path))
    logger.info("[RAG] Vector store saved to %s", store_path)

    return {
        "page_count": page_count,
        "chunk_count": chunk_count,
        "vector_store_id": pdf_id,
    }


def query(
    vector_store_id: str,
    question: str,
    chat_history: Optional[list] = None,
) -> dict:
    """
    Answer a question against a stored FAISS index.

    Parameters
    ----------
    vector_store_id : str
        ID of the previously built vector store.
    question : str
        The user's question.
    chat_history : list, optional
        Previous messages in the format:
            [{"role": "user"|"assistant", "content": "..."}]

    Returns
    -------
    dict
        {
            "answer": str,
            "sources": [{"page": int, "content": str}],
            "latency_ms": int,
        }

    Raises
    ------
    FileNotFoundError
        If the vector store does not exist on disk.
    """
    store_path = _store_path(vector_store_id)
    if not store_path.exists():
        raise FileNotFoundError(
            f"Vector store '{vector_store_id}' not found. "
            "The PDF may still be processing or an error occurred."
        )

    t0 = time.monotonic()
    embeddings = _embeddings()

    # allow_dangerous_deserialization required for FAISS >= 0.1.0
    vector_store = FAISS.load_local(
        str(store_path),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": _TOP_K},
    )

    # Build LangChain message history from our dict format
    lc_history: list[tuple[str, str]] = []
    if chat_history:
        # Pair up consecutive user / assistant turns
        i = 0
        msgs = [m for m in chat_history if m["role"] in ("user", "assistant")]
        while i < len(msgs) - 1:
            if msgs[i]["role"] == "user" and msgs[i + 1]["role"] == "assistant":
                lc_history.append((msgs[i]["content"], msgs[i + 1]["content"]))
                i += 2
            else:
                i += 1

    llm = _llm()

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": _QA_PROMPT},
        condense_question_prompt=_CONDENSE_QUESTION_PROMPT,
        verbose=False,
    )

    result = chain.invoke({"question": question, "chat_history": lc_history})

    latency_ms = int((time.monotonic() - t0) * 1_000)

    # De-duplicate sources by page number, keep snippet for display
    seen_pages: set[int] = set()
    sources: list[dict] = []
    for doc in result.get("source_documents", []):
        page = int(doc.metadata.get("page", 0)) + 1  # 0-indexed → 1-indexed
        if page not in seen_pages:
            seen_pages.add(page)
            snippet = doc.page_content[:250].strip()
            if len(doc.page_content) > 250:
                snippet += "…"
            sources.append({"page": page, "content": snippet})

    sources.sort(key=lambda s: s["page"])

    return {
        "answer": result["answer"].strip(),
        "sources": sources,
        "latency_ms": latency_ms,
    }


def delete_store(vector_store_id: str) -> None:
    """
    Remove the FAISS index directory from disk.

    Parameters
    ----------
    vector_store_id : str
        ID of the vector store to delete.
    """
    store_path = _store_path(vector_store_id)
    if store_path.exists():
        shutil.rmtree(store_path)
        logger.info("[RAG] Deleted vector store %s", vector_store_id)
    else:
        logger.warning("[RAG] delete_store: '%s' not found on disk", vector_store_id)


def store_exists(vector_store_id: str) -> bool:
    """Return True if the FAISS index folder exists on disk."""
    return _store_path(vector_store_id).exists()