from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import get_weight
from .map_tactics import locate_area, locate_player_area, AreaInfo, is_key_area
from .models import EventType, GameEvent, RoundContext, PredictionTick
from .tactical_phase import detect_round_phase, get_alive_counts


MID_AREAS = {"top_mid", "mid_boxes", "connector"}
CT_MID_AREAS = {"window", "short", "connector"}
A_EXECUTE_AREAS = {"a_ramp", "palace", "a_site", "default_plant_a", "triple", "ticket"}
B_EXECUTE_AREAS = {"b_apps", "b_site", "default_plant_b"}
A_POST_PLANT_AREAS = {"a_ramp", "palace", "a_site", "triple", "ticket", "jungle", "stairs"}
B_ROTATION_AREAS = {"market_window", "market_door", "short"}
POST_PLANT_STRONG_POSITIONS = {"a_ramp", "palace", "triple", "ticket", "stairs", "jungle", "van", "bench"}
KEY_AREAS = {"connector", "window", "short", "top_mid", "a_ramp", "b_apps"}


@dataclass
class TacticalEvent:
    player: str
    round_id: int
    tick: float
    label: str
    score: float
    reason: str
    area: str | None = None
    area_cn: str | None = None
    phase: str = ""


def _is_t_side(player: str, round_context: RoundContext) -> bool:
    if round_context.team1_on_ct:
        return player in round_context.team2_players
    return player in round_context.team1_players


def _is_ct_side(player: str, round_context: RoundContext) -> bool:
    return not _is_t_side(player, round_context)


def _get_team_players(player: str, round_context: RoundContext) -> list[str]:
    if _is_t_side(player, round_context):
        return round_context.team2_players if round_context.team1_on_ct else round_context.team1_players
    return round_context.team1_players if round_context.team1_on_ct else round_context.team2_players


def _get_enemy_players(player: str, round_context: RoundContext) -> list[str]:
    if _is_t_side(player, round_context):
        return round_context.team1_players if round_context.team1_on_ct else round_context.team2_players
    return round_context.team2_players if round_context.team1_on_ct else round_context.team1_players


def _find_nearest_tick_index(round_context: RoundContext, tick_time: float) -> int | None:
    best_idx = None
    best_diff = float("inf")
    for i, t in enumerate(round_context.ticks):
        diff = abs(t.round_seconds - tick_time)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx


def _count_alive_teammates_near(player: str, tick: PredictionTick, round_context: RoundContext, radius: float = 800.0) -> int:
    teammates = _get_team_players(player, round_context)
    player_pos = None
    for p in tick.players_info:
        if p.get("name") == player:
            player_pos = (p.get("X", 0.0), p.get("Y", 0.0))
            break
    if player_pos is None:
        return 0
    count = 0
    for p in tick.players_info:
        name = p.get("name", "")
        if name == player or name not in teammates:
            continue
        if not p.get("is_alive", True):
            continue
        tx, ty = p.get("X", 0.0), p.get("Y", 0.0)
        dist = ((player_pos[0] - tx) ** 2 + (player_pos[1] - ty) ** 2) ** 0.5
        if dist <= radius:
            count += 1
    return count


def _was_traded(player: str, death_tick: float, round_context: RoundContext, window: float = 5.0) -> bool:
    teammates = _get_team_players(player, round_context)
    for event in round_context.events:
        if event.event_type == EventType.KILL and event.player in teammates:
            if 0 < event.tick - death_tick <= window:
                return True
    return False


def _player_died_in_area(player: str, round_context: RoundContext, area_names: set[str]) -> tuple[bool, str | None]:
    for event in round_context.events:
        if event.event_type == EventType.DEATH and event.player == player:
            tick_idx = _find_nearest_tick_index(round_context, event.tick)
            if tick_idx is not None:
                tick = round_context.ticks[tick_idx]
                for p in tick.players_info:
                    if p.get("name") == player:
                        area = locate_area(round_context.map_name, p.get("X", 0.0), p.get("Y", 0.0))
                        if area and area.name in area_names:
                            return True, area.name
                        return False, area.name if area else None
    return False, None


