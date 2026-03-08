from typing import Dict
from ..shared_state import SharedState, ClassificationResult
from ..prompts import spam_classifier_prompt
from ..prompt_logging import prompt_for_logs, should_log_prompts
from ..json_utils import extract_json
from loguru import logger

class SpamClassifierAgent:
    """Spam classifier agent. Expects an LLM with a .predict(prompt:str)->str and model_name attr."""
    name = "spam_classifier"

    def __init__(self, llm, tools: Dict[str, object]):
        self.llm = llm
        self.tools = tools

    def run(self, state: SharedState) -> None:
        if state.body_text is None:
            state.mark_error(self.name, "No body_text to classify")
            return
        prompt = spam_classifier_prompt.format(subject=state.subject or "", body=state.body_text)
        if should_log_prompts():
            logger.info("[PROMPT][{}] {}", self.name, prompt_for_logs(prompt))
        response = getattr(self.llm, "invoke", lambda x: self.llm.predict(x))(prompt)
        content = getattr(response, "content", response)
        logger.info("[MODEL_OUTPUT][{}] {}", self.name, content)
        data = extract_json(content)
        if not data:
            data = {"is_spam": False, "confidence": 0.0}
        model_name = getattr(self.llm, "model_name", "unknown")
        logger.info("Classifier response | is_spam={} confidence={} model={}", data.get("is_spam"), data.get("confidence"), model_name)
        state.classification = ClassificationResult(is_spam=bool(data.get("is_spam")), confidence=float(data.get("confidence", 0.0)), model=model_name)
        state.status = "spam" if state.classification.is_spam else "classified"
        state.log(self.name, "classified", is_spam=state.classification.is_spam, confidence=state.classification.confidence)
        return
