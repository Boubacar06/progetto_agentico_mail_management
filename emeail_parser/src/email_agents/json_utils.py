"""Utility to extract JSON from LLM responses that may contain markdown or free text."""
import json
import re
from typing import Any, Dict


def extract_json(text: str) -> Dict[str, Any]:
    """Extract the first JSON object from *text*, tolerating markdown fences and prose.

    Tries in order:
    1. Direct ``json.loads`` on the whole text.
    2. Content inside ```json ... ``` or ``` ... ``` fences.
    3. First substring that looks like ``{ ... }``.
    Returns ``{}`` only if nothing can be parsed.
    """
    text = text.strip()

    # 1. Try direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Try markdown code fences (```json ... ``` or ``` ... ```)
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
    for match in fence_pattern.finditer(text):
        try:
            obj = json.loads(match.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    # 3. Try to find the first { ... } substring (greedy from first { to last })
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidate = text[first : last + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    return {}
