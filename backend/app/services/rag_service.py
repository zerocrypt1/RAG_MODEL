"""
app/services/rag_service.py

Fast Local RAG pipeline — v2

• HuggingFace embeddings (loaded once)
• FAISS vector store cache
• Ollama LLM with human-like, multilingual responses
• PDF, Image, Word, Excel support
• Web search fallback
• Hindi / English / Hinglish support
"""

import os
import shutil
import logging
import time
from pathlib import Path
from typing import Optional

# Document Loaders
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain_community.document_loaders import UnstructuredExcelLoader

from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain_community.vectorstores import FAISS

from langchain_core.prompts import PromptTemplate
from langchain.chains.conversational_retrieval.base import ConversationalRetrievalChain

from app.services.web_search_service import web_answer

# OCR for images
try:
    from PIL import Image
    import pytesseract
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

_VECTOR_STORE_DIR = Path(
    os.environ.get("VECTOR_STORE_DIR", "./vector_stores")
)

_CHUNK_SIZE    = 800   # smaller = faster retrieval
_CHUNK_OVERLAP = 100

_TOP_K            = 3
_SCORE_THRESHOLD  = 5.0

_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
_OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")

# ─────────────────────────────────────────────
# GLOBAL CACHE
# ─────────────────────────────────────────────

_embedding_model    = None
_llm_model          = None
_vector_store_cache = {}
_answer_cache: dict = {}          # simple in-memory answer cache
_ANSWER_CACHE_TTL   = 300         # seconds — reuse identical questions for 5 min

# ─────────────────────────────────────────────
# LANGUAGE DETECTION
# ─────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    Heuristic language detector.
    Returns: 'hindi', 'hinglish', or 'english'
    """
    import re

    # ── 1. Pure Hindi (Devanagari characters) ─────────────────────────────
    hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    if hindi_chars > 2:
        return "hindi"

    # ── 2. Strip punctuation and lowercase ────────────────────────────────
    clean  = re.sub(r"[^\w\s]", "", text.lower())
    words  = clean.split()

    # ── 3. Comprehensive Hinglish keyword set ─────────────────────────────
    #       Covers greetings, question words, common verbs, connectors,
    #       colloquials, and sentence-starters people actually type.
    hinglish_keywords = {
        # Greetings / fillers
        "haan", "nahi", "nah", "nahin", "haa", "oye", "arre", "arrey",
        "yaar", "bhai", "dost", "bro",
        # Question words
        "kya", "kyu", "kyun", "kaise", "kaisa", "kaisi", "kab", "kahan",
        "kaun", "kitna", "kitne", "kitni",
        # Pronouns
        "mai", "main", "mujhe", "mera", "meri", "mere", "mujhko",
        "tera", "teri", "tere", "tumhara", "tumhari", "aapka",
        "aap", "tum", "tu", "wo", "woh", "yeh", "ye", "isko", "usko",
        # Verbs / imperatives
        "hai", "hain", "tha", "thi", "the", "hoga", "hogi",
        "karo", "karna", "kar", "bolo", "bol", "batao", "bata",
        "dekho", "dekh", "suno", "sun", "samjho", "samajh",
        "aao", "jao", "ruko", "chalo", "lo", "do",
        "chahiye", "chahie", "chahta", "chahti",
        "likhna", "likhdo", "padho",
        # Common words
        "aur", "ya", "lekin", "magar", "par", "toh", "to", "bhi",
        "sirf", "bas", "hi", "na", "ne", "se", "mein", "pe", "ko",
        "ka", "ki", "ke", "wala", "wali",
        # Adjectives / adverbs
        "accha", "achha", "acha", "theek", "thik", "sahi", "galat",
        "bahut", "bohat", "thoda", "zyada", "jyada", "kam",
        "abhi", "baad", "pehle", "phir", "fir", "jaldi", "dhire",
        "aisa", "waisa", "itna",
        # Expressions
        "matlab", "yani", "matlab", "lagta", "lagti", "laga",
        "pata", "samajh", "sorry", "please", "thanks", "shukriya",
        "pyaar", "pyar", "dil", "zindagi",
    }

    count = sum(1 for w in words if w in hinglish_keywords)

    # Even ONE clear Hinglish word in a short message is enough
    if count >= 1:
        return "hinglish"

    return "english"


def _language_instruction(lang: str) -> str:
    """
    Return a STRICT language rule with few-shot examples.
    Mistral needs concrete examples — vague instructions get ignored.
    """
    if lang == "hindi":
        return """

