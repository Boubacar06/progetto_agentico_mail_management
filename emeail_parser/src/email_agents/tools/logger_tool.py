from typing import Any, Dict
from langchain.tools import tool
from rich.console import Console

_console = Console()

@tool("log_event")
def log_event(data: Dict[str, Any]) -> str:
    """Log an event dictionary to console (structured)."""
    _console.log(data)
    return "logged"
