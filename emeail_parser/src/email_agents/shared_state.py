from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

_logger = logging.getLogger("email_agents")

class ClassificationResult(BaseModel):
    is_spam: bool = False
    confidence: float = 0.0
    model: Optional[str] = None

class SemanticAnalysis(BaseModel):
    intent: Optional[str] = None
    tone: Optional[str] = None
    urgency: Optional[str] = None
    summary: Optional[str] = None
    model: Optional[str] = None

class RoutingDecision(BaseModel):
    department: Optional[str] = None
    rationale: Optional[str] = None

class HistoryEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent: str
    action: str
    data: Dict[str, Any] = Field(default_factory=dict)

class SharedState(BaseModel):
    # Raw email
    raw_email: str

    # Parsed components
    sender: Optional[str] = None
    recipients: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    headers: Dict[str, Any] = Field(default_factory=dict)

    # Results
    classification: Optional[ClassificationResult] = None
    semantic: Optional[SemanticAnalysis] = None
    routing: Optional[RoutingDecision] = None

    # Status & meta
    status: str = "pending"  # pending | spam | classified | routed | error
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # History for traceability
    history: List[HistoryEntry] = Field(default_factory=list)

    def log(self, agent: str, action: str, **data: Any) -> None:
        entry = HistoryEntry(agent=agent, action=action, data=data)
        self.history.append(entry)
        # Keep logs lightweight: avoid dumping entire raw email
        safe_data = {k: v for k, v in data.items() if k not in {"raw_email", "body_html", "body_text"}}
        _logger.info("%s:%s %s", agent, action, safe_data)

    def mark_error(self, agent: str, message: str) -> None:
        self.status = "error"
        self.error = message
        self.log(agent, "error", message=message)

    def as_tool_context(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "subject": self.subject,
            "intent": self.semantic.intent if self.semantic else None,
            "department": self.routing.department if self.routing else None,
        }
