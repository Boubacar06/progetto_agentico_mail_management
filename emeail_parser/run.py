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
DEFAULT_OLLAMA_FALLBACK_MODELS = ["llama3.1", "mistral", "deepseek-r1:14b", "deepseek-r1"]

def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(value.strip())
    return ordered


def _normalize_model_name(model_name: str) -> str:
    return model_name.strip().lower()


def _model_base_name(model_name: str) -> str:
    return _normalize_model_name(model_name).split(":", 1)[0]


def _fetch_ollama_models(base_url: str) -> list[str] | None:
    url = f"{base_url.rstrip('/')}/api/tags"
    req = urllib_request.Request(url, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:  # nosec B310
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("Unable to query Ollama models at {}: {}", url, exc)
        return None

    models = parsed.get("models") or []
    names: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        name = str(model.get("name") or model.get("model") or "").strip()
        if name:
            names.append(name)
    return _dedupe_keep_order(names)


def _rank_ollama_models(preferred_model: str, fallback_models: list[str], available_models: list[str] | None) -> list[str]:
    candidates = _dedupe_keep_order([preferred_model, *fallback_models])
    if not available_models:
        return candidates

    available_map = {_normalize_model_name(model): model for model in available_models}
    available_by_base: dict[str, str] = {}
    for model in available_models:
        available_by_base.setdefault(_model_base_name(model), model)

    ordered: list[str] = []
    for candidate in candidates:
        exact = available_map.get(_normalize_model_name(candidate))
        if exact:
            ordered.append(exact)
            continue
        base_match = available_by_base.get(_model_base_name(candidate))
        if base_match:
            ordered.append(base_match)

    if not ordered:
        ordered = list(available_models)
    else:
        for available in available_models:
            if available not in ordered:
                ordered.append(available)
    return _dedupe_keep_order(ordered)

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

    # Keyword lists for heuristic classification
    _SPAM_KEYWORDS = [
        "lottery", "win money", "congratulations you won", "free gift",
        "click here", "act now", "limited time", "buy now", "unsubscribe",
        "offerta speciale", "hai vinto", "clicca qui", "gratis",
    ]
    _DEPT_KEYWORDS = {
        "IT": ["vpn", "password", "login", "server", "computer", "software",
               "hardware", "rete", "accesso", "sistema", "errore", "bug"],
        "HR": ["ferie", "stipendio", "contratto", "assunzione", "colloquio",
               "vacancy", "salary", "leave", "hiring", "resume", "cv"],
        "SALES": ["preventivo", "ordine", "cliente", "vendita", "prezzo",
                  "quote", "order", "pricing", "deal", "proposal"],
        "FINANCE": ["fattura", "pagamento", "rimborso", "budget", "invoice",
                    "payment", "refund", "billing", "costo", "spesa"],
    }
    _URGENCY_KEYWORDS = {
        "alta": ["urgente", "urgent", "asap", "immediately", "subito",
                 "critico", "critical", "bloccato", "blocked", "emergency"],
        "bassa": ["quando puoi", "no rush", "non urgente", "low priority",
                  "a tuo comodo", "informativo", "fyi"],
    }
    _TONE_KEYWORDS = {
        "formale": ["gentile", "cordiali saluti", "distinti saluti", "egregio",
                    "dear", "regards", "sincerely", "spettabile"],
        "informale": ["ciao", "hey", "ehi", "bella", "grazie mille", "a presto"],
        "arrabbiato": ["inaccettabile", "scandaloso", "vergogna", "furioso",
                       "unacceptable", "outrageous", "angry", "frustrated"],
    }

    def _match_any(self, text: str, keywords: list[str]) -> bool:
        return any(kw in text for kw in keywords)

    def _detect_department(self, text: str) -> str:
        for dept, kws in self._DEPT_KEYWORDS.items():
            if self._match_any(text, kws):
                return dept
        return "SUPPORT"

    def _detect_tone(self, text: str) -> str:
        for tone, kws in self._TONE_KEYWORDS.items():
            if self._match_any(text, kws):
                return tone
        return "neutrale"

    def _detect_urgency(self, text: str) -> str:
        for urg, kws in self._URGENCY_KEYWORDS.items():
            if self._match_any(text, kws):
                return urg
        return "media"

    def invoke(self, prompt: str):
        import re as _re
        lower = prompt.lower()

        # --- Spam classification ---
        if "classify" in lower:
            is_spam = self._match_any(lower, self._SPAM_KEYWORDS)
            confidence = 0.92 if is_spam else 0.85
            return type("Resp", (), {"content": json.dumps(
                {"is_spam": is_spam, "confidence": confidence}
            )})()

        # --- Routing ---
        if "decide best department" in lower:
            dept = self._detect_department(lower)
            return type("Resp", (), {"content": json.dumps(
                {"department": dept, "rationale": "keyword heuristic"}
            )})()

        # --- Semantic analysis ---
        # Build a content-aware summary from the body
        body_match = _re.search(r"body:\s*(.+)", lower, _re.DOTALL)
        body_snippet = (body_match.group(1).strip()[:120] + "...") if body_match else ""
        subject_match = _re.search(r"subject:\s*(.+?)(?:\n|$)", lower)
        subject_snippet = subject_match.group(1).strip() if subject_match else ""

        tone = self._detect_tone(lower)
        urgency = self._detect_urgency(lower)

        # Determine intent from keywords
        if self._match_any(lower, ["aiuto", "help", "problema", "problem", "errore", "error", "non riesco", "cannot"]):
            intent = "richiesta_di_assistenza"
        elif self._match_any(lower, ["informazione", "info", "domanda", "question", "sapere", "know"]):
            intent = "richiesta_informazioni"
        elif self._match_any(lower, ["reclamo", "complaint", "lamentela", "insoddisfatto"]):
            intent = "reclamo"
        elif self._match_any(lower, ["grazie", "thank", "conferma", "confirm"]):
            intent = "conferma"
        else:
            intent = "comunicazione_generica"

        summary = subject_snippet if subject_snippet else (body_snippet if body_snippet else "Nessun contenuto rilevante")

        return type("Resp", (), {"content": json.dumps(
            {"intent": intent, "tone": tone, "urgency": urgency, "summary": summary},
            ensure_ascii=False,
        )})()


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

    def __init__(self, model: str, base_url: str, fallback_models: list[str] | None = None, available_models: list[str] | None = None):
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self._fallback_models = fallback_models or []
        self._available_models = available_models

    def _candidate_models(self) -> list[str]:
        return _rank_ollama_models(self.model_name, self._fallback_models, self._available_models)

    def _invoke_with_model(self, prompt: str, model_name: str):
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model_name,
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

        with urllib_request.urlopen(req, timeout=120) as resp:  # nosec B310
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        content = (parsed.get("response") or "{}").strip()
        self.model_name = model_name
        return type("Resp", (), {"content": content})()

    def invoke(self, prompt: str):
        url = f"{self.base_url}/api/generate"
        attempted_models: list[str] = []
        last_error: Exception | None = None

        for model_name in self._candidate_models():
            attempted_models.append(model_name)
            try:
                if model_name != self.model_name:
                    logger.warning("Configured Ollama model '{}' unavailable; retrying with '{}'", self.model_name, model_name)
                return self._invoke_with_model(prompt, model_name)
            except urllib_error.HTTPError as exc:
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8")
                except Exception:
                    pass

                is_missing_model = exc.code == 404 and "not found" in err_body.lower()
                if is_missing_model:
                    logger.warning(
                        "Ollama model '{}' not found at {}; trying next candidate if available",
                        model_name,
                        url,
                    )
                    last_error = exc
                    continue

                logger.exception(
                    "Ollama HTTP error | model={} url={} status={} body={} prompt={}",
                    model_name,
                    url,
                    exc.code,
                    err_body,
                    prompt_for_logs(prompt),
                )
                raise
            except Exception as exc:
                logger.exception(
                    "Ollama API call failed | model={} url={} prompt={}",
                    model_name,
                    url,
                    prompt_for_logs(prompt),
                )
                last_error = exc
                raise

        attempted = ", ".join(attempted_models) if attempted_models else self.model_name
        logger.error("No usable Ollama model found. Attempted models: {}", attempted)
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"No usable Ollama model found. Attempted models: {attempted}")


