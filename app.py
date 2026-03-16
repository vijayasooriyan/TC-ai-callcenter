"""
TC-EUSL Vapi.ai Flask Server
==============================
Endpoints:
  POST /vapi/webhook     ← Vapi sends all call events here
  POST /vapi/llm         ← Vapi calls our custom LLM endpoint
  GET  /vapi/calls       ← Fetch call history from Vapi API
  POST /vapi/setup       ← Create/update Vapi assistant
  GET  /api/status       ← System health check
  GET  /api/stats        ← DB stats
  POST /api/chat         ← Web chat
  GET  /api/live         ← SSE live events
  GET  /                 ← Dashboard
"""

import os, time, uuid, logging, json, queue, threading
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# ── Dirs & Logging ─────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "agent.log"))
    ]
)
logger = logging.getLogger("tc-eusl")

from vapi_agent import (ask_groq_vapi, build_system_prompt, check_vapi_health,
                         create_vapi_assistant, update_vapi_assistant,
                         get_vapi_assistants, get_vapi_calls,
                         get_vapi_phone_numbers, make_outbound_call,
                         VAPI_API_KEY, GROQ_API_KEY, GROQ_MODEL)
from database import (init_db, log_web_chat, get_stats, export_all,
                       log_system_event, upsert_session, log_turn, end_session)

# ── Config ──────────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")
_HERE    = os.path.dirname(os.path.abspath(__file__))
_TMPL    = os.path.join(_HERE, "templates")
os.makedirs(_TMPL, exist_ok=True)

init_db()

# ── Flask ───────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=_TMPL)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_headers(resp):
    resp.headers["ngrok-skip-browser-warning"]  = "true"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, ngrok-skip-browser-warning, Authorization"
    return resp

@app.route("/vapi/webhook",  methods=["OPTIONS"])
@app.route("/vapi/llm",      methods=["OPTIONS"])
@app.route("/api/status",    methods=["OPTIONS"])
@app.route("/api/stats",     methods=["OPTIONS"])
@app.route("/api/chat",      methods=["OPTIONS"])
def options_handler(): return "", 204

# ── Live SSE ────────────────────────────────────────────────────────────────────
_live_clients = []
_live_lock    = threading.Lock()

def push_live(event_type: str, data: dict):
    payload = json.dumps({"type": event_type, **data})
    with _live_lock:
        dead = []
        for q in _live_clients:
            try:    q.put_nowait(payload)
            except: dead.append(q)
        for q in dead: _live_clients.remove(q)

# ══════════════════════════════════════════════════════════════════════════════
#  VAPI WEBHOOKS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/vapi/webhook", methods=["POST"])
def vapi_webhook():
    """
    Vapi sends ALL call lifecycle events here.
    Event types: call-started, call-ended, transcript, function-call, hang, speech-update
    """
    try:
        data    = request.json or {}
        message = data.get("message", {})
        ev_type = message.get("type", data.get("type", "unknown"))
        call    = message.get("call", data.get("call", {}))
        call_id = call.get("id", data.get("callId", "unknown"))
        caller  = call.get("customer", {}).get("number", "unknown")

        logger.info(f"📨 Vapi webhook: {ev_type}  call={call_id}  caller={caller}")

        # ── Call Started ──────────────────────────────────────────────────────
        if ev_type == "call-started":
            upsert_session(f"vapi_{call_id}", call_id, caller)
            log_system_event("vapi_call_started", f"call_id={call_id} caller={caller}")
            push_live("call_start", {
                "call_sid": call_id, "caller": caller,
                "session_id": f"vapi_{call_id}",
                "time": time.strftime("%H:%M:%S"),
                "source": "vapi"
            })

        # ── Transcript (real-time speech) ─────────────────────────────────────
        elif ev_type == "transcript":
            transcript = message.get("transcript", "")
            role       = message.get("role", "")        # user or assistant
            if role == "user" and transcript:
                push_live("transcribed", {
                    "call_sid": call_id, "caller": caller,
                    "session_id": f"vapi_{call_id}",
                    "text": transcript, "language": "auto",
                    "confidence": "—", "whisper_ms": 0,
                    "time": time.strftime("%H:%M:%S"),
                    "source": "vapi"
                })
            elif role == "assistant" and transcript:
                push_live("answered", {
                    "call_sid": call_id, "caller": caller,
                    "session_id": f"vapi_{call_id}",
                    "question": "—", "answer": transcript,
                    "language": "auto",
                    "llm_source": "groq", "llm_model": GROQ_MODEL,
                    "llm_ms": 0, "total_ms": 0,
                    "time": time.strftime("%H:%M:%S"),
                    "source": "vapi"
                })

        # ── Call Ended ────────────────────────────────────────────────────────
        elif ev_type == "call-ended":
            ended_reason = message.get("endedReason", call.get("endedReason", "unknown"))
            duration     = call.get("duration", 0)
            summary      = message.get("analysis", {}).get("summary", "")

            end_session(f"vapi_{call_id}", ended_reason)
            log_system_event("vapi_call_ended",
                             f"call_id={call_id} reason={ended_reason} duration={duration}s")
            push_live("call_end", {
                "call_sid": call_id, "status": ended_reason,
                "duration_sec": duration, "summary": summary,
                "time": time.strftime("%H:%M:%S"),
                "source": "vapi"
            })

            # Save final transcript to DB
            transcript_obj = message.get("artifact", {}).get("transcript", "")
            if transcript_obj:
                log_turn(f"vapi_{call_id}", call_id, 1, caller,
                         None, transcript_obj, "auto", 0, 0,
                         "", "", GROQ_MODEL, "groq", 0, "", 0)

        # ── Speech Update ─────────────────────────────────────────────────────
        elif ev_type == "speech-update":
            status = message.get("status", "")
            if status == "started":
                push_live("speech_started", {
                    "call_sid": call_id, "caller": caller,
                    "time": time.strftime("%H:%M:%S"), "source": "vapi"
                })

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)

    return jsonify({"received": True}), 200