══ STRICT RULE: REPLY IN HINDI ONLY ══
User ne Hindi mein likha hai.
POORA reply SIRF Hindi (Devanagari) mein dena — ek bhi English sentence nahi.
Tone: warm, simple, dost jaisi.

Example:
User: यह document किस बारे में है?
AI:   यह document company की financial report है! Page 3 पर quarterly revenue है
      और page 7 पर expenses का breakdown। कुछ और जानना हो तो बताओ! 😊"""

    if lang == "hinglish":
        return """

══ STRICT RULE: REPLY IN HINGLISH ONLY ══
User Hinglish mein baat kar raha hai (Hindi + English mix).
POORA reply HINGLISH mein likhna — PURE ENGLISH mein reply karna GALAT hai.

Hinglish kya hai:
- English words use karo (love, machine, document, etc.)
- BUT Hindi sentence structure aur fillers use karo
- "yaar", "bhai", "toh", "hai", "kya", "matlab", "dekh", "arre" — zaroor use karo
- Casual, friendly, jaise dost baat karta hai

══ FEW-SHOT EXAMPLES ══

User: "suno i love you"
AI: "Arre yaar, 'I love you' ek bahut powerful feeling hai! Kisi ke liye deep
    affection aur care feel karne ko bolte hain isse. Jab dil se bolte ho toh
    samne wale ko bahut special feel hota hai. Kisi ko bolne ka plan chal raha
    hai kya? 😄 Bata, help karunga!"

User: "kya hai machine learning"
AI: "Bhai, machine learning basically computers ko experience se seekhne ki
    ability dena hai — bina manually program kiye! Jaise tu movies dekh ke
    apna taste develop karta hai, waise computer data dekh ke patterns seekhta
    hai. Netflix recommendations, face unlock, spam filter — yeh sab ML hai
    yaar! 🤖 Kuch aur jaanna hai?"

User: "document mein kya likha hai"
AI: "Dekh bhai, maine document check kiya — page 3 pe main points hain. Basically
    yeh report Q3 performance ke baare mein hai. Revenue 20% badha hai aur
    expenses thodi zyada hain. Koi specific cheez jaanni hai? Bata! 📄"

══ AB USER KA QUESTION HINGLISH MEIN ANSWER KAR ══
(Pure English = WRONG. Hinglish = CORRECT.)"""

    return """

Reply in friendly, conversational English — like a knowledgeable best friend.
Be warm, occasionally witty, and direct. No corporate/robotic language."""

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _ensure_dir():
    _VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _store_path(vector_store_id: str) -> Path:
    return _VECTOR_STORE_DIR / vector_store_id


def _embeddings():
    global _embedding_model
    if _embedding_model is None:
        logger.info("[RAG] Loading embedding model")
        _embedding_model = HuggingFaceEmbeddings(model_name=_EMBEDDING_MODEL)
    return _embedding_model


def _llm():
    global _llm_model
    if _llm_model is None:
        logger.info("[RAG] Connecting to Ollama")
        _llm_model = Ollama(
            model=_OLLAMA_MODEL,
            base_url=_OLLAMA_URL,
            temperature=0.3,
            num_ctx=2048,       # reduced context = faster generation
            num_thread=8,
            num_predict=512,    # cap output length for speed
            timeout=60,
        )
    return _llm_model


def _load_vector_store(vector_store_id: str):
    if vector_store_id in _vector_store_cache:
        return _vector_store_cache[vector_store_id]

    store_path = _store_path(vector_store_id)

    if not store_path.exists():
        raise FileNotFoundError(f"Vector store '{vector_store_id}' not found")

    logger.info("[RAG] Loading vector store %s", vector_store_id)

    vector_store = FAISS.load_local(
        str(store_path),
        _embeddings(),
        allow_dangerous_deserialization=True
    )

    _vector_store_cache[vector_store_id] = vector_store
    return vector_store

# ─────────────────────────────────────────────
# PROMPT  (dynamic — language injected at runtime)
# ─────────────────────────────────────────────

_QA_TEMPLATE = """You are Shivansh's AI buddy — smart, warm, and a little witty.
You feel like a knowledgeable best friend who happens to have read every document ever.

Rules:
1. Use ONLY the context below to answer.
2. If the answer isn't there, say so honestly in a friendly way.
3. Reference page numbers when possible.
4. Keep it conversational — no robotic bullet-point dumps unless they genuinely help.
5. Use light humor or empathy when appropriate.
{language_instruction}

Context:
{context}

Question:
{question}

