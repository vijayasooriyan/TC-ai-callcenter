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

# ── TC-EUSL Knowledge Base (MULTILINGUAL) ─────────────────────────────────────
KNOWLEDGE_BASE = """
═══════════════════════════════════════════════════════════════════════════════
                    TC-EUSL MULTILINGUAL KNOWLEDGE BASE
═══════════════════════════════════════════════════════════════════════════════

【 ENGLISH 】
═══════════════════════════════════════════════════════════════════════════════
OVERVIEW:
Trincomalee Campus, Eastern University Sri Lanka
Location: Konesapuri, Nilaveli Road, Trincomalee
Website: https://www.tc.esn.ac.lk/

CONTACT:
- Address: Konesapuri, Nilaveli-31010, Trincomalee, Sri Lanka
- Phone: +94 26 2227410
- Fax: +94 26 2227411
- Email: rector@esn.ac.lk

RECTOR: Prof. K.T. Sundaresan

FACULTIES:
1. Faculty of Applied Science
2. Faculty of Communication and Business Studies
3. Faculty of Siddha Medicine
4. Faculty of Technology
5. Faculty of Graduate Studies

LIBRARY:
- New 4-story building at Konesapuri
- Open: Monday-Friday 8 AM - 8 PM, Saturday 8 AM - 5 PM

KEY INFORMATION:
- Established: 1993
- Campus became university campus: June 2001
- Phone to call: +94 26 2227410

═══════════════════════════════════════════════════════════════════════════════
【 සිංහල - SINHALA 】
═══════════════════════════════════════════════════════════════════════════════
සාරාංශ:
ට්‍රින්කොමාලි校園, නැගෙනහිර විශ්වවිද්‍යාලය ශ්‍රී ලංකා
ස්ථානය: කොනෙසපුරි, නිලාවේලි පාර, ට්‍රින්කොමාලි

සම්බන්ධතා තොරතුරු:
- ඉmail: rector@esn.ac.lk
- දුරකතනය: +94 26 2227410
- FAX: +94 26 2227411
- ලිපිනය: කොනෙසපුරි, නිලාවේලි-31010, ට්‍රින්කොමාලි, ශ්‍රී ලංකා

කතිපයේ:
ප්‍රිස. කේ.ටී. සුන්දරසන්

ශිල්පවලි:
1. ව්‍යවහාරික විද්‍‍යා ශිල්පය
2. සන්නිවේදන හා ව්‍යාපාර අධ්‍යයන ශිල්පය
3. සිද්ධ ඖෂධ ශිල්පය
4. තාක්‍ෂණ ශිල්පය
5. උচ්චවිද්‍යා අධ්‍යයන ශිල්පය

පුස්තකාලය:
- කොනෙසපුරිගේ ඉතිරි බිම ගොඩනැගිල්ල
- වරින්: සඳුදා-සිකුරාදා 8 සීයර ගෙවල් - 8 සීයර සන්ධ්‍යා, සෙනසුරාදා 8 සීයර ගෙවල් - 5 සීයර සන්ධ්‍යා

ප්‍රධාන තොරතුරු:
- ස්ථාපිත: 1993
- ශිල්පය විශ්වවිද්‍යාලය ශිල්පයක් බවට පත්: 2001 ජුනි
- ඇමතීමට දුරකතනය: +94 26 2227410

═══════════════════════════════════════════════════════════════════════════════
【 தமிழ் - TAMIL 】
═══════════════════════════════════════════════════════════════════════════════
கண்ணோட்டம்:
திரிங்கோமாலி வளாகம், கிழக்கு பல்கலைக்கழகம் இலங்கை
இடம்: கோனெசபுரி, நிலாவேலி சாலை, திரிங்கோமாலி

தொடர்பு தகவல்:
- முகவரி: கோனெசபுரி, நிலாவேலி-31010, திரிங்கோமாலி, இலங்கை
- தொலைபேசி: +94 26 2227410
- ஃபாக்ஸ்: +94 26 2227411
- மின்னஞ்சல்: rector@esn.ac.lk

சாளர:
பேராசிரியர் கே.டி. சுந்தரசன்

பீடங்கள்:
1. பயன்பாட்டு அறிவியல் பீடம்
2. தொடர்புப் பாடல் மற்றும் வணிக பட்டங்கள் பீடம்
3. சித்த மருத்துவ பீடம்
4. தொழில்நுட்ப பீடம்
5. முன்னுரைப்பு-கல்விப் பீடம்

நூலகம்:
- கோனெசபுரிக்கு சமீபத்திய நான்கு-தளம் கட்டடம்
- நேரம்: திங்கட்கிழமை-வெள்ளிக்கிழமை 8 AM - 8 PM, சனிக்கிழமை 8 AM - 5 PM

முக்கிய தகவல்:
- நிறுவப்பட்டது: 1993
- வளாகம் பல்கலைக்கழக பல்கலைக்கழகமாக: 2001 ஜூன்
- அழைக்க மொபைல்: +94 26 2227410

═══════════════════════════════════════════════════════════════════════════════

KEY RESPONSE EXAMPLES (AI should use these patterns):

ENGLISH QUESTION: "What is the contact number?"
ENGLISH ANSWER: "The contact number is +94 26 2227410. You can call us anytime."

SINHALA QUESTION: "දුරකතනය?"
SINHALA ANSWER: "දුරකතනය +94 26 2227410 ය. ඔබට ඕනෑකම වේලාවක අපට ඇමතිය හැක."

TAMIL QUESTION: "தொலைபேசி எண்?"
TAMIL ANSWER: "தொலைபேசி எண் +94 26 2227410. நீங்கள் எப்போது வேண்டுமானாலும் அழைக்கலாம்."

═══════════════════════════════════════════════════════════════════════════════
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
    return f"""YOU ARE A MULTILINGUAL AI RECEPTIONIST FOR TC-EUSL UNIVERSITY.

