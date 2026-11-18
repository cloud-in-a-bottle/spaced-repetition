"""The reader tab: library (courses and texts), reading a text with word statuses, word details, marks, Claude
translations, and the offline dictionaries."""

from collections import Counter

import attr
from litestar import delete
from litestar import get
from litestar import post
from litestar import put
from litestar.exceptions import HTTPException
from litestar.params import FromPath
from litestar.params import FromQuery
from litestar.params import JSONBody

from srs.api.deps import Db
from srs.api.deps import Dicts
from srs.api.deps import Translations
from srs.dictionary.store import InstallStatus
from srs.domain.clock import now_ms
from srs.domain.errors import InvalidRequest
from srs.reader import library
from srs.reader.text_formats import parse_content
from srs.reader.text_formats import tokenize
from srs.reader.words import WordDetails
from srs.reader.words import mark_words
from srs.reader.words import word_details
from srs.reader.words import word_statuses
from srs.repo.decks import largest_main_deck
from srs.translate import TranslationUnavailable

# --- library ---


@attr.s(auto_attribs=True, frozen=True)
class TextSummary:
    id: str
    title: str
    position: int
    format: str
    blocks: int
    words: int
    read_at: int | None


@attr.s(auto_attribs=True, frozen=True)
class CourseView:
    id: str
    title: str
    language: str
    description: str
    texts: list[TextSummary]


def _summary(t: library.Text) -> TextSummary:
    words = sum(1 for b in t.blocks for tok in tokenize(b.text) if tok.key)
    return TextSummary(
        id=t.id,
        title=t.title,
        position=t.position,
        format=t.format,
        blocks=len(t.blocks),
        words=words,
        read_at=t.read_at,
    )


def _course_view(conn, c: library.Course) -> CourseView:  # type: ignore[no-untyped-def]
    return CourseView(
        id=c.id,
        title=c.title,
        language=c.language,
        description=c.description,
        texts=[_summary(t) for t in library.texts_of(conn, c.id)],
    )


@get("/library", sync_to_thread=True)
def library_index(db: Db) -> list[CourseView]:
    with db.transaction() as conn:
        return [_course_view(conn, c) for c in library.list_courses(conn)]


@attr.s(auto_attribs=True, frozen=True)
class CourseInput:
    title: str
    language: str
    description: str = ""


@post("/library/courses", sync_to_thread=True)
def course_create(db: Db, data: JSONBody[CourseInput]) -> CourseView:
    with db.transaction() as conn:
        c = library.save_course(conn, None, data.title, data.language, data.description, now_ms())
        return _course_view(conn, c)


@put("/library/courses/{course_id:str}", sync_to_thread=True)
def course_save(db: Db, course_id: FromPath[str], data: JSONBody[CourseInput]) -> CourseView:
    """Create-or-update under a chosen id."""
    with db.transaction() as conn:
        c = library.save_course(conn, course_id, data.title, data.language, data.description, now_ms())
        return _course_view(conn, c)


@delete("/library/courses/{course_id:str}", sync_to_thread=True)
def course_delete(db: Db, course_id: FromPath[str]) -> None:
    with db.transaction() as conn:
        library.delete_course(conn, course_id)


@attr.s(auto_attribs=True, frozen=True)
class TextInput:
    course_id: str
    title: str
    # where it sits in the course (eg the episode number); defaults to the end
    position: int | None = None
    # `text` (paragraphs separated by blank lines) or `srt` (subtitles); with `content`, required on create
    format: str | None = None
    content: str | None = None


def _save_text(db: Db, text_id: str | None, data: TextInput) -> TextSummary:
    fmt, blocks = (None, None)
    if data.content is not None:
        fmt, blocks = parse_content(data.format or "text", data.content)
    with db.transaction() as conn:
        t = library.save_text(conn, text_id, data.course_id, data.title, data.position, fmt, blocks, now_ms())
        return _summary(t)


@post("/library/texts", sync_to_thread=True)
def text_create(db: Db, data: JSONBody[TextInput]) -> TextSummary:
    return _save_text(db, None, data)


