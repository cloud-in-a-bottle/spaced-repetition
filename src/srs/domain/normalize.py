import unicodedata


def lookup_key(text: str) -> str:
    """Key used to match words across apps: NFC, case-folded, trimmed. Accents are kept since they're meaningful."""
    return unicodedata.normalize("NFC", text).strip().casefold()
