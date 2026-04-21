"""
SQLite database layer for TC-EUSL call logging.
"""
import sqlite3
import datetime
import os

DB_PATH = os.getenv("DB_PATH", "tc_eusl_calls.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS call_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT UNIQUE NOT NULL,
            call_sid        TEXT,
            caller_number   TEXT,
            started_at      TEXT NOT NULL,
            ended_at        TEXT,
            total_turns     INTEGER DEFAULT 0,
            primary_lang    TEXT DEFAULT 'en',
            status          TEXT DEFAULT 'active',
            recording_url   TEXT
        );

        CREATE TABLE IF NOT EXISTS call_turns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            call_sid        TEXT,
            turn_number     INTEGER DEFAULT 1,
            caller_number   TEXT,
            raw_audio_path  TEXT,
            whisper_text    TEXT,
            whisper_lang    TEXT,
            whisper_conf    REAL,
            whisper_ms      INTEGER,
            llm_prompt      TEXT,
            llm_response    TEXT,
            llm_model       TEXT,
            llm_source      TEXT,
            llm_ms          INTEGER,
            tts_text        TEXT,
            timestamp       TEXT NOT NULL,
            total_ms        INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS web_chat_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            language        TEXT DEFAULT 'en',
            user_question   TEXT NOT NULL,
            ai_response     TEXT NOT NULL,
            llm_model       TEXT,
            llm_source      TEXT,
            llm_ms          INTEGER,
            timestamp       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT,
            details     TEXT,
            timestamp   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT,
            call_sid        TEXT,
            caller_name     TEXT,
            caller_number   TEXT,
            booking_date    TEXT NOT NULL,
            booking_time    TEXT NOT NULL,
            faculty         TEXT,
            department      TEXT,
            purpose         TEXT,
            notes           TEXT,
            status          TEXT DEFAULT 'confirmed',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );
        """)


def log_system_event(event_type: str, details: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO system_events (event_type, details, timestamp) VALUES (?,?,?)",
            (event_type, details, datetime.datetime.now().isoformat())
        )


def upsert_session(session_id, call_sid=None, caller=None, lang='en'):
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO call_sessions (session_id, call_sid, caller_number, started_at, primary_lang)
            VALUES (?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
                total_turns   = total_turns + 1,
                primary_lang  = excluded.primary_lang
        """, (session_id, call_sid, caller, now, lang))


def log_turn(session_id, call_sid, turn_num, caller,
             audio_path, whisper_text, whisper_lang, whisper_conf, whisper_ms,
             llm_prompt, llm_response, llm_model, llm_source, llm_ms,
             tts_text, total_ms):
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO call_turns (
                session_id, call_sid, turn_number, caller_number,
                raw_audio_path, whisper_text, whisper_lang, whisper_conf, whisper_ms,
                llm_prompt, llm_response, llm_model, llm_source, llm_ms,
                tts_text, timestamp, total_ms
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (session_id, call_sid, turn_num, caller,
              audio_path, whisper_text, whisper_lang, whisper_conf, whisper_ms,
              llm_prompt, llm_response, llm_model, llm_source, llm_ms,
              tts_text, now, total_ms))


def end_session(session_id, status='completed'):
    with get_conn() as conn:
        conn.execute(
            "UPDATE call_sessions SET ended_at=?, status=? WHERE session_id=?",
            (datetime.datetime.now().isoformat(), status, session_id)
        )