def _build_llm():
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    ollama_fallback_models = _dedupe_keep_order(
        _parse_csv(os.getenv("OLLAMA_FALLBACK_MODELS")) or list(DEFAULT_OLLAMA_FALLBACK_MODELS)
    )
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    google_key = os.getenv("GOOGLE_API_KEY")
    available_ollama_models = _fetch_ollama_models(ollama_base_url)
    ranked_ollama_models = _rank_ollama_models(ollama_model, ollama_fallback_models, available_ollama_models)
    selected_ollama_model = ranked_ollama_models[0] if ranked_ollama_models else ollama_model

    if provider == "ollama":
        logger.info("Using Ollama model '{}' at {}", selected_ollama_model, ollama_base_url)
        return OllamaLLM(
            model=selected_ollama_model,
            base_url=ollama_base_url,
            fallback_models=ranked_ollama_models[1:],
            available_models=available_ollama_models,
        )

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
        if available_ollama_models is not None:
            logger.info("Trying Ollama model '{}' at {}", selected_ollama_model, ollama_base_url)
            return OllamaLLM(
                model=selected_ollama_model,
                base_url=ollama_base_url,
                fallback_models=ranked_ollama_models[1:],
                available_models=available_ollama_models,
            )
        logger.warning("Ollama non raggiungibile o senza modelli leggibili; provo provider alternativi")

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
