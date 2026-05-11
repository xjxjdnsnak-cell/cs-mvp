from typing import Any

from .models import PredictionTick, RoundContext

try:
    from .map_tactics import locate_area, locate_player_area, find_area_by_name
except ImportError:
    locate_area = None
    locate_player_area = None
    find_area_by_name = None

_SITE_RADIUS = 800.0
_UTILITY_NEAR_RADIUS = 1200.0
_SAVE_ROUND_SECONDS = 80
_SAVE_ALIVE_THRESHOLD = 1
_EXIT_BOMB_TIMER = 35
_EXIT_ALIVE_DIFF_THRESHOLD = 3
_EARLY_DEFAULT_SECONDS = 15
_RETAKE_CT_MIN = 2
_SITE_EXECUTE_T_MIN = 3


def get_alive_counts(round_context: RoundContext, tick_index: int) -> tuple[int, int]:
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return 0, 0
    tick = round_context.ticks[tick_index]
    team1_alive = 0
    team2_alive = 0
    for player in tick.players_info:
        if not player.get("is_alive", True):
            continue
        name = player.get("name")
        if name in round_context.team1_players:
            team1_alive += 1
        elif name in round_context.team2_players:
            team2_alive += 1
    return team1_alive, team2_alive


def _get_player_position(player: dict[str, Any]) -> tuple[float, float, float] | None:
    try:
        x = float(player.get("X", 0))
        y = float(player.get("Y", 0))
        z = float(player.get("Z", 0))
        return x, y, z
    except (TypeError, ValueError):
        return None


def _get_grenade_position(grenade: dict[str, Any]) -> tuple[float, float, float] | None:
    pos = grenade.get("position")
    if pos is None:
        try:
            x = float(grenade.get("x", 0))
            y = float(grenade.get("y", 0))
            z = float(grenade.get("z", 0))
            return x, y, z
        except (TypeError, ValueError):
            return None
    if isinstance(pos, dict):
        try:
            return float(pos.get("x", 0)), float(pos.get("y", 0)), float(pos.get("z", 0))
        except (TypeError, ValueError):
            return None
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        try:
            x, y = float(pos[0]), float(pos[1])
            z = float(pos[2]) if len(pos) > 2 else 0.0
            return x, y, z
        except (TypeError, ValueError):
            return None
    return None


def _distance_2d(p1: tuple[float, float, float], p2: tuple[float, float, float]) -> float:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return (dx * dx + dy * dy) ** 0.5


def _is_t_player(round_context: RoundContext, player_name: str) -> bool:
    if round_context.team1_on_ct:
        return player_name in round_context.team2_players
    return player_name in round_context.team1_players


def _is_ct_player(round_context: RoundContext, player_name: str) -> bool:
    if round_context.team1_on_ct:
        return player_name in round_context.team1_players
    return player_name in round_context.team2_players


def _get_site_center(round_context: RoundContext, site_name: str) -> tuple[float, float, float] | None:
    if find_area_by_name is None:
        return None
    try:
        area = find_area_by_name(round_context.map_name, site_name)
        if area is None:
            return None
        return area.center[0], area.center[1], 0.0
    except Exception:
        return None


def count_t_near_site(round_context: RoundContext, tick_index: int, site_name: str) -> int:
    if site_name not in ("a_site", "b_site"):
        return 0
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return 0
    tick = round_context.ticks[tick_index]
    site_center = _get_site_center(round_context, site_name)
    count = 0
    for player in tick.players_info:
        if not player.get("is_alive", True):
            continue
        name = player.get("name")
        if not _is_t_player(round_context, name):
            continue
        if site_center is not None:
            pos = _get_player_position(player)
            if pos is not None and _distance_2d(pos, site_center) <= _SITE_RADIUS:
                count += 1
        else:
            if locate_player_area is not None:
                try:
                    area_info = locate_player_area(player, round_context.map_name)
                    if area_info is not None and area_info.name == site_name:
                        count += 1
                except Exception:
                    pass
    return count


