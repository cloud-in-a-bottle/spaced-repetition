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


def parse_srt(content: str) -> list[Block]:
    """One block per cue, its lines joined; markup like <i> dropped."""
    blocks = []
    for chunk in re.split(r"\n\s*\n", content.replace("\r\n", "\n").lstrip("﻿")):
        lines = [ln.strip() for ln in chunk.strip().splitlines()]
        stamp = next((_TIMESTAMP.search(ln) for ln in lines if _TIMESTAMP.search(ln)), None)
        if stamp is None:
            continue
        body = [ln for ln in lines if ln and "-->" not in ln and not (ln.isdigit() and lines.index(ln) == 0)]
        text = re.sub(r"<[^>]+>|\{\\[^}]*\}", "", "\n".join(body)).strip()
        if text:
            g = stamp.groups()
            blocks.append(Block(text=text, start_ms=_ms(*g[:4]), end_ms=_ms(*g[4:])))
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