@put("/library/texts/{text_id:str}", sync_to_thread=True)
def text_save(db: Db, text_id: FromPath[str], data: JSONBody[TextInput]) -> TextSummary:
    """Create-or-update under a chosen id; without `content` an existing text keeps its content."""
    return _save_text(db, text_id, data)


@delete("/library/texts/{text_id:str}", sync_to_thread=True)
def text_delete(db: Db, text_id: FromPath[str]) -> None:
    with db.transaction() as conn:
        library.delete_text(conn, text_id)


@attr.s(auto_attribs=True, frozen=True)
class ReadInput:
    read: bool


@put("/library/texts/{text_id:str}/read", sync_to_thread=True)
def text_mark_read(db: Db, text_id: FromPath[str], data: JSONBody[ReadInput]) -> None:
    with db.transaction() as conn:
        library.mark_read(conn, text_id, now_ms() if data.read else None)


# --- reading ---


@attr.s(auto_attribs=True, frozen=True)
class ReadingBlock:
    # [text, key] pairs; key is null for spaces and punctuation
    tokens: list[tuple[str, str | None]]
    start_ms: int | None
    end_ms: int | None


@attr.s(auto_attribs=True, frozen=True)
class Reading:
    id: str
    title: str
    course_id: str
    course_title: str
    language: str
    format: str
    position: int
    previous_id: str | None
    next_id: str | None
    blocks: list[ReadingBlock]
    # status per word key (see srs.reader.words.Status)
    words: dict[str, str]
    # where "add to deck" puts words by default
    default_deck_id: str | None
    dictionary: bool


@get("/reader/texts/{text_id:str}", sync_to_thread=True)
def reading_show(db: Db, dicts: Dicts, text_id: FromPath[str]) -> Reading:
    with db.transaction() as conn:
        t = library.get_text(conn, text_id)
        course = library.get_course(conn, t.course_id)
        siblings = library.texts_of(conn, course.id)
        i = [s.id for s in siblings].index(t.id)
        dictionary = dicts.get(course.language)
        tokenized = [tokenize(b.text) for b in t.blocks]
        words = word_statuses(
            conn, dictionary, course.language, [tok for b in t.blocks for tok in tokenize(b.text + "\n")], now_ms()
        )
        return Reading(
            id=t.id,
            title=t.title,
            course_id=course.id,
            course_title=course.title,
            language=course.language,
            format=t.format,
            position=t.position,
            previous_id=siblings[i - 1].id if i > 0 else None,
            next_id=siblings[i + 1].id if i + 1 < len(siblings) else None,
            blocks=[
                ReadingBlock(tokens=[(tok.text, tok.key) for tok in ts], start_ms=b.start_ms, end_ms=b.end_ms)
                for b, ts in zip(t.blocks, tokenized, strict=True)
            ],
            words=words,
            default_deck_id=largest_main_deck(conn, course.language),
            dictionary=dictionary is not None,
        )


@get("/reader/texts/{text_id:str}/words", sync_to_thread=True)
def reading_words(db: Db, dicts: Dicts, text_id: FromPath[str]) -> dict[str, str]:
    """Just the word statuses of a text, to refresh the page after adding or marking a word."""
    with db.transaction() as conn:
        t = library.get_text(conn, text_id)
        language = library.get_course(conn, t.course_id).language
        tokens = [tok for b in t.blocks for tok in tokenize(b.text + "\n")]
        return word_statuses(conn, dicts.get(language), language, tokens, now_ms())


@attr.s(auto_attribs=True, frozen=True)
class StatusesInput:
    language: str
    words: list[str]


@post("/reader/statuses", sync_to_thread=True)
def reading_statuses(db: Db, dicts: Dicts, data: JSONBody[StatusesInput]) -> dict[str, str]:
    """Fresh statuses for some words, eg after adding one to a deck (which can change its other forms too)."""
    if len(data.words) > 20000:
        raise InvalidRequest("at most 20000 words per request")
    tokens = [t for w in data.words for t in tokenize(w + "\n")]
    with db.transaction() as conn:
        return word_statuses(conn, dicts.get(data.language), data.language, tokens, now_ms())


@get("/reader/word", sync_to_thread=True)
def reading_word(db: Db, dicts: Dicts, language: FromQuery[str], word: FromQuery[str]) -> WordDetails:
    with db.transaction() as conn:
        return word_details(conn, dicts.get(language), language, word, now_ms())


