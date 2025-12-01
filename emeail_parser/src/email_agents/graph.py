from typing import Any
from langgraph.graph import StateGraph, END
from .shared_state import SharedState
from .agents.classifier import SpamClassifierAgent
from .agents.semantic_analyzer import SemanticAnalyzerAgent
from .agents.router import RouterAgent
from .tools.parse_email import parse_email

# Simple wrapper for calling .run on agents

def build_graph(classifier: SpamClassifierAgent, semantic: SemanticAnalyzerAgent, router: RouterAgent):
    graph = StateGraph(SharedState)

    def parse_node(state: SharedState):
        # Only parse if not already parsed
        if state.subject is None or state.body_text is None:
            # parse_email is a StructuredTool; underlying callable is .func
            parsed = parse_email.func(state.raw_email)
            state.subject = parsed.get("subject")
            state.body_text = parsed.get("body_text")
            state.body_html = parsed.get("body_html")
            state.sender = parsed.get("sender")
            state.recipients = parsed.get("recipients", [])
            state.headers = parsed.get("headers", {})
            state.log("parser", "parsed", subject=state.subject)
        return state

    def classifier_node(state: SharedState):
        classifier.run(state)
        return state

    def semantic_node(state: SharedState):
        semantic.run(state)
        return state

    def router_node(state: SharedState):
        router.run(state)
        return state

    graph.add_node("parse", parse_node)
    graph.add_node("classifier", classifier_node)
    graph.add_node("semantic", semantic_node)
    graph.add_node("router", router_node)

    graph.set_entry_point("parse")

    # Conditional routing after classification
    def branch_after_classifier(state: SharedState):
        # Return a string key used in mapping below
        if state.status == "spam":
            return "end"
        return "semantic"

    # Use positional args to match installed langgraph version signature
    graph.add_edge("parse", "classifier")
    graph.add_conditional_edges(
        "classifier",
        branch_after_classifier,
        {
            "semantic": "semantic",
            "end": END,
        },
    )
    graph.add_edge("semantic", "router")
    graph.add_edge("router", END)

    return graph.compile()
