from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .map_tactics import AreaInfo, load_tactical_rules, locate_area
from .models import EventType, RoundContext, PredictionTick
from .tactical_phase import detect_round_phase, get_alive_counts


DEFAULT_MIRAGE_RULES: dict[str, Any] = {
    "mid_control": {
        "t_areas": ["top_mid", "mid_boxes", "connector"],
        "ct_areas": ["window", "short", "connector"],
    },
    "control_groups": [],
    "key_areas": ["connector", "window", "short", "top_mid", "a_ramp", "b_apps"],
    "site_execute": {
        "areas": ["a_ramp", "palace", "a_site", "default_plant_a", "triple", "ticket", "b_apps", "b_site", "default_plant_b"],
        "a_areas": ["a_ramp", "palace", "a_site", "default_plant_a", "triple", "ticket"],
        "b_areas": ["b_apps", "b_site", "default_plant_b"],
    },
    "post_plant": {
        "strong_positions": ["a_ramp", "palace", "triple", "ticket", "stairs", "jungle", "van", "bench"],
        "dangerous_overpeeks": [],
        "positive_label": "post_plant_crossfire_hold",
        "negative_label": "post_plant_discipline_error",
    },
    "retake": {
        "ct_origins": ["market", "ct_spawn", "jungle", "stairs", "short", "market_window", "market_door"],
    },
}


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


def _rules_for_map(map_name: str) -> dict[str, Any] | None:
    if not map_name or map_name == "Unknown":
        return None
    rules = load_tactical_rules(map_name)
    if rules:
        return rules
    if map_name == "de_mirage":
        return DEFAULT_MIRAGE_RULES
    return None


def _list_to_set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value}
    if isinstance(value, set):
        return {str(item) for item in value}
    return set()


def _section_set(rules: dict[str, Any], section: str, key: str, fallback: set[str] | None = None) -> set[str]:
    data = rules.get(section)
    if not isinstance(data, dict):
        return set(fallback or set())
    result = _list_to_set(data.get(key))
    return result if result else set(fallback or set())


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


def _control_event_reason(label: str, area_cn: str | None, is_t: bool) -> str:
    area_text = area_cn or "关键区域"
    if label == "mid_control_success":
        return f"玩家在{area_text}与队友形成推进，参与中路控制。"
    if label == "mid_control_hold":
        return f"玩家在{area_text}与队友形成防守联动，参与中路控制。"
    if label == "long_control_success":
        return f"玩家在{area_text}与队友形成推进，参与A大控制。"
    if label == "short_control_success":
        return f"玩家在{area_text}与队友形成推进，参与小道控制。"
    if label == "b_tunnel_control_success":
        return f"玩家在{area_text}与队友形成推进，参与B洞控制。"
    side = "进攻" if is_t else "防守"
    return f"玩家在{area_text}与队友形成{side}联动。"


def _add_control_presence_event(
    player: str,
    round_context: RoundContext,
    areas: set[str],
    label: str,
    score: float,
    phase: str,
) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    active_ticks: set[int] = set()
    for tick_idx, tick in enumerate(round_context.ticks):
        if tick.round_seconds < 5 or tick.round_seconds > 40:
            continue
        for p in tick.players_info:
            if p.get("name") != player or not p.get("is_alive", True):
                continue
            area = locate_area(round_context.map_name, p.get("X", 0.0), p.get("Y", 0.0))
            if area and area.name in areas:
                nearby_teammates = _count_alive_teammates_near(player, tick, round_context, 800.0)
                if nearby_teammates >= 1:
                    active_ticks.add(tick_idx)
                    break

    if active_ticks:
        first_tick = round_context.ticks[min(active_ticks)]
        area = _get_player_area_at_tick(player, first_tick, round_context.map_name)
        is_t = _is_t_side(player, round_context)
        events.append(TacticalEvent(
            player=player,
            round_id=round_context.round_id,
            tick=first_tick.round_seconds,
            label=label,
            score=score,
            reason=_control_event_reason(label, area.name_cn if area else None, is_t),
            area=area.name if area else None,
            area_cn=area.name_cn if area else None,
            phase=phase,
        ))
    return events


