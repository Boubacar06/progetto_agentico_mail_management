import json
from ..shared_state import SharedState, SemanticAnalysis
from ..prompts import semantic_analysis_prompt

class SemanticAnalyzerAgent:
    name = "semantic_analyzer"

    def __init__(self, llm):
        self.llm = llm

    def run(self, state: SharedState) -> None:
        if state.status == "spam":
            state.log(self.name, "skipped", reason="spam")
            return
        if state.body_text is None:
            state.mark_error(self.name, "No body_text to analyze")
            return
        # Flatten chat prompt messages into a single string for generic LLMs
        messages = semantic_analysis_prompt.format_messages(subject=state.subject or "", body=state.body_text)
        joined = "\n".join(m.content for m in messages if hasattr(m, "content"))
        response = getattr(self.llm, "invoke", lambda x: getattr(self.llm, "predict", lambda y: "{}")(x))(joined)
        content = getattr(response, "content", response)
        try:
            data = json.loads(content)
        except Exception:
            data = {"intent": None, "tone": None, "urgency": None, "summary": None}
        model_name = getattr(self.llm, "model_name", "unknown")
        state.semantic = SemanticAnalysis(**data, model=model_name)
        state.status = "classified"
        state.log(self.name, "semantic", **data)
        return