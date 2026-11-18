"""Translation in context with Claude Haiku, for the reader. Optional: the API key comes from openhost's secrets app
(ANTHROPIC_API_KEY), and without one the reader falls back to the offline dictionary alone."""

import json
import threading
import urllib.error
import urllib.request

import anthropic
from loguru import logger

from srs.config import Config

MODEL = "claude-haiku-5-5"

WORD_SYSTEM = (
    "You are a {language}-English dictionary. The user gives you a {language} word and the sentence it appears in. "
    "Reply with a brief English translation of the word as used in that sentence (1-6 words). If it's an "
    "inflected form, add its dictionary form in parentheses, eg 'set sail (zarpar)'. No other text."
)
TEXT_SYSTEM = (
    "You are a {language}-English translator. Translate the user's {language} text into natural English. If it's "
    "idiomatic, you may add a very brief note in parentheses. Output only the translation."
)
LANGUAGE_NAMES = {"es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese"}


class TranslationUnavailable(Exception):
    pass


class Translator:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: anthropic.Anthropic | None = None
        self._lock = threading.Lock()

    def _api_key(self) -> str:
        if self._config.anthropic_api_key:
            return self._config.anthropic_api_key
        if not (self._config.router_url and self._config.app_token):
            raise TranslationUnavailable("no Anthropic API key configured")
        request = urllib.request.Request(
            f"{self._config.router_url}/api/services/v2/call/secrets/get",
            data=json.dumps({"keys": ["ANTHROPIC_API_KEY"]}).encode(),
            headers={
                "X-OpenHost-Authorization": f"Bearer {self._config.app_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - the openhost router
                key = json.load(response).get("secrets", {}).get("ANTHROPIC_API_KEY")
        except urllib.error.HTTPError as e:
            raise TranslationUnavailable(f"secrets service refused ({e.code}); grant ANTHROPIC_API_KEY to srs") from e
        except urllib.error.URLError as e:
            raise TranslationUnavailable(f"couldn't reach the secrets service: {e.reason}") from e
        if not key:
            raise TranslationUnavailable("ANTHROPIC_API_KEY isn't set in the secrets app")
        return str(key)

    def _get_client(self) -> anthropic.Anthropic:
        with self._lock:
            if self._client is None:
                self._client = anthropic.Anthropic(api_key=self._api_key(), timeout=30.0)
            return self._client

    def _ask(self, system: str, content: str, max_tokens: int) -> str:
        client = self._get_client()
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                output_config={"effort": "low"},
                system=system,
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.AuthenticationError as e:
            with self._lock:
                self._client = None  # the key may have been rotated; fetch it again next time
            raise TranslationUnavailable("the Anthropic API key was rejected") from e
        except anthropic.APIStatusError as e:
            logger.warning(f"translation failed: {e.status_code} {e.message}")
            raise TranslationUnavailable(f"Claude API error ({e.status_code})") from e
        except anthropic.APIConnectionError as e:
            raise TranslationUnavailable("couldn't reach the Claude API") from e
        if response.stop_reason == "refusal":
            raise TranslationUnavailable("Claude declined to translate this")
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def word(self, language: str, word: str, sentence: str) -> str:
        name = LANGUAGE_NAMES.get(language, language)
        return self._ask(WORD_SYSTEM.format(language=name), f"Word: {word}\nSentence: {sentence}", 2000)

    def text(self, language: str, text: str) -> str:
        name = LANGUAGE_NAMES.get(language, language)
        return self._ask(TEXT_SYSTEM.format(language=name), text, 8000)
