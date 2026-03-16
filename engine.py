"""
Speech-to-Text : faster-whisper (free, local)
LLM            : Groq SDK — openai/gpt-oss-120b (free tier)
Fallback LLM   : requests-based Groq REST (if SDK unavailable)
"""

import os
import time
import logging

logger = logging.getLogger(__name__)

# ── STT: Faster-Whisper ───────────────────────────────────────────────────────
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        model_size = os.getenv("WHISPER_MODEL", "base")
        logger.info(f"Loading Whisper model: {model_size}")
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Whisper model loaded ✓")
    return _whisper_model


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio using faster-whisper. Returns text, language, confidence."""
    t0 = time.time()
    try:
        model = get_whisper_model()
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=None,          # auto-detect: en / si / ta
            task="transcribe",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        text = " ".join(seg.text for seg in segments).strip()
        return {
            "text":        text,
            "language":    info.language,
            "confidence":  round(info.language_probability, 3),
            "duration_ms": int((time.time() - t0) * 1000),
            "error":       None
        }
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        return {"text": "", "language": "en", "confidence": 0,
                "duration_ms": 0, "error": str(e)}


# ── LLM: Groq SDK ─────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def ask_groq(prompt: str, max_tokens: int = 300) -> dict:
    """
    Query Groq using the official Groq SDK.
    Model: openai/gpt-oss-120b with medium reasoning.
    """
    if not GROQ_API_KEY:
        return {"text": "", "error": "GROQ_API_KEY not set in .env",
                "source": "groq", "model": GROQ_MODEL, "duration_ms": 0}
    t0 = time.time()
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,              # lower = more factual answers
            max_completion_tokens=max_tokens,
            top_p=1,
            reasoning_effort="medium",    # as in your snippet
            stream=True,
            stop=None
        )

        # Collect streamed chunks into full response
        full_text = ""
        for chunk in completion:
            delta = chunk.choices[0].delta.content
            if delta:
                full_text += delta

        full_text = full_text.strip()
        duration_ms = int((time.time() - t0) * 1000)

        if full_text:
            logger.info(f"Groq answered in {duration_ms}ms: {full_text[:80]}…")
            return {
                "text":        full_text,
                "model":       GROQ_MODEL,
                "source":      "groq",
                "duration_ms": duration_ms,
                "error":       None
            }
        else:
            return {"text": "", "error": "Empty response from Groq",
                    "source": "groq", "model": GROQ_MODEL, "duration_ms": duration_ms}

    except Exception as e:
        logger.error(f"Groq SDK error: {e}")
        return {"text": "", "error": str(e),
                "source": "groq", "model": GROQ_MODEL,
                "duration_ms": int((time.time() - t0) * 1000)}


# ── Ollama fallback (optional local LLM) ─────────────────────────────────────
OLLAMA_BASE  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

def ask_ollama(prompt: str, max_tokens: int = 300) -> dict:
    """Query local Ollama — used only if GROQ_API_KEY is not set."""
    import requests
    t0 = time.time()
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": 0.3}
            },
            timeout=30
        )
        if resp.status_code == 200:
            text = resp.json().get("response", "").strip()
            return {"text": text, "model": OLLAMA_MODEL, "source": "ollama",
                    "duration_ms": int((time.time() - t0) * 1000), "error": None}
        return {"text": "", "error": f"Ollama HTTP {resp.status_code}",
                "source": "ollama", "model": OLLAMA_MODEL, "duration_ms": 0}
    except Exception as e:
        return {"text": "", "error": str(e), "source": "ollama",
                "model": OLLAMA_MODEL, "duration_ms": 0}


# ── Main LLM entry point ──────────────────────────────────────────────────────
def ask_llm(prompt: str, max_tokens: int = 300) -> dict:
    """
    Priority:
      1. Groq SDK (openai/gpt-oss-120b) — if GROQ_API_KEY is set
      2. Ollama (local)                  — fallback
      3. Hard-coded message              — last resort
    """
    # 1. Groq first (your preferred model)
    if GROQ_API_KEY:
        result = ask_groq(prompt, max_tokens)
        if result["error"] is None and result["text"]:
            return result
        logger.warning(f"Groq failed: {result['error']} — trying Ollama…")

    # 2. Ollama fallback
    result = ask_ollama(prompt, max_tokens)
    if result["error"] is None and result["text"]:
        return result

    logger.error("All LLMs failed — returning hard fallback")

    # 3. Hard fallback
    return {
        "text":        "I'm sorry, I'm having technical difficulties. Please call us on +94 26 2227410.",
        "model":       "fallback",
        "source":      "hardcoded",
        "duration_ms": 0,
        "error":       "All LLMs failed"
    }


# ── Health checks ─────────────────────────────────────────────────────────────
def check_ollama_health() -> bool:
    import requests
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return r.status_code == 200
    except:
        return False

def check_groq_health() -> bool:
    return bool(GROQ_API_KEY)

def list_ollama_models() -> list:
    import requests
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except:
        pass
    return []
