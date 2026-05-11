"""Rule-based flashbang impact scoring."""

from dataclasses import dataclass, field
from typing import Any

from .align import calculate_distance_2d, safe_float
from .config import FLASH_THRESHOLDS, get_weight
from .models import EventType, FlashImpact, GameEvent, PredictionTick, RoundContext


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_effective_blind(
    flash_duration: float,
    flash_max_alpha: float | None,
) -> float:
    if flash_max_alpha is not None:
        flash_strength = clamp(safe_float(flash_max_alpha) / 255.0, 0.0, 1.0)
        return safe_float(flash_duration) * flash_strength
    return safe_float(flash_duration)


def shortest_angle_delta(yaw_before: float, yaw_after: float) -> float:
    delta = (safe_float(yaw_after) - safe_float(yaw_before) + 180.0) % 360.0 - 180.0
    return abs(delta)


@dataclass
class FlashExposure:
    player: str
    team: str
    start_tick: float
    end_tick: float
    peak_tick: float
    effective_blind: float
    flash_duration: float
    flash_max_alpha: float | None
    yaw_before: float | None = None
    yaw_after: float | None = None
    distance_moved: float | None = None
    start_info: dict[str, Any] = field(default_factory=dict)
    peak_info: dict[str, Any] = field(default_factory=dict)


def blind_label(effective_blind: float) -> str:
    thresholds = get_weight("flash_impact.thresholds", FLASH_THRESHOLDS)
    if effective_blind < thresholds.get("ignore", 0.7):
        return "weak_flash"
    if effective_blind < thresholds.get("minor", 1.5):
        return "minor_flash"
    if effective_blind < thresholds.get("partial", 2.8):
        return "partial_blind"
    if effective_blind < thresholds.get("strong", 3.5):
        return "strong_blind"
    return "full_blind"


def flash_blind_phrase(effective_blind: float) -> str:
    label = blind_label(effective_blind)
    if label == "weak_flash":
        return "轻微擦白"
    if label == "minor_flash":
        return "轻微影响"
    if label == "partial_blind":
        return "半白/视野受损"
    if label == "strong_blind":
        return "强白"
    return "高质量全白"


def score_enemy_flash(
    thrower: str,
    round_id: int,
    tick: float,
    affected_player: str,
    effective_blind: float,
    converted_kills: list[dict[str, Any]] | None = None,
    forced_turn: bool = False,
    strong_forced_turn: bool = False,
    forced_turn_kill: bool = False,
    forced_position: bool = False,
    trade_flash: bool = False,
    entry_flash: bool = False,
    plant_support_flash: bool = False,
) -> FlashImpact:
    labels = [blind_label(effective_blind)]
    reasons = [f"{affected_player} {effective_blind:.1f}s {flash_blind_phrase(effective_blind)}"]
    converted_kills = converted_kills or []
    score = 0.0

    if forced_turn:
        labels.append("forced_turn")
        score += 0.4
    if strong_forced_turn:
        labels.append("strong_forced_turn")
        score += 0.2
    if forced_position:
        labels.append("forced_position")
        score += 0.3
    if forced_turn_kill:
        labels.append("forced_turn_kill")
        score += 0.8 if not strong_forced_turn else 1.0

    if converted_kills:
        labels.append("converted_flash")
    if trade_flash:
        labels.append("trade_flash")
    if entry_flash:
        labels.append("entry_flash")
    if plant_support_flash:
        labels.append("plant_support_flash")

    label = labels[0]
    if label == "weak_flash":
        if not any(l in labels for l in ("forced_turn", "forced_position", "converted_flash")):
            labels.append("no_flash_effect")
            reasons.append("轻微白屏且没有后续收益")
    elif label == "minor_flash":
        if converted_kills or entry_flash or plant_support_flash or trade_flash:
            score += 0.3
        else:
            reasons.append("轻微影响但没有转化")
    elif label == "partial_blind":
        if converted_kills or entry_flash or plant_support_flash or trade_flash:
            score += 0.6
        else:
            score += 0.1
            reasons.append("半白/视野受损但没有明确转化")
    elif label == "strong_blind":
        labels.append("direct_blind")
        score += 0.8
        if converted_kills:
            score += 0.8
    else:
        labels.append("direct_blind")
        score += 1.0
        if converted_kills:
            score += 1.0

    return FlashImpact(
        thrower=thrower,
        round_id=round_id,
        tick=tick,
        score=score,
        labels=_dedupe(labels),
        affected_enemies=[{
            "player": affected_player,
            "effective_blind": round(effective_blind, 3),
            "label": label,
        }],
        affected_teammates=[],
        converted_kills=converted_kills,
        reasons=reasons,
    )


