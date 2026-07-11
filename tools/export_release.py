from __future__ import annotations

import fnmatch
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release-manifest.toml"


def excluded(relative: Path, patterns: list[str]) -> bool:
    value = relative.as_posix()
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def copy_entry(source: Path, destination_root: Path, excludes: list[str]) -> int:
    copied = 0
    if source.is_file():
        relative = source.relative_to(ROOT)
        if excluded(relative, excludes):
            return 0
        target = destination_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return 1

    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if excluded(relative, excludes):
            continue
        target = destination_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def main() -> int:
    data = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    config = data["release"]
    output = ROOT / config["output"]
    includes = [ROOT / item for item in config["include"]]
    excludes = list(config.get("exclude", []))

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    copied = 0
    for source in includes:
        if not source.exists():
            raise FileNotFoundError(f"Release include does not exist: {source}")
        copied += copy_entry(source, output, excludes)

    print(f"Release snapshot created at {output} with {copied} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
