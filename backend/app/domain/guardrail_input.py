"""Conservative preprocessing; semantic attack detection remains a NeMo check."""
import re
import unicodedata


def normalize_input(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if unicodedata.category(c) != 'Cf')


def mask_sensitive(text: str) -> str:
    # Explicit credentials and contact/payment identifiers are unnecessary for search.
    patterns = [
        (r'(?i)\b(?:api[_ -]?key|password|access[_ -]?token|secret)\s*[:=]\s*[^\s,;"}]+', '[CREDENTIAL]'),
        (r'\b(?:sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,})\b', '[CREDENTIAL]'),
        (r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[TOKEN]'),
        (r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '[EMAIL]'),
        (r'\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b', '[ACCOUNT]'),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    def number(match):
        value = match.group()
        if re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
            return value
        return '[NUMBER]' if len(re.sub(r'\D', '', value)) >= 9 else value
    text = re.sub(r'(?<![\w-])\+?\d(?:[\d ()-]{7,}\d)(?![\w-])', number, text)
    return text


def obvious_override(text: str, *, retrieved: bool = False) -> bool:
    return bool(re.search(
        r'(?i)\b(?:ignore|override)\s+(?:all\s+)?(?:previous|system|safety)\s+(?:instructions|rules|prompts)\b'
        r'|\b(?:bypass|disable|skip)\s+(?:the\s+)?(?:safety checks|guardrails)\b', text)) or (
            retrieved and bool(re.search(r'(?i)\b(?:bypass|disable|skip)\s+(?:the\s+)?confirmation\b', text)))
