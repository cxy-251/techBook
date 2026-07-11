from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / "manifests" / "books"


def load_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def validate_plan(index_path: Path) -> list[str]:
    errors: list[str] = []
    plan = load_toml(index_path)
    label = index_path.relative_to(ROOT)

    if plan.get("status") != "frozen":
        return errors

    part_files = plan.get("part_files")
    if not isinstance(part_files, list) or not part_files:
        return [f"{label}: frozen plan must define part_files"]

    chapters: list[dict] = []
    for relative in part_files:
        part_path = ROOT / relative
        if not part_path.is_file():
            errors.append(f"{label}: missing part file {relative}")
            continue
        part = load_toml(part_path)
        entries = part.get("chapter", [])
        if not entries:
            errors.append(f"{part_path.relative_to(ROOT)}: no chapters")
        chapters.extend(entries)

    expected_count = plan.get("chapter_count")
    if expected_count != len(chapters):
        errors.append(
            f"{label}: chapter_count={expected_count}, loaded={len(chapters)}"
        )

    ids = [chapter.get("id") for chapter in chapters]
    if None in ids:
        errors.append(f"{label}: chapter without id")
    if len(ids) != len(set(ids)):
        errors.append(f"{label}: duplicate chapter id")

    orders = [chapter.get("order") for chapter in chapters]
    expected_orders = list(range(1, len(chapters) + 1))
    if orders != expected_orders:
        errors.append(f"{label}: chapter order must be {expected_orders}, got {orders}")

    seen: set[str] = set()
    for chapter in chapters:
        chapter_id = chapter.get("id", "<missing>")
        for prerequisite in chapter.get("prerequisites", []):
            if prerequisite not in seen:
                errors.append(
                    f"{label}: {chapter_id} prerequisite {prerequisite} "
                    "must refer to an earlier chapter"
                )
        seen.add(chapter_id)

    first = plan.get("first", {}).get("chapter_id")
    if chapters and first != chapters[0].get("id"):
        errors.append(
            f"{label}: first.chapter_id={first}, actual={chapters[0].get('id')}"
        )

    return errors


def main() -> int:
    indexes = sorted(BOOKS.glob("*-plan.toml"))
    if not indexes:
        print("No book plan indexes found", file=sys.stderr)
        return 2

    errors: list[str] = []
    for index in indexes:
        try:
            errors.extend(validate_plan(index))
        except (OSError, tomllib.TOMLDecodeError) as error:
            errors.append(f"{index.relative_to(ROOT)}: {error}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"Book plan validation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print(f"Book plan validation passed: {len(indexes)} plan(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
