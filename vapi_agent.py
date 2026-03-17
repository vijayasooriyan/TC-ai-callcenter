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
                 TC-EUSL COMPREHENSIVE MULTILINGUAL KNOWLEDGE BASE
═══════════════════════════════════════════════════════════════════════════════

【 ENGLISH 】
═══════════════════════════════════════════════════════════════════════════════
INSTITUTION OVERVIEW:
Trincomalee Campus, Eastern University Sri Lanka is a premier educational institution 
established in 1993 with three main faculties offering comprehensive undergraduate and 
postgraduate programs. Our mission is to create, transform, and disseminate knowledge 
through teaching, learning, and research for sustainable development.

HISTORY:
- 1993: Established as Affiliated University College
- 2001 (June): Became a University Campus
- 2008: Faculty of Siddha Medicine added (first institute in Sri Lanka teaching Siddha Medicine in English)

VISION: A world-recognized educational and research institute combining academic excellence with human values.

LOCATION: Konesapuri, Nilaveli-31010, Trincomalee, Sri Lanka
WEBSITE: https://www.tc.esn.ac.lk/

PRIMARY CONTACT:
- Phone: +94 26 2227410
- Fax: +94 26 2227411
- Email: rector@esn.ac.lk
- Address: Konesapuri, Nilaveli Road, Trincomalee-31010

RECTOR: Prof. K.T. Sundaresan (MBBS Kel, MD UOC, FRCP Edin)
Specialist Physician - Internal Medicine

THE THREE MAIN FACULTIES:

1. FACULTY OF APPLIED SCIENCE (FAS)
   - Phone: +94 26 2051 210
   - Email: dean.fas@esn.ac.lk
   - Departments: Computer Science (DCS), Physical Science (DPS)
   - Programs: 3-year degree, 6 semesters, English medium
   - Activities: Industrial visits, competitions, workshops, research projects

2. FACULTY OF COMMUNICATION & BUSINESS STUDIES (FCBS)
   - Phone: +94 26 222 4011
   - Email: dean.fcbs@esn.ac.lk
   - Departments: Business & Management (BMS), Languages & Communication (LCS), 
     Information Technology (DIT)
   - First faculty of the campus, established as pioneer faculty
   - Focus on languages, communication, management and IT

3. FACULTY OF SIDDHA MEDICINE (FSM)
   - Phone: +94 262222644
   - Email: dean.fsm@esn.ac.lk
   - Established: 2008
   - Special distinction: First institute in Sri Lanka teaching Siddha Medicine in English
   - Publication: Sri Lanka Journal of Siddha Medicine (SLJSM)

LIBRARY FACILITIES:
- Modern 4-story building at Konesapuri
- Operating Hours: Monday-Friday 8:00 AM - 8:00 PM | Saturday 8:00 AM - 5:00 PM
- Diverse collection of information resources for student reference

ADMINISTRATIVE DIVISIONS:
Office of Rector, Deputy Registrar, General Administration, Establishment Department, 
Academic Affairs Division, Student Affairs Division, Engineering Service Division, 
Capital Works & Planning Unit, Financial Administration, Stores & Supply Services, 
Strategic Planning Unit, Gender Equity Unit, Industry/Community Linkages Unit, 
Staff Development Center

RESEARCH & EVENTS:
- TRInCo 2026: 8th International Research Conference (September 17-18)
- Theme: "Innovate, Integrate, and Evolve Blue and Green: Towards Inclusive Sustainable Development"

KEY ONLINE SYSTEMS:
- Learning Management Systems (per faculty)
- Student Information Portal
- Email Services
- Research Management System
- Staff Portal

