"""Reader marks: words you know (or want ignored) that aren't in a deck."""

from wordfreq import top_n_list

from tools.reading.client import SrsClient


def mark(client: SrsClient, language: str, words: list[str], status: str | None) -> None:
    """status: "known", "ignored", or None to clear."""
    for i in range(0, len(words), 2000):
        client.put("/reader/marks", {"language": language, "words": words[i : i + 2000], "status": status})


def common_words(language: str, n: int) -> list[str]:
    """The n most frequent words of the language (wordfreq)."""
    return [w for w in top_n_list(language, n * 2) if w.isalpha()][:n]


def seed_common_known(client: SrsClient, language: str, n: int) -> list[str]:
    """Mark the n most common words known, so the reader doesn't highlight basics your deck never had. Words in a
    deck keep their deck status regardless (deck beats marks). Returns the words, eg to save for undoing."""
    words = common_words(language, n)
    mark(client, language, words, "known")
    return words