# ══════════════════════════════════════════════════════════════════════════════
#  VAPI CUSTOM LLM ENDPOINT (OpenAI-compatible)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/vapi/llm", methods=["POST"])
def vapi_llm():
    """
    Vapi calls this as a custom LLM (OpenAI-compatible format).
    We query Groq with TC-EUSL knowledge and return the answer.
    """
    t0   = time.time()
    data = request.json or {}

    messages  = data.get("messages", [])
    stream    = data.get("stream", False)
    call_id   = data.get("call", {}).get("id", "unknown")
    caller    = data.get("call", {}).get("customer", {}).get("number", "unknown")

    # Filter out system messages — we inject our own
    user_messages = [m for m in messages if m.get("role") != "system"]

    logger.info(f"🤖 LLM call from Vapi: {len(user_messages)} messages  call={call_id}")

    answer   = ask_groq_vapi(user_messages, max_tokens=250)
    duration = int((time.time() - t0) * 1000)

    logger.info(f"✅ LLM answered in {duration}ms: {answer[:80]}…")

    # Log last user message + answer to DB
    last_user = next((m["content"] for m in reversed(user_messages)
                      if m.get("role") == "user"), "")
    if last_user:
        upsert_session(f"vapi_{call_id}", call_id, caller, "auto")
        log_turn(f"vapi_{call_id}", call_id, 0, caller,
                 None, last_user, "auto", 0, 0,
                 "", answer, GROQ_MODEL, "groq", duration, answer, duration)

        push_live("answered", {
            "call_sid": call_id, "caller": caller,
            "session_id": f"vapi_{call_id}",
            "question": last_user, "answer": answer,
            "language": "auto",
            "llm_source": "groq", "llm_model": GROQ_MODEL,
            "llm_ms": duration, "total_ms": duration,
            "time": time.strftime("%H:%M:%S"),
            "source": "vapi"
        })

    # Return OpenAI-compatible response
    if stream:
        def generate():
            # Stream word by word for more natural speech
            words = answer.split()
            for i, word in enumerate(words):
                chunk = {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {"content": word + (" " if i < len(words)-1 else "")},
                        "finish_reason": None if i < len(words)-1 else "stop"
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        return Response(generate(), mimetype="text/event-stream")
    else:
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "model": GROQ_MODEL,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": len(answer.split()),
                      "total_tokens": len(answer.split())}
        })


# ══════════════════════════════════════════════════════════════════════════════
#  VAPI MANAGEMENT APIs
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/vapi/setup", methods=["POST"])
def vapi_setup():
    """Create or update the Vapi assistant."""
    data         = request.json or {}
    assistant_id = data.get("assistant_id", "")

    if assistant_id:
        result = update_vapi_assistant(assistant_id)
        action = "updated"
    else:
        result = create_vapi_assistant()
        action = "created"

    if result.get("success"):
        aid = result.get("data", {}).get("id", assistant_id)
        logger.info(f"Vapi assistant {action}: {aid}")
        return jsonify({"success": True, "action": action,
                        "assistant_id": aid, "data": result.get("data")})
    return jsonify({"success": False, "error": result.get("error")}), 400