def _get_player_area_at_tick(player: str, tick: PredictionTick, map_name: str) -> AreaInfo | None:
    for p in tick.players_info:
        if p.get("name") == player:
            return locate_area(map_name, p.get("X", 0.0), p.get("Y", 0.0))
    return None


def evaluate_mid_control(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    if round_context.map_name != "de_mirage":
        return events
    is_t = _is_t_side(player, round_context)
    relevant_areas = MID_AREAS if is_t else CT_MID_AREAS
    
    active_ticks: set[int] = set()
    for tick_idx, tick in enumerate(round_context.ticks):
        if tick.round_seconds < 5 or tick.round_seconds > 40:
            continue
        for p in tick.players_info:
            if p.get("name") != player or not p.get("is_alive", True):
                continue
            area = locate_area(round_context.map_name, p.get("X", 0.0), p.get("Y", 0.0))
            if area and area.name in relevant_areas:
                nearby_teammates = _count_alive_teammates_near(player, tick, round_context, 800.0)
                if nearby_teammates >= 1:
                    active_ticks.add(tick_idx)
                    break
    
    if active_ticks:
        first_tick_idx = min(active_ticks)
        first_tick = round_context.ticks[first_tick_idx]
        area = _get_player_area_at_tick(player, first_tick, round_context.map_name)
        events.append(TacticalEvent(
            player=player,
            round_id=round_context.round_id,
            tick=first_tick.round_seconds,
            label="mid_control_success" if is_t else "mid_control_hold",
            score=0.3,
            reason=f"玩家在{area.name_cn if area else '中路'}参与中路控制",
            area=area.name if area else None,
            area_cn=area.name_cn if area else None,
            phase="map_control",
        ))
    
    died_in_mid, death_area = _player_died_in_area(player, round_context, relevant_areas)
    if died_in_mid:
        death_event = next((e for e in round_context.events 
                           if e.event_type == EventType.DEATH and e.player == player), None)
        if death_event:
            tick_idx = _find_nearest_tick_index(round_context, death_event.tick - 2.0)
            if tick_idx is not None:
                tick = round_context.ticks[tick_idx]
                nearby = _count_alive_teammates_near(player, tick, round_context, 1000.0)
                if nearby == 0:
                    events.append(TacticalEvent(
                        player=player,
                        round_id=round_context.round_id,
                        tick=death_event.tick,
                        label="key_area_isolated_death",
                        score=-0.8,
                        reason=f"玩家在{death_area}独自前压，附近5秒内无队友补枪，死亡后队伍中路压力下降",
                        area=death_area,
                        phase="map_control",
                    ))
    return events


def evaluate_site_execute(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    if round_context.map_name != "de_mirage":
        return events
    if not _is_t_side(player, round_context):
        return events
    
    SITE_EXECUTE_AREAS = A_EXECUTE_AREAS | B_EXECUTE_AREAS
    
    for event in round_context.events:
        if event.event_type != EventType.DEATH or event.player != player:
            continue
        
        tick_idx = _find_nearest_tick_index(round_context, event.tick)
        if tick_idx is None:
            continue
        
        phase_tick_idx = max(0, tick_idx - 5)
        phase = detect_round_phase(round_context, phase_tick_idx)
        
        if phase not in ("site_execute", "map_control"):
            continue
        
        tick = round_context.ticks[tick_idx]
        area = _get_player_area_at_tick(player, tick, round_context.map_name)
        area_name = area.name if area else None
        area_cn = area.name_cn if area else None
        
        in_execute = area_name in SITE_EXECUTE_AREAS if area_name else False
        if not in_execute:
            continue
        
        traded = _was_traded(player, event.tick, round_context, 5.0)
        if traded:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="valid_entry_sacrifice",
                score=0.5,
                reason=f"玩家在{area_cn}作为可交易死亡，队友5秒内完成补枪，判定为有效进点牺牲",
                area=area_name,
                area_cn=area_cn,
                phase=phase,
            ))
        else:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="failed_entry_no_trade",
                score=-0.6,
                reason=f"玩家在{area_cn}进点死亡无人补枪，判定为无效进点",
                area=area_name,
                area_cn=area_cn,
                phase=phase,
            ))
    return events


