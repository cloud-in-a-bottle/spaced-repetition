"""Turning imported content into blocks (paragraphs or subtitle cues) and blocks into word tokens."""

import re

import attr

from srs.domain.errors import InvalidRequest
from srs.domain.normalize import lookup_key

# letters, with inner apostrophes ("l'eau"); digits and underscores aren't words
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
_TIMESTAMP = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{3})\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d{3})")


@attr.s(auto_attribs=True, frozen=True)
class Block:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


@attr.s(auto_attribs=True, frozen=True)
class Token:
    text: str
    # normalized word for lookups; None for spaces and punctuation
    key: str | None


def tokenize(text: str) -> list[Token]:
    tokens, pos = [], 0
    for m in _WORD.finditer(text):
        if m.start() > pos:
            tokens.append(Token(text[pos : m.start()], None))
        tokens.append(Token(m.group(), lookup_key(m.group())))
        pos = m.end()
    if pos < len(text):
        tokens.append(Token(text[pos:], None))
    return tokens


def _ms(h: str, m: str, s: str, ms: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


# A line ending in one of these finishes a sentence; a line starting with a dash is a new speaker.
_SENTENCE_END = (".", "?", "!", "…", ")", "]", '"', "»", ":", "♪")
_DASHES = ("-", "–", "—")
# Don't merge more cues than this into one line, however long the sentence runs.
_MAX_MERGED_CUES = 4


def _join_lines(lines: list[str]) -> str:
    """Subtitle line wraps become spaces; breaks after a finished sentence or before a speaker dash stay."""
    out = ""
    for line in lines:
        if not out:
            out = line
        elif out.endswith(_SENTENCE_END) or line.startswith(_DASHES):
            out += "\n" + line
        else:
            out += " " + line
    return out


def _cues(content: str) -> list[Block]:
    cues = []
    for chunk in re.split(r"\n\s*\n", content.replace("\r\n", "\n").lstrip("\ufeff")):
        lines = [ln.strip() for ln in chunk.strip().splitlines()]
        stamp = next((_TIMESTAMP.search(ln) for ln in lines if _TIMESTAMP.search(ln)), None)
        if stamp is None:
            continue
        body = [ln for ln in lines if ln and "-->" not in ln and not (ln.isdigit() and lines.index(ln) == 0)]
        body = [re.sub(r"<[^>]+>|\{\\[^}]*\}", "", ln).strip() for ln in body]
        text = _join_lines([ln for ln in body if ln])
        if text:
            g = stamp.groups()
            cues.append(Block(text=text, start_ms=_ms(*g[:4]), end_ms=_ms(*g[4:])))
    return cues


def parse_srt(content: str) -> list[Block]:
    """One block per sentence-ish run of cues: line wraps inside a cue are joined, and a cue that stops mid-sentence
    is merged with the next (keeping the first one's start time). Markup like <i> is dropped."""
    blocks: list[Block] = []
    merged = 0
    for cue in _cues(content):
        prev = blocks[-1] if blocks else None
        if prev is not None and not prev.text.endswith(_SENTENCE_END) and merged < _MAX_MERGED_CUES - 1:
            blocks[-1] = Block(text=_join_lines([prev.text, cue.text]), start_ms=prev.start_ms, end_ms=cue.end_ms)
            merged += 1
        else:
            blocks.append(cue)
            merged = 0
    if not blocks:
        raise InvalidRequest("no subtitle cues found; is this an .srt file?")
    return blocks


def parse_plain(content: str) -> list[Block]:
    """Paragraphs separated by blank lines; single newlines inside a paragraph are kept."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content.replace("\r\n", "\n"))]
    blocks = [Block(text=p) for p in paragraphs if p]
    if not blocks:
        raise InvalidRequest("the text is empty")
    return blocks


def parse_content(fmt: str, content: str) -> tuple[str, list[Block]]:
    """(stored format, blocks) for an import in `fmt`: `srt` or `text`."""
    if fmt == "srt":
        return "subtitles", parse_srt(content)
    if fmt == "text":
        return "text", parse_plain(content)
    raise InvalidRequest(f"unknown format {fmt!r}; use `text` or `srt`")