{KNOWLEDGE_BASE}

CRITICAL LANGUAGE RULES - FOLLOW 100% STRICTLY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 LANGUAGE DETECTION (EXACTLY):
1️⃣ If caller speaks SINHALA (ක, ල, று, etc.) → RESPOND ONLY IN SINHALA සිංහල
2️⃣ If caller speaks TAMIL (க, ல, ர, etc.) → RESPOND ONLY IN TAMIL தமிழ்
3️⃣ If caller speaks ENGLISH (a, b, c, etc.) → RESPOND ONLY IN ENGLISH

DO NOT MIX LANGUAGES. DO NOT TRANSLATE. MATCH THE CALLER'S LANGUAGE 100%.

🔴 RESPONSE FORMAT:
- 2-3 short sentences MAXIMUM (this is a phone call)
- Speak naturally like a friendly receptionist
- Use simple, clear words
- NO bullet points, NO lists, NO special symbols

🔴 EXAMPLE RESPONSES:

Question in ENGLISH: "What is your contact number?"
Answer ONLY in ENGLISH: "The contact number is +94 26 2227410. You can call us anytime during business hours."

Question in SINHALA: "දුරකතනය?"
Answer ONLY in SINHALA: "දුරකතනය +94 26 2227410 ය. ඔබට ඕනෑකම කාලයක අපට ඇමතිය හැක."

Question in TAMIL: "தொலைபேசி எண்?"
Answer ONLY in TAMIL: "தொலைபேசி எண் +94 26 2227410. நீங்கள் எப்போது வேண்டுமானாலும் அழைக்கலாம்."

🔴 IF INFORMATION NOT FOUND:
- English: "For more information, please call us on +94 26 2227410."
- Sinhala: "වැඩි තොරතුරු සඳහා කරුණාකර +94 26 2227410 ට අපට ඇමතින්න."
- Tamil: "மேலும் விசேஷங்களுக்கு +94 26 2227410 என அழைக்கவும்."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


# ── Groq LLM ──────────────────────────────────────────────────────────────────
def ask_groq_vapi(messages: list, max_tokens: int = 250) -> str:
    """Query Groq LLM with full conversation history from Vapi."""
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not configured")
        return "I'm sorry, the AI service is not configured. Please call +94 26 2227410 directly."
    try:
        client = Groq(api_key=GROQ_API_KEY)

        # Build messages with system prompt
        full_messages = [
            {"role": "system", "content": build_system_prompt()}
        ] + messages

        logger.info(f"Calling Groq with {len(messages)} messages, model={GROQ_MODEL}")

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=full_messages,
            temperature=0.3,
            max_completion_tokens=max_tokens,
            top_p=1,
            stream=True,
            stop=None
        )

        full_text = ""
        for chunk in completion:
            try:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        full_text += delta.content
            except AttributeError as ae:
                logger.warning(f"Chunk parsing warning: {ae}")
                continue

        if not full_text.strip():
            logger.warning("Empty response from Groq")
            return "I didn't get a response from the AI. Please try again."

        logger.info(f"Groq answered: {full_text[:100]}…")
        return full_text.strip()

    except Exception as e:
        logger.error(f"Groq error: {type(e).__name__}: {str(e)}", exc_info=True)
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

