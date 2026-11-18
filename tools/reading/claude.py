"""Claude helpers for preparing material, ported from the old spanish-reader app (sync, Claude Haiku).

Needs credentials for the Anthropic SDK locally (ANTHROPIC_API_KEY, or an `ant auth login` profile). Without them,
`via_app` translates through the deployed app instead, which uses the key in the openhost secrets app.
"""

import base64
import json
from functools import cache
from typing import Any

import anthropic

from tools.reading.client import SrsClient

MODEL = "claude-haiku-5-5"
LANGUAGE_NAMES = {
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "en": "English",
}


@cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _ask(system: str, content: Any, max_tokens: int = 4000) -> str:
    response = _client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        output_config={"effort": "low"},
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined")
    return "".join(b.text for b in response.content if b.type == "text").strip()


def detect_language(text: str) -> str:
    return _ask(
        "Identify the language of the user's text. Reply with only its ISO 639-1 code (eg 'en' or 'es').",
        text[:500],
        200,
    ).lower()


def translate_text(text: str, to_language: str = "es") -> str:
    """Translate into `to_language` (eg to make reading material from English text), keeping paragraphs."""
    name = LANGUAGE_NAMES.get(to_language, to_language)
    return _ask(
        f"You are a professional translator. Translate the user's text into natural, fluent {name}. Preserve "
        f"paragraph structure. Output only the translation.",
        text,
        16000,
    )


def translate_word(word: str, sentence: str, language: str = "es") -> str:
    name = LANGUAGE_NAMES.get(language, language)
    return _ask(
        f"You are a {name}-English dictionary. The user gives you a {name} word and the sentence it appears in. "
        "Reply with a brief English translation (1-5 words). No explanations, no extra text.",
        f"Word: {word}\nSentence: {sentence}",
        1000,
    )


def translate_phrase(phrase: str, sentence: str, language: str = "es") -> str:
    name = LANGUAGE_NAMES.get(language, language)
    return _ask(
        f"You are a {name}-English translator. The user gives you a {name} phrase and the sentence it appears in. "
        "Reply with a concise English translation. If the phrase is idiomatic, you may add a very brief note in "
        "parentheses. No other text.",
        f"Phrase: {phrase}\nSentence: {sentence}",
        1000,
    )


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Body text of a PDF for the reader: no page numbers, headers, footnotes or captions."""
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
    return _ask(
        "You are a text extraction tool. The user provides a PDF document. Extract all the readable body text from "
        "it for use in a plain text reader. Strip all extraneous content: page numbers, headers, footers, footnotes, "
        "figure captions, table formatting, URLs, and any non-body-text elements. Preserve paragraph structure "
        "using blank lines between paragraphs. Output only the clean body text, nothing else.",
        [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": "Extract the body text from this PDF."},
        ],
        32000,
    )


def gloss_words(words: list[dict[str, str]], language: str = "es") -> list[dict[str, Any]]:
    """Dictionary entries for review sets. `words`: [{"word": ..., "context": a sentence it appears in}]. Returns,
    in order, [{"word", "lemma", "pos", "gloss", "gender"}], with glosses fitted to how the word is used."""
    name = LANGUAGE_NAMES.get(language, language)
    out: list[dict[str, Any]] = []
    for i in range(0, len(words), 60):
        batch = words[i : i + 60]
        reply = _ask(
            f"You write concise {name}-English flashcard entries. For each input word (with a sentence it appears "
            "in) give its dictionary form (lemma; infinitive for verbs, masculine singular for adjectives, singular "
            "for nouns), part of speech (one of: noun, verb, adjective, adverb, pronoun, determiner, preposition, "
            "conjunction, numeral, interjection, other), grammatical gender for nouns (masculine/feminine, else "
            "null), and a short English gloss fitting the context, adding a common fixed expression in parentheses "
            "if the context uses one. Reply with only a JSON array of objects with keys word, lemma, pos, gender, "
            "gloss, in input order.",
            json.dumps(batch, ensure_ascii=False),
            8000,
        )
        start, end = reply.find("["), reply.rfind("]")
        out.extend(json.loads(reply[start : end + 1]))
    return out


def via_app(client: SrsClient, text: str, language: str = "es", context: str | None = None) -> str:
    """Translate through the deployed app (its key, its cache): a word in `context`, or a passage."""
    body = {"language": language, "kind": "word" if context else "text", "text": text, "context": context or ""}
    return str(client.post("/reader/translate", body)["translation"])
