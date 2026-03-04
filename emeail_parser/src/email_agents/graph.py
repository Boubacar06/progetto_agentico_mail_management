from typing import Any
from langgraph.graph import StateGraph, END
from .shared_state import SharedState
from .agents.classifier import SpamClassifierAgent
from .agents.semantic_analyzer import SemanticAnalyzerAgent
from .agents.router import RouterAgent
from .tools.parse_email import parse_email


class _CompiledGraphWrapper:
    def __init__(self, compiled: Any):
        self._compiled = compiled

    def invoke(self, state: SharedState) -> SharedState:
        result_state = self._compiled.invoke(state)
        if isinstance(result_state, dict) and not isinstance(result_state, SharedState):
            base = state.model_dump()
            result_state = SharedState(**{**base, **result_state})
        return result_state

    def stream(self, state: SharedState):
        for step in self._compiled.stream(state):
            if isinstance(step, dict) and not isinstance(step, SharedState):
                base = state.model_dump()
                yield SharedState(**{**base, **step})
            else:
                yield step

    def __getattr__(self, name: str):
        return getattr(self._compiled, name)

# Simple wrapper for calling .run on agents

def build_graph(classifier: SpamClassifierAgent, semantic: SemanticAnalyzerAgent, router: RouterAgent):
    graph = StateGraph(SharedState)

    def handoff(state: SharedState, from_agent: str, to_agent: str, **data: Any) -> None:
        # Centralized transition log so execution flow is easy to follow in history and file logs.
        state.log("orchestrator", "handoff", from_agent=from_agent, to_agent=to_agent, **data)

    def parse_node(state: SharedState):
        if not state.history:
            state.log("orchestrator", "start", entry_point="parse")
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
        handoff(
            state,
            from_agent="parser",
            to_agent="spam_classifier",
            subject=state.subject,
            body_length=len(state.body_text or ""),
        )
        return state

    def classifier_node(state: SharedState):
        classifier.run(state)
        if state.status == "spam":
            handoff(
                state,
                from_agent="spam_classifier",
                to_agent="END",
                decision="spam",
                confidence=state.classification.confidence if state.classification else None,
            )
        else:
            handoff(
                state,
                from_agent="spam_classifier",
                to_agent="semantic_analyzer",
                decision="ham",
                confidence=state.classification.confidence if state.classification else None,
            )
        return state

    def semantic_node(state: SharedState):
        semantic.run(state)
        handoff(
            state,
            from_agent="semantic_analyzer",
            to_agent="router",
            intent=state.semantic.intent if state.semantic else None,
            tone=state.semantic.tone if state.semantic else None,
            urgency=state.semantic.urgency if state.semantic else None,
        )
        return state

    def router_node(state: SharedState):
        router.run(state)
        handoff(
            state,
            from_agent="router",
            to_agent="END",
            department=state.routing.department if state.routing else None,
        )
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

    return _CompiledGraphWrapper(graph.compile())
