from typing import Dict, Any
from langchain.tools import tool

_FAKE_CRM = {
    'known_senders': {
        'hr@example.com': {'relationship': 'internal_hr'},
        'vendor@sales.com': {'relationship': 'vendor'},
    }
}

@tool("lookup_crm")
def lookup_crm(sender: str) -> Dict[str, Any]:
    """Lookup sender in fake CRM returning relationship info (stub)."""
    return _FAKE_CRM['known_senders'].get(sender, {'relationship': 'unknown'})