def evaluate_post_plant_discipline(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    if round_context.map_name != "de_mirage":
        return events
    if not _is_t_side(player, round_context):
        return events
    if round_context.bomb_planted_time is None:
        return events
    
    for event in round_context.events:
        if event.event_type != EventType.DEATH or event.player != player:
            continue
        if event.tick < round_context.bomb_planted_time:
            continue
        
        tick_idx = _find_nearest_tick_index(round_context, event.tick)
        if tick_idx is None:
            continue
        
        tick = round_context.ticks[tick_idx]
        area = _get_player_area_at_tick(player, tick, round_context.map_name)
        area_name = area.name if area else None
        area_cn = area.name_cn if area else None
        
        in_strong = area_name in POST_PLANT_STRONG_POSITIONS if area_name else False
        
        team1_alive, team2_alive = get_alive_counts(round_context, tick_idx)
        if round_context.team1_on_ct:
            t_alive, ct_alive = team2_alive, team1_alive
        else:
            t_alive, ct_alive = team1_alive, team2_alive
        
        if in_strong:
            nearby = _count_alive_teammates_near(player, tick, round_context, 800.0)
            if nearby >= 1:
                events.append(TacticalEvent(
                    player=player,
                    round_id=round_context.round_id,
                    tick=event.tick,
                    label="post_plant_crossfire_hold",
                    score=0.4,
                    reason=f"玩家在{area_cn}与队友形成交叉火力守包",
                    area=area_name,
                    area_cn=area_cn,
                    phase="post_plant",
                ))
            continue
        
        if t_alive >= ct_alive:
            nearby = _count_alive_teammates_near(player, tick, round_context, 800.0)
            if nearby == 0:
                events.append(TacticalEvent(
                    player=player,
                    round_id=round_context.round_id,
                    tick=event.tick,
                    label="post_plant_discipline_error",
                    score=-1.0,
                    reason=f"炸弹已下后，玩家远离守包枪线单独接敌死亡，CT获得回防机会，判定为纪律失误",
                    area=area_name,
                    area_cn=area_cn,
                    phase="post_plant",
                ))
            else:
                events.append(TacticalEvent(
                    player=player,
                    round_id=round_context.round_id,
                    tick=event.tick,
                    label="post_plant_discipline_error",
                    score=-0.5,
                    reason=f"下包后离开强位死亡，判定为纪律失误",
                    area=area_name,
                    area_cn=area_cn,
                    phase="post_plant",
                ))
    return events


def evaluate_retake_discipline(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    if round_context.map_name != "de_mirage":
        return events
    if not _is_ct_side(player, round_context):
        return events
    if round_context.bomb_planted_time is None:
        return events
    
    for event in round_context.events:
        if event.event_type != EventType.DEATH or event.player != player:
            continue
        if event.tick < round_context.bomb_planted_time:
            continue
        
        tick_idx = _find_nearest_tick_index(round_context, event.tick)
        if tick_idx is None:
            continue
        
        tick = round_context.ticks[tick_idx]
        nearby_teammates = _count_alive_teammates_near(player, tick, round_context, 800.0)
        area = _get_player_area_at_tick(player, tick, round_context.map_name)
        area_cn = area.name_cn if area else None
        
        if nearby_teammates == 0:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="retake_solo_feed",
                score=-0.8,
                reason=f"CT单人无队友同步强行进点死亡于{area_cn if area_cn else '包点'}，判定为回防纪律失误",
                phase="retake",
            ))
        else:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="retake_grouped",
                score=0.3,
                reason=f"CT与队友{nearby_teammates}人同步回防{area_cn if area_cn else '包点'}",
                phase="retake",
            ))
    return events


