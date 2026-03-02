"""
PICT InC 2026 Chatbot — FastAPI + Groq LLM
Answers questions about the event using info.txt as the sole knowledge source.
"""

import os
import time
import logging
from pathlib import Path
from collections import OrderedDict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import AsyncGroq

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pictinc-chatbot")

# ---------------------------------------------------------------------------
# Load environment variables (.env for local dev)
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Groq API key handling — supports multiple comma-separated keys for fallback
# ---------------------------------------------------------------------------
_raw_keys = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS: list[str] = [k.strip() for k in _raw_keys.split(",") if k.strip()]

if not GROQ_API_KEYS:
    raise RuntimeError(
        "GROQ_API_KEY is not set. "
        "Set it in .env or as an environment variable. "
        "You can provide multiple keys separated by commas for fallback."
    )

logger.info("Loaded %d Groq API key(s)", len(GROQ_API_KEYS))

# ---------------------------------------------------------------------------
# Load info.txt once at startup
# ---------------------------------------------------------------------------
INFO_PATH = Path(__file__).parent / "info.txt"

if not INFO_PATH.exists() or INFO_PATH.stat().st_size == 0:
    raise RuntimeError(
        f"info.txt is missing or empty at {INFO_PATH}. "
        "This file is required for the chatbot to function."
    )

EVENT_INFO: str = INFO_PATH.read_text(encoding="utf-8")
logger.info("Loaded info.txt (%d characters)", len(EVENT_INFO))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL = "llama-3.1-8b-instant"
MAX_TOKENS = 400
TEMPERATURE = 0.1
API_TIMEOUT = 15  # seconds
RATE_LIMIT = 10  # requests per minute per IP
CACHE_MAX_SIZE = 100
PORT = int(os.getenv("PORT", "8000"))

# ---------------------------------------------------------------------------
# System prompt — injected with full event info on every request
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""You are the official assistant for PICT InC 2026, organized by Pune Institute of Computer Technology.

Rules you must ALWAYS follow:
1. Answer ONLY using the event information provided below.
2. If the answer is not in the provided information, respond EXACTLY with:
   "I don't have that information. Please contact inc2k26@gmail.com or visit www.pictinc.org"
3. Never make up facts, dates, fees, rules, or eligibility criteria.
4. Never answer questions unrelated to PICT InC 2026.
5. Be concise, clear, and professional.
6. If a user greets you, respond politely and offer to help with event-related questions.

--- EVENT INFORMATION ---
{EVENT_INFO}
--- END OF EVENT INFORMATION ---"""

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str

# ---------------------------------------------------------------------------
# In-memory rate limiter (IP → list of timestamps)
# ---------------------------------------------------------------------------
rate_limit_store: dict[str, list[float]] = {}

def is_rate_limited(ip: str) -> bool:
    """Return True if the IP has exceeded RATE_LIMIT requests in the last 60s."""
    now = time.time()
    window = now - 60

    # Prune old timestamps
    timestamps = rate_limit_store.get(ip, [])
    timestamps = [t for t in timestamps if t > window]
    rate_limit_store[ip] = timestamps

    if len(timestamps) >= RATE_LIMIT:
        return True

    timestamps.append(now)
    return False

# ---------------------------------------------------------------------------
# In-memory response cache (normalized question → answer)
# ---------------------------------------------------------------------------
response_cache: OrderedDict[str, str] = OrderedDict()

def normalize_question(q: str) -> str:
    """Lowercase and strip whitespace for cache key."""
    return q.strip().lower()

def cache_get(question: str) -> str | None:
    key = normalize_question(question)
    return response_cache.get(key)

def cache_set(question: str, answer: str) -> None:
    key = normalize_question(question)
    response_cache[key] = answer
    # Evict oldest entry if cache exceeds max size
    while len(response_cache) > CACHE_MAX_SIZE:
        response_cache.popitem(last=False)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="PICT InC 2026 Chatbot", version="1.0.0")

# CORS — allow all origins for embedding in the college website
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Groq API call with multi-key fallback
# ---------------------------------------------------------------------------
async def call_groq(question: str) -> str:
    """
    Call the Groq API with the user's question.
    Tries each API key in order; if one fails, falls back to the next.
    """
    last_error = None

    for idx, api_key in enumerate(GROQ_API_KEYS):
        client = AsyncGroq(api_key=api_key, timeout=API_TIMEOUT)
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            logger.warning("Groq key #%d failed: %s", idx + 1, str(e)[:120])
            continue

    # All keys exhausted
    raise last_error  # type: ignore[misc]

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "model": MODEL}


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    """Main chat endpoint — answers questions about PICT InC 2026."""

    # --- Rate limiting ---
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Please wait."},
        )

    # --- Input validation ---
    question = body.question.strip()
    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Question cannot be empty."},
        )
    question = question[:500]  # trim to max 500 characters

    # --- Cache check ---
    cached = cache_get(question)
    if cached is not None:
        logger.info(
            "CACHE HIT | q=%.100s | a=%.100s",
            question,
            cached,
        )
        return ChatResponse(answer=cached)

    # --- Call Groq LLM ---
    try:
        answer = await call_groq(question)
    except TimeoutError:
        logger.error("Groq API timed out for q=%.100s", question)
        return JSONResponse(
            status_code=504,
            content={"error": "Request timed out. Please try again."},
        )
    except Exception:
        logger.exception("Groq API error for q=%.100s", question)
        return JSONResponse(
            status_code=503,
            content={"error": "Service temporarily unavailable. Please try again."},
        )

    # --- Cache the response ---
    cache_set(question, answer)

    logger.info(
        "NEW CALL  | q=%.100s | a=%.100s",
        question,
        answer,
    )
    return ChatResponse(answer=answer)

# ---------------------------------------------------------------------------
# Startup log
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    logger.info(
        "PICT InC 2026 Chatbot started | model=%s | keys=%d | port=%d",
        MODEL,
        len(GROQ_API_KEYS),
        PORT,
    )

# ---------------------------------------------------------------------------
# Run with: uvicorn main:app --host 0.0.0.0 --port 8000
# ---------------------------------------------------------------------------
