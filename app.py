from flask import Flask, render_template, request, jsonify
from emeail_parser.run import SharedState, build_graph, SpamClassifierAgent, SemanticAnalyzerAgent, RouterAgent, GraphExecutor

app = Flask(__name__)

# Inizializza il grafo e l'executor una sola volta all'avvio
# Riutilizzeremo la stessa configurazione di run.py ma esposta via API


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze_email():
    data = request.get_json(force=True)
    sender = data.get("mittente") or data.get("sender") or "user@example.com"
    recipient = data.get("destinatario") or data.get("recipient") or "support@example.com"
    message = data.get("messaggio") or data.get("body") or ""

    raw_email = f"From: {sender}\nTo: {recipient}\nSubject: Analisi da frontend\n\n{message}"

    from emeail_parser.run import SharedState, compiled, executor  # type: ignore

    state = SharedState(raw_email=raw_email)
    final_state = executor.run(state)

    return jsonify({
        "status": final_state.status,
        "classification": final_state.classification.dict() if final_state.classification else None,
        "semantic": final_state.semantic.dict() if final_state.semantic else None,
        "routing": final_state.routing.dict() if final_state.routing else None,
    })


if __name__ == "__main__":
    app.run(debug=True)