Answer:"""


def _build_prompt(lang: str) -> PromptTemplate:
    template = _QA_TEMPLATE.replace(
        "{language_instruction}",
        _language_instruction(lang)
    )
    return PromptTemplate(
        input_variables=["context", "question"],
        template=template
    )

# ─────────────────────────────────────────────
# DOCUMENT LOADERS  (multi-format)
# ─────────────────────────────────────────────

def _load_document(file_path: str):
    """Load PDF / CSV / image / Word / Excel → list[Document]"""
    path   = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return PyPDFLoader(str(path)).load()

    if suffix in (".doc", ".docx"):
        return UnstructuredWordDocumentLoader(str(path)).load()

    if suffix in (".xls", ".xlsx"):
        return UnstructuredExcelLoader(str(path)).load()

    if suffix == ".csv":
        return _load_csv(str(path))

    if suffix == ".txt":
        return _load_txt(str(path))

    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
        return _load_image(str(path))

    raise ValueError(f"Unsupported file type: {suffix}")


def _load_csv(csv_path: str):
    """
    Load a CSV file — each row becomes a Document.
    Handles both comma and semicolon separators.
    """
    import csv
    from langchain_core.documents import Document

    docs = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
            # Auto-detect delimiter
            sample = f.read(2048)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            reader  = csv.DictReader(f, dialect=dialect)
            headers = reader.fieldnames or []

            for i, row in enumerate(reader):
                # Convert row to readable text: "Column: Value, Column: Value …"
                parts = [f"{k}: {v}" for k, v in row.items() if v and v.strip()]
                text  = " | ".join(parts)
                if text.strip():
                    docs.append(Document(
                        page_content=text,
                        metadata={
                            "source":  csv_path,
                            "row":     i + 1,
                            "page":    i,
                            "columns": ", ".join(headers),
                        }
                    ))
    except Exception as e:
        logger.warning("[RAG] CSV parse error: %s", e)
        # Fallback: read raw text
        with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
        docs = [Document(page_content=text, metadata={"source": csv_path, "page": 0})]

    logger.info("[RAG] CSV loaded: %d rows from %s", len(docs), csv_path)
    return docs


def _load_txt(txt_path: str):
    """Load a plain text file."""
    from langchain_core.documents import Document
    with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return [Document(page_content=text, metadata={"source": txt_path, "page": 0})]


def _load_image(image_path: str):
    """OCR an image and return a list with one Document."""
    if not _OCR_AVAILABLE:
        raise RuntimeError(
            "Pillow and pytesseract are required for image processing. "
            "Run: pip install Pillow pytesseract"
        )

    from langchain_core.documents import Document

    img  = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang="eng+hin")  # English + Hindi OCR

    if not text.strip():
        text = "[No readable text found in image]"

    return [
        Document(
            page_content=text,
            metadata={"source": image_path, "page": 0}
        )
    ]

# ─────────────────────────────────────────────
# PROCESS FILE  (PDF / image / doc)
# ─────────────────────────────────────────────

def process_file(file_path: str, file_id: str) -> dict:
    """
    Ingest any supported file type into a FAISS vector store.
    Replaces the old process_pdf() — but process_pdf() still works as alias.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    _ensure_dir()

    logger.info("[RAG] Processing file %s", file_path)

    pages = _load_document(file_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP
    )

    chunks = splitter.split_documents(pages)

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
        chunk.metadata["file_id"]     = file_id

    vector_store = FAISS.from_documents(chunks, _embeddings())

    store_path = _store_path(file_id)
    vector_store.save_local(str(store_path))

    logger.info("[RAG] Vector store saved to %s", store_path)

    return {
        "page_count":       len(pages),
        "chunk_count":      len(chunks),
        "vector_store_id":  file_id
    }


# Backward-compat alias
def process_pdf(pdf_path: str, pdf_id: str) -> dict:
    return process_file(pdf_path, pdf_id)

# ─────────────────────────────────────────────
# QUERY
# ─────────────────────────────────────────────

