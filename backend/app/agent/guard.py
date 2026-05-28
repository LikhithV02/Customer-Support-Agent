"""Lightweight prompt-injection detection.

This is observability only — it lets the admin dashboard flag suspicious
messages. It is NOT the enforcement mechanism. Enforcement is the deterministic
policy gate in `issue_refund`, which holds even when an injection slips past
these heuristics.
"""

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("override_policy", re.compile(r"ignore (the |all |your )?(rules|policy|policies|instructions)", re.I)),
    ("force_approval", re.compile(r"\b(approve|refund) (it|this|me|the order)?\s*(anyway|regardless|now)\b", re.I)),
    ("authority_claim", re.compile(r"\b(i am|i'm|as) (the |a )?(ceo|manager|admin|administrator|supervisor|owner|developer)\b", re.I)),
    ("role_override", re.compile(r"\b(you are now|act as|pretend to be|new instructions|system prompt|developer mode|jailbreak)\b", re.I)),
    ("bypass", re.compile(r"\b(bypass|override|disable|skip) (the )?(policy|rules|check|verification|escalation)\b", re.I)),
    ("exfiltration", re.compile(r"\b(reveal|show|print|repeat) (me )?(your |the )?(system prompt|instructions|policy rules)\b", re.I)),
]


def detect_injection(text: str) -> list[str]:
    """Return the names of any suspicious patterns found in `text`."""
    if not text:
        return []
    return [name for name, pattern in _PATTERNS if pattern.search(text)]
