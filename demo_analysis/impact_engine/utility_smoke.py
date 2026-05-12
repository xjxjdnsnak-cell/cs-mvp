"""Rule-based smoke grenade impact scoring."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .align import calculate_distance_2d, safe_float
from .config import get_weight
from .models import EventType, GameEvent, PredictionTick, RoundContext, SmokeImpact


SMOKE_LABELS = {
    "targeted_smoke",
    "complete_block_smoke",
    "partial_block_smoke",
    "leaky_smoke",
    "fatal_leaky_smoke",
    "false_confidence_smoke",
    "missed_smoke",
    "converted_execute_smoke",
    "successful_fake_smoke",
    "unconverted_fake_smoke",
    "random_smoke",
    "blocking_teammate_smoke",
    "defensive_delay_smoke",
    "retake_support_smoke",
}


@dataclass
class SmokeEvent:
    entityid: Any
    start_tick: float
    end_tick: float
    position: tuple[float, float, float]
    thrower: str = "unknown"


@dataclass
class SmokeTarget:
    name: str
    map_name: str
    intent: str
    target_area: str
    target_center: tuple[float, float]
    smoke_radius: float
    required_block_lines: list[dict[str, Any]] = field(default_factory=list)
    teammate_cross_routes: list[Any] = field(default_factory=list)
    allowed_leak_tolerance: float = 0.15
    teammate_block_lines: list[dict[str, Any]] = field(default_factory=list)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_player_smoke_impact(
    player_name: str,
    round_context: RoundContext,
) -> tuple[float, list[SmokeImpact]]:
    impacts = []
    for smoke in collect_smoke_events(round_context):
        if smoke.thrower != player_name:
            continue
        impacts.append(score_smoke_event(smoke, round_context))
    return sum(impact.score for impact in impacts), impacts


def score_smoke_event(
    smoke_event: SmokeEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget] | None = None,
) -> SmokeImpact:
    map_knowledge = map_knowledge or load_smoke_targets(round_context)
    smoke_target = match_smoke_target(smoke_event, round_context, map_knowledge)
    intent = classify_smoke_intent(smoke_event, round_context, map_knowledge, smoke_target)
    target_matched = smoke_target is not None

    score = 0.0
    labels: list[str] = []
    reasons: list[str] = []

    if target_matched:
        score += get_weight("smoke_impact.target_match_score", 0.2)
        labels.append("targeted_smoke")
        reasons.append(f"烟雾落点匹配 {smoke_target.name}，但目标匹配只作为低权重基础分")
    elif intent == "random_smoke":
        labels.append("random_smoke")
        reasons.append("烟雾未匹配已知目标，按 random_smoke 保守处理")

    block_score, block_labels, block_reasons = score_smoke_quality(
        smoke_event, smoke_target, round_context, map_knowledge
    )
    score += block_score
    labels.extend(block_labels)
    reasons.extend(block_reasons)

    (
        teammate_dependency,
        enemy_exploitation,
        risk_penalty,
        risk_labels,
        risk_reasons,
    ) = evaluate_smoke_risk(smoke_event, smoke_target, round_context, map_knowledge, block_labels)
    score += risk_penalty
    labels.extend(risk_labels)
    reasons.extend(risk_reasons)

    teammate_block_penalty, block_team_labels, block_team_reasons = evaluate_teammate_blocking(
        smoke_event, smoke_target, round_context, map_knowledge
    )
    score += teammate_block_penalty
    labels.extend(block_team_labels)
    reasons.extend(block_team_reasons)

    conversion_score, conversion_labels, conversion_reasons = score_smoke_conversion(
        smoke_event, smoke_target, intent, block_score, round_context, map_knowledge
    )
    score += conversion_score
    labels.extend(conversion_labels)
    reasons.extend(conversion_reasons)

    if intent == "fake_smoke":
        fake_score, fake_labels, fake_reasons = score_fake_smoke(
            smoke_event, round_context, map_knowledge
        )
        score += fake_score
        labels.extend(fake_labels)
        reasons.extend(fake_reasons)

    leak_risk = "none"
    if "fatal_leaky_smoke" in labels:
        leak_risk = "fatal"
    elif "false_confidence_smoke" in labels:
        leak_risk = "false_confidence"
    elif "leaky_smoke" in labels:
        leak_risk = "leaky"
    elif "missed_smoke" in labels:
        leak_risk = "missed"

    return SmokeImpact(
        thrower=smoke_event.thrower,
        round_id=round_context.round_id,
        tick=smoke_event.start_tick,
        intent=intent,
        score=round(score, 3),
        labels=_dedupe(labels),
        reasons=_dedupe(reasons),
        target_matched=target_matched,
        block_score=round(block_score, 3),
        leak_risk=leak_risk,
        conversion_score=round(conversion_score, 3),
        teammate_dependency=round(teammate_dependency, 3),
        enemy_exploitation=round(enemy_exploitation, 3),
    )


def collect_smoke_events(round_context: RoundContext) -> list[SmokeEvent]:
    events: dict[Any, SmokeEvent] = {}
    for tick in sorted(round_context.ticks, key=lambda item: item.round_seconds):
        for projectile in tick.projectiles:
            if projectile.get("type") != "smokegrenade":
                continue
            entityid = projectile.get("entityid", f"smoke-{len(events)}")
            position = coerce_position(projectile.get("position"))
            if position is None:
                continue
            duration = safe_float(projectile.get("duration"), 0.0)
            start_tick = max(0.0, tick.round_seconds - duration)
            if entityid not in events:
                events[entityid] = SmokeEvent(
                    entityid=entityid,
                    start_tick=start_tick,
                    end_tick=tick.round_seconds,
                    position=position,
                    thrower=projectile.get("name") or "unknown",
                )
            else:
                events[entityid].end_tick = tick.round_seconds
                events[entityid].position = position

    throwers = infer_smoke_throwers(round_context)
    for smoke in events.values():
        if smoke.thrower == "unknown":
            smoke.thrower = throwers.get(smoke.entityid) or infer_inventory_thrower(smoke, round_context)
    return list(events.values())


def infer_smoke_throwers(round_context: RoundContext) -> dict[Any, str]:
    throwers: dict[Any, str] = {}
    for tick in sorted(round_context.ticks, key=lambda item: item.round_seconds):
        for grenade in tick.entity_grenades:
            entityid = grenade.get("entityid")
            name = grenade.get("name")
            if entityid is not None and name:
                throwers[entityid] = name
    return throwers


def infer_inventory_thrower(smoke_event: SmokeEvent, round_context: RoundContext) -> str:
    candidates = []
    for player in round_context.team1_players + round_context.team2_players:
        before = find_player_info_before(round_context.ticks, player, smoke_event.start_tick)
        after = find_player_info_after(round_context.ticks, player, smoke_event.start_tick)
        if smoke_inventory_count((before or {}).get("inventory")) > smoke_inventory_count((after or {}).get("inventory")):
            candidates.append(player)
    return candidates[0] if len(candidates) == 1 else "unknown"


def smoke_inventory_count(inventory: Any) -> int:
    if not isinstance(inventory, list):
        return 0
    return sum(1 for item in inventory if "smoke" in str(item).lower())


def load_smoke_targets(round_context: RoundContext) -> dict[str, SmokeTarget]:
    map_name = get_round_map_name(round_context)
    if not map_name:
        return {}
    cfg_path = Path(__file__).resolve().parents[2] / "config" / "callouts" / f"{map_name}.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw_targets = data.get("smoke_targets") or {}
    targets = {}
    for name, raw in raw_targets.items():
        center = coerce_xy(raw.get("target_center"))
        if center is None:
            continue
        targets[name] = SmokeTarget(
            name=name,
            map_name=str(raw.get("map") or map_name),
            intent=str(raw.get("intent") or "unknown_smoke"),
            target_area=str(raw.get("target_area") or name),
            target_center=center,
            smoke_radius=safe_float(raw.get("smoke_radius"), get_weight("smoke_impact.smoke_radius", 170.0)),
            required_block_lines=raw.get("required_block_lines") or [],
            teammate_cross_routes=raw.get("teammate_cross_routes") or [],
            allowed_leak_tolerance=safe_float(raw.get("allowed_leak_tolerance"), 0.15),
            teammate_block_lines=raw.get("teammate_block_lines") or [],
        )
    return targets


def get_round_map_name(round_context: RoundContext) -> str | None:
    for tick in round_context.ticks:
        map_name = getattr(tick, "map_name", None)
        if map_name:
            return str(map_name)
    return getattr(round_context, "map_name", None)


def classify_smoke_intent(
    smoke_event: SmokeEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget],
    smoke_target: SmokeTarget | None = None,
) -> str:
    if smoke_target is not None:
        if smoke_target.intent == "fake_smoke" or looks_like_fake(smoke_event, round_context):
            return "fake_smoke"
        return smoke_target.intent
    if looks_like_fake(smoke_event, round_context):
        return "fake_smoke"
    return "random_smoke"


def match_smoke_target(
    smoke_event: SmokeEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget],
) -> SmokeTarget | None:
    best: tuple[float, SmokeTarget] | None = None
    sx, sy, _ = smoke_event.position
    for target in map_knowledge.values():
        radius = target.smoke_radius * get_weight("smoke_impact.target_match_radius_multiplier", 1.2)
        dist = calculate_distance_2d(sx, sy, target.target_center[0], target.target_center[1])
        if dist <= radius and (best is None or dist < best[0]):
            best = (dist, target)
    return best[1] if best else None


def collect_smoke_target_diagnostics(
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget] | None = None,
) -> tuple[dict[str, int], list[str]]:
    """Collect smoke target match counts and detect overmatched targets.

    Returns:
        (target_match_counts, possible_overmatched_smoke_targets)
    """
    map_knowledge = map_knowledge or load_smoke_targets(round_context)
    smoke_events = collect_smoke_events(round_context)
    target_match_counts: dict[str, int] = {}
    for smoke in smoke_events:
        target = match_smoke_target(smoke, round_context, map_knowledge)
        if target is not None:
            target_match_counts[target.name] = target_match_counts.get(target.name, 0) + 1

    total_smoke_events = len(smoke_events)
    threshold = max(5, int(total_smoke_events * 0.30))
    overmatched = [
        name for name, count in target_match_counts.items()
        if count > threshold
    ]
    return target_match_counts, overmatched


def score_smoke_quality(
    smoke_event: SmokeEvent,
    smoke_target: SmokeTarget | None,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget],
) -> tuple[float, list[str], list[str]]:
    if smoke_target is None:
        return 0.0, [], ["没有匹配烟雾目标，跳过高置信封线评分"]
    if not smoke_target.required_block_lines:
        return 0.0, [], ["目标缺少 required_block_lines，无法判断关键枪线封锁质量"]

    line_results = []
    for line in smoke_target.required_block_lines:
        p1, p2 = line_points(line, smoke_target)
        if p1 is None or p2 is None:
            continue
        distance = point_to_segment_distance(smoke_event.position[0], smoke_event.position[1], p1, p2)
        line_results.append((distance, line))

    if not line_results:
        return 0.0, [], ["关键枪线缺少可用坐标，降级为不加分"]

    radius = smoke_target.smoke_radius
    worst_label = "complete_block_smoke"
    worst_score = get_weight("smoke_impact.complete_block_score", 0.8)
    worst_distance = 0.0
    worst_line = line_results[0][1]
    rank = {
        "missed_smoke": 0,
        "leaky_smoke": 1,
        "partial_block_smoke": 2,
        "complete_block_smoke": 3,
    }
    for distance, line in line_results:
        if distance <= radius * 0.65:
            label = "complete_block_smoke"
            score = get_weight("smoke_impact.complete_block_score", 0.8)
        elif distance <= radius:
            label = "partial_block_smoke"
            score = get_weight("smoke_impact.partial_block_score", 0.3)
        elif distance <= radius * 1.2:
            label = "leaky_smoke"
            score = get_weight("smoke_impact.leaky_smoke_score", -0.5)
        else:
            label = "missed_smoke"
            score = get_weight("smoke_impact.missed_smoke_score", -0.8)
        if rank[label] < rank[worst_label]:
            worst_label = label
            worst_score = score
            worst_distance = distance
            worst_line = line

    line_name = worst_line.get("name", "关键枪线")
    if worst_label == "complete_block_smoke":
        reason = f"烟雾完整覆盖 {line_name}，关键枪线封锁质量高"
    elif worst_label == "partial_block_smoke":
        reason = f"烟雾边缘覆盖 {line_name}，只能算部分封线"
    elif worst_label == "leaky_smoke":
        reason = f"烟雾接近 {line_name} 但主枪线存在漏缝风险"
    else:
        reason = f"烟雾未封住 {line_name}，落点接近不等于有效封线"
    return worst_score, [worst_label], [reason + f"（距离 {worst_distance:.1f}）"]


def evaluate_smoke_risk(
    smoke_event: SmokeEvent,
    smoke_target: SmokeTarget | None,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget],
    quality_labels: list[str],
) -> tuple[float, float, float, list[str], list[str]]:
    labels = []
    reasons = []
    penalty = 0.0
    dependency = teammate_dependency_score(smoke_event, smoke_target, round_context)
    exploitation = enemy_exploitation_score(smoke_event, round_context)

    if "leaky_smoke" in quality_labels:
        if dependency > 0:
            penalty += get_weight("smoke_impact.false_confidence_penalty", -1.0)
            labels.append("false_confidence_smoke")
            reasons.append("队友依赖这颗漏缝烟行动，存在错误安全感")
        if exploitation > 0:
            penalty += get_weight("smoke_impact.fatal_leak_penalty", -2.0)
            labels.append("fatal_leaky_smoke")
            reasons.append("漏缝烟被敌人利用，队友在错误安全感下被缝隙击杀/抽死")
    return dependency, exploitation, penalty, labels, reasons


def evaluate_teammate_blocking(
    smoke_event: SmokeEvent,
    smoke_target: SmokeTarget | None,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget],
) -> tuple[float, list[str], list[str]]:
    if smoke_target is None:
        return 0.0, [], []
    lines = smoke_target.teammate_block_lines or []
    for line in lines:
        p1, p2 = line_points(line, smoke_target)
        if p1 is None or p2 is None:
            continue
        distance = point_to_segment_distance(smoke_event.position[0], smoke_event.position[1], p1, p2)
        if distance <= smoke_target.smoke_radius and teammate_dependency_score(smoke_event, smoke_target, round_context) > 0:
            return (
                get_weight("smoke_impact.blocking_teammate_penalty", -0.8),
                ["blocking_teammate_smoke"],
                ["烟雾覆盖己方关键路线或补枪线，影响队友清点/补枪"],
            )
    return 0.0, [], []


def score_smoke_conversion(
    smoke_event: SmokeEvent,
    smoke_target: SmokeTarget | None,
    intent: str,
    block_score: float,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget],
) -> tuple[float, list[str], list[str]]:
    if smoke_target is None or block_score < 0.6 or not team_action_uses_this_smoke(smoke_event, smoke_target, round_context):
        return 0.0, [], ["战术转化未通过 gating：烟雾未匹配目标、封线质量不足，或队友没有使用这颗烟"]
    if intent not in {"execute_smoke", "cross_smoke", "isolation_smoke"}:
        return 0.0, [], ["非 execute/cross/isolation 烟不吃进点/下包转化分"]

    score = 0.0
    reasons = []
    if has_friendly_entry(smoke_event, smoke_target, round_context):
        score += get_weight("smoke_impact.site_entry_success", 0.4)
        reasons.append("烟雾质量达标且队友利用该烟完成进点")
    if has_bomb_plant_after(smoke_event, round_context):
        score += get_weight("smoke_impact.bomb_planted", 0.5)
        reasons.append("烟雾质量达标且与下包路径相关，允许计入下包转化")
    if score > 0:
        return score, ["converted_execute_smoke"], reasons
    return 0.0, [], []


def score_fake_smoke(
    smoke_event: SmokeEvent,
    round_context: RoundContext,
    map_knowledge: dict[str, SmokeTarget],
) -> tuple[float, list[str], list[str]]:
    rotation = enemy_rotation_triggered(smoke_event, round_context)
    success_elsewhere = real_execute_success_elsewhere(smoke_event, round_context)
    if rotation and success_elsewhere:
        return (
            get_weight("smoke_impact.fake_rotation_score", 0.6) + get_weight("smoke_impact.fake_success_score", 0.8),
            ["successful_fake_smoke"],
            ["该烟没有直接用于进点，但诱发防守转点，帮助另一侧完成进攻"],
        )
    if rotation:
        return (
            get_weight("smoke_impact.fake_rotation_score", 0.6),
            ["successful_fake_smoke"],
            ["该烟诱发防守注意力转移"],
        )
    return (
        get_weight("smoke_impact.unconverted_fake_score", 0.1),
        ["unconverted_fake_smoke"],
        ["假打烟未观察到明确防守反应或另一侧收益"],
    )


def teammate_dependency_score(
    smoke_event: SmokeEvent,
    smoke_target: SmokeTarget | None,
    round_context: RoundContext,
) -> float:
    thrower_team = get_player_team(smoke_event.thrower, round_context)
    if thrower_team == "unknown":
        return 0.0
    window = get_weight("smoke_impact.dependency_window_seconds", 5.0)
    count = 0
    for tick in round_context.ticks:
        if not 0 <= tick.round_seconds - smoke_event.start_tick <= window:
            continue
        for player in tick.players_info:
            name = player.get("name")
            if not name or name == smoke_event.thrower or get_player_team(name, round_context) != thrower_team:
                continue
            pos = player_position(player)
            if pos is None:
                continue
            if calculate_distance_2d(pos[0], pos[1], smoke_event.position[0], smoke_event.position[1]) <= 650:
                count += 1
                break
            if smoke_target and calculate_distance_2d(pos[0], pos[1], smoke_target.target_center[0], smoke_target.target_center[1]) <= 650:
                count += 1
                break
    if has_bomb_plant_after(smoke_event, round_context):
        count += 1
    return clamp(count / 3.0, 0.0, 1.0)


def enemy_exploitation_score(smoke_event: SmokeEvent, round_context: RoundContext) -> float:
    thrower_team = get_player_team(smoke_event.thrower, round_context)
    if thrower_team == "unknown":
        return 0.0
    window = get_weight("smoke_impact.dependency_window_seconds", 5.0)
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if not 0 <= event.tick - smoke_event.start_tick <= window:
            continue
        if get_player_team(event.player, round_context) == thrower_team:
            continue
        if get_player_team(event.other_player or "", round_context) != thrower_team:
            continue
        if event.through_smoke:
            return 1.0
    return 0.0


def team_action_uses_this_smoke(
    smoke_event: SmokeEvent,
    smoke_target: SmokeTarget,
    round_context: RoundContext,
) -> bool:
    return (
        teammate_dependency_score(smoke_event, smoke_target, round_context) > 0
        or has_bomb_plant_after(smoke_event, round_context)
        or has_friendly_entry(smoke_event, smoke_target, round_context)
    )


def has_friendly_entry(smoke_event: SmokeEvent, smoke_target: SmokeTarget, round_context: RoundContext) -> bool:
    thrower_team = get_player_team(smoke_event.thrower, round_context)
    window = get_weight("smoke_impact.conversion_window_seconds", 8.0)
    for tick in round_context.ticks:
        if not 0 <= tick.round_seconds - smoke_event.start_tick <= window:
            continue
        near = 0
        for player in tick.players_info:
            name = player.get("name")
            if not name or get_player_team(name, round_context) != thrower_team:
                continue
            pos = player_position(player)
            if pos and calculate_distance_2d(pos[0], pos[1], smoke_target.target_center[0], smoke_target.target_center[1]) <= 750:
                near += 1
        if near >= 2:
            return True
    return False


def has_bomb_plant_after(smoke_event: SmokeEvent, round_context: RoundContext) -> bool:
    window = get_weight("smoke_impact.conversion_window_seconds", 8.0)
    if round_context.bomb_planted_time is not None:
        return 0 <= round_context.bomb_planted_time - smoke_event.start_tick <= window
    return any(
        tick.is_bomb_planted and 0 <= tick.round_seconds - smoke_event.start_tick <= window
        for tick in round_context.ticks
    )


def has_nearby_team_action(smoke_event: SmokeEvent, round_context: RoundContext) -> bool:
    return teammate_dependency_score(smoke_event, None, round_context) > 0


def looks_like_fake(smoke_event: SmokeEvent, round_context: RoundContext) -> bool:
    thrower_team = get_player_team(smoke_event.thrower, round_context)
    if thrower_team != "team2" and not (thrower_team == "team1" and not round_context.team1_on_ct):
        return False
    first = nearest_tick(round_context.ticks, smoke_event.start_tick)
    later = nearest_tick(round_context.ticks, smoke_event.start_tick + 10.0)
    if first is None or later is None:
        return False
    bomb_start = bomb_xy(first)
    bomb_later = bomb_xy(later)
    if bomb_start is None or bomb_later is None:
        return False
    return calculate_distance_2d(bomb_start[0], bomb_start[1], bomb_later[0], bomb_later[1]) >= 1200


def enemy_rotation_triggered(smoke_event: SmokeEvent, round_context: RoundContext) -> bool:
    thrower_team = get_player_team(smoke_event.thrower, round_context)
    enemy_team = "team1" if thrower_team == "team2" else "team2"
    before = nearest_tick(round_context.ticks, smoke_event.start_tick)
    after = nearest_tick(round_context.ticks, smoke_event.start_tick + 8.0)
    if before is None or after is None:
        return False
    moved = 0
    for player in after.players_info:
        name = player.get("name")
        if not name or get_player_team(name, round_context) != enemy_team:
            continue
        before_info = player_info_at_tick(before, name)
        p1 = player_position(before_info)
        p2 = player_position(player)
        if p1 and p2 and calculate_distance_2d(p1[0], p1[1], p2[0], p2[1]) >= 650:
            moved += 1
    return moved >= 1


def real_execute_success_elsewhere(smoke_event: SmokeEvent, round_context: RoundContext) -> bool:
    return has_bomb_plant_after(smoke_event, round_context) or any(
        event.event_type == EventType.KILL
        and 5.0 <= event.tick - smoke_event.start_tick <= get_weight("smoke_impact.fake_window_seconds", 20.0)
        and get_player_team(event.player, round_context) == get_player_team(smoke_event.thrower, round_context)
        for event in round_context.events
    )


def line_points(
    line: dict[str, Any],
    smoke_target: SmokeTarget,
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    p1 = coerce_xy(line.get("from_xy"))
    p2 = coerce_xy(line.get("to_xy"))
    if p1 is not None and p2 is not None:
        return p1, p2
    return None, None


def point_to_segment_distance(
    px: float,
    py: float,
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return calculate_distance_2d(px, py, ax, ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = clamp(t, 0.0, 1.0)
    return calculate_distance_2d(px, py, ax + t * dx, ay + t * dy)


def get_player_team(player_name: str, round_context: RoundContext) -> str:
    if player_name in round_context.team1_players:
        return "team1"
    if player_name in round_context.team2_players:
        return "team2"
    return "unknown"


def find_player_info_before(
    ticks: list[PredictionTick],
    player_name: str,
    target_time: float,
) -> dict[str, Any] | None:
    candidates = [tick for tick in ticks if 0 <= target_time - tick.round_seconds <= 3.0]
    candidates.sort(key=lambda item: item.round_seconds, reverse=True)
    for tick in candidates:
        info = player_info_at_tick(tick, player_name)
        if info is not None:
            return info
    return None


def find_player_info_after(
    ticks: list[PredictionTick],
    player_name: str,
    target_time: float,
) -> dict[str, Any] | None:
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


def nearest_tick(ticks: list[PredictionTick], target_time: float) -> PredictionTick | None:
    if not ticks:
        return None
    return min(ticks, key=lambda item: abs(item.round_seconds - target_time))


def bomb_xy(tick: PredictionTick) -> tuple[float, float] | None:
    position = coerce_position(tick.bomb_position)
    if position is not None:
        return position[0], position[1]
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