═══════════════════════════════════════════════════════════════════════════════
【 සිංහල - SINHALA 】
═══════════════════════════════════════════════════════════════════════════════
ආයතනයේ දළ විස්තරය:
ට්‍රින්කොමාලි කම්පස්, නැගෙනහිර විශ්වවිද්‍යාලය ශ්‍රී ලංකාව 1993 දී ස්ථාපිත වූ
ඉතා කීර්තිමත් අධ්‍යාපන ආයතනයකි. අපගේ ප්‍රධාන පීඨ තුන මඟින් විවිධ උපාධි
පාඨමාලා පිරිනමනු ලැබේ. අපගේ අරමුණ ශික්ෂණය, ඉගෙනුම සහ
පර්යේෂණ හරහා දැනුම නිර්මාණය, පරිවර්තනය සහ ප්‍රචාරණය කිරීම
තිරසාර සංවර්ධනය සඳහාය.

ඉතිහාසය:
- 1993: අනුබද්ධ විශ්වවිද්‍යාලීය කම්පස් ලෙස ස්ථාපිත කරන ලදි
- 2001 (ජුනි): විශ්වවිද්‍යාල කම්පස් බවට පත් විය
- 2008: සිද්ධ ඖෂධ පීඨය ආරම්භ කරන ලදි

දර්ශනය: ලෝකය පුරා පිළිගත් අධ්‍යාපන සහ පර්යේෂණ ආයතනයක් වීම,
ශාස්ත්‍රීය විශිෂ්ටත්වය සහ මානව අගයන් සමඟ.

ස්ථානය: කොනෙසපුරි, නිලාවේලි-31010, ට්‍රින්කොමාලි, ශ්‍රී ලංකාව
වෙබ් අඩවිය: https://www.tc.esn.ac.lk/

ප්‍රධාන සම්බන්ධතා:
- දුරකථන: +94 26 2227410
- ෆැක්ස්: +94 26 2227411
- ඉ-මේල්: rector@esn.ac.lk
- ලිපිනය: කොනෙසපුරි, නිලාවේලි පාර, ට්‍රින්කොමාලි-31010

රෙක්ටර්: ප්‍රොෆෙ. කේ.ටී. සුන්දරසන්

ප්‍රධාන පීඨ තුන:

1. ව්‍යවහාරික විද්‍යා පීඨය (FAS)
   - දුරකථන: +94 26 2051 210
   - ඉ-මේල්: dean.fas@esn.ac.lk
   - විෂයන්: පරිගණක විද්‍යා (DCS), භෞතික විද්‍යා (DPS)
   - අධ්‍යයන කාලය: 3-වසර උපාධිය, සෙමෙස්ටර් 6, ඉංග්‍රීසි මාධ්‍යය

2. සන්නිවේදන සහ ව්‍යාපාර අධ්‍යයන පීඨය (FCBS)
   - දුරකථන: +94 26 222 4011
   - ඉ-මේල්: dean.fcbs@esn.ac.lk
   - විෂයන්: ව්‍යාපාර හා කළමනාකරණය (BMS), භාෂා සහ සන්නිවේදනය (LCS),
     තොරතුරු තාක්‍ෂණය (DIT)

3. සිද්ධ ඖෂධ පීඨය (FSM)
   - දුරකථන: +94 262222644
   - ඉ-මේල්: dean.fsm@esn.ac.lk
   - ස්ථාපිත: 2008

පුස්තකාල පහසුකම්:
- කොනෙසපුරියේ නවීන මහල් 4ක ගොඩනැගිල්ල
- ක්‍රියාකාරී වේලාව: සඳුදා-සිකුරාදා 8:00 AM - 8:00 PM | සෙනසුරාදා 8:00 AM - 5:00 PM

