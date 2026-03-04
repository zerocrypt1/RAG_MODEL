"""
app/services/web_search_service.py

Enhanced web search with:
• DuckDuckGo API + HTML scraping fallback
• Multilingual answer generation (Hindi / Hinglish / English)
• Human-like response style
"""

import requests
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _language_note(lang: str) -> str:
    """
    Strong language rule with examples — Mistral needs this to actually follow it.
    """
    if lang == "hindi":
        return """══ STRICT RULE: REPLY IN HINDI ONLY ══
User ne Hindi mein likha hai. POORA reply SIRF Hindi (Devanagari) mein dena.
Ek bhi English sentence mat likhna. Tone: dost jaisi, warm, simple."""

    if lang == "hinglish":
        return """══ STRICT RULE: REPLY IN HINGLISH ONLY ══
User Hinglish use kar raha hai (Hindi + English mix).
PURE ENGLISH reply karna BILKUL GALAT hai — Hinglish mein hi reply karna hai.

Hinglish = English words + Hindi fillers jaise: yaar, bhai, toh, hai, kya,
matlab, dekh, arre, aur, nahi, sach mein, etc.

EXAMPLES:
Q: "suno i love you"
A: "Arre yaar, 'I love you' ek bahut deep feeling hai! Kisi ke liye genuine
    care aur affection feel karna — wahi toh real love hai na. Dil se feel hona
    chahiye, sirf words nahi. Kisi ko bolne ka plan hai? 😄"

Q: "weather kaisa hai aaj"
A: "Oye bhai, abhi check kiya — tera area mein aaj thodi clouds hain aur
    temperature around 28°C hai. Evening mein rain ho sakti hai, umbrella
    saath rakhna! ☂️ Kahan jaana hai aaj?"

Q: "what is AI"
A: "Bhai AI matlab Artificial Intelligence — basically computers ko smart
    banana taaki woh insaan jaisi thinking kar sakein. Netflix recommendations,
    Google translate, face recognition — yeh sab AI hai yaar! 🤖"

AB ANSWER HINGLISH MEIN DE. Pure English = WRONG."""

    return "Reply in friendly, conversational English — like a knowledgeable best friend. Be warm, direct, no corporate tone."


def _ddg_instant(question: str) -> str | None:
    """Try DuckDuckGo Instant Answer API."""
    try:
        r = requests.get(
            "https://api.duckduckgo.com",
            params={"q": question, "format": "json", "no_redirect": 1},
            timeout=8
        )
        data = r.json()
        return data.get("AbstractText") or data.get("Answer") or None
    except Exception:
        return None


def _ddg_html_search(question: str, n: int = 3) -> str:
    """
    Scrape DuckDuckGo HTML results for snippets when the instant API
    returns nothing.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": question},
            headers=headers,
            timeout=10
        )
        soup    = BeautifulSoup(r.text, "html.parser")
        results = soup.select(".result__snippet")[:n]
        snippets = [s.get_text(strip=True) for s in results if s.get_text(strip=True)]
        return " ".join(snippets) if snippets else ""
    except Exception as e:
        logger.warning("[WebSearch] HTML scrape failed: %s", e)
        return ""


def web_answer(question: str, llm, lang: str = "english") -> dict:
    """
    Search the web and generate a human-like answer in the right language.
    """
    # 1. Try instant API
    text = _ddg_instant(question)

    # 2. Fall back to HTML snippets
    if not text:
        text = _ddg_html_search(question)

    if not text:
        text = "No relevant information found on the web."

    lang_note = _language_note(lang)

    prompt = f"""{lang_note}

You are a smart, friendly AI buddy helping a user.

Web search result:
\"\"\"
{text[:800]}
\"\"\"

Use the above result to answer the question naturally — don't copy-paste it.
Explain it like a friend would. Keep it concise but useful.

User's question: {question}

Your reply ({lang} only):"""

    try:
        response = llm.invoke(prompt)
        answer   = response.strip() if isinstance(response, str) else str(response).strip()
    except Exception as e:
        logger.error("[WebSearch] LLM invoke failed: %s", e)
        answer = text[:500]

    return {
        "answer":   answer,
        "sources":  [{"page": "web", "content": text[:250]}],
        "latency_ms": 0,
        "language": lang,
        "mode":     "web"
    }