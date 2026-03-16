"""
TC-EUSL Vapi.ai Voice Agent Backend
=====================================
Vapi handles: STT (speech-to-text) + TTS (text-to-speech) + call management
Our server handles: LLM answers using TC-EUSL knowledge base

Flow:
  Caller → Vapi Phone Number
         → Vapi STT transcribes speech
         → Vapi sends webhook to /vapi/chat
         → Our server queries Groq LLM with TC-EUSL knowledge
         → Returns answer to Vapi
         → Vapi TTS speaks answer to caller
"""

import os
import json
import time
import logging
from groq import Groq

logger = logging.getLogger("tc-eusl.vapi")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")

# ── TC-EUSL Knowledge Base ─────────────────────────────────────────────────────
KNOWLEDGE_BASE = """
=== TC-EUSL OFFICIAL KNOWLEDGE BASE ===

OVERVIEW:
Trincomalee Campus, Eastern University Sri Lanka.
Located at Konesapuri, Nilaveli Road, Trincomalee, Sri Lanka.
Website: https://www.tc.esn.ac.lk/

HISTORY:
- Started April 1993 as Trincomalee Affiliated University College (AUC)
- Initially: Diploma in English + Diploma in Accountancy and Finance
- Became Trincomalee Campus of Eastern University, June 2001
- 2008: Siddha Medicine introduced; Library relocated to Konesapuri
- 2018: Faculty of Technology + UGEE unit established
- 2022: Faculty of Graduate Studies approved
- 2023: Faculty of Siddha Medicine formally established
- 2024: Technopark established

VISION: World-recognized educational and research institution with academic excellence.
MISSION: Create, transform, disseminate knowledge through teaching, learning, research.

CONTACT:
- Address: Konesapuri, Nilaveli-31010, Trincomalee, Sri Lanka
- Phone: +94 26 2227410
- Fax: +94 26 2227411
- Email: rector@esn.ac.lk

RECTOR: Prof. K.T. Sundaresan, MBBS (Kel), MD (UOC), FRCP (Edin)

FACULTIES (5):
1. Faculty of Applied Science
2. Faculty of Communication and Business Studies
3. Faculty of Siddha Medicine
4. Faculty of Technology
5. Faculty of Graduate Studies

FACULTY OF APPLIED SCIENCE:
- 3-year English-medium degree, 6 semesters (~15 weeks each)
- BSc in Applied Physics and Electronics (Dept of Physical Science, est. 2014)
- Activities: Robotics, Electronics workshops, Green energy, School outreach

LIBRARY:
- Relocated to Konesapuri 2008
- New 4-story building opened 19 May 2017

SPECIAL UNITS:
- Staff Development Center: Teaching, leadership, AI training workshops
- UGEE (Gender Equity): Est. 2018, Coordinator: Mrs. S. Priyadharsan
  Email: coordinator_gee_tc@esn.ac.lk
- Unit of Industry and Community Linkages
- Strategic Planning Unit

RESEARCH: International Research Conference (TRInCo)
STUDENT ACTIVITIES: Skill Expo, Technopark (2024)

=== END ===
"""

# ── Vapi Assistant Configuration ──────────────────────────────────────────────
def get_vapi_assistant_config() -> dict:
    """
    Returns the full Vapi assistant configuration.
    This is sent to Vapi API to create/update the assistant.
    """
    return {
        "name": "TC-EUSL AI Receptionist",
        "model": {
            "provider": "custom-llm",
            "url": f"{os.getenv('BASE_URL', 'http://localhost:5000')}/vapi/llm",
            "model": "tc-eusl-groq",
            "systemPrompt": build_system_prompt(),
        },
        "voice": {
            "provider": "playht",
            "voiceId": "jennifer",        # clear female voice
            "speed": 1.0,
            "stability": 0.7,
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "multi",           # auto-detect Sinhala/English/Tamil
        },
        "firstMessage": (
            "Welcome to TC-EUSL, Trincomalee Campus of Eastern University Sri Lanka. "
            "How may I assist you today? You may speak in English, Sinhala, or Tamil."
        ),
        "endCallMessage": "Thank you for calling TC-EUSL. Have a wonderful day. Goodbye!",
        "endCallPhrases": ["goodbye", "bye", "that's all", "thank you bye",
                           "ස්තූතියි", "ඉවරයි", "நன்றி"],
        "maxDurationSeconds": 600,         # 10 minute max call
        "backgroundSound": "off",
        "backchannelingEnabled": False,
        "analysisPlan": {
            "summaryPrompt": "Summarize what the caller asked about TC-EUSL and what information was provided.",
            "structuredDataPrompt": "Extract: caller_language, topics_asked, satisfaction_level",
        },
    }


