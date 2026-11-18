"""uv run python -m tools.reading <command> --help"""

import argparse
import json
from pathlib import Path

from tools.reading import content
from tools.reading import lingq
from tools.reading import marks
from tools.reading.client import DEFAULT_APP_URL
from tools.reading.client import SrsClient


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m tools.reading")
    p.add_argument("--url", default=DEFAULT_APP_URL, help="app URL; http://127.0.0.1:PORT for a local server")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="word statuses for a .srt or text file")
    a.add_argument("file", type=Path)
    a.add_argument("--language", default="es")
    a.add_argument("--top", type=int, default=60)
    a.add_argument("--json", type=Path, help="also write the full list here")

    t = sub.add_parser("add-text", help="put a .srt or text file in the library (creating the course if needed)")
    t.add_argument("file", type=Path)
    t.add_argument("--course-id", required=True)
    t.add_argument("--course-title")
    t.add_argument("--language", default="es")
    t.add_argument("--text-id", required=True)
    t.add_argument("--title", required=True)
    t.add_argument("--position", type=int)

    s = sub.add_parser("seed-known", help="mark the N most common words known (undo with --clear)")
    s.add_argument("--language", default="es")
    s.add_argument("-n", type=int, default=1000)
    s.add_argument("--clear", action="store_true")

    m = sub.add_parser("mark-lingq", help="mark every word of a LingQ CSV export known/ignored (phrases are skipped)")
    m.add_argument("file", type=Path)
    m.add_argument("--language", default="es")
    m.add_argument("--status", choices=["known", "ignored", "clear"], default="known")

    d = sub.add_parser("install-dictionary", help="have the app download and build an offline dictionary")
    d.add_argument("--language", default="es")

    args = p.parse_args()
    client = SrsClient(args.url)
    if args.cmd == "analyze":
        words = content.analyze(client, args.language, args.file)
        content.print_report(words, args.top)
        if args.json:
            args.json.write_text(json.dumps(words, ensure_ascii=False, indent=1))
    elif args.cmd == "add-text":
        if args.course_title:
            content.ensure_course(client, args.course_id, args.course_title, args.language)
        print(content.add_text(client, args.text_id, args.course_id, args.title, args.file, args.position))
    elif args.cmd == "seed-known":
        words = marks.common_words(args.language, args.n)
        marks.mark(client, args.language, words, None if args.clear else "known")
        print(f"{'cleared' if args.clear else 'marked known'}: {len(words)} words")
    elif args.cmd == "mark-lingq":
        words, phrases = lingq.read_terms(args.file)
        marks.mark(client, args.language, words, None if args.status == "clear" else args.status)
        print(f"{args.status}: {len(words)} words; skipped {len(phrases)} phrases (the reader marks single words)")
    elif args.cmd == "install-dictionary":
        print(client.post(f"/dictionaries/{args.language}/install", {}))


if __name__ == "__main__":
    main()