def score_team_flash(
    thrower: str,
    round_id: int,
    tick: float,
    affected_player: str,
    effective_blind: float,
    friendly_kill_within_3s: bool = False,
    friendly_entry_or_trade_or_plant_within_window: bool = False,
    teammate_died_while_flashed: bool = False,
    teammate_active: bool = False,
    missed_trade_or_stopped_push: bool = False,
    converted_kills: list[dict[str, Any]] | None = None,
) -> FlashImpact:
    labels = [blind_label(effective_blind)]
    reasons = [f"队友 {affected_player} {effective_blind:.1f}s {flash_blind_phrase(effective_blind)}"]
    converted_kills = converted_kills or []
    score = 0.0

    if effective_blind < FLASH_THRESHOLDS["ignore"]:
        labels.append("harmless_team_flash")
    elif effective_blind < FLASH_THRESHOLDS["partial"] and friendly_kill_within_3s:
        labels.extend(["team_flash_with_conversion", "effective_team_flash"])
        score += 0.3
    elif effective_blind < FLASH_THRESHOLDS["partial"] and friendly_entry_or_trade_or_plant_within_window:
        labels.append("effective_team_flash")
        score += 0.2
    elif effective_blind < FLASH_THRESHOLDS["partial"] and (missed_trade_or_stopped_push or teammate_died_while_flashed):
        labels.append("harmful_team_flash")
        score -= 0.5 if teammate_died_while_flashed else 0.3
    elif effective_blind < FLASH_THRESHOLDS["partial"]:
        labels.append("harmless_team_flash")
    else:
        if teammate_died_while_flashed or teammate_active:
            labels.append("severe_team_flash")
            score -= 1.5 if teammate_died_while_flashed else 1.0
        else:
            labels.append("harmful_team_flash")
            score -= 0.6

        if friendly_kill_within_3s:
            score += 0.4
            if "severe_team_flash" in labels and not teammate_died_while_flashed:
                labels.remove("severe_team_flash")
                labels.append("harmful_team_flash")
            labels.append("team_flash_with_conversion")

    return FlashImpact(
        thrower=thrower,
        round_id=round_id,
        tick=tick,
        score=score,
        labels=_dedupe(labels),
        affected_enemies=[],
        affected_teammates=[{
            "player": affected_player,
            "effective_blind": round(effective_blind, 3),
            "label": labels[0],
        }],
        converted_kills=converted_kills,
        reasons=reasons,
    )


def detect_forced_turn(
    effective_blind: float,
    yaw_before: float | None,
    yaw_after: float | None,
) -> tuple[bool, bool, float | None]:
    if effective_blind >= FLASH_THRESHOLDS["ignore"]:
        return False, False, None
    if yaw_before is None or yaw_after is None:
        return False, False, None

    yaw_delta = shortest_angle_delta(yaw_before, yaw_after)
    forced_yaw = get_weight("flash_impact.forced_turn_yaw", 80.0)
    strong_yaw = get_weight("flash_impact.strong_forced_turn_yaw", 120.0)
    return yaw_delta >= forced_yaw, yaw_delta >= strong_yaw, yaw_delta


