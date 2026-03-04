import os
import sys
import webbrowser
import json
import threading
import uuid
from urllib import request as urllib_request
from urllib import error as urllib_error
from pathlib import Path
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from loguru import logger

try:
    from emeail_parser.logging_setup import configure_logging
except ModuleNotFoundError:  # pragma: no cover - script execution fallback
    from logging_setup import configure_logging  # type: ignore

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
LOG_DIR = configure_logging()

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
        logger.info("Starting root app server | url={} log_dir={}", url, LOG_DIR)
        root_app.run(host="127.0.0.1", port=port, debug=debug)
        return
    except Exception as exc:
        # Fall back to static frontend-only server when root app import is unavailable.
        print(f"[WARN] Avvio app completa non riuscito ({exc}); uso server frontend-only.")
        logger.warning("Root app import failed, using fallback server: {}", exc)

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

        logger.bind(request_id=request_id, source="frontend").info(
            "analyze_email received | sender={} recipient={} chars={}",
            sender,
            recipient,
            len(message),
        )

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

        logger.bind(request_id=request_id, source="frontend").info(
            "analyze_email completed | status={} history_entries={}",
            final_state.status,
            len(history_json),
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
    logger.info("Starting fallback app server | url={} log_dir={}", url, LOG_DIR)
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

# Proviamo a importare OpenAI SDK; se manca useremo fallback.
try:
    from openai import OpenAI  # type: ignore
    HAS_OPENAI = True
except Exception:
    OpenAI = None  # type: ignore[assignment]
    HAS_OPENAI = False

from email_agents.shared_state import SharedState  # type: ignore
from email_agents.graph import build_graph  # type: ignore
from email_agents.agents.classifier import SpamClassifierAgent  # type: ignore
from email_agents.agents.semantic_analyzer import SemanticAnalyzerAgent  # type: ignore
from email_agents.agents.router import RouterAgent  # type: ignore
from email_agents.executor import GraphExecutor  # type: ignore
from email_agents.prompt_logging import prompt_for_logs  # type: ignore

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


class OpenAILLM:
    """Small OpenAI wrapper compatible with existing agent calls (.invoke + model_name)."""

    def __init__(self, api_key: str, model: str):
        self.model_name = model
        self._client = OpenAI(api_key=api_key)

    def invoke(self, prompt: str):
        try:
            resp = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an email triage assistant. Return only valid JSON when asked.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            content = (resp.choices[0].message.content or "{}").strip()
            return type("Resp", (), {"content": content})()
        except Exception:
            logger.exception("OpenAI API call failed | model={} | prompt={}", self.model_name, prompt_for_logs(prompt))
            raise


class OllamaLLM:
    """Minimal Ollama client compatible with existing agent calls (.invoke + model_name)."""

    def __init__(self, model: str, base_url: str):
        self.model_name = model
        self.base_url = base_url.rstrip("/")

    def invoke(self, prompt: str):
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=120) as resp:  # nosec B310
                raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            content = (parsed.get("response") or "{}").strip()
            return type("Resp", (), {"content": content})()
        except urllib_error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            logger.exception(
                "Ollama HTTP error | model={} url={} status={} body={} prompt={}",
                self.model_name,
                url,
                exc.code,
                err_body,
                prompt_for_logs(prompt),
            )
            raise
        except Exception:
            logger.exception(
                "Ollama API call failed | model={} url={} prompt={}",
                self.model_name,
                url,
                prompt_for_logs(prompt),
            )
            raise


def _build_llm():
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    google_key = os.getenv("GOOGLE_API_KEY")

    if provider == "ollama":
        logger.info("Using Ollama model '{}' at {}", ollama_model, ollama_base_url)
        return OllamaLLM(model=ollama_model, base_url=ollama_base_url)

    if provider == "openai":
        if HAS_OPENAI and openai_key:
            logger.info("Using OpenAI model '{}' for agent pipeline", openai_model)
            return OpenAILLM(api_key=openai_key, model=openai_model)
        logger.warning("LLM_PROVIDER=openai but OpenAI SDK/key missing; falling back")

    if provider == "google":
        if HAS_GOOGLE and google_key:
            logger.info("Using Google model 'gemini-1.5-flash' for agent pipeline")
            return ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
        logger.warning("LLM_PROVIDER=google but Google SDK/key missing; falling back")

    if provider == "dummy":
        logger.warning("LLM_PROVIDER=dummy set; using DummyLLM")
        return DummyLLM()

    # Auto priority: Ollama -> OpenAI -> Gemini -> DummyLLM
    if provider == "auto":
        logger.info("LLM_PROVIDER=auto enabled")
        try:
            logger.info("Trying Ollama model '{}' at {}", ollama_model, ollama_base_url)
            return OllamaLLM(model=ollama_model, base_url=ollama_base_url)
        except Exception:
            logger.warning("Ollama initialization failed; trying cloud providers")

    if HAS_OPENAI and openai_key:
        logger.info("Using OpenAI model '{}' for agent pipeline", openai_model)
        return OpenAILLM(api_key=openai_key, model=openai_model)

    if openai_key and not HAS_OPENAI:
        logger.warning("OPENAI_API_KEY provided but OpenAI SDK not installed; falling back")

    # Se abbiamo sia la libreria che la chiave API usiamo Gemini, altrimenti DummyLLM
    if HAS_GOOGLE and google_key:
        logger.info("Using Google model 'gemini-1.5-flash' for agent pipeline")
        return ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)

    logger.warning("No LLM API key configured; using DummyLLM")
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
