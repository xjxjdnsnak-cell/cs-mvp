from typing import Any

from .models import EventType, PredictionTick, RoundContext

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
_SITE_EXECUTE_T_MIN = 2

_A_EXECUTE_AREAS = {"a_ramp", "palace", "a_site", "default_plant_a", "triple"}
_B_EXECUTE_AREAS = {"b_apps", "b_site", "default_plant_b"}
_CT_RETAKE_ORIGINS = {"market", "ct_spawn", "jungle", "stairs", "short", "market_window", "market_door"}


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


def count_ct_moving_to_site(round_context: RoundContext, tick_index: int) -> int:
    if tick_index < 1 or tick_index >= len(round_context.ticks):
        return 0
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
    return ct_moving_count


def _count_t_in_site_execute_areas(round_context: RoundContext, tick_index: int) -> tuple[int, int]:
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return 0, 0
    tick = round_context.ticks[tick_index]
    a_count = 0
    b_count = 0
    for player in tick.players_info:
        if not player.get("is_alive", True):
            continue
        name = player.get("name")
        if not _is_t_player(round_context, name):
            continue
        if locate_player_area is not None:
            try:
                area_info = locate_player_area(player, round_context.map_name)
                if area_info is not None:
                    if area_info.name in _A_EXECUTE_AREAS:
                        a_count += 1
                    elif area_info.name in _B_EXECUTE_AREAS:
                        b_count += 1
            except Exception:
                pass
    return a_count, b_count


def _has_recent_combat_or_utility(round_context: RoundContext, tick_index: int, window: float = 3.0) -> bool:
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return False
    tick = round_context.ticks[tick_index]
    tick_time = tick.round_seconds
    for event in round_context.events:
        if event.event_type in (EventType.KILL, EventType.DEATH):
            if abs(event.tick - tick_time) <= window:
                return True
    return has_utility_near_site(round_context, tick_index, "a_site") or has_utility_near_site(round_context, tick_index, "b_site")


def _count_ct_from_retake_origins(round_context: RoundContext, tick_index: int) -> int:
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return 0
    tick = round_context.ticks[tick_index]
    count = 0
    for player in tick.players_info:
        if not player.get("is_alive", True):
            continue
        name = player.get("name")
        if not _is_ct_player(round_context, name):
            continue
        if locate_player_area is not None:
            try:
                area_info = locate_player_area(player, round_context.map_name)
                if area_info is not None and area_info.name in _CT_RETAKE_ORIGINS:
                    count += 1
            except Exception:
                pass
    return count


def _has_traded_death_in_site_areas(round_context: RoundContext, tick_index: int) -> bool:
    if tick_index < 0 or tick_index >= len(round_context.ticks):
        return False
    tick = round_context.ticks[tick_index]
    tick_time = tick.round_seconds
    for event in round_context.events:
        if event.event_type != EventType.DEATH:
            continue
        if abs(event.tick - tick_time) > 5.0:
            continue
        death_tick_idx = _find_nearest_tick_index(round_context, event.tick)
        if death_tick_idx < 0 or death_tick_idx >= len(round_context.ticks):
            continue
        death_tick = round_context.ticks[death_tick_idx]
        for p in death_tick.players_info:
            if p.get("name") == event.player:
                if locate_area is not None:
                    try:
                        area = locate_area(round_context.map_name, p.get("X", 0.0), p.get("Y", 0.0))
                        if area is not None and area.name in _A_EXECUTE_AREAS | _B_EXECUTE_AREAS:
                            teammates = (
                                round_context.team2_players if round_context.team1_on_ct else round_context.team1_players
                            )
                            for kill_event in round_context.events:
                                if kill_event.event_type == EventType.KILL and kill_event.player in teammates:
                                    if 0 < kill_event.tick - event.tick <= 5.0:
                                        return True
                    except Exception:
                        pass
                break
    return False


def _find_nearest_tick_index(round_context: RoundContext, tick_time: float) -> int:
    best_idx = 0
    best_diff = float("inf")
    for i, t in enumerate(round_context.ticks):
        diff = abs(t.round_seconds - tick_time)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx


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
        if tick.round_seconds < round_context.bomb_planted_time:
            if round_context.bomb_planted_time - tick.round_seconds <= 10.0:
                return "site_execute"
        
        if tick.round_seconds > round_context.bomb_planted_time + _EXIT_BOMB_TIMER:
            return "exit_phase"
        
        ct_moving = count_ct_moving_to_site(round_context, tick_index)
        if ct_moving >= _RETAKE_CT_MIN:
            return "retake"
        
        ct_from_origins = _count_ct_from_retake_origins(round_context, tick_index)
        if ct_from_origins >= _RETAKE_CT_MIN:
            return "retake"
        
        return "post_plant"
    
    a_count, b_count = _count_t_in_site_execute_areas(round_context, tick_index)
    has_combat = _has_recent_combat_or_utility(round_context, tick_index)
    
    if _has_traded_death_in_site_areas(round_context, tick_index):
        return "site_execute"
    
    if (a_count >= 2 or b_count >= 2) and has_combat:
        return "site_execute"
    
    if a_count >= _SITE_EXECUTE_T_MIN and has_utility_near_site(round_context, tick_index, "a_site"):
        return "site_execute"
    
    if b_count >= _SITE_EXECUTE_T_MIN and has_utility_near_site(round_context, tick_index, "b_site"):
        return "site_execute"
    
    if a_count >= _SITE_EXECUTE_T_MIN or b_count >= _SITE_EXECUTE_T_MIN:
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