def calculate_player_flash_impact(
    player_name: str,
    round_context: RoundContext,
) -> tuple[float, list[FlashImpact]]:
    exposures = collect_flash_exposures(round_context)
    attributed = attribute_flash_exposures(player_name, exposures, round_context)
    flash_events: list[FlashImpact] = []

    for exposure in attributed:
        converted = find_converted_kills(exposure, player_name, round_context)
        friendly_conversion = bool(find_friendly_kills(exposure, player_name, round_context))
        plant_support = has_plant_support(exposure, player_name, round_context)
        is_enemy = get_player_team(exposure.player, round_context) != get_player_team(player_name, round_context)

        if is_enemy:
            forced, strong_forced, _ = detect_forced_turn(
                exposure.effective_blind,
                exposure.yaw_before,
                exposure.yaw_after,
            )
            forced_position = (
                exposure.effective_blind < FLASH_THRESHOLDS["ignore"]
                and exposure.distance_moved is not None
                and exposure.distance_moved >= get_weight("flash_impact.forced_position_distance", 250.0)
            )
            impact = score_enemy_flash(
                thrower=player_name,
                round_id=round_context.round_id,
                tick=exposure.peak_tick,
                affected_player=exposure.player,
                effective_blind=exposure.effective_blind,
                converted_kills=converted,
                forced_turn=forced,
                strong_forced_turn=strong_forced,
                forced_turn_kill=bool(converted and forced),
                forced_position=forced_position,
                trade_flash=any(k.get("trade") for k in converted),
                entry_flash=False,
                plant_support_flash=plant_support,
            )
        else:
            teammate_died = any(
                e.event_type == EventType.DEATH
                and e.player == exposure.player
                and 0 <= e.tick - exposure.start_tick <= get_weight("flash_impact.conversion_window_seconds", 3.0)
                for e in round_context.events
            )
            impact = score_team_flash(
                thrower=player_name,
                round_id=round_context.round_id,
                tick=exposure.peak_tick,
                affected_player=exposure.player,
                effective_blind=exposure.effective_blind,
                friendly_kill_within_3s=friendly_conversion,
                friendly_entry_or_trade_or_plant_within_window=plant_support,
                teammate_died_while_flashed=teammate_died,
                teammate_active=teammate_died,
                converted_kills=find_friendly_kills(exposure, player_name, round_context),
            )
        flash_events.append(impact)

    merged = merge_flash_impacts(player_name, round_context.round_id, flash_events)
    return sum(f.score for f in merged), merged


def collect_flash_exposures(round_context: RoundContext) -> list[FlashExposure]:
    by_player: dict[str, list[tuple[PredictionTick, dict[str, Any], float]]] = {}
    for tick in sorted(round_context.ticks, key=lambda t: t.round_seconds):
        for player in tick.players_info:
            name = player.get("name")
            if not name:
                continue
            duration = safe_float(player.get("flash_duration"), 0.0)
            alpha = player.get("flash_max_alpha")
            alpha_value = None if alpha is None else safe_float(alpha)
            effective = compute_effective_blind(duration, alpha_value)
            if duration > 0 or effective > 0:
                by_player.setdefault(name, []).append((tick, player, effective))

    exposures: list[FlashExposure] = []
    for name, rows in by_player.items():
        current: list[tuple[PredictionTick, dict[str, Any], float]] = []
        previous_time: float | None = None
        for row in rows:
            tick_time = row[0].round_seconds
            if current and previous_time is not None and tick_time - previous_time > 1.0:
                exposures.append(build_exposure(name, current, round_context))
                current = []
            current.append(row)
            previous_time = tick_time
        if current:
            exposures.append(build_exposure(name, current, round_context))
    return exposures


def build_exposure(
    player_name: str,
    rows: list[tuple[PredictionTick, dict[str, Any], float]],
    round_context: RoundContext,
) -> FlashExposure:
    peak_tick, peak_info, peak_effective = max(rows, key=lambda r: r[2])
    start_tick, start_info, _ = rows[0]
    end_tick, end_info, _ = rows[-1]
    before_info = find_player_info_before(round_context.ticks, player_name, start_tick.round_seconds)
    after_info = find_player_info_after(round_context.ticks, player_name, start_tick.round_seconds)
    start_pos = position_tuple(start_info)
    after_pos = position_tuple(after_info)
    distance = None
    if start_pos is not None and after_pos is not None:
        distance = calculate_distance_2d(start_pos[0], start_pos[1], after_pos[0], after_pos[1])
    return FlashExposure(
        player=player_name,
        team=get_player_team(player_name, round_context),
        start_tick=start_tick.round_seconds,
        end_tick=end_tick.round_seconds,
        peak_tick=peak_tick.round_seconds,
        effective_blind=peak_effective,
        flash_duration=safe_float(peak_info.get("flash_duration")),
        flash_max_alpha=None if peak_info.get("flash_max_alpha") is None else safe_float(peak_info.get("flash_max_alpha")),
        yaw_before=None if before_info is None or before_info.get("yaw") is None else safe_float(before_info.get("yaw")),
        yaw_after=None if after_info is None or after_info.get("yaw") is None else safe_float(after_info.get("yaw")),
        distance_moved=distance,
        start_info=start_info,
        peak_info=peak_info,
    )


