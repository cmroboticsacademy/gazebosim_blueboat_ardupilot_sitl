"""Create a seeded Mission 4 world from the editable level6.sdf template."""

from dataclasses import dataclass
from itertools import chain
from pathlib import Path
import math
import os
import random
import secrets
import tempfile
from typing import Iterable, Optional


HAZARD_START_MARKER = "<!-- MISSION4_HAZARDS_START -->"
HAZARD_END_MARKER = "<!-- MISSION4_HAZARDS_END -->"
PROJECT_WORLD_RELATIVE_PATH = Path(
    "src/asv_wave_sim/gz-waves-models/worlds/level6.sdf"
)

HAZARD_Z = -10.0
ZONE_EDGE_CLEARANCE = 2.0
OBJECT_CLEARANCE = 1.0
BUOY_CLEARANCE = 15.0
MAX_OBJECTS_PER_ZONE = 5
PLACEMENT_ATTEMPTS = 1000


@dataclass(frozen=True)
class Footprint:
    """Axis-aligned visual bounds in the model's local XY frame."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float


@dataclass(frozen=True)
class Hazard:
    name: str
    uri: str
    category: str
    footprint: Footprint


@dataclass(frozen=True)
class Zone:
    name: str
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    @property
    def buoy_positions(self) -> tuple[tuple[float, float], ...]:
        return (
            (self.min_x, self.min_y),
            (self.min_x, self.max_y),
            (self.max_x, self.min_y),
            (self.max_x, self.max_y),
        )


@dataclass(frozen=True)
class Placement:
    hazard: Hazard
    zone: Zone
    x: float
    y: float
    z: float
    yaw: float

    @property
    def entity_name(self) -> str:
        return (
            f"{self.zone.name}__{self.hazard.category}__{self.hazard.name}"
        )


@dataclass(frozen=True)
class GeneratedWorld:
    seed: int
    template_path: Path
    world_path: Path
    placements: tuple[Placement, ...]


POSITIVE_HAZARDS = (
    Hazard(
        "cmra_airplane", "model://cmra_models/airplane", "positive",
        Footprint(-3.252852, 3.252852, -1.198347, 3.698348),
    ),
    Hazard(
        "cmra_boat", "model://cmra_models/boat", "positive",
        Footprint(-1.083506, 1.219350, -2.657625, 3.604496),
    ),
    Hazard(
        "cmra_bus", "model://cmra_models/bus", "positive",
        Footprint(-1.122308, 1.122048, -5.153109, 5.263928),
    ),
    Hazard(
        "cmra_car_wrecked", "model://cmra_models/car_wrecked", "positive",
        Footprint(-1.466965, 1.232500, -1.996108, 2.213610),
    ),
    Hazard(
        "cmra_drone", "model://cmra_models/drone", "positive",
        Footprint(-0.510976, 0.510976, -0.616007, 0.616007),
    ),
    Hazard(
        "cmra_drum", "model://cmra_models/drum", "positive",
        Footprint(-0.294789, 0.295212, -0.292221, 0.294657),
    ),
    Hazard(
        "cmra_truck", "model://cmra_models/truck", "positive",
        Footprint(-1.343817, 1.343817, -3.251290, 2.812716),
    ),
)

NEGATIVE_HAZARDS = (
    Hazard(
        "cmra_canoe", "model://cmra_models/canoe", "negative",
        Footprint(-0.595945, 0.589223, -2.491255, 2.329140),
    ),
    Hazard(
        "cmra_couch", "model://cmra_models/couch", "negative",
        Footprint(-1.181077, 1.181077, -0.516914, 0.499982),
    ),
    Hazard(
        "cmra_picnic_table", "model://cmra_models/picnic_table", "negative",
        Footprint(-1.237377, 1.237377, -1.262453, 1.262453),
    ),
    Hazard(
        "cmra_seaweed", "model://cmra_models/seaweed", "negative",
        Footprint(-1.503687, 1.403338, -1.389800, 1.513528),
    ),
)

ZONES = (
    Zone("zone_1", -40.0, 40.0, -80.0, -40.0),
    Zone("zone_2", 100.0, 180.0, -40.0, 0.0),
    Zone("zone_3", 150.0, 190.0, 40.0, 120.0),
    Zone("zone_4", 90.0, 170.0, 145.0, 185.0),
)


def parse_seed(seed_text: Optional[str]) -> int:
    if seed_text is None or not seed_text.strip():
        return secrets.randbits(32)
    try:
        return int(seed_text, 10)
    except ValueError as exc:
        raise ValueError(
            f"Mission 4 seed must be an integer; received {seed_text!r}."
        ) from exc


def _unique_existing_paths(paths: Iterable[Path]) -> list[Path]:
    unique = []
    seen = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def find_world_template(requested_path: Optional[str] = None) -> Path:
    """Resolve the editable source world without silently choosing a stale copy."""

    if requested_path and requested_path.strip():
        explicit_path = Path(requested_path.strip()).expanduser().resolve()
        if explicit_path.is_file():
            return explicit_path
        raise FileNotFoundError(
            f"The requested Mission 4 world template does not exist: "
            f"{explicit_path}"
        )

    cwd = Path.cwd().resolve()
    search_roots = (cwd, *cwd.parents)
    project_candidates = []
    for root in search_roots:
        project_candidates.extend((
            root / PROJECT_WORLD_RELATIVE_PATH,
            root / "gz_ws" / PROJECT_WORLD_RELATIVE_PATH,
        ))
    project_candidates.append(
        Path.home() / "gz_ws" / PROJECT_WORLD_RELATIVE_PATH
    )
    project_matches = _unique_existing_paths(project_candidates)
    if project_matches:
        return project_matches[0]

    resource_candidates = []
    for resource_dir in os.environ.get("GZ_SIM_RESOURCE_PATH", "").split(
        os.pathsep
    ):
        if resource_dir:
            resource_candidates.append(
                Path(resource_dir).expanduser() / "level6.sdf"
            )
    resource_matches = _unique_existing_paths(resource_candidates)

    if len(resource_matches) == 1:
        return resource_matches[0]
    if len(resource_matches) > 1:
        formatted = "\n  - ".join(str(path) for path in resource_matches)
        raise RuntimeError(
            "Multiple level6.sdf files were found. Select the editable one "
            "with world_template:=<absolute-path>:\n  - " + formatted
        )

    raise FileNotFoundError(
        "Could not find the Mission 4 level6.sdf template. Launch from the "
        "gz_ws directory or pass world_template:=<absolute-path>."
    )


def _assign_hazards(rng: random.Random) -> dict[str, list[Hazard]]:
    assignments = {zone.name: [] for zone in ZONES}
    shuffled_zones = list(ZONES)
    positives = list(POSITIVE_HAZARDS)
    negatives = list(NEGATIVE_HAZARDS)
    rng.shuffle(shuffled_zones)
    rng.shuffle(positives)
    rng.shuffle(negatives)

    for zone, hazard in zip(shuffled_zones, positives[: len(ZONES)]):
        assignments[zone.name].append(hazard)
    for zone, hazard in zip(shuffled_zones, negatives[: len(ZONES)]):
        assignments[zone.name].append(hazard)

    remaining = positives[len(ZONES):] + negatives[len(ZONES):]
    rng.shuffle(remaining)
    for hazard in remaining:
        available = [
            zone for zone in ZONES
            if len(assignments[zone.name]) < MAX_OBJECTS_PER_ZONE
        ]
        if not available:
            raise RuntimeError("No zone has capacity for all Mission 4 hazards.")
        assignments[rng.choice(available).name].append(hazard)
    return assignments


def footprint_corners(
    placement: Placement,
    inflation: float = 0.0,
) -> tuple[tuple[float, float], ...]:
    footprint = placement.hazard.footprint
    local_corners = (
        (footprint.min_x - inflation, footprint.min_y - inflation),
        (footprint.max_x + inflation, footprint.min_y - inflation),
        (footprint.max_x + inflation, footprint.max_y + inflation),
        (footprint.min_x - inflation, footprint.max_y + inflation),
    )
    cos_yaw = math.cos(placement.yaw)
    sin_yaw = math.sin(placement.yaw)
    return tuple(
        (
            placement.x + local_x * cos_yaw - local_y * sin_yaw,
            placement.y + local_x * sin_yaw + local_y * cos_yaw,
        )
        for local_x, local_y in local_corners
    )


def _rectangle_axes(
    corners: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    axes = []
    for index in (0, 1):
        x1, y1 = corners[index]
        x2, y2 = corners[index + 1]
        edge_x = x2 - x1
        edge_y = y2 - y1
        length = math.hypot(edge_x, edge_y)
        axes.append((-edge_y / length, edge_x / length))
    return tuple(axes)


def footprints_overlap(first: Placement, second: Placement) -> bool:
    inflation = OBJECT_CLEARANCE / 2.0
    first_corners = footprint_corners(first, inflation)
    second_corners = footprint_corners(second, inflation)
    axes = chain(
        _rectangle_axes(first_corners),
        _rectangle_axes(second_corners),
    )
    for axis_x, axis_y in axes:
        first_projection = [
            x * axis_x + y * axis_y for x, y in first_corners
        ]
        second_projection = [
            x * axis_x + y * axis_y for x, y in second_corners
        ]
        if (
            max(first_projection) <= min(second_projection)
            or max(second_projection) <= min(first_projection)
        ):
            return False
    return True


def footprint_is_inside_zone(placement: Placement) -> bool:
    zone = placement.zone
    return all(
        zone.min_x + ZONE_EDGE_CLEARANCE <= x
        <= zone.max_x - ZONE_EDGE_CLEARANCE
        and zone.min_y + ZONE_EDGE_CLEARANCE <= y
        <= zone.max_y - ZONE_EDGE_CLEARANCE
        for x, y in footprint_corners(placement)
    )


def distance_to_footprint(
    placement: Placement,
    point: tuple[float, float],
) -> float:
    delta_x = point[0] - placement.x
    delta_y = point[1] - placement.y
    cos_yaw = math.cos(placement.yaw)
    sin_yaw = math.sin(placement.yaw)
    local_x = delta_x * cos_yaw + delta_y * sin_yaw
    local_y = -delta_x * sin_yaw + delta_y * cos_yaw
    footprint = placement.hazard.footprint
    nearest_x = min(max(local_x, footprint.min_x), footprint.max_x)
    nearest_y = min(max(local_y, footprint.min_y), footprint.max_y)
    return math.hypot(local_x - nearest_x, local_y - nearest_y)


def footprint_is_clear_of_buoys(placement: Placement) -> bool:
    return all(
        distance_to_footprint(placement, buoy) >= BUOY_CLEARANCE
        for buoy in placement.zone.buoy_positions
    )


def placement_is_clear(
    candidate: Placement,
    existing: Iterable[Placement],
) -> bool:
    return (
        footprint_is_inside_zone(candidate)
        and footprint_is_clear_of_buoys(candidate)
        and all(
            not footprints_overlap(candidate, placement)
            for placement in existing
        )
    )


def _place_hazards(seed: int) -> tuple[Placement, ...]:
    rng = random.Random(seed)
    assignments = _assign_hazards(rng)
    placements: list[Placement] = []
    for zone in ZONES:
        for hazard in assignments[zone.name]:
            for _ in range(PLACEMENT_ATTEMPTS):
                placement = Placement(
                    hazard=hazard,
                    zone=zone,
                    x=rng.uniform(zone.min_x, zone.max_x),
                    y=rng.uniform(zone.min_y, zone.max_y),
                    z=HAZARD_Z,
                    yaw=rng.uniform(-math.pi, math.pi),
                )
                if placement_is_clear(placement, placements):
                    placements.append(placement)
                    break
            else:
                raise RuntimeError(
                    f"Could not place {hazard.name} in {zone.name} after "
                    f"{PLACEMENT_ATTEMPTS} attempts."
                )
    return tuple(placements)


def _format_includes(seed: int, placements: Iterable[Placement]) -> str:
    blocks = [f"    <!-- Generated Mission 4 hazards; seed={seed} -->"]
    current_zone = None
    for placement in placements:
        if placement.zone.name != current_zone:
            current_zone = placement.zone.name
            blocks.append(f"    <!-- {current_zone} -->")
        blocks.extend((
            "    <include>",
            f"      <name>{placement.entity_name}</name>",
            (
                "      <pose>"
                f"{placement.x:.6f} {placement.y:.6f} {placement.z:.1f} "
                f"0 0 {placement.yaw:.6f}</pose>"
            ),
            f"      <uri>{placement.hazard.uri}</uri>",
            "    </include>",
        ))
    return "\n".join(blocks)


def render_seeded_world(
    template_text: str,
    seed: int,
) -> tuple[str, tuple[Placement, ...]]:
    if template_text.count(HAZARD_START_MARKER) != 1:
        raise ValueError(f"Template must contain exactly one {HAZARD_START_MARKER}.")
    if template_text.count(HAZARD_END_MARKER) != 1:
        raise ValueError(f"Template must contain exactly one {HAZARD_END_MARKER}.")
    start_index = template_text.index(HAZARD_START_MARKER) + len(
        HAZARD_START_MARKER
    )
    end_index = template_text.index(HAZARD_END_MARKER)
    if start_index >= end_index:
        raise ValueError("Mission 4 hazard template markers are in the wrong order.")
    placements = _place_hazards(seed)
    generated_block = "\n" + _format_includes(seed, placements) + "\n    "
    world_text = (
        template_text[:start_index]
        + generated_block
        + template_text[end_index:]
    )
    return world_text, placements


def create_seeded_world(
    seed_text: Optional[str],
    requested_template: Optional[str] = None,
) -> GeneratedWorld:
    seed = parse_seed(seed_text)
    template_path = find_world_template(requested_template)
    template_text = template_path.read_text(encoding="utf-8")
    world_text, placements = render_seeded_world(template_text, seed)
    world_path = Path(tempfile.gettempdir()) / f"mission4_level6_seed_{seed}.sdf"
    world_path.write_text(world_text, encoding="utf-8")
    return GeneratedWorld(
        seed=seed,
        template_path=template_path,
        world_path=world_path,
        placements=placements,
    )