def build_system_prompt() -> str:
    return f"""You are the official AI phone receptionist for TC-EUSL (Trincomalee Campus of Eastern University Sri Lanka).

{KNOWLEDGE_BASE}

LANGUAGE RULE — CRITICAL:
- Detect the caller's language from their speech
- If Sinhala → reply ONLY in Sinhala
- If English → reply ONLY in English
- If Tamil  → reply ONLY in Tamil

VOICE CALL RULES:
- Maximum 2-3 short sentences — this is spoken aloud on a phone call
- No bullet points, no markdown, no asterisks, no lists
- Speak naturally and warmly like a helpful university receptionist
- If information is NOT in the knowledge base, say:
  "For more details, please contact us on +94 26 2227410 or email rector@esn.ac.lk"
- Never guess or invent information not in the knowledge base"""


# ── Groq LLM ──────────────────────────────────────────────────────────────────
def ask_groq_vapi(messages: list, max_tokens: int = 250) -> str:
    """Query Groq LLM with full conversation history from Vapi."""
    if not GROQ_API_KEY:
        return "I'm sorry, the AI service is not configured. Please call +94 26 2227410 directly."
    try:
        client = Groq(api_key=GROQ_API_KEY)

        # Build messages with system prompt
        full_messages = [
            {"role": "system", "content": build_system_prompt()}
        ] + messages

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=full_messages,
            temperature=0.3,
            max_completion_tokens=max_tokens,
            top_p=1,
            reasoning_effort="medium",
            stream=True,
            stop=None
        )

        full_text = ""
        for chunk in completion:
            delta = chunk.choices[0].delta.content
            if delta:
                full_text += delta

        return full_text.strip()

    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "I'm having technical difficulties. Please call +94 26 2227410 directly."


# ── Vapi API calls ─────────────────────────────────────────────────────────────
import requests

VAPI_BASE = "https://api.vapi.ai"

def vapi_headers() -> dict:
    return {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type":  "application/json"
    }


def create_vapi_assistant() -> dict:
    """Create the TC-EUSL assistant on Vapi and return assistant ID."""
    config = get_vapi_assistant_config()
    try:
        r = requests.post(
            f"{VAPI_BASE}/assistant",
            headers=vapi_headers(),
            json=config,
            timeout=15
        )
        if r.status_code in (200, 201):
            data = r.json()
            logger.info(f"Vapi assistant created: {data.get('id')}")
            return {"success": True, "id": data.get("id"), "data": data}
        return {"success": False, "error": r.text, "status": r.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_vapi_assistant(assistant_id: str) -> dict:
    """Update existing Vapi assistant config."""
    config = get_vapi_assistant_config()
    try:
        r = requests.patch(
            f"{VAPI_BASE}/assistant/{assistant_id}",
            headers=vapi_headers(),
            json=config,
            timeout=15
        )
        return {"success": r.status_code in (200, 201), "data": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_vapi_assistants() -> list:
    try:
        r = requests.get(f"{VAPI_BASE}/assistant", headers=vapi_headers(), timeout=10)
        if r.status_code == 200:
            return r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        return []
    except:
        return []


def get_vapi_calls(limit: int = 20) -> list:
    try:
        r = requests.get(
            f"{VAPI_BASE}/call?limit={limit}",
            headers=vapi_headers(), timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else data.get("data", [])
        return []
    except:
        return []


def get_vapi_phone_numbers() -> list:
    try:
        r = requests.get(f"{VAPI_BASE}/phone-number", headers=vapi_headers(), timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else data.get("data", [])
        return []
    except:
        return []


def make_outbound_call(to_number: str, assistant_id: str) -> dict:
    """Initiate an outbound call via Vapi."""
    try:
        r = requests.post(
            f"{VAPI_BASE}/call/phone",
            headers=vapi_headers(),
            json={
                "assistantId": assistant_id,
                "customer": {"number": to_number},
                "phoneNumberId": os.getenv("VAPI_PHONE_NUMBER_ID", "")
            },
            timeout=15
        )
        return {"success": r.status_code in (200, 201), "data": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_vapi_health() -> bool:
    return bool(VAPI_API_KEY)
