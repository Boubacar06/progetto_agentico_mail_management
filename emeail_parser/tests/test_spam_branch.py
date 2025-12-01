from email_agents.shared_state import SharedState
from email_agents.graph import build_graph
from email_agents.agents.classifier import SpamClassifierAgent
from email_agents.agents.semantic_analyzer import SemanticAnalyzerAgent
from email_agents.agents.router import RouterAgent

class DummyLLM:
    model_name = "dummy"
    def invoke(self, prompt: str):
        # Force spam on classifier prompt
        if "Classify" in prompt:
            return type("Resp", (), {"content": '{"is_spam": true, "confidence": 0.9}'})()
        return type("Resp", (), {"content": '{}'})()


def test_spam_short_circuit():
    llm = DummyLLM()
    classifier = SpamClassifierAgent(llm=llm, tools={})
    semantic = SemanticAnalyzerAgent(llm=llm)
    router = RouterAgent(llm=llm)
    graph = build_graph(classifier, semantic, router)
    spam_email = "Subject: Lottery WIN\n\nWin money now"
    state = SharedState(raw_email=spam_email)
    final_state = graph.invoke(state)
    assert final_state.status == "spam"
    assert final_state.routing is None
