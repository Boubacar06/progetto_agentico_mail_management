from ..shared_state import SharedState, RoutingDecision
from ..prompts import routing_prompt
from ..prompt_logging import prompt_for_logs, should_log_prompts
from ..json_utils import extract_json
from loguru import logger

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
        recipients_str = ", ".join(state.recipients) if state.recipients else ""
        prompt = routing_prompt.format(
            intent=state.semantic.intent or "", tone=state.semantic.tone or "", urgency=state.semantic.urgency or "",
            subject=state.subject or "", body=state.body_text or "",
            sender=state.sender or "", recipients=recipients_str,
        )
        if should_log_prompts():
            logger.info("[PROMPT][{}] {}", self.name, prompt_for_logs(prompt))
        response = getattr(self.llm, "invoke", lambda x: self.llm.predict(x))(prompt)
        content = getattr(response, "content", response)
        logger.info("[MODEL_OUTPUT][{}] {}", self.name, content)
        data = extract_json(content)
        if not data:
            data = {"department": "support", "rationale": "default"}
        dept_raw = (data.get("department") or "support").lower()
        department = _DEPT_MAP.get(dept_raw, dept_raw.upper())
        routing = RoutingDecision(department=department, rationale=data.get("rationale"))
        state.routing = routing
        state.status = "routed"
        state.log(self.name, "routed", department=department)
        return
