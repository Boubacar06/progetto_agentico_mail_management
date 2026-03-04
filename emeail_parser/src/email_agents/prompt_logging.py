from __future__ import annotations

import os


def _truthy_env(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def should_log_prompts() -> bool:
    return _truthy_env("LOG_PROMPTS", "true")


def prompt_for_logs(text: str) -> str:
    """Return full or truncated prompt text based on env settings."""
    max_chars_raw = os.getenv("PROMPT_LOG_MAX_CHARS", "6000")
    try:
        max_chars = max(int(max_chars_raw), 200)
    except Exception:
        max_chars = 6000

    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n... [TRUNCATED {len(text) - max_chars} chars]"
