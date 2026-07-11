from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "manifests"


def load_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def validate_tracks() -> list[str]:
    path = MANIFESTS / "tracks.toml"
    if not path.is_file():
        return ["manifests/tracks.toml is missing"]

    data = load_toml(path)
    tracks = data.get("track", [])
    errors: list[str] = []
    ids = [track.get("id") for track in tracks]

    if not tracks:
        errors.append("manifests/tracks.toml has no tracks")
    if None in ids:
        errors.append("a track is missing id")
    if len(ids) != len(set(ids)):
        errors.append("track ids must be unique")

    for track in tracks:
        for field in ("id", "title", "source_path", "status"):
            if not track.get(field):
                errors.append(f"track {track.get('id', '<missing>')} is missing {field}")
    return errors


def validate_track_files() -> list[str]:
    errors: list[str] = []
    directory = MANIFESTS / "tracks"
    for path in sorted(directory.glob("*.toml")):
        data = load_toml(path)
        label = path.relative_to(ROOT)
        target = data.get("target", {})
        stages = data.get("stage", [])

        for field in ("reader", "entry_level", "target_level", "outcome"):
            if not target.get(field):
                errors.append(f"{label}: target.{field} is missing")

        orders = [stage.get("order") for stage in stages]
        if orders != list(range(1, len(stages) + 1)):
            errors.append(f"{label}: stage order must be continuous from 1")

        stage_ids = [stage.get("id") for stage in stages]
        if None in stage_ids or len(stage_ids) != len(set(stage_ids)):
            errors.append(f"{label}: stage ids must exist and be unique")
    return errors


def validate_units() -> list[str]:
    errors: list[str] = []
    directory = MANIFESTS / "units"
    for path in sorted(directory.glob("*.toml")):
        data = load_toml(path)
        label = path.relative_to(ROOT)
        for field in ("id", "track", "stage", "title", "status"):
            if not data.get(field):
                errors.append(f"{label}: {field} is missing")

        loop = data.get("learning_loop", {})
        for field in (
            "opening_problem",
            "prediction_required",
            "variation_required",
            "misconception_required",
            "transfer_task_required",
        ):
            if field not in loop:
                errors.append(f"{label}: learning_loop.{field} is missing")
    return errors


def main() -> int:
    errors: list[str] = []
    try:
        errors.extend(validate_tracks())
        errors.extend(validate_track_files())
        errors.extend(validate_units())
    except (OSError, tomllib.TOMLDecodeError) as error:
        errors.append(str(error))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"Learning model validation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print("Learning model validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
