import html
import re

_BREAKS = re.compile(r"<\s*(br|/div|/p|/li)\s*/?\s*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_SOUND = re.compile(r"\[sound:[^\]]*\]")
_SPACES = re.compile(r"[ \t ]+")


def clean(raw: str) -> str:
    """Anki field html -> plain text: line breaks kept, tags/sound refs dropped, entities decoded, whitespace tidied."""
    text = _SOUND.sub("", raw)
    text = _BREAKS.sub("\n", text)
    text = _TAGS.sub("", text)
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def one_line(raw: str) -> str:
    return " ".join(clean(raw).split("\n"))
