from dataclasses import dataclass
from functools import lru_cache
from math import hypot
from pathlib import Path
from typing import Any, Optional, Tuple, List, Dict

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class AreaInfo:
    name: str
    name_cn: str
    type: str
    center: Tuple[float, float]
    radius: float
    side_value: Optional[Dict[str, str]] = None


@dataclass
class PlantZone:
    name: str
    site: str
    center: Tuple[float, float]
    radius: float
    post_plant_holds: List[str]
    dangerous_overpeeks: List[str]


@lru_cache(maxsize=None)
def load_map_areas(map_name: str) -> List[AreaInfo]:
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
    result: List[AreaInfo] = []
    for entry in areas_raw:
        if not isinstance(entry, dict):
            continue
        try:
            center_raw = entry.get("center", [])
            center = (float(center_raw[0]), float(center_raw[1]))
            side_value = entry.get("side_value")
            if side_value and isinstance(side_value, dict):
                side_value = {k: str(v) for k, v in side_value.items()}
            else:
                side_value = None
            result.append(
                AreaInfo(
                    name=str(entry.get("name", "")),
                    name_cn=str(entry.get("name_cn", "")),
                    type=str(entry.get("type", "")),
                    center=center,
                    radius=float(entry.get("radius", 0)),
                    side_value=side_value,
                )
            )
        except (IndexError, TypeError, ValueError):
            continue
    return result


@lru_cache(maxsize=None)
def load_plant_zones(map_name: str) -> List[PlantZone]:
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
    zones_raw = data.get("plant_zones")
    if not isinstance(zones_raw, list):
        return []
    result: List[PlantZone] = []
    for entry in zones_raw:
        if not isinstance(entry, dict):
            continue
        try:
            center_raw = entry.get("center", [])
            center = (float(center_raw[0]), float(center_raw[1]))
            result.append(
                PlantZone(
                    name=str(entry.get("name", "")),
                    site=str(entry.get("site", "")),
                    center=center,
                    radius=float(entry.get("radius", 0)),
                    post_plant_holds=[str(h) for h in entry.get("post_plant_holds", [])],
                    dangerous_overpeeks=[str(o) for o in entry.get("dangerous_overpeeks", [])],
                )
            )
        except (IndexError, TypeError, ValueError):
            continue
    return result


@lru_cache(maxsize=None)
def load_tactical_rules(map_name: str) -> Dict[str, Any]:
    config_path = _PROJECT_ROOT / "config" / "callouts" / f"{map_name}.yaml"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    rules = data.get("tactical_rules")
    return rules if isinstance(rules, dict) else {}


def point_in_area(x: float, y: float, area: AreaInfo) -> bool:
    return hypot(x - area.center[0], y - area.center[1]) <= area.radius


def locate_area(map_name: str, x: float, y: float, z: float = 0.0) -> Optional[AreaInfo]:
    areas = load_map_areas(map_name)
    if not areas:
        return None
    best: Optional[AreaInfo] = None
    best_dist: float = float("inf")
    for area in areas:
        dist = hypot(x - area.center[0], y - area.center[1])
        if dist <= area.radius and dist < best_dist:
            best = area
            best_dist = dist
    return best


def get_player_position(player_info: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
    try:
        x = float(player_info["X"])
        y = float(player_info["Y"])
        z = float(player_info["Z"])
        return (x, y, z)
    except (KeyError, TypeError, ValueError):
        return None


def locate_player_area(player_info: Dict[str, Any], map_name: str) -> Optional[AreaInfo]:
    pos = get_player_position(player_info)
    if pos is None:
        return None
    return locate_area(map_name, pos[0], pos[1], pos[2])


def find_area_by_name(map_name: str, area_name: str) -> Optional[AreaInfo]:
    areas = load_map_areas(map_name)
    for area in areas:
        if area.name == area_name:
            return area
    return None


def area_type(area: Optional[AreaInfo]) -> str:
    if area is None:
        return ""
    return area.type


def is_key_area(area: Optional[AreaInfo]) -> bool:
    if area is None:
        return False
    key_types = {"choke", "power_position", "rotation_key", "bombsite"}
    return area.type in key_types


def is_power_position(area: Optional[AreaInfo]) -> bool:
    if area is None:
        return False
    return area.type == "power_position"


def is_post_plant_hold(map_name: str, area_name: str, plant_zone_name: str) -> bool:
    plant_zones = load_plant_zones(map_name)
    for zone in plant_zones:
        if zone.name == plant_zone_name:
            return area_name in zone.post_plant_holds
    return False


def is_dangerous_overpeek(map_name: str, area_name: str, plant_zone_name: str) -> bool:
    plant_zones = load_plant_zones(map_name)
    for zone in plant_zones:
        if zone.name == plant_zone_name:
            return area_name in zone.dangerous_overpeeks
    return False


def distance_to_area(point: Tuple[float, float], area: AreaInfo) -> float:
    return hypot(point[0] - area.center[0], point[1] - area.center[1])


def get_areas_by_type(map_name: str, area_type: str) -> List[AreaInfo]:
    areas = load_map_areas(map_name)
    return [area for area in areas if area.type == area_type]


def find_plant_zone_by_name(map_name: str, zone_name: str) -> Optional[PlantZone]:
    zones = load_plant_zones(map_name)
    for zone in zones:
        if zone.name == zone_name:
            return zone
    return None


def find_plant_zone_by_site(map_name: str, site_name: str) -> List[PlantZone]:
    zones = load_plant_zones(map_name)
    return [zone for zone in zones if zone.site == site_name]
