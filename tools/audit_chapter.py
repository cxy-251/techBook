from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

BANNED_PHRASES = (
    "本章将",
    "读完本章",
    "本章总结",
    "深入理解",
)
EVIDENCE_MARKERS = (
    ".. literalinclude::",
    ".. code-block:: console",
    ".. doctest::",
)


def rst_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".rst":
            files.append(path)
            continue
        if path.is_dir():
            files.extend(
                candidate
                for candidate in path.rglob("*.rst")
                if "_build" not in candidate.parts
            )
    return sorted(set(files))


def prose_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].startswith((".. ", ":", "* ", "- ", "#.", "#. ")):
            continue
        if len(lines) == 2 and set(lines[1]) <= set("=-~^\"'`:+*#<>"):
            continue
        normalized = " ".join(lines)
        if len(normalized) >= 40:
            paragraphs.append(normalized)
    return paragraphs


def audit_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    if "```" in text:
        errors.append("contains Markdown fenced code block")

    is_chapter = path.name.startswith("chapter-")
    if not is_chapter:
        return errors

    for phrase in BANNED_PHRASES:
        if phrase in text:
            errors.append(f"contains banned phrase: {phrase}")

    if not any(marker in text for marker in EVIDENCE_MARKERS):
        errors.append("chapter has no literalinclude, console output, or doctest evidence")

    seen: dict[str, list[int]] = defaultdict(list)
    for index, paragraph in enumerate(prose_paragraphs(text), start=1):
        key = re.sub(r"\s+", " ", paragraph).casefold()
        seen[key].append(index)
    for indexes in seen.values():
        if len(indexes) > 1:
            errors.append(f"contains duplicated prose paragraphs: {indexes}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit source-first RST chapters")
    parser.add_argument("paths", nargs="*", default=["docs"], type=Path)
    args = parser.parse_args()

    files = rst_files(args.paths)
    if not files:
        print("No RST files found", file=sys.stderr)
        return 2

    failures = 0
    for path in files:
        for error in audit_file(path):
            failures += 1
            print(f"{path}: {error}", file=sys.stderr)

    if failures:
        print(f"RST audit failed with {failures} error(s)", file=sys.stderr)
        return 1

    print(f"RST audit passed: {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