def has_utility_near_site(round_context: RoundContext, tick_index: int, site_name: str) -> bool:
    if site_name not in ("a_site", "b_site"):
        return False
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return False
    tick = round_context.ticks[tick_index]
    site_center = _get_site_center(round_context, site_name)
    utility_types = {"smokegrenade", "flashbang", "molotov", "incgrenade", "hegrenade", "smoke", "flash", "fire", "inferno"}
    for projectile in tick.projectiles:
        ptype = str(projectile.get("type", "")).lower().replace(" ", "").replace("_", "").replace("-", "")
        matched = any(t.replace("_", "").replace("-", "") in ptype or ptype in t.replace("_", "").replace("-", "") for t in utility_types)
        if not matched:
            continue
        if site_center is not None:
            pos = _get_grenade_position(projectile)
            if pos is not None and _distance_2d(pos, site_center) <= _UTILITY_NEAR_RADIUS:
                return True
        else:
            return True
    for grenade in tick.entity_grenades:
        gtype = str(grenade.get("type", grenade.get("name", ""))).lower().replace(" ", "").replace("_", "").replace("-", "")
        matched = any(t.replace("_", "").replace("-", "") in gtype or gtype in t.replace("_", "").replace("-", "") for t in utility_types)
        if not matched:
            continue
        if site_center is not None:
            pos = _get_grenade_position(grenade)
            if pos is not None and _distance_2d(pos, site_center) <= _UTILITY_NEAR_RADIUS:
                return True
        else:
            return True
    return False


def is_ct_moving_to_site(round_context: RoundContext, tick_index: int) -> bool:
    if tick_index < 1 or tick_index >= len(round_context.ticks):
        return False
    tick = round_context.ticks[tick_index]
    prev_tick = round_context.ticks[tick_index - 1]
    ct_moving_count = 0
    for site_name in ("a_site", "b_site"):
        site_center = _get_site_center(round_context, site_name)
        if site_center is None:
            continue
        for player in tick.players_info:
            name = player.get("name")
            if not name or not _is_ct_player(round_context, name):
                continue
            if not player.get("is_alive", True):
                continue
            curr_pos = _get_player_position(player)
            if curr_pos is None:
                continue
            curr_dist = _distance_2d(curr_pos, site_center)
            if curr_dist > _SITE_RADIUS * 2:
                continue
            prev_pos = None
            for prev_player in prev_tick.players_info:
                if prev_player.get("name") == name:
                    prev_pos = _get_player_position(prev_player)
                    break
            if prev_pos is None:
                continue
            prev_dist = _distance_2d(prev_pos, site_center)
            if curr_dist < prev_dist:
                ct_moving_count += 1
    return ct_moving_count >= _RETAKE_CT_MIN


def detect_round_phase(round_context: RoundContext, tick_index: int) -> str:
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return "map_control"
    tick = round_context.ticks[tick_index]
    team1_alive, team2_alive = get_alive_counts(round_context, tick_index)
    if round_context.team1_on_ct:
        ct_alive = team1_alive
        t_alive = team2_alive
    else:
        ct_alive = team2_alive
        t_alive = team1_alive
    if round_context.bomb_planted_time is not None:
        if tick.round_seconds > round_context.bomb_planted_time + _EXIT_BOMB_TIMER:
            return "exit_phase"
        if is_ct_moving_to_site(round_context, tick_index):
            return "retake"
        return "post_plant"
    a_count = count_t_near_site(round_context, tick_index, "a_site")
    b_count = count_t_near_site(round_context, tick_index, "b_site")
    if a_count >= _SITE_EXECUTE_T_MIN and has_utility_near_site(round_context, tick_index, "a_site"):
        return "site_execute"
    if b_count >= _SITE_EXECUTE_T_MIN and has_utility_near_site(round_context, tick_index, "b_site"):
        return "site_execute"
    if tick.round_seconds > _SAVE_ROUND_SECONDS:
        if t_alive <= _SAVE_ALIVE_THRESHOLD and ct_alive >= 3:
            return "save"
        if ct_alive <= _SAVE_ALIVE_THRESHOLD and t_alive >= 3:
            return "save"
    alive_diff = abs(ct_alive - t_alive)
    if (ct_alive <= 1 or t_alive <= 1) and alive_diff >= _EXIT_ALIVE_DIFF_THRESHOLD:
        return "exit_phase"
    if tick.round_seconds < _EARLY_DEFAULT_SECONDS:
        return "early_default"
    return "map_control"