@app.route("/vapi/assistants", methods=["GET"])
def vapi_assistants():
    return jsonify(get_vapi_assistants())


@app.route("/vapi/calls", methods=["GET"])
def vapi_call_list():
    limit = int(request.args.get("limit", 20))
    calls = get_vapi_calls(limit)
    return jsonify(calls)


@app.route("/vapi/phone_numbers", methods=["GET"])
def vapi_phone_numbers():
    return jsonify(get_vapi_phone_numbers())


@app.route("/vapi/call_outbound", methods=["POST"])
def vapi_call_outbound():
    data         = request.json or {}
    to_number    = data.get("to_number", "")
    assistant_id = data.get("assistant_id", "")
    if not to_number or not assistant_id:
        return jsonify({"error": "to_number and assistant_id required"}), 400
    result = make_outbound_call(to_number, assistant_id)
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
#  WEB CHAT + STATS + SSE
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data     = request.json or {}
    session  = data.get("session_id", str(uuid.uuid4()))
    lang     = data.get("language", "en")
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "No question"}), 400

    logger.info(f"📝 Chat request: lang={lang}, question={question[:60]}…")
    
    t0     = time.time()
    answer = ask_groq_vapi([{"role": "user", "content": question}], max_tokens=300)
    dur    = int((time.time() - t0) * 1000)

    logger.info(f"✅ Chat answered in {dur}ms: {answer[:80]}…")
    
    log_web_chat(session, lang, question, answer, GROQ_MODEL, "groq", dur)
    return jsonify({"answer": answer, "session_id": session,
                    "llm_source": "groq", "llm_model": GROQ_MODEL, "duration_ms": dur})


@app.route("/api/status", methods=["GET"])
def api_status():
    vapi_ok = check_vapi_health()
    groq_ok = bool(GROQ_API_KEY)
    return jsonify({
        "vapi_configured":  vapi_ok,
        "groq_configured":  groq_ok,
        "groq_model":       GROQ_MODEL,
        "base_url":         BASE_URL,
        "webhook_url":      f"{BASE_URL}/vapi/webhook",
        "llm_url":          f"{BASE_URL}/vapi/llm",
        "server_mode":      "vapi"
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(get_stats())


@app.route("/api/logs/export", methods=["GET"])
def api_export():
    return jsonify(export_all())


@app.route("/api/live")
def api_live():
    def stream():
        q = queue.Queue(maxsize=50)
        with _live_lock: _live_clients.append(q)
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'type':'heartbeat'})}\n\n"
        finally:
            with _live_lock:
                if q in _live_clients: _live_clients.remove(q)
    resp = Response(stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"]              = "no-cache"
    resp.headers["X-Accel-Buffering"]          = "no"
    resp.headers["ngrok-skip-browser-warning"] = "true"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/api/live_log")
def api_live_log():
    s = get_stats()
    return jsonify({"recent_turns": s.get("recent_turns", []),
                    "recent_sessions": s.get("recent_sessions", []),
                    "total_call_turns": s.get("total_call_turns", 0),
                    "total_sessions": s.get("total_sessions", 0)})


# ── Frontend ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    for path in [os.path.join(_TMPL, "index.html"),
                 os.path.join(_HERE, "index.html")]:
        if os.path.exists(path):
            return send_from_directory(os.path.dirname(path), "index.html")
    return ("<h2>TC-EUSL Vapi Agent ✓</h2>"
            "<p><a href='/api/status'>/api/status</a></p>"), 200


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*62)
    print("  TC-EUSL Vapi.ai Voice Agent")
    print("="*62)
    print(f"  Vapi Key   : {'✓ Set' if VAPI_API_KEY else '✗ Missing — add to .env'}")
    print(f"  Groq Key   : {'✓ Set' if GROQ_API_KEY else '✗ Missing — add to .env'}")
    print(f"  LLM URL    : {BASE_URL}/vapi/llm")
    print(f"  Webhook    : {BASE_URL}/vapi/webhook")
    print(f"  Dashboard  : http://127.0.0.1:5000")
    print("="*62 + "\n")
    app.run(debug=False, port=5000, threaded=True)
