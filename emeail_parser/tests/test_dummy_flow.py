from email_agents.shared_state import SharedState
from email_agents.graph import build_graph
from email_agents.agents.classifier import SpamClassifierAgent
from email_agents.agents.semantic_analyzer import SemanticAnalyzerAgent
from email_agents.agents.router import RouterAgent

class DummyLLM:
    model_name = "dummy"
    def predict(self, text: str):
        return '{"is_spam": false, "confidence": 0.9}'
    def predict_messages(self, messages):
        return type("Resp", (), {"content": '{"intent": "support_request", "tone": "neutral", "urgency": "high", "summary": "User needs help"}'})()


def test_flow_non_spam():
    llm = DummyLLM()
    classifier = SpamClassifierAgent(llm=llm, tools={})
    semantic = SemanticAnalyzerAgent(llm=llm)
    router = RouterAgent(llm=llm)
    graph = build_graph(classifier, semantic, router)
    sample_email = "Subject: VPN issue\n\nCannot access VPN"
    state = SharedState(raw_email=sample_email, subject="VPN issue", body_text="Cannot access VPN", sender="user@example.com")
    final_state = graph.invoke(state)
    assert final_state.routing is not None
    assert final_state.status == "routed"
