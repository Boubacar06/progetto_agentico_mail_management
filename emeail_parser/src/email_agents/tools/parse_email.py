from typing import Optional, Dict, Any, List
from langchain.tools import tool
from email import message_from_string
from email.message import Message
import re

@tool("parse_email", return_direct=True)
def parse_email(raw_email: str) -> Dict[str, Any]:
    """Parse raw RFC822 email string extracting headers, subject, sender, recipients and body (text/html)."""
    msg: Message = message_from_string(raw_email)
    headers = {k: v for k, v in msg.items()}
    subject = msg.get('Subject', '')
    sender = msg.get('From')
    recipients = [addr.strip() for addr in (msg.get('To', '') + ',' + msg.get('Cc', '')).split(',') if addr.strip()]

    body_text: Optional[str] = None
    body_html: Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get('Content-Disposition'))
            if ctype == 'text/plain' and 'attachment' not in disp:
                body_text = (part.get_payload(decode=True) or b'').decode(errors='ignore')
            elif ctype == 'text/html' and 'attachment' not in disp:
                body_html = (part.get_payload(decode=True) or b'').decode(errors='ignore')
    else:
        ctype = msg.get_content_type()
        payload = (msg.get_payload(decode=True) or b'').decode(errors='ignore')
        if ctype == 'text/plain':
            body_text = payload
        elif ctype == 'text/html':
            body_html = payload
        else:
            body_text = payload  # fallback

    # Clean excessive whitespace
    if body_text:
        body_text = re.sub(r'\s+', ' ', body_text).strip()

    return {
        'headers': headers,
        'subject': subject,
        'sender': sender,
        'recipients': recipients,
        'body_text': body_text,
        'body_html': body_html,
    }