def attribute_flash_exposures(
    player_name: str,
    exposures: list[FlashExposure],
    round_context: RoundContext,
) -> list[FlashExposure]:
    result: list[FlashExposure] = []
    for exposure in exposures:
        if assisted_flash_attributes(player_name, exposure, round_context):
            result.append(exposure)
            continue
        if inventory_throw_attributes(player_name, exposure, round_context):
            result.append(exposure)
    return result


def assisted_flash_attributes(
    player_name: str,
    exposure: FlashExposure,
    round_context: RoundContext,
) -> bool:
    window = get_weight("flash_impact.conversion_window_seconds", 3.0)
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if not event.assisted_flash or event.assister != player_name:
            continue
        if event.other_player != exposure.player:
            continue
        if 0 <= event.tick - exposure.start_tick <= window:
            return True
    return False


def inventory_throw_attributes(
    player_name: str,
    exposure: FlashExposure,
    round_context: RoundContext,
) -> bool:
    throw_times = infer_flash_throw_times(round_context)
    candidates = [
        t for t in throw_times.get(player_name, [])
        if 0 <= exposure.start_tick - t <= get_weight("flash_impact.conversion_window_seconds", 3.0)
    ]
    if not candidates:
        return False
    other_candidates = 0
    for other, times in throw_times.items():
        if other == player_name:
            continue
        other_candidates += sum(
            1 for t in times
            if 0 <= exposure.start_tick - t <= get_weight("flash_impact.conversion_window_seconds", 3.0)
        )
    return other_candidates == 0


def infer_flash_throw_times(round_context: RoundContext) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    previous_counts: dict[str, int] = {}
    for tick in sorted(round_context.ticks, key=lambda t: t.round_seconds):
        for player in tick.players_info:
            name = player.get("name")
            if not name:
                continue
            count = flash_inventory_count(player.get("inventory"))
            previous = previous_counts.get(name)
            if previous is not None and count < previous:
                result.setdefault(name, []).append(tick.round_seconds)
            previous_counts[name] = count
    return result


def flash_inventory_count(inventory: Any) -> int:
    if not isinstance(inventory, list):
        return 0
    return sum(1 for item in inventory if "flash" in str(item).lower())


def find_converted_kills(
    exposure: FlashExposure,
    thrower: str,
    round_context: RoundContext,
) -> list[dict[str, Any]]:
    window = get_weight("flash_impact.conversion_window_seconds", 3.0)
    converted = []
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if event.other_player != exposure.player:
            continue
        if get_player_team(event.player, round_context) != get_player_team(thrower, round_context):
            continue
        if 0 <= event.tick - exposure.start_tick <= window:
            converted.append({
                "killer": event.player,
                "victim": event.other_player,
                "tick": event.tick,
                "trade": is_trade_kill_event(event, round_context),
            })
    return converted


def find_friendly_kills(
    exposure: FlashExposure,
    thrower: str,
    round_context: RoundContext,
) -> list[dict[str, Any]]:
    window = get_weight("flash_impact.conversion_window_seconds", 3.0)
    friendly_team = get_player_team(thrower, round_context)
    kills = []
    for event in round_context.events:
        if event.event_type != EventType.KILL:
            continue
        if get_player_team(event.player, round_context) != friendly_team:
            continue
        if 0 <= event.tick - exposure.start_tick <= window:
            kills.append({"killer": event.player, "victim": event.other_player, "tick": event.tick})
    return kills


def has_plant_support(exposure: FlashExposure, thrower: str, round_context: RoundContext) -> bool:
    window = get_weight("flash_impact.plant_support_window_seconds", 5.0)
    thrower_team = get_player_team(thrower, round_context)
    for event in round_context.events:
        if event.event_type != EventType.BOMB_PLANT:
            continue
        if get_player_team(event.player, round_context) == thrower_team or event.player == "unknown":
            if 0 <= event.tick - exposure.start_tick <= window:
                return True
    return False