@attr.s(auto_attribs=True, frozen=True)
class MarksInput:
    language: str
    words: list[str]
    # `known` (on the words' roots), `ignored` (on the exact spellings), or null to clear both
    status: str | None
    # for `known`: mark these roots instead of all the words' roots (eg "casa" but not "casar" for "casas")
    roots: list[str] | None = None


@put("/reader/marks", sync_to_thread=True)
def reading_marks(db: Db, dicts: Dicts, data: JSONBody[MarksInput]) -> None:
    if data.status not in ("known", "ignored", None):
        raise InvalidRequest("status must be `known`, `ignored` or null")
    dictionary = dicts.get(data.language)
    with db.transaction() as conn:
        mark_words(conn, dictionary, data.language, data.words, data.status, now_ms(), data.roots)


@attr.s(auto_attribs=True, frozen=True)
class AnalyzeInput:
    language: str
    content: str
    # `text` or `srt`
    format: str = "text"


@attr.s(auto_attribs=True, frozen=True)
class WordCount:
    key: str
    count: int
    status: str
    forms: list[str]


@post("/reader/analyze", sync_to_thread=True)
def reading_analyze(db: Db, dicts: Dicts, data: JSONBody[AnalyzeInput]) -> list[WordCount]:
    """Every distinct word in some content, most frequent first, with its status: for scripts that prepare review
    sets (see tools/reading)."""
    _, blocks = parse_content(data.format, data.content)
    tokens = [t for b in blocks for t in tokenize(b.text)]
    counts = Counter(t.key for t in tokens if t.key)
    forms: dict[str, set[str]] = {}
    for t in tokens:
        if t.key:
            forms.setdefault(t.key, set()).add(t.text)
    with db.transaction() as conn:
        statuses = word_statuses(conn, dicts.get(data.language), data.language, tokens, now_ms())
    return [WordCount(key=k, count=n, status=statuses[k], forms=sorted(forms[k])) for k, n in counts.most_common()]


# --- translation ---


@attr.s(auto_attribs=True, frozen=True)
class TranslateInput:
    language: str
    # `word` (translated as used in `context`) or `text` (a sentence, subtitle line or paragraph)
    kind: str
    text: str
    context: str = ""


@attr.s(auto_attribs=True, frozen=True)
class TranslateResult:
    translation: str
    cached: bool


@post("/reader/translate", sync_to_thread=True)
def reading_translate(db: Db, translator: Translations, data: JSONBody[TranslateInput]) -> TranslateResult:
    if data.kind not in ("word", "text"):
        raise InvalidRequest("kind must be `word` or `text`")
    if not data.text.strip() or len(data.text) > 5000:
        raise InvalidRequest("text must be 1-5000 characters")
    context = data.context if data.kind == "word" else ""
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT translation FROM translations WHERE language = ? AND kind = ? AND source = ? AND context = ?",
            (data.language, data.kind, data.text, context),
        ).fetchone()
    if row is not None:
        return TranslateResult(translation=row["translation"], cached=True)
    try:
        if data.kind == "word":
            translation = translator.word(data.language, data.text, context)
        else:
            translation = translator.text(data.language, data.text)
    except TranslationUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO translations (language, kind, source, context, translation, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (data.language, data.kind, data.text, context, translation, now_ms()),
        )
    return TranslateResult(translation=translation, cached=False)


# --- dictionaries ---


@attr.s(auto_attribs=True, frozen=True)
class DictionaryView:
    language: str
    status: InstallStatus


@get("/dictionaries", sync_to_thread=True)
def dictionaries_index(dicts: Dicts) -> list[DictionaryView]:
    return [DictionaryView(language=lang, status=dicts.status(lang)) for lang in dicts.available()]


@post("/dictionaries/{language:str}/install", sync_to_thread=True)
def dictionary_install(dicts: Dicts, language: FromPath[str]) -> DictionaryView:
    """Download (~100 MB from kaikki.org) and build in the background; poll GET /dictionaries for progress."""
    try:
        return DictionaryView(language=language, status=dicts.install(language))
    except ValueError as e:
        raise InvalidRequest(str(e)) from e