def log_web_chat(session_id, lang, question, response, model, source, llm_ms):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO web_chat_logs (session_id, language, user_question, ai_response,
                                       llm_model, llm_source, llm_ms, timestamp)
            VALUES (?,?,?,?,?,?,?,?)
        """, (session_id, lang, question, response, model, source, llm_ms,
              datetime.datetime.now().isoformat()))


def get_stats():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM call_turns")
        total_call_turns = c.fetchone()[0]

        c.execute("SELECT COUNT(DISTINCT session_id) FROM call_sessions")
        total_sessions = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM web_chat_logs")
        total_web = c.fetchone()[0]

        c.execute("""
            SELECT whisper_lang, COUNT(*) as n
            FROM call_turns WHERE whisper_lang IS NOT NULL
            GROUP BY whisper_lang ORDER BY n DESC
        """)
        lang_stats = [dict(r) for r in c.fetchall()]

        c.execute("""
            SELECT AVG(total_ms) as avg_ms, AVG(whisper_ms), AVG(llm_ms)
            FROM call_turns WHERE total_ms > 0
        """)
        perf = c.fetchone()
        avg_total = round(perf[0] or 0)
        avg_stt   = round(perf[1] or 0)
        avg_llm   = round(perf[2] or 0)

        c.execute("""
            SELECT cs.caller_number, cs.started_at, cs.total_turns, cs.primary_lang, cs.status
            FROM call_sessions cs ORDER BY cs.started_at DESC LIMIT 15
        """)
        recent_sessions = [dict(r) for r in c.fetchall()]

        c.execute("""
            SELECT whisper_text, llm_response, whisper_lang, llm_source, llm_ms, timestamp, caller_number
            FROM call_turns ORDER BY timestamp DESC LIMIT 25
        """)
        recent_turns = [dict(r) for r in c.fetchall()]

        c.execute("""
            SELECT user_question, ai_response, language, llm_source, llm_ms, timestamp
            FROM web_chat_logs ORDER BY timestamp DESC LIMIT 25
        """)
        recent_web = [dict(r) for r in c.fetchall()]

        c.execute("SELECT llm_source, COUNT(*) FROM call_turns GROUP BY llm_source")
        llm_usage = [dict(r) for r in c.fetchall()]

    return {
        "total_call_turns":  total_call_turns,
        "total_sessions":    total_sessions,
        "total_web":         total_web,
        "lang_stats":        lang_stats,
        "avg_total_ms":      avg_total,
        "avg_stt_ms":        avg_stt,
        "avg_llm_ms":        avg_llm,
        "recent_sessions":   recent_sessions,
        "recent_turns":      recent_turns,
        "recent_web":        recent_web,
        "llm_usage":         llm_usage,
    }


def export_all():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM call_turns ORDER BY timestamp DESC")
        turns = [dict(r) for r in c.fetchall()]
        c.execute("SELECT * FROM call_sessions ORDER BY started_at DESC")
        sessions = [dict(r) for r in c.fetchall()]
        c.execute("SELECT * FROM web_chat_logs ORDER BY timestamp DESC")
        web = [dict(r) for r in c.fetchall()]
    return {"call_turns": turns, "call_sessions": sessions, "web_chat_logs": web}


def create_booking(session_id=None, call_sid=None, caller_name=None, caller_number=None,
                   booking_date=None, booking_time=None, faculty=None, department=None,
                   purpose=None, notes=None):
    """Create a new booking from a customer call."""
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bookings (
                session_id, call_sid, caller_name, caller_number,
                booking_date, booking_time, faculty, department,
                purpose, notes, status, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (session_id, call_sid, caller_name, caller_number,
              booking_date, booking_time, faculty, department,
              purpose, notes, 'confirmed', now, now))
        conn.commit()
        return cursor.lastrowid


def get_all_bookings():
    """Get all bookings."""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM bookings ORDER BY booking_date DESC, booking_time DESC
        """)
        return [dict(r) for r in c.fetchall()]


def get_bookings_by_date(date_str):
    """Get bookings for a specific date."""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM bookings WHERE booking_date = ? ORDER BY booking_time
        """, (date_str,))
        return [dict(r) for r in c.fetchall()]


def get_booking_by_id(booking_id):
    """Get a specific booking by ID."""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = c.fetchone()
        return dict(row) if row else None


def update_booking_status(booking_id, status):
    """Update booking status."""
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, booking_id)
        )
        conn.commit()

