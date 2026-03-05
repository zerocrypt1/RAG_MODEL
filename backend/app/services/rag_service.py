"""
app/services/rag_service.py

Stable Local RAG pipeline

Priority
1. Document search
2. LLM answer from document
3. Web fallback (ONLY if document not found)
"""

import os
import shutil
import logging
import time
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import (
    PyPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredExcelLoader
)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama

from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate

from app.services.web_search_service import web_answer

logger = logging.getLogger(__name__)

# ------------------------------------------------
# CONFIG
# ------------------------------------------------

VECTOR_DIR = Path(os.environ.get("VECTOR_STORE_DIR", "./vector_stores"))

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

TOP_K = 4

# FAISS similarity distance
SCORE_THRESHOLD = 2.0

EMBED_MODEL = "BAAI/bge-small-en-v1.5"

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

_embeddings = None
_llm = None
_vector_cache = {}

# ------------------------------------------------
# LANGUAGE DETECTION
# ------------------------------------------------

def detect_language(text: str):

    import re

    hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')

    if hindi_chars > 2:
        return "hindi"

    clean = re.sub(r"[^\w\s]", "", text.lower())
    words = clean.split()

    hinglish_words = {
        "kya","kaise","kyu","bhai","yaar","hai",
        "nahi","haan","bolo","bata"
    }

    if any(w in hinglish_words for w in words):
        return "hinglish"

    return "english"


# ------------------------------------------------
# EMBEDDINGS
# ------------------------------------------------

def emb():

    global _embeddings

    if _embeddings is None:

        logger.info("[RAG] loading embeddings")

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

        logger.info("[RAG] connecting ollama")

        _llm = Ollama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
            temperature=0.2,
            num_ctx=4096,
            num_thread=8
        )

    return _llm


# ------------------------------------------------
# VECTOR STORE
# ------------------------------------------------

def store_path(store_id):
    return VECTOR_DIR / store_id


def load_store(store_id):

    if store_id in _vector_cache:
        return _vector_cache[store_id]

    path = store_path(store_id)

    if not path.exists():
        raise FileNotFoundError(store_id)

    logger.info("[RAG] loading vector store %s", store_id)

    store = FAISS.load_local(
        str(path),
        emb(),
        allow_dangerous_deserialization=True
    )

    _vector_cache[store_id] = store

    return store


# ------------------------------------------------
# PROMPT
# ------------------------------------------------

PROMPT = PromptTemplate(

    input_variables=["context", "question"],

    template="""

You are an AI assistant answering from a document.

Rules:

1. ONLY use the document context.
2. If answer not found reply exactly:
"This information is not present in the document."
3. Never use external knowledge.

Context:
{context}

Question:
{question}

Answer:
"""
)


# ------------------------------------------------
# DOCUMENT LOADER
# ------------------------------------------------

def load_document(file_path):

    path = Path(file_path)
    suffix = path.suffix.lower()

    logger.info("[RAG] loading file %s", suffix)

    if suffix == ".pdf":

        docs = PyPDFLoader(str(path)).load()

        logger.info("[RAG] PDF pages: %s", len(docs))

        return docs

    if suffix in (".doc", ".docx"):

        return UnstructuredWordDocumentLoader(
            str(path)
        ).load()

    if suffix in (".xls", ".xlsx"):

        return UnstructuredExcelLoader(
            str(path)
        ).load()

    if suffix == ".csv":

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        return [Document(page_content=text)]

    if suffix == ".txt":

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        return [Document(page_content=text)]

    if suffix in (".png",".jpg",".jpeg",".webp",".bmp",".tiff"):

        from PIL import Image
        import pytesseract

        img = Image.open(file_path)

        img = img.convert("L")

        text = pytesseract.image_to_string(
            img,
            lang="eng+hin",
            config="--psm 6"
        )

        logger.info("[OCR] extracted %s chars", len(text))

        if not text.strip():
            text = "[No readable text found in image]"

        return [Document(page_content=text)]

    raise ValueError(f"Unsupported file: {suffix}")


# ------------------------------------------------
# FILE PROCESSING
# ------------------------------------------------

def process_file(file_path, file_id):

    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    docs = load_document(file_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    chunks = splitter.split_documents(docs)

    logger.info("[RAG] chunks created %s", len(chunks))

    store = FAISS.from_documents(
        chunks,
        emb()
    )

    store.save_local(str(store_path(file_id)))

    return {
        "page_count": len(docs),
        "chunk_count": len(chunks),
        "vector_store_id": file_id
    }


# ------------------------------------------------
# QUERY
# ------------------------------------------------

def query(
    vector_store_id,
    question,
    chat_history: Optional[list] = None,
    mode="document"
):

    start = time.monotonic()

    try:
        store = load_store(vector_store_id)

    except Exception:

        logger.warning("[RAG] vector store missing")

        return web_answer(question, llm(), detect_language(question))

    results = store.similarity_search_with_score(
        question,
        k=TOP_K
    )

    if not results:

        logger.warning("[RAG] no document results")

        return web_answer(question, llm(), detect_language(question))

    best_score = results[0][1]

    logger.info("[RAG] best score %s", best_score)

    if best_score > SCORE_THRESHOLD:

        logger.warning("[RAG] weak document match")

        return web_answer(question, llm(), detect_language(question))

    context_parts = []

    for doc, score in results:
        context_parts.append(doc.page_content)

    context = "\n\n".join(context_parts)

    prompt = PROMPT.format(
        context=context[:4000],
        question=question
    )

    answer = llm().invoke(prompt)

    answer_text = answer.strip()

    # ------------------------------------------------
    # WEB FALLBACK IF ANSWER NOT FOUND
    # ------------------------------------------------

    if "not present in the document" in answer_text.lower():

        logger.info("[RAG] answer not in document → using web")

        return web_answer(question, llm(), detect_language(question))

    latency = int((time.monotonic() - start) * 1000)

    return {
        "answer": answer_text,
        "sources": [{"content": context[:200]}],
        "latency_ms": latency
    }


# ------------------------------------------------
# DELETE STORE
# ------------------------------------------------

def delete_store(store_id):

    path = store_path(store_id)

    if path.exists():
        shutil.rmtree(path)

    _vector_cache.pop(store_id, None)


def store_exists(store_id):

    return store_path(store_id).exists()