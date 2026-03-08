from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request, send_from_directory
from loguru import logger

from emeail_parser.run import SharedState, get_executor  # type: ignore
from emeail_parser.logging_setup import configure_logging

app = Flask(__name__)

LOG_DIR = configure_logging()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

DATA_DIR = Path(__file__).resolve().parent / "data"
EMAILS_FILE = DATA_DIR / "emails.json"

_emails_lock = threading.Lock()
_logs_lock = threading.Lock()
_logs: deque[Dict[str, Any]] = deque(maxlen=int(os.getenv("LOG_BUFFER_SIZE", "500")))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_emails() -> List[Dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not EMAILS_FILE.exists():
        _atomic_write_json(EMAILS_FILE, [])
    data = _read_json_file(EMAILS_FILE, [])
    if isinstance(data, list):
        return data
    return []


def _append_email(email_record: Dict[str, Any]) -> Dict[str, Any]:
    with _emails_lock:
        emails = _load_emails()
        emails.append(email_record)
        _atomic_write_json(EMAILS_FILE, emails)
    return email_record


def _push_log(event: Dict[str, Any]) -> None:
    with _logs_lock:
        _logs.append(event)


def _history_to_json(history: List[Any], request_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for entry in history:
        ts = getattr(entry, "timestamp", None)
        out.append(
            {
                "request_id": request_id,
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else _utc_now_iso(),
                "agent": getattr(entry, "agent", "unknown"),
                "action": getattr(entry, "action", ""),
                "data": getattr(entry, "data", {}) or {},
            }
        )
    return out


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    static_dir = Path(app.root_path) / "static"
    icon_path = static_dir / "favicon.ico"
    if icon_path.exists():
        return send_from_directory(static_dir, "favicon.ico")
    return ("", 204)


@app.route("/api/analyze", methods=["POST"])
def analyze_email():
    request_id = str(uuid.uuid4())
    data = request.get_json(force=True)
    sender = data.get("mittente") or data.get("sender") or "user@example.com"
    recipient = data.get("destinatario") or data.get("recipient") or "support@example.com"
    subject = data.get("oggetto") or data.get("subject") or "(nessun oggetto)"
    message = data.get("messaggio") or data.get("body") or ""

    logger.bind(request_id=request_id, source="frontend").info(
        "analyze_email received | sender={} recipient={} subject={} chars={}",
        sender,
        recipient,
        subject,
        len(message),
    )

    raw_email = f"From: {sender}\nTo: {recipient}\nSubject: {subject}\n\n{message}"

    state = SharedState(raw_email=raw_email)
    executor = get_executor()
    final_state = executor.run(state)

    logger.bind(request_id=request_id, source="frontend").info(
        "analyze_email completed | status={} history_entries={}",
        final_state.status,
        len(final_state.history or []),
    )

    history_json = _history_to_json(final_state.history or [], request_id=request_id)
    for event in history_json:
        _push_log(event)

    return jsonify(
        {
            "request_id": request_id,
            "status": final_state.status,
            "classification": final_state.classification.model_dump() if final_state.classification else None,
            "semantic": final_state.semantic.model_dump() if final_state.semantic else None,
            "routing": final_state.routing.model_dump() if final_state.routing else None,
            "history": history_json,
        }
    )


@app.route("/api/emails", methods=["GET"])
def get_emails():
    limit_raw = request.args.get("limit")
    try:
        limit = int(limit_raw) if limit_raw else None
    except Exception:
        limit = None
    with _emails_lock:
        emails = list(_load_emails())
    # Most recent first
    emails.reverse()
    if limit is not None:
        emails = emails[: max(limit, 0)]
    return jsonify({"emails": emails})


@app.route("/api/emails", methods=["POST"])
def post_email():
    payload = request.get_json(force=True) or {}
    now_iso = _utc_now_iso()
    email_record = {
        "id": payload.get("id") or str(uuid.uuid4()),
        "mittente": payload.get("mittente") or payload.get("sender") or "",
        "destinatario": payload.get("destinatario") or payload.get("recipient") or "",
        "oggetto": payload.get("oggetto") or payload.get("subject") or "",
        "messaggio": payload.get("messaggio") or payload.get("body") or "",
        "timestamp": payload.get("timestamp") or now_iso,
        "categoria": payload.get("categoria"),
        "paroleChiave": payload.get("paroleChiave") or [],
        "riassunto": payload.get("riassunto"),
        "allegati": payload.get("allegati") or [],
        "classification": payload.get("classification"),
        "semantic": payload.get("semantic"),
        "routing": payload.get("routing"),
        "request_id": payload.get("request_id"),
    }

    if not email_record["mittente"] or not email_record["destinatario"] or not email_record["messaggio"]:
        return jsonify({"error": "Missing required fields"}), 400

    stored = _append_email(email_record)
    _push_log({"timestamp": now_iso, "agent": "api", "action": "email_saved", "data": {"id": stored["id"]}})
    return jsonify({"email": stored})


@app.route("/api/emails", methods=["DELETE"])
def clear_emails():
    with _emails_lock:
        _atomic_write_json(EMAILS_FILE, [])
    _push_log({"timestamp": _utc_now_iso(), "agent": "api", "action": "emails_cleared", "data": {}})
    return jsonify({"cleared": True})


@app.route("/api/logs", methods=["GET"])
def get_logs():
    limit_raw = request.args.get("limit")
    try:
        limit = int(limit_raw) if limit_raw else 200
    except Exception:
        limit = 200
    with _logs_lock:
        logs = list(_logs)
    if limit is not None:
        logs = logs[-max(limit, 0) :]
    return jsonify({"logs": logs})


if __name__ == "__main__":
    logger.info("Starting Flask app | log_dir={}", LOG_DIR)
    app.run(debug=True)
