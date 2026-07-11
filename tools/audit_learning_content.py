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
    "全面掌握",
)

REQUIRED_UNIT_HEADINGS = (
    "先预测",
    "真实结果",
    "逐步推理",
    "改变一个条件",
    "常见误解",
    "答案与推理",
    "独立任务",
    "完成标准",
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

    is_unit = path.name.startswith("unit-")
    if not is_unit:
        return errors

    for phrase in BANNED_PHRASES:
        if phrase in text:
            errors.append(f"contains banned phrase: {phrase}")

    for heading in REQUIRED_UNIT_HEADINGS:
        if heading not in text:
            errors.append(f"missing learning section: {heading}")

    if not any(marker in text for marker in EVIDENCE_MARKERS):
        errors.append("unit has no runnable, console, or doctest evidence")

    seen: dict[str, list[int]] = defaultdict(list)
    for index, paragraph in enumerate(prose_paragraphs(text), start=1):
        key = re.sub(r"\s+", " ", paragraph).casefold()
        seen[key].append(index)
    for indexes in seen.values():
        if len(indexes) > 1:
            errors.append(f"contains duplicated prose paragraphs: {indexes}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit executable learning RST content")
    parser.add_argument("paths", nargs="*", default=["docs"], type=Path)
    args = parser.parse_args()

    files = rst_files(args.paths)
    if not files:
        print("No RST files found", file=sys.stderr)
        return 2

    failures = 0
    unit_count = 0
    for path in files:
        if path.name.startswith("unit-"):
            unit_count += 1
        for error in audit_file(path):
            failures += 1
            print(f"{path}: {error}", file=sys.stderr)

    if failures:
        print(f"Learning content audit failed with {failures} error(s)", file=sys.stderr)
        return 1

    print(f"Learning content audit passed: {len(files)} RST file(s), {unit_count} unit(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
