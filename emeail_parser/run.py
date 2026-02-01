import os
import sys
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "src"
if SRC.exists():
    sys.path.append(str(SRC))

def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

def _find_dir(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

def _should_run_pipeline() -> bool:
    return _truthy_env("RUN_PIPELINE") or "--run-agents" in sys.argv

def _run_frontend_server() -> None:
    try:
        from flask import Flask, render_template
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

    port = int(os.getenv("FRONTEND_PORT", "8000"))
    debug = _truthy_env("FLASK_DEBUG")
    auto_open = os.getenv("AUTO_OPEN_BROWSER", "1").strip().lower() not in {"0", "false", "no", "off"}
    url = f"http://127.0.0.1:{port}/"
    if auto_open:
        webbrowser.open(url)
    app.run(host="127.0.0.1", port=port, debug=debug)

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

load_dotenv()
google_key = os.getenv("GOOGLE_API_KEY")

# Se abbiamo sia la libreria che la chiave API usiamo Gemini, altrimenti DummyLLM
if HAS_GOOGLE and google_key:
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
else:
    llm = DummyLLM()

classifier = SpamClassifierAgent(llm=llm, tools={})
semantic = SemanticAnalyzerAgent(llm=llm)
router = RouterAgent(llm=llm)

compiled = build_graph(classifier, semantic, router)
executor = GraphExecutor(compiled)

# sample_email = """From: user@example.com\nTo: support@example.com\nSubject: Help needed\n\nHi team, I cannot access the VPN since yesterday. Please assist."""
sample_email = """From: user@example.com\nTo: support@example.com\nSubject: Ciao, ho bisogno di aiuto\n\nNon riesco ad accedere alla VPN da ieri. Per favore assistenza."""
state = SharedState(raw_email=sample_email)

final_state = executor.run(state)
print("Status:", final_state.status)
print("Classification:", final_state.classification)
print("Semantic:", final_state.semantic)
print("Routing:", final_state.routing)
print("History entries:", len(final_state.history))