def evaluate_save_and_exit(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    last_tick_idx = len(round_context.ticks) - 1
    if last_tick_idx < 0:
        return events
    
    last_tick = round_context.ticks[last_tick_idx]
    if last_tick.round_seconds < 80:
        return events
    
    team1_alive, team2_alive = get_alive_counts(round_context, last_tick_idx)
    player_is_t = _is_t_side(player, round_context)
    
    if player_is_t:
        team_alive = team2_alive
        enemy_alive = team1_alive
    else:
        team_alive = team1_alive
        enemy_alive = team2_alive
    
    player_alive = False
    for p in last_tick.players_info:
        if p.get("name") == player and p.get("is_alive", True):
            player_alive = True
            break
    
    if team_alive <= 1 and enemy_alive >= 3:
        if player_alive:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=last_tick.round_seconds,
                label="save_correct",
                score=0.15,
                reason="回合无望且保枪成功",
                phase="save",
            ))
    
    for event in round_context.events:
        if event.event_type == EventType.KILL and event.player == player:
            if event.tick > last_tick.round_seconds - 10:
                events.append(TacticalEvent(
                    player=player,
                    round_id=round_context.round_id,
                    tick=event.tick,
                    label="exit_frag_low_impact",
                    score=0.05,
                    reason="出口杀，低影响",
                    phase="exit_phase",
                ))
    
    for event in round_context.events:
        if event.event_type == EventType.DEATH and event.player == player:
            if event.tick > last_tick.round_seconds - 10:
                events.append(TacticalEvent(
                    player=player,
                    round_id=round_context.round_id,
                    tick=event.tick,
                    label="save_throw",
                    score=-0.4,
                    reason="保枪阶段主动送枪",
                    phase="save",
                ))
    
    return events


def aggregate_tactical_events(events: list[TacticalEvent]) -> list[dict[str, Any]]:
    if not events:
        return []
    
    sorted_events = sorted(events, key=lambda e: (e.player, e.round_id, e.label, e.area or "", e.tick))
    groups: list[list[TacticalEvent]] = []
    current_group: list[TacticalEvent] = []
    
    for ev in sorted_events:
        if not current_group:
            current_group.append(ev)
            continue
        
        last = current_group[-1]
        if (
            ev.player == last.player
            and ev.round_id == last.round_id
            and ev.label == last.label
            and (ev.area or "") == (last.area or "")
            and ev.tick - last.tick <= 2.0
        ):
            current_group.append(ev)
        else:
            groups.append(current_group)
            current_group = [ev]
    if current_group:
        groups.append(current_group)
    
    aggregated: list[dict[str, Any]] = []
    for group in groups:
        first = group[0]
        last = group[-1]
        raw_sum = sum(ev.score for ev in group)
        
        if raw_sum > 0:
            impact = min(0.5, raw_sum)
        else:
            impact = max(-0.5, raw_sum)
        
        duration = last.tick - first.tick
        aggregated.append({
            "round": first.round_id,
            "start_tick": first.tick,
            "end_tick": last.tick,
            "phase": first.phase,
            "area": first.area,
            "area_cn": first.area_cn,
            "label": first.label,
            "impact": impact,
            "reason": first.reason,
            "duration": duration,
        })
    
    return aggregated


def calculate_player_tactical_impact(player: str, round_context: RoundContext) -> tuple[float, float, list[dict[str, Any]]]:
    all_events: list[TacticalEvent] = []
    all_events.extend(evaluate_mid_control(player, round_context))
    all_events.extend(evaluate_site_execute(player, round_context))
    all_events.extend(evaluate_post_plant_discipline(player, round_context))
    all_events.extend(evaluate_retake_discipline(player, round_context))
    all_events.extend(evaluate_save_and_exit(player, round_context))
    
    aggregated = aggregate_tactical_events(all_events)
    
    map_control = 0.0
    tactical_discipline = 0.0
    for ev in aggregated:
        label = ev["label"]
        impact = ev["impact"]
        if label in ("mid_control_success", "mid_control_hold", "key_area_isolated_death"):
            map_control += impact
        else:
            tactical_discipline += impact
    
    map_control = max(-0.5, min(0.5, map_control))
    tactical_discipline = max(-1.0, min(1.0, tactical_discipline))
    
    return map_control, tactical_discipline, aggregated
