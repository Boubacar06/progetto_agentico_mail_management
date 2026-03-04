import os
import sys
import webbrowser
import json
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    def load_dotenv(*args, **kwargs):  # type: ignore
        return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "src"
if SRC.exists():
    sys.path.append(str(SRC))

DATA_DIR = PROJECT_ROOT / "data"
EMAILS_FILE = DATA_DIR / "emails.json"
_emails_lock = threading.Lock()

def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

def _find_dir(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

def _should_run_pipeline() -> bool:
    return _truthy_env("RUN_PIPELINE") or "--run-agents" in sys.argv


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


def _load_emails() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not EMAILS_FILE.exists():
        _atomic_write_json(EMAILS_FILE, [])
    data = _read_json_file(EMAILS_FILE, [])
    if isinstance(data, list):
        return data
    return []


def _append_email(email_record: dict[str, Any]) -> dict[str, Any]:
    with _emails_lock:
        emails = _load_emails()
        emails.append(email_record)
        _atomic_write_json(EMAILS_FILE, emails)
    return email_record

def _run_frontend_server() -> None:
    # Prefer the root Flask app because it also exposes /api/analyze and /api/emails.
    try:
        from app import app as root_app  # type: ignore

        port = int(os.getenv("FRONTEND_PORT", "3000"))
        debug = _truthy_env("FLASK_DEBUG")
        auto_open = os.getenv("AUTO_OPEN_BROWSER", "1").strip().lower() not in {"0", "false", "no", "off"}
        url = f"http://127.0.0.1:{port}/"
        if auto_open:
            webbrowser.open(url)
        root_app.run(host="127.0.0.1", port=port, debug=debug)
        return
    except Exception as exc:
        # Fall back to static frontend-only server when root app import is unavailable.
        print(f"[WARN] Avvio app completa non riuscito ({exc}); uso server frontend-only.")

    try:
        from flask import Flask, jsonify, render_template, request, send_from_directory
    except Exception as exc:
        raise SystemExit("Flask non installato. Installa Flask o usa app.py per servire il frontend.") from exc

    templates_dir = _find_dir(PROJECT_ROOT / "templates", PROJECT_ROOT / "Templates")
    static_dir = _find_dir(PROJECT_ROOT / "static", PROJECT_ROOT / "Templates" / "static")
    if not templates_dir:
        raise SystemExit("Cartella templates non trovata (templates/ o Templates/).")

    app = Flask(
        __name__,
        template_folder=str(templates_dir),
        static_folder=str(static_dir) if static_dir else None,
        static_url_path="/static",
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/favicon.ico")
    def favicon():
        if not static_dir:
            return ("", 204)
        icon_path = static_dir / "favicon.ico"
        if icon_path.exists():
            return send_from_directory(static_dir, "favicon.ico")
        return ("", 204)

    @app.route("/api/analyze", methods=["POST"])
    def analyze_email():
        request_id = str(uuid.uuid4())
        data = request.get_json(force=True) or {}
        sender = data.get("mittente") or data.get("sender") or "user@example.com"
        recipient = data.get("destinatario") or data.get("recipient") or "support@example.com"
        message = data.get("messaggio") or data.get("body") or ""

        raw_email = f"From: {sender}\\nTo: {recipient}\\nSubject: Analisi da frontend\\n\\n{message}"
        state = SharedState(raw_email=raw_email)
        executor = get_executor()
        final_state = executor.run(state)

        history_json = []
        for entry in final_state.history or []:
            ts = getattr(entry, "timestamp", None)
            history_json.append(
                {
                    "request_id": request_id,
                    "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else _utc_now_iso(),
                    "agent": getattr(entry, "agent", "unknown"),
                    "action": getattr(entry, "action", ""),
                    "data": getattr(entry, "data", {}) or {},
                }
            )

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
            "messaggio": payload.get("messaggio") or payload.get("body") or "",
            "timestamp": payload.get("timestamp") or now_iso,
            "categoria": payload.get("categoria"),
            "paroleChiave": payload.get("paroleChiave") or [],
            "riassunto": payload.get("riassunto"),
            "classification": payload.get("classification"),
            "semantic": payload.get("semantic"),
            "routing": payload.get("routing"),
            "request_id": payload.get("request_id"),
        }

        if not email_record["mittente"] or not email_record["destinatario"] or not email_record["messaggio"]:
            return jsonify({"error": "Missing required fields"}), 400

        stored = _append_email(email_record)
        return jsonify({"email": stored})

    @app.route("/api/emails", methods=["DELETE"])
    def clear_emails():
        with _emails_lock:
            _atomic_write_json(EMAILS_FILE, [])
        return jsonify({"cleared": True})

    port = int(os.getenv("FRONTEND_PORT", "3000"))
    debug = _truthy_env("FLASK_DEBUG")
    auto_open = os.getenv("AUTO_OPEN_BROWSER", "1").strip().lower() not in {"0", "false", "no", "off"}
    url = f"http://127.0.0.1:{port}/"
    if auto_open:
        webbrowser.open(url)
    app.run(host="127.0.0.1", port=port, debug=debug)


def _maybe_run_frontend_when_script() -> None:
    if not _should_run_pipeline():
        _run_frontend_server()
        raise SystemExit(0)

# Proviamo a importare il modello Google; se fallisce useremo solo il DummyLLM
try:
    from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
    HAS_GOOGLE = True
except Exception:
    ChatGoogleGenerativeAI = None  # type: ignore[assignment]
    HAS_GOOGLE = False

from email_agents.shared_state import SharedState  # type: ignore
from email_agents.graph import build_graph  # type: ignore
from email_agents.agents.classifier import SpamClassifierAgent  # type: ignore
from email_agents.agents.semantic_analyzer import SemanticAnalyzerAgent  # type: ignore
from email_agents.agents.router import RouterAgent  # type: ignore
from email_agents.executor import GraphExecutor  # type: ignore

# Fallback mock for development if no API key
class DummyLLM:
    model_name = "dummy"
    def invoke(self, prompt: str):
        lower = prompt.lower()
        if "classify" in lower:
            if "lottery" in lower or "win money" in lower:
                return type("Resp", (), {"content": '{"is_spam": true, "confidence": 0.95}'})()
            return type("Resp", (), {"content": '{"is_spam": false, "confidence": 0.82}'})()
        if "decide best department" in lower:
            dept = "IT" if ("vpn" in lower or "access" in lower) else "SUPPORT"
            return type("Resp", (), {"content": f'{{"department": "{dept}", "rationale": "keyword heuristic"}}'})()
        return type("Resp", (), {"content": '{"intent": "support_request", "tone": "neutral", "urgency": "medium", "summary": "User needs assistance"}'})()


def _build_llm():
    load_dotenv()
    google_key = os.getenv("GOOGLE_API_KEY")

    # Se abbiamo sia la libreria che la chiave API usiamo Gemini, altrimenti DummyLLM
    if HAS_GOOGLE and google_key:
        return ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    return DummyLLM()


@lru_cache(maxsize=1)
def get_compiled():
    llm = _build_llm()
    classifier = SpamClassifierAgent(llm=llm, tools={})
    semantic = SemanticAnalyzerAgent(llm=llm)
    router = RouterAgent(llm=llm)
    return build_graph(classifier, semantic, router)


@lru_cache(maxsize=1)
def get_executor() -> GraphExecutor:
    return GraphExecutor(get_compiled())


# Backward-compatible module attributes (lazy)
compiled = None
executor = None


def _ensure_runtime_globals() -> None:
    global compiled, executor
    if compiled is None:
        compiled = get_compiled()
    if executor is None:
        executor = GraphExecutor(compiled)


def main() -> None:
    _maybe_run_frontend_when_script()

    _ensure_runtime_globals()

    # sample_email = """From: user@example.com\nTo: support@example.com\nSubject: Help needed\n\nHi team, I cannot access the VPN since yesterday. Please assist."""
    sample_email = """From: user@example.com\nTo: support@example.com\nSubject: Ciao, ho bisogno di aiuto\n\nNon riesco ad accedere alla VPN da ieri. Per favore assistenza."""
    state = SharedState(raw_email=sample_email)

    final_state = executor.run(state)
    print("Status:", final_state.status)
    print("Classification:", final_state.classification)
    print("Semantic:", final_state.semantic)
    print("Routing:", final_state.routing)
    print("History entries:", len(final_state.history))


if __name__ == "__main__":
    main()
