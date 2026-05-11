from dataclasses import dataclass
from functools import lru_cache
from math import hypot
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class AreaInfo:
    name: str
    name_cn: str
    type: str
    center: tuple[float, float]
    radius: float


@lru_cache(maxsize=None)
def load_map_areas(map_name: str) -> list[AreaInfo]:
    config_path = _PROJECT_ROOT / "config" / "callouts" / f"{map_name}.yaml"
    if not config_path.exists():
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    areas_raw = data.get("areas")
    if not isinstance(areas_raw, list):
        return []
    result: list[AreaInfo] = []
    for entry in areas_raw:
        if not isinstance(entry, dict):
            continue
        try:
            center_raw = entry.get("center", [])
            center = (float(center_raw[0]), float(center_raw[1]))
            result.append(
                AreaInfo(
                    name=str(entry.get("name", "")),
                    name_cn=str(entry.get("name_cn", "")),
                    type=str(entry.get("type", "")),
                    center=center,
                    radius=float(entry.get("radius", 0)),
                )
            )
        except (IndexError, TypeError, ValueError):
            continue
    return result


def point_in_area(x: float, y: float, area: AreaInfo) -> bool:
    return hypot(x - area.center[0], y - area.center[1]) <= area.radius


def locate_area(map_name: str, x: float, y: float, z: float = 0.0) -> AreaInfo | None:
    areas = load_map_areas(map_name)
    if not areas:
        return None
    best: AreaInfo | None = None
    best_dist: float = float("inf")
    for area in areas:
        dist = hypot(x - area.center[0], y - area.center[1])
        if dist <= area.radius and dist < best_dist:
            best = area
            best_dist = dist
    return best


def get_player_position(player_info: dict) -> tuple[float, float, float] | None:
    try:
        x = float(player_info["X"])
        y = float(player_info["Y"])
        z = float(player_info["Z"])
        return (x, y, z)
    except (KeyError, TypeError, ValueError):
        return None


def locate_player_area(player_info: dict, map_name: str) -> AreaInfo | None:
    pos = get_player_position(player_info)
    if pos is None:
        return None
    return locate_area(map_name, pos[0], pos[1], pos[2])


def find_area_by_name(map_name: str, area_name: str) -> AreaInfo | None:
    areas = load_map_areas(map_name)
    for area in areas:
        if area.name == area_name:
            return area
    return None
