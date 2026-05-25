from __future__ import annotations

import re


INJECTION_PATTERNS = [
    r"\bignore\s+(all\s+)?previous\s+instructions\b",
    r"\breveal\s+secrets?\b",
    r"\bsend\s+tokens?\b",
    r"\bdisable\s+security\b",
    r"\bbypass\s+policy\b",
    r"\brun\s+this\s+command\b",
    r"\bexfiltrate\b",
    r"\bsystem\s+prompt\b",
    r"\bdeveloper\s+message\b",
]


def detect_prompt_injection(text: str) -> bool:
    normalized = text.lower()
    return any(re.search(pattern, normalized) for pattern in INJECTION_PATTERNS)
