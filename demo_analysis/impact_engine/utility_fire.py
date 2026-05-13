"""Rule-based Molotov / Incendiary impact scoring."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .align import calculate_distance_2d, safe_float
from .config import get_weight
from .models import EventType, FireImpact, GameEvent, PredictionTick, RoundContext


FIRE_WEAPONS = {"molotov", "incendiary", "inferno", "firebomb"}


@dataclass
class FireEvent:
    entityid: Any
    start_tick: float
    end_tick: float
    position: tuple[float, float, float]
    thrower: str = "unknown"
    fire_type: str = "inferno"
    low_confidence: bool = False
    attribution_method: str = "unknown"


@dataclass
class FireTarget:
    name: str
    map_name: str
    intent: str
    target_area: str
    center: tuple[float, float]
    radius: float = 180.0
    kind: str = "choke"
    teammate_block_lines: list[dict[str, Any]] = field(default_factory=list)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_player_fire_impact(
    player_name: str,
    round_context: RoundContext,
) -> tuple[float, list[FireImpact]]:
    impacts = []
    for fire in collect_fire_events(round_context):
        if fire.thrower != player_name:
            continue
        impacts.append(score_fire_event(fire, round_context))
    return sum(impact.score for impact in impacts), impacts


def score_fire_event(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget] | None = None,
) -> FireImpact:
    map_knowledge = map_knowledge or load_fire_targets(round_context)
    fire_target = match_fire_target(fire_event, round_context, map_knowledge)
    intent = classify_fire_intent(fire_event, round_context, map_knowledge, fire_target)

    score = 0.0
    labels: list[str] = []
    reasons: list[str] = []
    damage_events: list[dict[str, Any]] = []
    forced_movements: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []

    if fire_event.low_confidence:
        labels.append("low_confidence")
        reasons.append("缺少 inferno_expire，使用保守默认持续时间")

    damage_score, damage_labels, damage_reasons, damage_events = score_fire_damage(
        fire_event, round_context
    )
    score += damage_score
    labels.extend(damage_labels)
    reasons.extend(damage_reasons)

    zone_score, zone_labels, zone_reasons = score_fire_zone_control(
        fire_event, round_context, map_knowledge, fire_target
    )
    score += zone_score
    labels.extend(zone_labels)
    reasons.extend(zone_reasons)

    forced_score, forced_labels, forced_reasons, forced_movements = score_forced_position(
        fire_event, round_context, map_knowledge, fire_target
    )
    score += forced_score
    labels.extend(forced_labels)
    reasons.extend(forced_reasons)

    objective_score, objective_labels, objective_reasons, objective_conversions = score_objective_fire(
        fire_event, round_context, map_knowledge, fire_target
    )
    score += objective_score
    labels.extend(objective_labels)
    reasons.extend(objective_reasons)
    conversions.extend(objective_conversions)

    extinguish_score, extinguish_labels, extinguish_reasons = score_extinguished_fire(
        fire_event, round_context
    )
    score += extinguish_score
    labels.extend(extinguish_labels)
    reasons.extend(extinguish_reasons)

    harmful_score, harmful_labels, harmful_reasons = score_harmful_fire(
        fire_event, round_context, map_knowledge, fire_target
    )
    score += harmful_score
    labels.extend(harmful_labels)
    reasons.extend(harmful_reasons)

    if intent == "fake_pressure_fire":
        fake_score, fake_labels, fake_reasons = score_fake_pressure_fire(
            fire_event, round_context, map_knowledge
        )
        score += fake_score
        labels.extend(fake_labels)
        reasons.extend(fake_reasons)

    if not labels:
        labels.append("random_fire")
        reasons.append("没有伤害、控图、逼位或目标转化证据，按 random_fire 处理")

    if score <= 0 and any(label in labels for label in ("random_fire", "extinguished_no_value")):
        labels.append("wasted_fire")

    score = clamp(
        score,
        get_weight("fire_impact.min_fire_score_per_fire", -3.0),
        get_weight("fire_impact.max_fire_score_per_fire", 3.0),
    )

    return FireImpact(
        thrower=fire_event.thrower,
        round_id=round_context.round_id,
        tick=fire_event.start_tick,
        fire_type=fire_event.fire_type,
        intent=intent,
        score=round(score, 3),
        labels=_dedupe(labels),
        damage_events=damage_events,
        forced_movements=forced_movements,
        conversions=conversions,
        reasons=_dedupe(reasons),
    )


def collect_fire_events(round_context: RoundContext) -> list[FireEvent]:
    events: dict[Any, FireEvent] = {}
    # 1. inferno projectiles with direct thrower
    for tick in sorted(round_context.ticks, key=lambda item: item.round_seconds):
        for projectile in tick.projectiles:
            if projectile.get("type") != "inferno":
                continue
            entityid = projectile.get("entityid", f"inferno-{len(events)}")
            position = coerce_position(projectile.get("position"))
            if position is None:
                continue
            duration = safe_float(projectile.get("duration"), 0.0)
            start_tick = max(0.0, tick.round_seconds - duration)
            thrower = projectile.get("name") or "unknown"
            if entityid not in events:
                events[entityid] = FireEvent(
                    entityid=entityid,
                    start_tick=start_tick,
                    end_tick=tick.round_seconds,
                    position=position,
                    thrower=thrower,
                    fire_type="inferno",
                    attribution_method="entityid_direct" if thrower != "unknown" else "unknown",
                )
            else:
                events[entityid].end_tick = tick.round_seconds
                events[entityid].position = position
                if events[entityid].thrower == "unknown" and thrower != "unknown":
                    events[entityid].thrower = thrower
                    events[entityid].attribution_method = "entityid_direct"

    # 2. entity_grenade_match attribution
    throwers = infer_fire_throwers(round_context)
    for fire in events.values():
        if fire.thrower == "unknown":
            matched_thrower = throwers.get(fire.entityid)
            if matched_thrower:
                fire.thrower = matched_thrower
                fire.attribution_method = "entity_grenade_match"

    # 3. projectile_position_time: molotov/incendiary projectile last position matches inferno start
    _attribute_by_projectile_position(events, round_context)

    # 4. inventory_drop inference
    for fire in events.values():
        if fire.thrower == "unknown":
            inferred = infer_inventory_thrower(fire, round_context)
            if inferred != "unknown":
                fire.thrower = inferred
                fire.attribution_method = "inventory_drop"

    # 5. damage_attacker from DAMAGE events and future_damage
    _attribute_and_generate_from_damage(events, round_context)

    for fire in events.values():
        if fire.end_tick <= fire.start_tick:
            fire.end_tick = fire.start_tick + get_weight("fire_impact.default_duration", 6.0)
            fire.low_confidence = True
    return list(events.values())


def _attribute_by_projectile_position(events: dict[Any, FireEvent], round_context: RoundContext) -> None:
    """Attribute fire events by matching molotov/incendiary projectile positions to inferno start."""
    # Gather molotov/incendiary projectiles with positions and times
    fire_projectiles: list[dict[str, Any]] = []
    for tick in sorted(round_context.ticks, key=lambda item: item.round_seconds):
        for projectile in tick.projectiles:
            ptype = str(projectile.get("type", "")).lower()
            if "molotov" in ptype or "incendiary" in ptype:
                position = coerce_position(projectile.get("position"))
                if position is not None:
                    fire_projectiles.append({
                        "position": position,
                        "time": tick.round_seconds,
                        "name": projectile.get("name") or "unknown",
                    })
        for grenade in tick.entity_grenades:
            gtype = str(grenade.get("type", "")).lower()
            if "molotov" in gtype or "incendiary" in gtype or "incgrenade" in gtype:
                position = coerce_position(grenade.get("position"))
                if position is not None:
                    fire_projectiles.append({
                        "position": position,
                        "time": tick.round_seconds,
                        "name": grenade.get("name") or "unknown",
                    })

    for fire in events.values():
        if fire.thrower != "unknown":
            continue
        for fp in fire_projectiles:
            time_diff = abs(fp["time"] - fire.start_tick)
            dist = calculate_distance_2d(fp["position"][0], fp["position"][1], fire.position[0], fire.position[1])
            if time_diff <= 1.5 and dist <= 350.0:
                fire.thrower = fp["name"]
                fire.attribution_method = "projectile_position_time"
                break


def _attribute_and_generate_from_damage(events: dict[Any, FireEvent], round_context: RoundContext) -> None:
    """Enhance existing fire events or generate low-confidence ones from damage."""
    # Collect fire damage from events and future_damage
    fire_damages: list[dict[str, Any]] = []
    for event in round_context.events:
        if event.event_type == EventType.DAMAGE and is_fire_weapon(event.weapon):
            fire_damages.append({
                "tick": event.tick,
                "attacker": event.player,
                "victim": event.other_player,
                "position": player_position_at(round_context, event.other_player, event.tick),
            })
    for tick in round_context.ticks:
        for dmg in tick.future_damage:
            if is_fire_weapon(dmg.get("weapon", "")):
                dmg_time = safe_float(dmg.get("time"), tick.round_seconds)
                attacker = dmg.get("attacker_name") or dmg.get("attacker") or "unknown"
                victim = dmg.get("victim_name") or dmg.get("user_name") or dmg.get("player")
                fire_damages.append({
                    "tick": dmg_time,
                    "attacker": attacker,
                    "victim": victim,
                    "position": player_position_at(round_context, victim, dmg_time),
                })

    for fd in fire_damages:
        # Try to enhance nearby existing fire event
        enhanced = False
        for fire in events.values():
            if fire.thrower == "unknown" and fd.get("attacker") and fd["attacker"] != "unknown":
                time_diff = abs(fd["tick"] - fire.start_tick)
                if time_diff <= get_weight("fire_impact.damage_window_seconds", 6.0):
                    fire.thrower = fd["attacker"]
                    fire.attribution_method = "damage_attacker"
                    enhanced = True
                    break
            elif fire.thrower != "unknown" and fd.get("attacker") == fire.thrower:
                time_diff = abs(fd["tick"] - fire.start_tick)
                if time_diff <= get_weight("fire_impact.damage_window_seconds", 6.0):
                    enhanced = True
                    break
        # If no inferno event exists, generate low-confidence FireEvent
        if not enhanced and fd.get("attacker") and fd["attacker"] != "unknown":
            entityid = f"fire-damage-{fd['attacker']}-{fd['tick']}"
            if entityid not in events:
                pos = fd.get("position")
                if pos is None:
                    pos = (0.0, 0.0, 0.0)
                events[entityid] = FireEvent(
                    entityid=entityid,
                    start_tick=fd["tick"],
                    end_tick=fd["tick"] + get_weight("fire_impact.default_duration", 6.0),
                    position=pos,
                    thrower=fd["attacker"],
                    fire_type="inferno",
                    low_confidence=True,
                    attribution_method="damage_attacker",
                )


def infer_fire_throwers(round_context: RoundContext) -> dict[Any, str]:
    throwers: dict[Any, str] = {}
    for tick in sorted(round_context.ticks, key=lambda item: item.round_seconds):
        for grenade in tick.entity_grenades:
            entityid = grenade.get("entityid")
            name = grenade.get("name")
            grenade_type = str(grenade.get("type", "")).lower()
            if entityid is not None and name and any(word in grenade_type for word in FIRE_WEAPONS):
                throwers[entityid] = name
    return throwers


def infer_inventory_thrower(fire_event: FireEvent, round_context: RoundContext) -> str:
    candidates = []
    for player in round_context.team1_players + round_context.team2_players:
        before = find_player_info_before(round_context.ticks, player, fire_event.start_tick)
        after = find_player_info_after(round_context.ticks, player, fire_event.start_tick)
        if fire_inventory_count((before or {}).get("inventory")) > fire_inventory_count((after or {}).get("inventory")):
            candidates.append(player)
    return candidates[0] if len(candidates) == 1 else "unknown"


def fire_inventory_count(inventory: Any) -> int:
    if not isinstance(inventory, list):
        return 0
    return sum(
        1 for item in inventory
        if any(word in str(item).lower() for word in ("molotov", "incendiary"))
    )


def load_fire_targets(round_context: RoundContext) -> dict[str, FireTarget]:
    map_name = round_context.map_name
    if not map_name or map_name == "Unknown":
        return {}
    cfg_path = Path(__file__).resolve().parents[2] / "config" / "callouts" / f"{map_name}.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    targets = {}
    for name, raw in (data.get("fire_targets") or {}).items():
        center = coerce_xy(raw.get("center") or raw.get("target_center"))
        if center is None:
            continue
        targets[name] = FireTarget(
            name=name,
            map_name=str(raw.get("map") or map_name),
            intent=str(raw.get("intent") or "unknown_fire"),
            target_area=str(raw.get("target_area") or name),
            center=center,
            radius=safe_float(raw.get("radius"), get_weight("fire_impact.default_radius", 180.0)),
            kind=str(raw.get("kind") or "choke"),
            teammate_block_lines=raw.get("teammate_block_lines") or [],
        )
    return targets


def classify_fire_intent(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget],
    fire_target: FireTarget | None = None,
) -> str:
    if fire_target is not None:
        if fire_target.intent == "fake_pressure_fire" or looks_like_fake_pressure(fire_event, round_context):
            return "fake_pressure_fire"
        if round_context.bomb_planted_time is not None and fire_target.intent in {"post_plant_fire", "anti_defuse_fire"}:
            return fire_target.intent
        return fire_target.intent
    if round_context.bomb_planted_time is not None and near_bomb(fire_event, round_context):
        return "anti_defuse_fire"
    if looks_like_fake_pressure(fire_event, round_context):
        return "fake_pressure_fire"
    if enemies_near_fire(fire_event, round_context) >= get_weight("fire_impact.rush_enemy_count", 2):
        return "anti_rush_fire"
    return "random_fire"


def match_fire_target(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget],
) -> FireTarget | None:
    best: tuple[float, FireTarget] | None = None
    for target in map_knowledge.values():
        dist = calculate_distance_2d(fire_event.position[0], fire_event.position[1], target.center[0], target.center[1])
        if dist <= target.radius * 1.5 and (best is None or dist < best[0]):
            best = (dist, target)
    return best[1] if best else None


def score_fire_damage(
    fire_event: FireEvent,
    round_context: RoundContext,
) -> tuple[float, list[str], list[str], list[dict[str, Any]]]:
    labels = []
    reasons = []
    damage_events = collect_fire_damage_events(fire_event, round_context)
    enemy_damage = sum(item["damage"] for item in damage_events if not item["team_damage"])
    team_damage = sum(item["damage"] for item in damage_events if item["team_damage"])
    score = enemy_damage * get_weight("fire_impact.damage_multiplier", 0.015)

    if enemy_damage > 0:
        labels.append("damage_fire")
        reasons.append(f"火造成敌方 {enemy_damage} 点伤害")
    if enemy_damage >= get_weight("fire_impact.high_damage_threshold", 40):
        labels.append("high_damage_fire")
        score += 0.3
        reasons.append("火造成高额伤害")

    if any(item.get("kill") for item in damage_events if not item["team_damage"]):
        labels.append("kill_fire")
        score += get_weight("fire_impact.kill_bonus", 0.8)
        reasons.append("火直接造成击杀")
    elif enemy_damage > 0 and fire_assist_kill(fire_event, round_context):
        labels.append("assist_fire")
        score += get_weight("fire_impact.assist_bonus", 0.3)
        reasons.append("火造成伤害后队友完成击杀")

    if team_damage > 0:
        labels.append("team_damage_fire")
        score += team_damage * get_weight("fire_impact.team_damage_multiplier", -0.02)
        reasons.append(f"火造成队友 {team_damage} 点伤害")
        if any(item.get("kill") for item in damage_events if item["team_damage"]):
            labels.append("harmful_fire")
            score += get_weight("fire_impact.harmful_fire_penalty", -1.2)
            reasons.append("火导致队友死亡或严重破坏补枪")

    return score, labels, reasons, damage_events


def score_fire_zone_control(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget],
    fire_target: FireTarget | None,
) -> tuple[float, list[str], list[str]]:
    if fire_target is None or fire_target.kind not in {"choke", "rush_path"}:
        return 0.0, [], []
    enemy_count = enemies_near_fire(fire_event, round_context)
    if enemy_count <= 0:
        return 0.0, [], ["火覆盖 choke，但敌人不在附近，不能给高控图分"]

    labels = ["choke_control_fire"]
    reasons = ["火覆盖关键 choke point 并影响敌方通过"]
    score = get_weight("fire_impact.choke_control_bonus", 0.5)
    if enemy_count >= get_weight("fire_impact.rush_enemy_count", 2):
        labels.append("anti_rush_fire")
        score += get_weight("fire_impact.anti_rush_bonus", 0.7)
        reasons.append("敌方多人接近入口，火成功阻止 rush")
    if enemy_delayed_or_rotated(fire_event, round_context):
        labels.append("successful_delay_fire")
        score += 0.4
        reasons.append("敌方等待、绕路或后撤，火拖延了关键时间")
    return score, labels, reasons


def score_forced_position(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget],
    fire_target: FireTarget | None = None,
) -> tuple[float, list[str], list[str], list[dict[str, Any]]]:
    labels = []
    reasons = []
    movements = []
    score = 0.0
    before = nearest_tick(round_context.ticks, fire_event.start_tick)
    after = nearest_tick(round_context.ticks, fire_event.start_tick + get_weight("fire_impact.forced_position_window_seconds", 3.0))
    if before is None or after is None:
        return 0.0, [], [], []

    thrower_team = get_player_team(fire_event.thrower, round_context)
    for player in before.players_info:
        name = player.get("name")
        if not name or get_player_team(name, round_context) == thrower_team:
            continue
        start = player_position(player)
        end_info = player_info_at_tick(after, name)
        end = player_position(end_info)
        if start is None or end is None:
            continue
        if calculate_distance_2d(start[0], start[1], fire_event.position[0], fire_event.position[1]) > get_fire_radius(fire_event, fire_target):
            continue
        moved = calculate_distance_2d(start[0], start[1], end[0], end[1])
        if moved >= get_weight("fire_impact.delay_distance_threshold", 450.0):
            labels.append("forced_position_fire")
            score += get_weight("fire_impact.forced_position_bonus", 0.4)
            movement = {"player": name, "distance": round(moved, 1)}
            if killed_after(fire_event, name, round_context, seconds=5.0):
                score += 0.6
                movement["killed_after"] = True
                reasons.append("火逼敌人离开强位，随后被击杀")
            else:
                reasons.append("火逼敌人离开强位")
            movements.append(movement)
    return score, _dedupe(labels), _dedupe(reasons), movements


def score_objective_fire(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget],
    fire_target: FireTarget | None,
) -> tuple[float, list[str], list[str], list[dict[str, Any]]]:
    labels = []
    reasons = []
    conversions = []
    score = 0.0
    intent = fire_target.intent if fire_target else classify_fire_intent(fire_event, round_context, map_knowledge, fire_target)

    if round_context.bomb_planted_time is not None and near_bomb(fire_event, round_context):
        labels.append("post_plant_fire")
        score += get_weight("fire_impact.post_plant_bonus", 0.8)
        reasons.append("炸弹已下，火覆盖拆包区域或 CT 到炸弹路径")
        conversions.append({"type": "post_plant_delay"})
        if ct_near_bomb_after(fire_event, round_context):
            labels.append("anti_defuse_fire")
            score += get_weight("fire_impact.anti_defuse_bonus", 1.0)
            reasons.append("火阻止或拖延 CT 拆包")
            conversions.append({"type": "anti_defuse"})
    elif intent == "anti_plant_fire":
        labels.append("anti_plant_fire")
        score += get_weight("fire_impact.anti_plant_bonus", 0.8)
        reasons.append("火覆盖默认下包点或下包路线，拖延 T 下包")
        conversions.append({"type": "anti_plant"})

    return score, labels, reasons, conversions


def score_extinguished_fire(
    fire_event: FireEvent,
    round_context: RoundContext,
) -> tuple[float, list[str], list[str]]:
    smoke = overlapping_smoke_after_fire(fire_event, round_context)
    if smoke is None:
        return 0.0, [], []
    if fire_event.end_tick - fire_event.start_tick <= 1.5:
        if enemies_near_fire(fire_event, round_context) > 0 or round_context.bomb_planted_time is not None:
            return (
                get_weight("fire_impact.forced_smoke_bonus", 0.5),
                ["forced_smoke_extinguish", "extinguished_but_forced_smoke"],
                ["火逼迫对手交烟灭火，消耗关键烟雾资源"],
            )
        return 0.0, ["extinguished_no_value"], ["火很快被烟灭且没有伤害、拖延或资源价值"]
    return (
        get_weight("fire_impact.forced_smoke_bonus", 0.5),
        ["forced_smoke_extinguish", "extinguished_but_forced_smoke"],
        ["火被烟灭，但已迫使对手交烟处理"],
    )


def score_harmful_fire(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget],
    fire_target: FireTarget | None,
) -> tuple[float, list[str], list[str]]:
    labels = []
    reasons = []
    score = 0.0
    if fire_blocks_teammate_push(fire_event, round_context):
        labels.append("teammate_blocking_fire")
        score += get_weight("fire_impact.teammate_block_penalty", -0.8)
        reasons.append("火挡住队友进点路线或补枪路径")
    return score, labels, reasons


def score_fake_pressure_fire(
    fire_event: FireEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, FireTarget],
) -> tuple[float, list[str], list[str]]:
    if enemy_rotation_triggered(fire_event, round_context) and real_execute_success_elsewhere(fire_event, round_context):
        return 1.3, ["fake_pressure_fire"], ["该火用于制造压力，诱发 CT 转点并帮助另一侧成功"]
    if enemy_rotation_triggered(fire_event, round_context):
        return 0.5, ["fake_pressure_fire"], ["该火制造压力并诱发防守反应"]
    return 0.1, ["fake_pressure_fire"], ["假打火没有烧到人，但保留低分压力价值"]


def collect_fire_damage_events(fire_event: FireEvent, round_context: RoundContext) -> list[dict[str, Any]]:
    items = []
    thrower_team = get_player_team(fire_event.thrower, round_context)
    for event in round_context.events:
        if event.event_type == EventType.DAMAGE and 0 <= event.tick - fire_event.start_tick <= get_weight("fire_impact.damage_window_seconds", 6.0):
            if event.weapon and not is_fire_weapon(event.weapon):
                continue
            victim = event.other_player or event.player
            items.append({
                "tick": event.tick,
                "attacker": event.player,
                "victim": victim,
                "damage": int(event.damage_health or 0),
                "team_damage": get_player_team(victim, round_context) == thrower_team,
                "kill": killed_after_any(fire_event, victim, round_context, seconds=0.2),
            })
    for tick in round_context.ticks:
        for dmg in tick.future_damage:
            dmg_time = safe_float(dmg.get("time"), tick.round_seconds)
            if not 0 <= dmg_time - fire_event.start_tick <= get_weight("fire_impact.damage_window_seconds", 6.0):
                continue
            if not is_fire_weapon(dmg.get("weapon", "")):
                continue
            victim = dmg.get("victim_name") or dmg.get("user_name") or dmg.get("player")
            attacker = dmg.get("attacker_name") or fire_event.thrower
            damage = int(safe_float(dmg.get("dmg_health") or dmg.get("damage_health") or dmg.get("damage"), 0))
            if victim:
                items.append({
                    "tick": dmg_time,
                    "attacker": attacker,
                    "victim": victim,
                    "damage": damage,
                    "team_damage": get_player_team(victim, round_context) == thrower_team,
                    "kill": killed_after_any(fire_event, victim, round_context, seconds=0.2),
                })
    return items


def fire_assist_kill(fire_event: FireEvent, round_context: RoundContext) -> bool:
    victims = {
        item["victim"]
        for item in collect_fire_damage_events(fire_event, round_context)
        if not item["team_damage"]
    }
    for victim in victims:
        if killed_after(fire_event, victim, round_context, seconds=get_weight("fire_impact.assist_window_seconds", 5.0)):
            return True
    return False


def killed_after(fire_event: FireEvent, player_name: str | None, round_context: RoundContext, seconds: float) -> bool:
    if not player_name:
        return False
    thrower_team = get_player_team(fire_event.thrower, round_context)
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if event.other_player != player_name:
            continue
        if not 0 <= event.tick - fire_event.start_tick <= seconds:
            continue
        return get_player_team(event.player, round_context) == thrower_team
    return False


def killed_after_any(fire_event: FireEvent, player_name: str | None, round_context: RoundContext, seconds: float) -> bool:
    if not player_name:
        return False
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if event.other_player != player_name:
            continue
        if 0 <= event.tick - fire_event.start_tick <= seconds:
            return True
    return False


def enemies_near_fire(fire_event: FireEvent, round_context: RoundContext) -> int:
    tick = nearest_tick(round_context.ticks, fire_event.start_tick)
    if tick is None:
        return 0
    thrower_team = get_player_team(fire_event.thrower, round_context)
    count = 0
    for player in tick.players_info:
        name = player.get("name")
        if not name or get_player_team(name, round_context) == thrower_team:
            continue
        pos = player_position(player)
        if pos and calculate_distance_2d(pos[0], pos[1], fire_event.position[0], fire_event.position[1]) <= get_weight("fire_impact.enemy_near_radius", 650.0):
            count += 1
    return count


def enemy_delayed_or_rotated(fire_event: FireEvent, round_context: RoundContext) -> bool:
    before = nearest_tick(round_context.ticks, fire_event.start_tick)
    after = nearest_tick(round_context.ticks, fire_event.start_tick + 2.5)
    if before is None or after is None:
        return False
    thrower_team = get_player_team(fire_event.thrower, round_context)
    for before_player in before.players_info:
        name = before_player.get("name")
        if not name or get_player_team(name, round_context) == thrower_team:
            continue
        start = player_position(before_player)
        end = player_position(player_info_at_tick(after, name))
        if start and end:
            start_dist = calculate_distance_2d(start[0], start[1], fire_event.position[0], fire_event.position[1])
            end_dist = calculate_distance_2d(end[0], end[1], fire_event.position[0], fire_event.position[1])
            if start_dist <= 650 and end_dist > start_dist + 250:
                return True
    return False


def near_bomb(fire_event: FireEvent, round_context: RoundContext) -> bool:
    for tick in round_context.ticks:
        position = coerce_position(tick.bomb_position)
        if position and calculate_distance_2d(position[0], position[1], fire_event.position[0], fire_event.position[1]) <= 350:
            return True
    return False


def ct_near_bomb_after(fire_event: FireEvent, round_context: RoundContext) -> bool:
    for tick in round_context.ticks:
        if not 0 <= tick.round_seconds - fire_event.start_tick <= get_weight("fire_impact.objective_window_seconds", 6.0):
            continue
        bomb = coerce_position(tick.bomb_position)
        if bomb is None:
            continue
        for player in tick.players_info:
            name = player.get("name")
            if not name:
                continue
            is_ct = (name in round_context.team1_players and round_context.team1_on_ct) or (name in round_context.team2_players and not round_context.team1_on_ct)
            pos = player_position(player)
            if is_ct and pos and calculate_distance_2d(pos[0], pos[1], bomb[0], bomb[1]) <= 500:
                return True
    return False


def overlapping_smoke_after_fire(fire_event: FireEvent, round_context: RoundContext) -> dict[str, Any] | None:
    for tick in round_context.ticks:
        if not 0 <= tick.round_seconds - fire_event.start_tick <= 2.0:
            continue
        for projectile in tick.projectiles:
            if projectile.get("type") != "smokegrenade":
                continue
            pos = coerce_position(projectile.get("position"))
            if pos and calculate_distance_2d(pos[0], pos[1], fire_event.position[0], fire_event.position[1]) <= 220:
                return projectile
    return None


def fire_blocks_teammate_push(fire_event: FireEvent, round_context: RoundContext) -> bool:
    tick = nearest_tick(round_context.ticks, fire_event.start_tick + 1.0)
    if tick is None:
        return False
    thrower_team = get_player_team(fire_event.thrower, round_context)
    for player in tick.players_info:
        name = player.get("name")
        if not name or name == fire_event.thrower or get_player_team(name, round_context) != thrower_team:
            continue
        pos = player_position(player)
        if pos and calculate_distance_2d(pos[0], pos[1], fire_event.position[0], fire_event.position[1]) <= get_fire_radius(fire_event, None):
            return True
    return False


def looks_like_fake_pressure(fire_event: FireEvent, round_context: RoundContext) -> bool:
    before = nearest_tick(round_context.ticks, fire_event.start_tick)
    after = nearest_tick(round_context.ticks, fire_event.start_tick + 10.0)
    if before is None or after is None:
        return False
    b1 = coerce_position(before.bomb_position)
    b2 = coerce_position(after.bomb_position)
    if b1 is None or b2 is None:
        return False
    return calculate_distance_2d(b1[0], b1[1], b2[0], b2[1]) >= 1200


def enemy_rotation_triggered(fire_event: FireEvent, round_context: RoundContext) -> bool:
    before = nearest_tick(round_context.ticks, fire_event.start_tick)
    after = nearest_tick(round_context.ticks, fire_event.start_tick + 8.0)
    if before is None or after is None:
        return False
    thrower_team = get_player_team(fire_event.thrower, round_context)
    for player in after.players_info:
        name = player.get("name")
        if not name or get_player_team(name, round_context) == thrower_team:
            continue
        b = player_position(player_info_at_tick(before, name))
        a = player_position(player)
        if b and a and calculate_distance_2d(b[0], b[1], a[0], a[1]) >= 650:
            return True
    return False


def real_execute_success_elsewhere(fire_event: FireEvent, round_context: RoundContext) -> bool:
    if round_context.bomb_planted_time is not None and 5 <= round_context.bomb_planted_time - fire_event.start_tick <= get_weight("fire_impact.fake_window_seconds", 20.0):
        return True
    thrower_team = get_player_team(fire_event.thrower, round_context)
    return any(
        event.event_type == EventType.KILL
        and 5 <= event.tick - fire_event.start_tick <= get_weight("fire_impact.fake_window_seconds", 20.0)
        and get_player_team(event.player, round_context) == thrower_team
        for event in round_context.events
    )


def get_fire_radius(fire_event: FireEvent, fire_target: FireTarget | None) -> float:
    return fire_target.radius if fire_target else get_weight("fire_impact.default_radius", 180.0)


def is_fire_weapon(weapon: Any) -> bool:
    text = str(weapon or "").lower()
    return any(word in text for word in FIRE_WEAPONS)


def get_player_team(player_name: str, round_context: RoundContext) -> str:
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


def player_position_at(round_context: RoundContext, player_name: str | None, tick_time: float) -> tuple[float, float, float] | None:
    if not player_name:
        return None
    tick = nearest_tick(round_context.ticks, tick_time)
    if tick is None:
        return None
    return player_position(player_info_at_tick(tick, player_name))


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


def coerce_xy(value: Any) -> tuple[float, float] | None:
    position = coerce_position(value)
    if position is None:
        return None
    return position[0], position[1]


def _dedupe(items: list[Any]) -> list[Any]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