def evaluate_mid_control(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    rules = _rules_for_map(round_context.map_name)
    if not rules:
        return events

    is_t = _is_t_side(player, round_context)
    mid_areas = _section_set(rules, "mid_control", "t_areas" if is_t else "ct_areas")
    if mid_areas:
        events.extend(_add_control_presence_event(
            player,
            round_context,
            mid_areas,
            "mid_control_success" if is_t else "mid_control_hold",
            0.3,
            "map_control",
        ))

    control_groups = rules.get("control_groups", [])
    if isinstance(control_groups, list):
        for group in control_groups:
            if not isinstance(group, dict):
                continue
            side = str(group.get("side", "T")).upper()
            if (side == "T" and not is_t) or (side == "CT" and is_t):
                continue
            areas = _list_to_set(group.get("areas"))
            if not areas:
                continue
            label = str(group.get("label", "key_area_control"))
            score = float(group.get("score", 0.25))
            phase = str(group.get("phase", "map_control"))
            events.extend(_add_control_presence_event(player, round_context, areas, label, score, phase))

    key_areas = _list_to_set(rules.get("key_areas"))
    if not key_areas:
        key_areas = set(mid_areas)
    died_in_key_area, death_area = _player_died_in_area(player, round_context, key_areas)
    if died_in_key_area:
        death_event = next((e for e in round_context.events if e.event_type == EventType.DEATH and e.player == player), None)
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
                        reason=f"玩家在{death_area or '关键区域'}孤身接敌死亡，附近无队友补枪，关键区域压力下降。",
                        area=death_area,
                        phase="map_control",
                    ))
    return events


def evaluate_site_execute(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    rules = _rules_for_map(round_context.map_name)
    if not rules or not _is_t_side(player, round_context):
        return events

    execute_areas = _section_set(rules, "site_execute", "areas")
    if not execute_areas:
        a_areas = _section_set(rules, "site_execute", "a_areas")
        b_areas = _section_set(rules, "site_execute", "b_areas")
        execute_areas = a_areas | b_areas

    for event in round_context.events:
        if event.event_type != EventType.DEATH or event.player != player:
            continue
        tick_idx = _find_nearest_tick_index(round_context, event.tick)
        if tick_idx is None:
            continue

        phase = detect_round_phase(round_context, max(0, tick_idx - 5))
        if phase not in ("site_execute", "map_control", "early_default"):
            continue

        tick = round_context.ticks[tick_idx]
        area = _get_player_area_at_tick(player, tick, round_context.map_name)
        area_name = area.name if area else None
        area_cn = area.name_cn if area else None
        if not area_name or area_name not in execute_areas:
            continue

        traded = _was_traded(player, event.tick, round_context, 5.0)
        if traded:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="valid_entry_sacrifice",
                score=0.5,
                reason=f"玩家在{area_cn or area_name}进点死亡，但队友5秒内完成补枪，判定为有效进点牺牲。",
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
                reason=f"玩家在{area_cn or area_name}进点死亡，5秒内没有队友补枪，判定为无效进点。",
                area=area_name,
                area_cn=area_cn,
                phase=phase,
            ))
    return events