def is_trade_kill_event(kill: GameEvent, round_context: RoundContext) -> bool:
    for event in round_context.events:
        if event.event_type != EventType.DEATH:
            continue
        if event.player == kill.player:
            continue
        if get_player_team(event.player, round_context) != get_player_team(kill.player, round_context):
            continue
        if event.other_player == kill.other_player and 0 < kill.tick - event.tick <= 5.0:
            return True
    return False


def merge_flash_impacts(
    thrower: str,
    round_id: int,
    impacts: list[FlashImpact],
) -> list[FlashImpact]:
    if not impacts:
        return []
    groups: list[list[FlashImpact]] = []
    for impact in sorted(impacts, key=lambda item: item.tick):
        if not groups or impact.tick - groups[-1][0].tick > 1.0:
            groups.append([impact])
        else:
            groups[-1].append(impact)

    return [
        merge_flash_impact_group(thrower, round_id, group)
        for group in groups
    ]


def merge_flash_impact_group(
    thrower: str,
    round_id: int,
    impacts: list[FlashImpact],
) -> FlashImpact:
    enemy_score = sum(i.score for i in impacts if i.affected_enemies)
    team_score = sum(i.score for i in impacts if i.affected_teammates)
    max_enemy = get_weight("flash_impact.max_enemy_flash_score_per_flash", 3.0)
    min_team = get_weight("flash_impact.min_team_flash_score_per_flash", -3.0)
    total_score = clamp(enemy_score, 0.0, max_enemy) + max(team_score, min_team)
    labels: list[str] = []
    enemies: list[dict[str, Any]] = []
    teammates: list[dict[str, Any]] = []
    converted: list[dict[str, Any]] = []
    reasons: list[str] = []
    for impact in impacts:
        labels.extend(impact.labels)
        enemies.extend(impact.affected_enemies)
        teammates.extend(impact.affected_teammates)
        converted.extend(impact.converted_kills)
        reasons.extend(impact.reasons)
    return FlashImpact(
        thrower=thrower,
        round_id=round_id,
        tick=min(i.tick for i in impacts),
        score=total_score,
        labels=_dedupe(labels),
        affected_enemies=enemies,
        affected_teammates=teammates,
        converted_kills=converted,
        reasons=_dedupe(reasons),
    )


def get_player_team(player_name: str, round_context: RoundContext) -> str:
    if player_name in round_context.team1_players:
        return "team1"
    if player_name in round_context.team2_players:
        return "team2"
    for tick in round_context.ticks:
        for player in tick.players_info:
            if player.get("name") == player_name:
                team_num = player.get("team_num")
                if team_num == "CT":
                    return "team1" if round_context.team1_on_ct else "team2"
                if team_num == "T":
                    return "team2" if round_context.team1_on_ct else "team1"
    return "unknown"


def find_player_info_before(
    ticks: list[PredictionTick],
    player_name: str,
    target_time: float,
) -> dict[str, Any] | None:
    before = [
        t for t in ticks
        if 0 < target_time - t.round_seconds <= get_weight("flash_impact.forced_turn_window_seconds", 0.8)
    ]
    before.sort(key=lambda t: t.round_seconds, reverse=True)
    for tick in before:
        info = player_info_at_tick(tick, player_name)
        if info is not None:
            return info
    return None


def find_player_info_after(
    ticks: list[PredictionTick],
    player_name: str,
    target_time: float,
) -> dict[str, Any] | None:
    after = [
        t for t in ticks
        if 0 < t.round_seconds - target_time <= get_weight("flash_impact.forced_position_window_seconds", 2.0)
    ]
    after.sort(key=lambda t: t.round_seconds)
    for tick in after:
        info = player_info_at_tick(tick, player_name)
        if info is not None:
            return info
    return None


def player_info_at_tick(tick: PredictionTick, player_name: str) -> dict[str, Any] | None:
    for player in tick.players_info:
        if player.get("name") == player_name:
            return player
    return None


def position_tuple(player_info: dict[str, Any] | None) -> tuple[float, float, float] | None:
    if player_info is None:
        return None
    try:
        return (
            float(player_info["X"]),
            float(player_info["Y"]),
            float(player_info.get("Z", 0.0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _dedupe(items: list[Any]) -> list[Any]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
