"""Rule-based HE grenade impact scoring."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .align import calculate_distance_2d, safe_float
from .config import get_weight
from .models import EventType, GameEvent, HEImpact, PredictionTick, RoundContext


HE_WEAPONS = {"hegrenade", "he grenade", "weapon_hegrenade", "grenade_he"}


@dataclass
class HEEvent:
    entityid: Any
    tick: float
    position: tuple[float, float, float] | None
    thrower: str = "unknown"
    low_confidence: bool = False


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_player_he_impact(
    player_name: str,
    round_context: RoundContext,
) -> tuple[float, list[HEImpact]]:
    he_events = collect_he_events(round_context)
    impacts = []
    for he_event in he_events:
        if he_event.thrower != player_name:
            continue
        impacts.append(score_he_event(he_event, round_context, all_he_events=he_events))
    return sum(impact.score for impact in impacts), impacts


def score_he_event(
    he_event: HEEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, Any] | None = None,
    all_he_events: list[HEEvent] | None = None,
) -> HEImpact:
    map_knowledge = map_knowledge if map_knowledge is not None else load_he_map_knowledge(round_context)
    score = 0.0
    labels: list[str] = []
    reasons: list[str] = []

    if he_event.low_confidence:
        reasons.append("缺少可靠 HE 爆点，按低置信度伤害事件处理")

    damage_score, damage_labels, damage_reasons, damage_events, kill_events = score_he_damage(
        he_event, round_context
    )
    score += damage_score
    labels.extend(damage_labels)
    reasons.extend(damage_reasons)

    smoke_score, smoke_labels, smoke_reasons, smoke_context = score_anti_smoke_he(
        he_event, round_context, map_knowledge, damage_events, kill_events
    )
    score += smoke_score
    labels.extend(smoke_labels)
    reasons.extend(smoke_reasons)

    cross_score, cross_labels, cross_reasons = score_anti_cross_he(
        he_event, round_context, map_knowledge, damage_events
    )
    score += cross_score
    labels.extend(cross_labels)
    reasons.extend(cross_reasons)

    objective_score, objective_labels, objective_reasons, objective_context = score_objective_he(
        he_event, round_context, map_knowledge, damage_events, kill_events
    )
    score += objective_score
    labels.extend(objective_labels)
    reasons.extend(objective_reasons)

    rush_score, rush_labels, rush_reasons = score_anti_rush_he(
        he_event, round_context, damage_events
    )
    score += rush_score
    labels.extend(rush_labels)
    reasons.extend(rush_reasons)

    stack_score, stack_labels, stack_reasons = score_nade_stack(
        he_event, all_he_events or [he_event], round_context
    )
    score += stack_score
    labels.extend(stack_labels)
    reasons.extend(stack_reasons)

    if detect_low_value_he(damage_events, kill_events, labels):
        labels.append("low_value_he")
        reasons.append("这颗 HE 低伤害且没有阻止行动或形成补杀，价值较低")

    if not labels:
        labels.extend(["random_he", "wasted_he"])
        reasons.append("缺少伤害、目标转化或战术阻止证据，按 random_he/wasted_he 处理")

    if "low_value_he" in labels and not any(label in labels for label in ("team_damage_he", "harmful_he")):
        labels.append("wasted_he")

    score = clamp(
        score,
        get_weight("he_impact.min_he_score_per_grenade", -2.0),
        get_weight("he_impact.max_he_score_per_grenade", 3.0),
    )

    return HEImpact(
        thrower=he_event.thrower,
        round_id=round_context.round_id,
        tick=he_event.tick,
        score=round(score, 3),
        labels=_dedupe(labels),
        damage_events=damage_events,
        kill_events=kill_events,
        smoke_context=smoke_context,
        objective_context=objective_context,
        reasons=_dedupe(reasons),
    )


def collect_he_events(round_context: RoundContext) -> list[HEEvent]:
    events: dict[Any, HEEvent] = {}
    throwers = infer_he_throwers(round_context)
    for tick in sorted(round_context.ticks, key=lambda item: item.round_seconds):
        for projectile in tick.projectiles:
            if not is_he_weapon(projectile.get("type")):
                continue
            entityid = projectile.get("entityid", f"he-{len(events)}")
            position = coerce_position(projectile.get("position"))
            if entityid not in events:
                events[entityid] = HEEvent(
                    entityid=entityid,
                    tick=tick.round_seconds,
                    position=position,
                    thrower=projectile.get("name") or throwers.get(entityid) or "unknown",
                    low_confidence=position is None,
                )
            else:
                events[entityid].tick = tick.round_seconds
                events[entityid].position = position or events[entityid].position
                events[entityid].thrower = events[entityid].thrower if events[entityid].thrower != "unknown" else throwers.get(entityid, "unknown")

    for damage in he_damage_game_events(round_context):
        entityid = f"he-damage-{damage.player}-{damage.tick}"
        if any(abs(event.tick - damage.tick) <= 0.5 and event.thrower == damage.player for event in events.values()):
            continue
        position = player_position_at(round_context, damage.other_player, damage.tick)
        events[entityid] = HEEvent(
            entityid=entityid,
            tick=damage.tick,
            position=position,
            thrower=damage.player or "unknown",
            low_confidence=position is None,
        )

    for tick in round_context.ticks:
        for dmg in tick.future_damage:
            if not is_he_weapon(dmg.get("weapon", "")):
                continue
            dmg_time = safe_float(dmg.get("time"), tick.round_seconds)
            thrower = dmg.get("attacker_name") or dmg.get("attacker") or "unknown"
            entityid = f"he-future-{thrower}-{dmg_time}"
            if entityid in events:
                continue
            victim = dmg.get("victim_name") or dmg.get("user_name") or dmg.get("player")
            events[entityid] = HEEvent(
                entityid=entityid,
                tick=dmg_time,
                position=player_position_at(round_context, victim, dmg_time),
                thrower=thrower,
                low_confidence=True,
            )

    # Source 3: EventType.KILL or tick future_kills with HE weapon -> low-confidence HEEvent
    for event in round_context.events:
        if event.event_type == EventType.KILL and is_he_weapon(event.weapon):
            entityid = f"he-kill-{event.player}-{event.tick}"
            if any(abs(e.tick - event.tick) <= 0.5 and e.thrower == event.player for e in events.values()):
                continue
            events[entityid] = HEEvent(
                entityid=entityid,
                tick=event.tick,
                position=player_position_at(round_context, event.other_player, event.tick),
                thrower=event.player or "unknown",
                low_confidence=True,
            )

    for tick in round_context.ticks:
        for fk in tick.future_kills:
            if not is_he_weapon(fk.get("weapon", "")):
                continue
            fk_time = safe_float(fk.get("time"), tick.round_seconds)
            killer = fk.get("killer") or fk.get("attacker") or fk.get("attacker_name") or "unknown"
            victim = fk.get("victim") or fk.get("victim_name") or fk.get("user_name") or fk.get("target")
            entityid = f"he-kill-{killer}-{fk_time}"
            if entityid in events:
                continue
            events[entityid] = HEEvent(
                entityid=entityid,
                tick=fk_time,
                position=player_position_at(round_context, victim, fk_time),
                thrower=killer,
                low_confidence=True,
            )

    for he_event in events.values():
        if he_event.thrower == "unknown":
            inferred = infer_inventory_thrower(he_event, round_context)
            he_event.thrower = inferred
    return list(events.values())


def infer_he_throwers(round_context: RoundContext) -> dict[Any, str]:
    throwers: dict[Any, str] = {}
    for tick in sorted(round_context.ticks, key=lambda item: item.round_seconds):
        for grenade in tick.entity_grenades:
            entityid = grenade.get("entityid")
            name = grenade.get("name")
            if entityid is not None and name and is_he_weapon(grenade.get("type")):
                throwers[entityid] = name
    return throwers


def infer_inventory_thrower(he_event: HEEvent, round_context: RoundContext) -> str:
    candidates = []
    for player_name in round_context.team1_players + round_context.team2_players:
        before = find_player_info_before(round_context.ticks, player_name, he_event.tick)
        after = find_player_info_after(round_context.ticks, player_name, he_event.tick)
        if he_inventory_count((before or {}).get("inventory")) > he_inventory_count((after or {}).get("inventory")):
            candidates.append(player_name)
    return candidates[0] if len(candidates) == 1 else "unknown"


def he_inventory_count(inventory: Any) -> int:
    if not isinstance(inventory, list):
        return 0
    return sum(1 for item in inventory if is_he_weapon(item))


def load_he_map_knowledge(round_context: RoundContext) -> dict[str, Any]:
    map_name = getattr(round_context, "map_name", None)
    if not map_name or map_name == "Unknown":
        return {}
    cfg_path = Path(__file__).resolve().parents[2] / "config" / "callouts" / f"{map_name}.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "smoke_targets": data.get("smoke_targets") or {},
        "he_cross_zones": data.get("he_cross_zones") or [],
        "plant_zones": data.get("plant_zones") or [],
    }


def score_he_damage(
    he_event: HEEvent,
    round_context: RoundContext,
) -> tuple[float, list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    labels: list[str] = []
    reasons: list[str] = []
    damage_events = collect_he_damage_events(he_event, round_context)
    enemy_damage = sum(item["damage"] for item in damage_events if not item["team_damage"])
    team_damage = sum(item["damage"] for item in damage_events if item["team_damage"])
    kill_events = collect_he_kill_events(he_event, round_context)
    enemy_kills = [item for item in kill_events if not item["team_kill"]]
    team_kills = [item for item in kill_events if item["team_kill"]]

    score = enemy_damage * get_weight("he_impact.damage_multiplier", 0.015)
    if enemy_damage > 0:
        labels.append("normal_he_damage")
        reasons.append(f"HE 造成敌方 {enemy_damage} 点伤害")
    if enemy_damage >= get_weight("he_impact.high_damage_threshold", 50):
        labels.append("high_damage_he")
        score += get_weight("he_impact.high_damage_bonus", 0.3)
        reasons.append("HE 造成高额伤害")
    if enemy_kills:
        labels.append("kill_he")
        score += get_weight("he_impact.kill_bonus", 0.8)
        reasons.append("HE 直接造成击杀")
    elif enemy_damage > 0 and he_assist_kill(he_event, round_context, damage_events):
        labels.append("assist_he")
        score += get_weight("he_impact.assist_bonus", 0.3)
        reasons.append("HE 打残目标后 5 秒内由我方完成补杀")

    if enemy_kills and any(item.get("health_before") is not None and item["health_before"] <= 25 for item in damage_events if not item["team_damage"]):
        labels.append("finishing_he")
        score += get_weight("he_impact.finishing_he_bonus", 0.4)
        reasons.append("目标被 HE 击杀前已是低血量，按收残雷处理")

    if team_damage > 0:
        labels.append("team_damage_he")
        score += team_damage * get_weight("he_impact.team_damage_multiplier", -0.02)
        reasons.append(f"HE 造成队友 {team_damage} 点伤害")
    if team_kills or any(item.get("team_damage") and teammate_died_after(he_event, item.get("victim"), round_context) for item in damage_events):
        labels.append("harmful_he")
        score += get_weight("he_impact.harmful_he_penalty", -1.2)
        reasons.append("HE 导致队友死亡或严重破坏队友行动")

    return score, labels, reasons, damage_events, kill_events


def score_anti_smoke_he(
    he_event: HEEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, Any],
    damage_events: list[dict[str, Any]],
    kill_events: list[dict[str, Any]],
) -> tuple[float, list[str], list[str], dict[str, Any] | None]:
    if he_event.position is None:
        return 0.0, [], [], None
    context = match_anti_smoke_context(he_event, round_context, map_knowledge, damage_events)
    if not context.get("type"):
        return 0.0, [], [], None

    has_enemy_damage = any(not item["team_damage"] for item in damage_events)
    has_enemy_kill = any(not item["team_kill"] for item in kill_events)
    if not (has_enemy_damage or has_enemy_kill):
        return 0.0, [], [], context

    labels = []
    reasons = list(context.get("reasons") or [])
    score = 0.0
    if context["type"] == "direct":
        labels.append("anti_smoke_he_direct")
        score += get_weight("he_impact.anti_smoke_direct_bonus", 0.5)
        if has_enemy_kill:
            labels.append("anti_smoke_he_direct_kill")
            score += get_weight("he_impact.anti_smoke_direct_kill_bonus", 1.2)
    elif context["type"] == "route":
        labels.append("anti_smoke_route_he")
        score += get_weight("he_impact.anti_smoke_route_bonus", 0.4)
        if has_enemy_kill:
            labels.append("anti_smoke_route_he_kill")
            score += get_weight("he_impact.anti_smoke_route_kill_bonus", 1.0)
    return score, labels, reasons, context


def match_anti_smoke_context(
    he_event: HEEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, Any],
    damage_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_smokes = active_smokes_at(round_context, he_event.tick)
    if he_event.position is None or not active_smokes:
        return {"type": None, "confidence": 0.0, "reasons": []}

    radius = get_weight("he_impact.smoke_radius", 170.0)
    tolerance = get_weight("he_impact.smoke_tolerance", 80.0)
    for smoke in active_smokes:
        smoke_pos = coerce_position(smoke.get("position"))
        if smoke_pos is None:
            continue
        he_to_smoke = calculate_distance_2d(he_event.position[0], he_event.position[1], smoke_pos[0], smoke_pos[1])
        victim_near_smoke = any(
            victim_position_close_to(dmg, smoke_pos, radius + tolerance)
            for dmg in (damage_events or [])
        )
        if he_to_smoke <= radius + tolerance or victim_near_smoke:
            target_name = match_smoke_target_name(smoke_pos, map_knowledge)
            return {
                "type": "direct",
                "smoke_target": target_name,
                "zone": None,
                "confidence": 0.9,
                "reasons": ["HE 直接炸烟内/烟边目标"],
            }

    for smoke in active_smokes:
        smoke_pos = coerce_position(smoke.get("position"))
        target_name = match_smoke_target_name(smoke_pos, map_knowledge) if smoke_pos else None
        target = (map_knowledge.get("smoke_targets") or {}).get(target_name or "")
        if not target:
            continue
        for zone in target.get("counter_he_zones") or []:
            if he_or_victim_in_zone(he_event, damage_events or [], zone):
                return {
                    "type": "route",
                    "smoke_target": target_name,
                    "zone": zone.get("name"),
                    "confidence": 0.75,
                    "reasons": ["HE 命中烟后默认路线的预判区域"],
                }
    return {"type": None, "confidence": 0.0, "reasons": []}


def score_anti_cross_he(
    he_event: HEEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, Any],
    damage_events: list[dict[str, Any]],
) -> tuple[float, list[str], list[str]]:
    if he_event.position is None:
        return 0.0, [], []
    in_cross_zone = any(point_in_zone(he_event.position, zone) for zone in map_knowledge.get("he_cross_zones", []))
    if not in_cross_zone:
        return 0.0, [], []
    enemy_damage = any(not item["team_damage"] for item in damage_events)
    if enemy_damage or enemy_delayed_or_stopped(he_event, round_context):
        return (
            get_weight("he_impact.anti_cross_bonus", 0.8),
            ["anti_cross_he"],
            ["HE 炸在敌方过点路线，并通过伤害或停滞阻止过点"],
        )
    return 0.0, [], []


def score_objective_he(
    he_event: HEEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, Any],
    damage_events: list[dict[str, Any]],
    kill_events: list[dict[str, Any]],
) -> tuple[float, list[str], list[str], dict[str, Any] | None]:
    if he_event.position is None:
        return 0.0, [], [], None
    labels = []
    reasons = []
    score = 0.0
    context: dict[str, Any] | None = None

    if round_context.bomb_planted_time is not None and near_bomb(he_event, round_context):
        has_enemy_damage = any(not item["team_damage"] for item in damage_events)
        has_enemy_kill = any(not item["team_kill"] for item in kill_events)
        if ct_near_bomb_after(he_event, round_context) or has_enemy_damage or has_enemy_kill:
            labels.append("anti_defuse_he")
            score += get_weight("he_impact.anti_defuse_bonus", 1.0)
            reasons.append("HE 落在炸弹/拆包区域附近，阻止或打断 CT 拆包")
            context = {"type": "anti_defuse", "near_bomb": True}
    elif any(point_in_zone(he_event.position, zone) for zone in map_knowledge.get("plant_zones", [])):
        if enemies_near_he(he_event, round_context) > 0 or any(not item["team_damage"] for item in damage_events):
            labels.append("anti_plant_he")
            score += get_weight("he_impact.anti_plant_bonus", 0.8)
            reasons.append("HE 覆盖默认下包点或下包路线，阻止/延迟下包")
            context = {"type": "anti_plant"}
    return score, labels, reasons, context


def score_anti_rush_he(
    he_event: HEEvent,
    round_context: RoundContext,
    damage_events: list[dict[str, Any]],
) -> tuple[float, list[str], list[str]]:
    enemy_hits = sum(1 for item in damage_events if not item["team_damage"])
    enemy_count = enemies_near_he(he_event, round_context)
    if enemy_count < get_weight("he_impact.rush_enemy_count", 2):
        return 0.0, [], []
    if enemy_hits < 2:
        return 0.0, [], []

    score = get_weight("he_impact.anti_rush_bonus", 0.7)
    if enemy_hits >= 3:
        score += 0.6
    elif enemy_hits >= 2:
        score += 0.3
    return score, ["anti_rush_he"], ["敌方多人 rush/聚集时 HE 命中或迫使其停止推进"]


def score_nade_stack(
    he_event: HEEvent,
    all_he_events: list[HEEvent],
    round_context: RoundContext,
) -> tuple[float, list[str], list[str]]:
    if he_event.position is None:
        return 0.0, [], []
    stack = [
        other for other in all_he_events
        if other.position is not None
        and abs(other.tick - he_event.tick) <= get_weight("he_impact.nade_stack_window_seconds", 3.0)
        and calculate_distance_2d(other.position[0], other.position[1], he_event.position[0], he_event.position[1]) <= get_weight("he_impact.nade_stack_radius", 260.0)
    ]
    throwers = {item.thrower for item in stack if item.thrower != "unknown"}
    if len(stack) < 2 or len(throwers) < 2:
        return 0.0, [], []
    total_damage = 0
    for item in stack:
        total_damage += sum(dmg["damage"] for dmg in collect_he_damage_events(item, round_context) if not dmg["team_damage"])
    if total_damage < 80:
        return 0.0, [], []
    return (
        get_weight("he_impact.nade_stack_bonus", 0.4),
        ["nade_stack_damage"],
        [f"多颗 HE 在 3 秒内命中同一区域，总伤害 {total_damage}，按多雷配合计分"],
    )


def detect_low_value_he(
    damage_events: list[dict[str, Any]],
    kill_events: list[dict[str, Any]],
    labels: list[str],
) -> bool:
    enemy_damage = sum(item["damage"] for item in damage_events if not item["team_damage"])
    if enemy_damage >= get_weight("he_impact.low_value_damage_threshold", 10):
        return False
    if any(not item["team_kill"] for item in kill_events):
        return False
    valuable = {
        "assist_he",
        "anti_smoke_he_direct",
        "anti_smoke_he_direct_kill",
        "anti_smoke_route_he",
        "anti_smoke_route_he_kill",
        "anti_cross_he",
        "anti_plant_he",
        "anti_defuse_he",
        "anti_rush_he",
        "nade_stack_damage",
    }
    return not any(label in valuable for label in labels)


def collect_he_damage_events(he_event: HEEvent, round_context: RoundContext) -> list[dict[str, Any]]:
    items = []
    thrower_team = get_player_team(he_event.thrower, round_context)
    for event in he_damage_game_events(round_context):
        if abs(event.tick - he_event.tick) > get_weight("he_impact.damage_window_seconds", 2.0):
            continue
        if event.player != he_event.thrower:
            continue
        victim = event.other_player or event.player
        health_before = player_health_before(round_context, victim, event.tick)
        victim_position = player_position_at(round_context, victim, event.tick)
        items.append({
            "tick": event.tick,
            "attacker": event.player,
            "victim": victim,
            "damage": int(event.damage_health or 0),
            "team_damage": get_player_team(victim, round_context) == thrower_team,
            "health_before": health_before,
            "position": victim_position,
        })
    for tick in round_context.ticks:
        for dmg in tick.future_damage:
            if not is_he_weapon(dmg.get("weapon", "")):
                continue
            dmg_time = safe_float(dmg.get("time"), tick.round_seconds)
            if abs(dmg_time - he_event.tick) > get_weight("he_impact.damage_window_seconds", 2.0):
                continue
            attacker = dmg.get("attacker_name") or dmg.get("attacker") or he_event.thrower
            if attacker != he_event.thrower:
                continue
            victim = dmg.get("victim_name") or dmg.get("user_name") or dmg.get("player")
            damage = int(safe_float(dmg.get("dmg_health") or dmg.get("damage_health") or dmg.get("damage"), 0))
            items.append({
                "tick": dmg_time,
                "attacker": attacker,
                "victim": victim,
                "damage": damage,
                "team_damage": get_player_team(victim, round_context) == thrower_team,
                "health_before": player_health_before(round_context, victim, dmg_time),
                "position": player_position_at(round_context, victim, dmg_time),
            })
    return items


def collect_he_kill_events(he_event: HEEvent, round_context: RoundContext) -> list[dict[str, Any]]:
    items = []
    seen: set[tuple[float, str, str]] = set()
    thrower_team = get_player_team(he_event.thrower, round_context)
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if event.player != he_event.thrower:
            continue
        if not is_he_weapon(event.weapon):
            continue
        if abs(event.tick - he_event.tick) > get_weight("he_impact.damage_window_seconds", 2.0):
            continue
        victim = event.other_player
        key = (round(event.tick, 3), str(event.player), str(victim))
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "tick": event.tick,
            "killer": event.player,
            "victim": victim,
            "team_kill": get_player_team(victim, round_context) == thrower_team,
        })
    for tick in round_context.ticks:
        for future_kill in tick.future_kills:
            if not is_he_weapon(future_kill.get("weapon", "")):
                continue
            kill_time = safe_float(
                future_kill.get("time") or future_kill.get("tick") or future_kill.get("round_seconds"),
                tick.round_seconds,
            )
            if abs(kill_time - he_event.tick) > get_weight("he_impact.damage_window_seconds", 2.0):
                continue
            killer = (
                future_kill.get("killer")
                or future_kill.get("attacker_name")
                or future_kill.get("attacker")
                or future_kill.get("player")
            )
            if killer != he_event.thrower:
                continue
            victim = (
                future_kill.get("victim")
                or future_kill.get("victim_name")
                or future_kill.get("user_name")
                or future_kill.get("other_player")
            )
            key = (round(kill_time, 3), str(killer), str(victim))
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "tick": kill_time,
                "killer": killer,
                "victim": victim,
                "team_kill": get_player_team(victim, round_context) == thrower_team,
            })
    return items


def he_damage_game_events(round_context: RoundContext) -> list[GameEvent]:
    return [
        event for event in round_context.events
        if event.event_type == EventType.DAMAGE and is_he_weapon(event.weapon)
    ]


def he_assist_kill(he_event: HEEvent, round_context: RoundContext, damage_events: list[dict[str, Any]]) -> bool:
    thrower_team = get_player_team(he_event.thrower, round_context)
    victims = {item["victim"] for item in damage_events if not item["team_damage"]}
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if event.other_player not in victims:
            continue
        if event.player == he_event.thrower and is_he_weapon(event.weapon):
            continue
        if 0 <= event.tick - he_event.tick <= get_weight("he_impact.assist_window_seconds", 5.0):
            if get_player_team(event.player, round_context) == thrower_team:
                return True
    return False


def teammate_died_after(he_event: HEEvent, player_name: str | None, round_context: RoundContext) -> bool:
    if not player_name:
        return False
    for event in round_context.events:
        if event.event_type == EventType.KILL and event.other_player == player_name and 0 <= event.tick - he_event.tick <= 3.0:
            return True
    return False


def active_smokes_at(round_context: RoundContext, tick_time: float) -> list[dict[str, Any]]:
    smokes = []
    for tick in round_context.ticks:
        if abs(tick.round_seconds - tick_time) > get_weight("he_impact.smoke_active_window_seconds", 8.0):
            continue
        for projectile in tick.projectiles:
            if projectile.get("type") != "smokegrenade":
                continue
            duration = safe_float(projectile.get("duration"), 0.0)
            start_time = tick.round_seconds - duration
            if duration <= 0 or start_time <= tick_time <= tick.round_seconds + 0.5:
                smokes.append(projectile)
    return smokes


def match_smoke_target_name(smoke_pos: tuple[float, float, float] | None, map_knowledge: dict[str, Any]) -> str | None:
    if smoke_pos is None:
        return None
    best: tuple[float, str] | None = None
    for name, raw in (map_knowledge.get("smoke_targets") or {}).items():
        center = coerce_position(raw.get("target_center"))
        if center is None:
            continue
        radius = safe_float(raw.get("smoke_radius"), get_weight("he_impact.smoke_radius", 170.0)) * 1.8
        dist = calculate_distance_2d(smoke_pos[0], smoke_pos[1], center[0], center[1])
        if dist <= radius and (best is None or dist < best[0]):
            best = (dist, name)
    return best[1] if best else None


def victim_position_close_to(damage_event: dict[str, Any], position: tuple[float, float, float], radius: float) -> bool:
    victim_pos = damage_event.get("position")
    if victim_pos is None:
        return False
    return calculate_distance_2d(victim_pos[0], victim_pos[1], position[0], position[1]) <= radius


def he_or_victim_in_zone(
    he_event: HEEvent,
    damage_events: list[dict[str, Any]],
    zone: dict[str, Any],
) -> bool:
    if he_event.position is not None and point_in_zone(he_event.position, zone):
        return True
    return any(item.get("position") is not None and point_in_zone(item["position"], zone) for item in damage_events)


def point_in_zone(position: tuple[float, float, float], zone: dict[str, Any]) -> bool:
    polygon = zone.get("polygon")
    if polygon:
        return point_in_polygon(position[0], position[1], polygon)
    center = coerce_position(zone.get("center"))
    if center is not None:
        radius = safe_float(zone.get("radius"), get_weight("he_impact.cross_radius", 250.0))
        return calculate_distance_2d(position[0], position[1], center[0], center[1]) <= radius
    return False


def point_in_polygon(x: float, y: float, polygon: list[Any]) -> bool:
    points = [(safe_float(p[0]), safe_float(p[1])) for p in polygon if isinstance(p, (list, tuple)) and len(p) >= 2]
    inside = False
    j = len(points) - 1
    for i, point in enumerate(points):
        xi, yi = point
        xj, yj = points[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def near_bomb(he_event: HEEvent, round_context: RoundContext) -> bool:
    if he_event.position is None:
        return False
    for tick in round_context.ticks:
        bomb = coerce_position(tick.bomb_position)
        if bomb and calculate_distance_2d(he_event.position[0], he_event.position[1], bomb[0], bomb[1]) <= get_weight("he_impact.objective_radius", 350.0):
            return True
    return False


def ct_near_bomb_after(he_event: HEEvent, round_context: RoundContext) -> bool:
    for tick in round_context.ticks:
        if not 0 <= tick.round_seconds - he_event.tick <= 4.0:
            continue
        bomb = coerce_position(tick.bomb_position)
        if bomb is None:
            continue
        for info in tick.players_info:
            name = info.get("name")
            if not name or not is_ct(name, round_context):
                continue
            pos = player_position(info)
            if pos and calculate_distance_2d(pos[0], pos[1], bomb[0], bomb[1]) <= 500:
                return True
    return False


def enemy_delayed_or_stopped(he_event: HEEvent, round_context: RoundContext) -> bool:
    if he_event.position is None:
        return False
    before = nearest_tick(round_context.ticks, he_event.tick)
    after = nearest_tick(round_context.ticks, he_event.tick + 2.0)
    if before is None or after is None:
        return False
    thrower_team = get_player_team(he_event.thrower, round_context)
    for info in before.players_info:
        name = info.get("name")
        if not name or get_player_team(name, round_context) == thrower_team:
            continue
        start = player_position(info)
        end = player_position(player_info_at_tick(after, name))
        if start is None or end is None:
            continue
        start_dist = calculate_distance_2d(start[0], start[1], he_event.position[0], he_event.position[1])
        end_dist = calculate_distance_2d(end[0], end[1], he_event.position[0], he_event.position[1])
        moved = calculate_distance_2d(start[0], start[1], end[0], end[1])
        if start_dist <= 650 and (moved < 80 or end_dist > start_dist + 220):
            return True
    return False


def enemies_near_he(he_event: HEEvent, round_context: RoundContext) -> int:
    if he_event.position is None:
        return 0
    tick = nearest_tick(round_context.ticks, he_event.tick)
    if tick is None:
        return 0
    thrower_team = get_player_team(he_event.thrower, round_context)
    count = 0
    for info in tick.players_info:
        name = info.get("name")
        if not name or get_player_team(name, round_context) == thrower_team:
            continue
        pos = player_position(info)
        if pos and calculate_distance_2d(pos[0], pos[1], he_event.position[0], he_event.position[1]) <= get_weight("he_impact.enemy_near_radius", 650.0):
            count += 1
    return count


def player_health_before(round_context: RoundContext, player_name: str | None, tick_time: float) -> int | None:
    info = find_player_info_before(round_context.ticks, player_name or "", tick_time)
    if info is None:
        return None
    value = info.get("health")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def player_position_at(round_context: RoundContext, player_name: str | None, tick_time: float) -> tuple[float, float, float] | None:
    if not player_name:
        return None
    tick = nearest_tick(round_context.ticks, tick_time)
    if tick is None:
        return None
    return player_position(player_info_at_tick(tick, player_name))


def is_ct(player_name: str, round_context: RoundContext) -> bool:
    return (player_name in round_context.team1_players and round_context.team1_on_ct) or (
        player_name in round_context.team2_players and not round_context.team1_on_ct
    )


def is_he_weapon(value: Any) -> bool:
    text = str(value or "").lower()
    return any(word in text for word in HE_WEAPONS)


def get_player_team(player_name: str | None, round_context: RoundContext) -> str:
    if player_name in round_context.team1_players:
        return "team1"
    if player_name in round_context.team2_players:
        return "team2"
    return "unknown"


def nearest_tick(ticks: list[PredictionTick], target_time: float) -> PredictionTick | None:
    if not ticks:
        return None
    return min(ticks, key=lambda item: abs(item.round_seconds - target_time))


def find_player_info_before(ticks: list[PredictionTick], player_name: str, target_time: float) -> dict[str, Any] | None:
    candidates = [tick for tick in ticks if 0 <= target_time - tick.round_seconds <= 3.0]
    candidates.sort(key=lambda item: item.round_seconds, reverse=True)
    for tick in candidates:
        info = player_info_at_tick(tick, player_name)
        if info is not None:
            return info
    return None


def find_player_info_after(ticks: list[PredictionTick], player_name: str, target_time: float) -> dict[str, Any] | None:
    candidates = [tick for tick in ticks if 0 <= tick.round_seconds - target_time <= 3.0]
    candidates.sort(key=lambda item: item.round_seconds)
    for tick in candidates:
        info = player_info_at_tick(tick, player_name)
        if info is not None:
            return info
    return None


def player_info_at_tick(tick: PredictionTick, player_name: str) -> dict[str, Any] | None:
    for player in tick.players_info:
        if player.get("name") == player_name:
            return player
    return None


def player_position(player: dict[str, Any] | None) -> tuple[float, float, float] | None:
    if player is None:
        return None
    try:
        return float(player["X"]), float(player["Y"]), float(player.get("Z", 0.0))
    except (KeyError, TypeError, ValueError):
        return None


def coerce_position(value: Any) -> tuple[float, float, float] | None:
    if isinstance(value, dict):
        x, y, z = value.get("x"), value.get("y"), value.get("z", 0.0)
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = value[0], value[1]
        z = value[2] if len(value) > 2 else 0.0
    else:
        return None
    try:
        return float(x), float(y), float(z)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[Any]) -> list[Any]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