def evaluate_post_plant_discipline(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    rules = _rules_for_map(round_context.map_name)
    if not rules or not _is_t_side(player, round_context) or round_context.bomb_planted_time is None:
        return events

    strong_positions = _section_set(rules, "post_plant", "strong_positions")
    overpeek_areas = _section_set(rules, "post_plant", "dangerous_overpeeks")
    post_plant_rules = rules.get("post_plant", {})
    positive_label = "post_plant_crossfire_hold"
    negative_label = "post_plant_discipline_error"
    if isinstance(post_plant_rules, dict):
        positive_label = str(post_plant_rules.get("positive_label", positive_label))
        negative_label = str(post_plant_rules.get("negative_label", negative_label))

    for tick in round_context.ticks:
        if tick.round_seconds < round_context.bomb_planted_time + 2.0:
            continue
        if tick.round_seconds > round_context.bomb_planted_time + 22.0:
            break
        area = _get_player_area_at_tick(player, tick, round_context.map_name)
        area_name = area.name if area else None
        if area_name not in strong_positions:
            continue
        player_alive = any(p.get("name") == player and p.get("is_alive", True) for p in tick.players_info)
        if not player_alive:
            continue
        nearby = _count_alive_teammates_near(player, tick, round_context, 800.0)
        if nearby >= 1:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=tick.round_seconds,
                label=positive_label,
                score=0.4,
                reason=f"下包后玩家在{area.name_cn or area_name}与队友形成守包联动。",
                area=area_name,
                area_cn=area.name_cn,
                phase="post_plant",
            ))
            break

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

        team1_alive, team2_alive = get_alive_counts(round_context, tick_idx)
        t_alive, ct_alive = (team2_alive, team1_alive) if round_context.team1_on_ct else (team1_alive, team2_alive)

        if area_name in strong_positions:
            continue

        if t_alive >= ct_alive:
            nearby = _count_alive_teammates_near(player, tick, round_context, 800.0)
            high_risk = area_name in overpeek_areas if area_name else False
            penalty = -1.0 if nearby == 0 or high_risk else -0.5
            reason = (
                f"下包后玩家离开可守包位置，在{area_cn or area_name or '未知区域'}前压死亡，判定为post_plant_overpeek。"
                if negative_label == "post_plant_overpeek"
                else f"下包后玩家离开强位死亡，判定为纪律失误。"
            )
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label=negative_label,
                score=penalty,
                reason=reason,
                area=area_name,
                area_cn=area_cn,
                phase="post_plant",
            ))
    return events


def evaluate_retake_discipline(player: str, round_context: RoundContext) -> list[TacticalEvent]:
    events: list[TacticalEvent] = []
    rules = _rules_for_map(round_context.map_name)
    if not rules or not _is_ct_side(player, round_context) or round_context.bomb_planted_time is None:
        return events

    retake_origins = _section_set(rules, "retake", "ct_origins")
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
        area_name = area.name if area else None
        area_cn = area.name_cn if area else None
        if nearby_teammates == 0:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="retake_solo_feed",
                score=-0.8,
                reason=f"CT回防时孤身从{area_cn or area_name or '回防路线'}推进死亡，附近无队友补枪。",
                area=area_name,
                area_cn=area_cn,
                phase="retake",
            ))
        elif nearby_teammates > 0:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="retake_grouped",
                score=0.3,
                reason=f"CT与{nearby_teammates}名队友同步回防{area_cn or area_name or '包点'}。",
                area=area_name,
                area_cn=area_cn,
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
    team_alive = team2_alive if player_is_t else team1_alive
    enemy_alive = team1_alive if player_is_t else team2_alive

    player_alive = any(p.get("name") == player and p.get("is_alive", True) for p in last_tick.players_info)
    if team_alive <= 1 and enemy_alive >= 3 and player_alive:
        events.append(TacticalEvent(
            player=player,
            round_id=round_context.round_id,
            tick=last_tick.round_seconds,
            label="save_correct",
            score=0.15,
            reason="回合胜算较低时成功保枪。",
            phase="save",
        ))

    for event in round_context.events:
        if event.event_type == EventType.KILL and event.player == player and event.tick > last_tick.round_seconds - 10:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="exit_frag_low_impact",
                score=0.05,
                reason="出口击杀，回合影响较低。",
                phase="exit_phase",
            ))
        if event.event_type == EventType.DEATH and event.player == player and event.tick > last_tick.round_seconds - 10:
            events.append(TacticalEvent(
                player=player,
                round_id=round_context.round_id,
                tick=event.tick,
                label="save_throw",
                score=-0.4,
                reason="保枪阶段主动送枪。",
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
        impact = min(0.5, raw_sum) if raw_sum > 0 else max(-0.5, raw_sum)
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
            "duration": last.tick - first.tick,
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
    map_control_labels = {
        "mid_control_success",
        "mid_control_hold",
        "long_control_success",
        "short_control_success",
        "b_tunnel_control_success",
        "key_area_isolated_death",
    }
    for ev in aggregated:
        label = ev["label"]
        impact = ev["impact"]
        if label in map_control_labels:
            map_control += impact
        else:
            tactical_discipline += impact

    map_control = max(-0.5, min(0.5, map_control))
    tactical_discipline = max(-1.0, min(1.0, tactical_discipline))

    return map_control, tactical_discipline, aggregated
