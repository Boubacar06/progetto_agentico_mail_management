import json
from ..shared_state import SharedState, RoutingDecision
from ..prompts import routing_prompt

_DEPT_MAP = {"hr": "HR", "it": "IT", "sales": "SALES", "finance": "FINANCE", "support": "SUPPORT"}

class RouterAgent:
    name = "router"

    def __init__(self, llm):
        self.llm = llm

    def run(self, state: SharedState) -> None:
        if state.status == "spam":
            state.log(self.name, "skipped", reason="spam")
            return
        if not state.semantic:
            state.mark_error(self.name, "Semantic analysis missing")
            return
        prompt = routing_prompt.format(
            intent=state.semantic.intent or "", tone=state.semantic.tone or "", urgency=state.semantic.urgency or "", subject=state.subject or "", body=state.body_text or ""
        )
        response = getattr(self.llm, "invoke", lambda x: self.llm.predict(x))(prompt)
        content = getattr(response, "content", response)
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {"department": "support", "rationale": "default"}
        dept_raw = (data.get("department") or "support").lower()
        department = _DEPT_MAP.get(dept_raw, dept_raw.upper())
        routing = RoutingDecision(department=department, rationale=data.get("rationale"))
        state.routing = routing
        state.status = "routed"
        state.log(self.name, "routed", department=department)
        return
