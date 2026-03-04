"""
app/services/rag_service.py

Local RAG pipeline using:

• HuggingFace embeddings
• FAISS vector store
• Ollama local LLM

No OpenAI API required.
"""

import os
import shutil
import logging
import time
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama

from langchain_community.vectorstores import FAISS

from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

_VECTOR_STORE_DIR = Path(
    os.environ.get("VECTOR_STORE_DIR", "./vector_stores")
)

_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 200
_TOP_K = 4

_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _ensure_dir():
    _VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _store_path(vector_store_id: str) -> Path:
    return _VECTOR_STORE_DIR / vector_store_id


def _embeddings():
    """
    Load HuggingFace embedding model
    """
    return HuggingFaceEmbeddings(
        model_name=_EMBEDDING_MODEL
    )


def _llm():
    """
    Local Ollama LLM
    """
    return Ollama(
        model=_OLLAMA_MODEL,
        base_url=_OLLAMA_URL,
        temperature=0.2
    )


# ─────────────────────────────────────────────
# Prompt Template
# ─────────────────────────────────────────────

_QA_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""
You are an assistant helping users understand a document.

Use ONLY the provided context to answer the question.

If the answer cannot be found in the document say:
"I couldn't find that information in the document."

Always mention page numbers if possible.

Context:
{context}

Question:
{question}

Answer:
"""
)


# ─────────────────────────────────────────────
# Process PDF
# ─────────────────────────────────────────────

def process_pdf(pdf_path: str, pdf_id: str) -> dict:

    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found at {pdf_path}")

    _ensure_dir()

    logger.info("[RAG] Processing PDF %s", pdf_path)

    loader = PyPDFLoader(pdf_path)

    pages = loader.load()

    page_count = len(pages)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        length_function=len
    )

    chunks = splitter.split_documents(pages)

    for i, chunk in enumerate(chunks):

        chunk.metadata["chunk_index"] = i
        chunk.metadata["pdf_id"] = pdf_id

    chunk_count = len(chunks)

    logger.info("[RAG] Creating embeddings")

    embeddings = _embeddings()

    vector_store = FAISS.from_documents(
        chunks,
        embeddings
    )

    store_path = _store_path(pdf_id)

    vector_store.save_local(str(store_path))

    logger.info("[RAG] Vector store saved to %s", store_path)

    return {
        "page_count": page_count,
        "chunk_count": chunk_count,
        "vector_store_id": pdf_id
    }


# ─────────────────────────────────────────────
# Query RAG
# ─────────────────────────────────────────────

def query(
    vector_store_id: str,
    question: str,
    chat_history: Optional[list] = None
) -> dict:

    store_path = _store_path(vector_store_id)

    if not store_path.exists():
        raise FileNotFoundError(
            f"Vector store '{vector_store_id}' not found"
        )

    start = time.monotonic()

    embeddings = _embeddings()

    # ❌ FIXED HERE (removed allow_dangerous_deserialization)

    vector_store = FAISS.load_local(
        str(store_path),
        embeddings
    )

    retriever = vector_store.as_retriever(
        search_kwargs={"k": _TOP_K}
    )

    history = []

    if chat_history:

        msgs = [
            m for m in chat_history
            if m["role"] in ("user", "assistant")
        ]

        i = 0

        while i < len(msgs) - 1:

            if (
                msgs[i]["role"] == "user"
                and msgs[i + 1]["role"] == "assistant"
            ):

                history.append(
                    (
                        msgs[i]["content"],
                        msgs[i + 1]["content"]
                    )
                )

                i += 2

            else:

                i += 1

    llm = _llm()

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": _QA_PROMPT}
    )

    result = chain.invoke(
        {
            "question": question,
            "chat_history": history
        }
    )

    latency_ms = int((time.monotonic() - start) * 1000)

    seen_pages = set()
    sources = []

    for doc in result.get("source_documents", []):

        page = int(doc.metadata.get("page", 0)) + 1

        if page not in seen_pages:

            seen_pages.add(page)

            snippet = doc.page_content[:250].strip()

            if len(doc.page_content) > 250:
                snippet += "..."

            sources.append(
                {
                    "page": page,
                    "content": snippet
                }
            )

    sources.sort(key=lambda s: s["page"])

    return {
        "answer": result["answer"].strip(),
        "sources": sources,
        "latency_ms": latency_ms
    }


# ─────────────────────────────────────────────
# Delete Vector Store
# ─────────────────────────────────────────────

def delete_store(vector_store_id: str):

    store_path = _store_path(vector_store_id)

    if store_path.exists():

        shutil.rmtree(store_path)

        logger.info(
            "[RAG] Deleted vector store %s",
            vector_store_id
        )


# ─────────────────────────────────────────────
# Store Exists
# ─────────────────────────────────────────────

def store_exists(vector_store_id: str) -> bool:

    return _store_path(vector_store_id).exists()