def query(
    vector_store_id: str,
    question: str,
    chat_history:    Optional[list] = None,
    mode:            str = "document"   # "document" | "chat" | "web"
):
    start = time.monotonic()

    lang   = detect_language(question)
    logger.info("[RAG] Detected language: %s", lang)

    # ── Answer cache (skip for chat mode — always fresh) ─────────────────────
    if mode not in ("chat",):
        _cache_key = f"{vector_store_id}:{mode}:{lang}:{question.strip().lower()[:120]}"
        cached     = _answer_cache.get(_cache_key)
        if cached and (time.monotonic() - cached["ts"]) < _ANSWER_CACHE_TTL:
            logger.info("[RAG] Cache hit — returning instantly")
            return cached["result"]

    # ── Free chat mode ────────────────────────────────────────────────────────
    if mode == "chat":
        return _free_chat(question, lang, chat_history)

    # ── Forced web search ─────────────────────────────────────────────────────
    if mode == "web":
        result = web_answer(question, _llm(), lang)
        _answer_cache[_cache_key] = {"result": result, "ts": time.monotonic()}
        return result

    # ── Document RAG ──────────────────────────────────────────────────────────
    try:
        vector_store = _load_vector_store(vector_store_id)
    except FileNotFoundError:
        logger.info("[RAG] Vector store missing → Web search")
        return web_answer(question, _llm(), lang)

    docs_with_scores = vector_store.similarity_search_with_score(question, k=_TOP_K)

    if not docs_with_scores:
        logger.info("[RAG] No match → Web search")
        return web_answer(question, _llm(), lang)

    best_score = docs_with_scores[0][1]

    if best_score > _SCORE_THRESHOLD:
        logger.info("[RAG] Weak match (%.2f) → Web search", best_score)
        return web_answer(question, _llm(), lang)

    retriever = vector_store.as_retriever(
        search_type="mmr",
        search_kwargs={"k": _TOP_K, "fetch_k": 8}   # fetch_k reduced for speed
    )

    # Build conversation history pairs
    history = []
    if chat_history:
        msgs = [m for m in chat_history if m["role"] in ("user", "assistant")]
        i = 0
        while i < len(msgs) - 1:
            if msgs[i]["role"] == "user" and msgs[i + 1]["role"] == "assistant":
                history.append((msgs[i]["content"], msgs[i + 1]["content"]))
                i += 2
            else:
                i += 1

    chain = ConversationalRetrievalChain.from_llm(
        llm=_llm(),
        retriever=retriever,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": _build_prompt(lang)}
    )

    result = chain.invoke({"question": question, "chat_history": history})

    latency_ms = int((time.monotonic() - start) * 1000)

    seen_pages = set()
    sources    = []

    for doc in result.get("source_documents", []):
        page = int(doc.metadata.get("page", 0)) + 1
        if page not in seen_pages:
            seen_pages.add(page)
            snippet = doc.page_content[:250].strip()
            if len(doc.page_content) > 250:
                snippet += "..."
            sources.append({"page": page, "content": snippet})

    sources.sort(key=lambda s: s["page"])

    final = {
        "answer":     result["answer"].strip(),
        "sources":    sources,
        "latency_ms": latency_ms,
        "language":   lang,
        "mode":       "document",
    }

    # Store in cache for identical future questions
    _answer_cache[_cache_key] = {"result": final, "ts": time.monotonic()}

    return final


def _free_chat(question: str, lang: str, chat_history: Optional[list] = None) -> dict:
    """
    Friendly conversational chat with NO document context.
    Works like a smart buddy who can chat in Hindi/Hinglish/English.
    """
    start = time.monotonic()

    system_persona = (
        "You are a brilliant, funny, and warm AI buddy. "
        "You talk like a close friend — honest, helpful, sometimes witty. "
        "You can talk in Hindi, Hinglish, and English seamlessly based on what the user uses. "
        "Keep answers concise but genuinely useful. No corporate speak."
    )

    history_text = ""
    if chat_history:
        for m in chat_history[-6:]:      # last 6 messages for context
            role  = "User" if m["role"] == "user" else "You"
            history_text += f"\n{role}: {m['content']}"

    prompt = f"""{system_persona}

{_language_instruction(lang)}

Previous conversation:{history_text if history_text else ' (none)'}

User: {question}

You:"""

    answer = _llm().invoke(prompt)

    return {
        "answer":     answer.strip(),
        "sources":    [],
        "latency_ms": int((time.monotonic() - start) * 1000),
        "language":   lang,
        "mode":       "chat"
    }

# ─────────────────────────────────────────────
# DELETE / EXISTS
# ─────────────────────────────────────────────

def delete_store(vector_store_id: str):
    store_path = _store_path(vector_store_id)
    if store_path.exists():
        shutil.rmtree(store_path)
        _vector_store_cache.pop(vector_store_id, None)
        logger.info("[RAG] Deleted vector store %s", vector_store_id)


def store_exists(vector_store_id: str) -> bool:
    return _store_path(vector_store_id).exists()