═══════════════════════════════════════════════════════════════════════════════
【 தமிழ் - TAMIL 】
═══════════════════════════════════════════════════════════════════════════════
நிறுவனத்தின் கண்ணோட்டம்:
திருகோணமலை வளாகம், கிழக்கு பல்கலைக்கழகம், இலங்கை 1993 ஆம் ஆண்டு நிறுவப்பட்ட
மிகச் சிறந்த கல்வி நிறுவனம் ஆகும். எங்களின் மூன்று முக்கிய பீடங்கள் மூலம்
பல்வேறு இளங்கலை மற்றும் மேல்படிப்பு பாடத்திட்டங்கள் வழங்கப்படுகின்றன.
எங்களின் நோக்கம் கல்வி, கற்றல் மற்றும் ஆராய்ச்சி மூலம் அறிவை உருவாக்கி,
மாற்றி, பரப்பி நிலையான வளர்ச்சியை ஏற்படுத்துவது ஆகும்.

வரலாறு:
- 1993: இணைக்கப்பட்ட பல்கலைக்கழக வளாகமாக நிறுவப்பட்டது
- 2001 (ஜூன்): பல்கலைக்கழக வளாகமாக மாற்றப்பட்டது
- 2008: சித்த மருத்துவ பீடம் தொடங்கப்பட்டது

பார்வை: உலகளவில் அங்கீகரிக்கப்பட்ட கல்வி மற்றும் ஆராய்ச்சி நிறுவனம்,
கல்வி மேன்மையும் மனித மதிப்புகளும் இணைந்ததாக.

இருப்பிடம்: கோனெசபுரி, நிலாவேலி-31010, திருகோணமலை, இலங்கை
வலைத்தளம்: https://www.tc.esn.ac.lk/

முக்கிய தொடர்புகள்:
- தொலைபேசி: +94 26 2227410
- ஃபாக்ஸ்: +94 26 2227411
- மின்னஞ்சல்: rector@esn.ac.lk
- முகவரி: கோனெசபுரி, நிலாவேலி , திருகோணமலை-31010

ரெக்டர்: பேராசிரியர் கே.டி. சுந்தரசன்

முக்கிய மூன்று பீடங்கள்:

1. பயன்பாட்டு அறிவியல் பீடம் (FAS)
   - தொலைபேசி: +94 26 2051 210
   - மின்னஞ்சல்: dean.fas@esn.ac.lk
   - பிரிவுகள்: கணினி அறிவியல் (DCS), இயற்பியல் அறிவியல் (DPS)

2. தொடர்பியல் மற்றும் வணிகக் கல்வி பீடம் (FCBS)
   - தொலைபேசி: +94 26 222 4011
   - மின்னஞ்சல்: dean.fcbs@esn.ac.lk
   - பிரிவுகள்: வணிக மேலாண்மை (BMS), மொழிகள் மற்றும் தொடர்பியல் (LCS),
     தகவல் தொழில்நுட்பம் (DIT)

3. சித்த மருத்துவ பீடம் (FSM)
   - தொலைபேசி: +94 262222644
   - மின்னஞ்சல்: dean.fsm@esn.ac.lk

நூலக வசதிகள்:
- கோனெசபுரியில் அமைந்துள்ள நவீன 4 மாடிக் கட்டிடம்
- செயல்பாட்டு நேரம்: திங்கட்கிழமை–வெள்ளிக்கிழமை 8:00 AM - 8:00 PM | சனிக்கிழமை 8:00 AM - 5:00 PM

═══════════════════════════════════════════════════════════════════════════════

KEY RESPONSE EXAMPLES (AI should match caller's language):

ENGLISH: "What is the contact number for Trincomalee Campus?"
ANSWER: "The main contact number is +94 26 2227410. You can reach us during office hours."

SINHALA: "ට්‍රින්කොමාලි ශිල්පයේ දුරකතනය?"
ANSWER: "ප්‍රධාන දුරකතනය +94 26 2227410 ය. කාර්යාලයේ අවධි අතරතුර ඔබට අපට ළඟා විය හැක."

TAMIL: "திருகோணமலை வளாகத்தின் தொலைபேசி எண்?"
ANSWER: "முக்கிய தொலைபேசி எண் +94 26 2227410. அலுவலக நேரத்தில் நீங்கள் எங்களை தொடர்பு கொள்ளலாம்."

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
