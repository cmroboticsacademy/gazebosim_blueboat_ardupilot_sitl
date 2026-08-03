#!/usr/bin/env python3
"""Configure the FPV cameras in one or more BlueBoat model SDF files."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
from typing import Iterable


BOAT_MODELS = ("blueboat", "blueboat2", "blueboat3", "blueboat4")

BOAT_ALIASES = {
    "1": "blueboat",
    "boat1": "blueboat",
    "blueboat1": "blueboat",
    "blueboat": "blueboat",
    "2": "blueboat2",
    "boat2": "blueboat2",
    "blueboat2": "blueboat2",
    "3": "blueboat3",
    "boat3": "blueboat3",
    "blueboat3": "blueboat3",
    "4": "blueboat4",
    "boat4": "blueboat4",
    "blueboat4": "blueboat4",
}

SENSOR_PATTERN = re.compile(
    r'<sensor\s+name="fpv_camera"\s+type="camera">.*?</sensor>',
    re.DOTALL,
)


def parse_size(value: str) -> tuple[int, int]:
    """Parse SIZE as WIDTHxHEIGHT, WIDTH,HEIGHT, or a square WIDTH."""

    cleaned = value.strip().lower().replace(" ", "")
    parts = re.split(r"[x,]", cleaned)

    if len(parts) == 1:
        parts = [parts[0], parts[0]]

    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            "size must be WIDTHxHEIGHT, such as 256x256"
        )

    try:
        width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "camera width and height must be integers"
        ) from exc

    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(
            "camera width and height must be greater than zero"
        )

    return width, height


def parse_hz(value: str) -> float:
    """Parse and validate the requested camera update rate."""

    try:
        hz = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("hz must be a number") from exc

    if hz <= 0:
        raise argparse.ArgumentTypeError("hz must be greater than zero")

    return hz


def normalize_boats(requested_boats: Iterable[str]) -> list[str]:
    """Resolve aliases and the special all selection."""

    requested = [boat.strip().lower() for boat in requested_boats]

    if "all" in requested:
        if len(requested) != 1:
            raise ValueError("'all' cannot be combined with individual boats")
        return list(BOAT_MODELS)

    selected = []
    for requested_boat in requested:
        model_name = BOAT_ALIASES.get(requested_boat)
        if model_name is None:
            valid = ", ".join(("all", *BOAT_MODELS))
            raise ValueError(
                f"Unknown boat {requested_boat!r}. Valid choices: {valid}"
            )
        if model_name not in selected:
            selected.append(model_name)

    return selected


def find_models_root(explicit_root: str | None) -> Path:
    """Find SITL_Models/Gazebo/models inside or outside the container."""

    if explicit_root:
        requested = Path(explicit_root).expanduser().resolve()
        if requested.is_dir():
            return requested
        raise FileNotFoundError(f"Models directory does not exist: {requested}")

    cwd = Path.cwd().resolve()
    candidates = [
        Path.home() / "SITL_Models/Gazebo/models",
        cwd / "SITL_Models/Gazebo/models",
    ]

    for parent in cwd.parents:
        candidates.append(parent / "SITL_Models/Gazebo/models")

    seen = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)

        if all((resolved / model / "model.sdf").is_file()
               for model in BOAT_MODELS):
            return resolved

    raise FileNotFoundError(
        "Could not find SITL_Models/Gazebo/models. Run this from the "
        "BlueBoat project/container or pass --models-root."
    )


def replace_sensor_value(
    sensor_text: str,
    tag_name: str,
    value: str,
    model_name: str,
) -> str:
    """Replace exactly one simple XML value inside the FPV sensor."""

    pattern = rf"(<{tag_name}>)[^<]*(</{tag_name}>)"
    updated, count = re.subn(
        pattern,
        lambda match: f"{match.group(1)}{value}{match.group(2)}",
        sensor_text,
        count=1,
    )

    if count != 1:
        raise RuntimeError(
            f"Expected one <{tag_name}> in {model_name}'s fpv_camera"
        )

    return updated


def configure_model(
    model_path: Path,
    model_name: str,
    width: int,
    height: int,
    hz: float,
    create_backup: bool,
) -> None:
    """Update one model while preserving the rest of its formatting."""

    original = model_path.read_text(encoding="utf-8")
    sensor_match = SENSOR_PATTERN.search(original)

    if sensor_match is None:
        raise RuntimeError(f"fpv_camera sensor not found in {model_path}")

    sensor = sensor_match.group(0)

    # Use the camera's native periodic update mode. Remove triggered-camera
    # settings that may have been added by an earlier experiment.
    sensor = re.sub(
        r"(?m)^[ \t]*<triggered>.*?</triggered>[ \t]*\n?",
        "",
        sensor,
    )
    sensor = re.sub(
        r"(?m)^[ \t]*<trigger_topic>.*?</trigger_topic>[ \t]*\n?",
        "",
        sensor,
    )

    hz_text = f"{hz:g}"
    sensor = replace_sensor_value(
        sensor, "update_rate", hz_text, model_name
    )
    sensor = replace_sensor_value(
        sensor, "width", str(width), model_name
    )
    sensor = replace_sensor_value(
        sensor, "height", str(height), model_name
    )

    updated = (
        original[:sensor_match.start()]
        + sensor
        + original[sensor_match.end():]
    )

    if updated == original:
        print(
            f"{model_name}: already configured as "
            f"{width}x{height} at {hz_text} Hz"
        )
        return

    if create_backup:
        backup_path = model_path.with_name(
            model_path.name + ".camera-config.bak"
        )
        if not backup_path.exists():
            shutil.copy2(model_path, backup_path)

    temporary_path = model_path.with_name(model_path.name + ".camera-config.tmp")
    temporary_path.write_text(updated, encoding="utf-8")
    temporary_path.replace(model_path)

    print(f"{model_name}: set to {width}x{height} at {hz_text} Hz")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Set the FPV camera resolution and update rate for selected "
            "BlueBoat Gazebo model files. Run this while Gazebo is stopped."
        )
    )
    parser.add_argument(
        "--boats",
        nargs="+",
        metavar="BOAT",
        help=(
            "Boats to configure, for example: --boats blueboat blueboat3. "
            "Use --boats all for every boat."
        ),
    )
    parser.add_argument(
        "--size",
        type=parse_size,
        metavar="WIDTHxHEIGHT",
        help="Camera image size, for example: --size 256x256",
    )
    parser.add_argument(
        "--hz",
        type=parse_hz,
        metavar="RATE",
        help="Camera update rate in simulation Hz, for example: --hz 16",
    )
    parser.add_argument(
        "--list-boats",
        action="store_true",
        help="List available boat names and exit",
    )
    parser.add_argument(
        "--models-root",
        help=(
            "Optional path to SITL_Models/Gazebo/models. Normally detected "
            "automatically."
        ),
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create model.sdf.camera-config.bak files",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.list_boats:
        print("Available boats:")
        for model_name in BOAT_MODELS:
            print(f"  {model_name}")
        print("  all")

        if args.boats is None and args.size is None and args.hz is None:
            return 0

    if args.boats is None:
        parser.error("--boats is required unless only --list-boats is used")
    if args.size is None:
        parser.error("--size is required")
    if args.hz is None:
        parser.error("--hz is required")

    try:
        selected_boats = normalize_boats(args.boats)
        models_root = find_models_root(args.models_root)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    width, height = args.size
    print(f"Models directory: {models_root}")

    for model_name in selected_boats:
        configure_model(
            model_path=models_root / model_name / "model.sdf",
            model_name=model_name,
            width=width,
            height=height,
            hz=args.hz,
            create_backup=not args.no_backup,
        )

    print(
        "Configuration complete. Restart Gazebo so the cameras are "
        "recreated with these settings."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
