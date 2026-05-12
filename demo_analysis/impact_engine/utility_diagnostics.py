"""Diagnostics for utility scoring data availability and attribution."""

from collections import Counter
from typing import Any

from .align import safe_float
from .models import EventType, PlayerMatchImpact, RoundContext
from .utility_fire import collect_fire_events, is_fire_weapon
from .utility_flash import attribute_flash_exposures, collect_flash_exposures
from .utility_he import collect_he_events, is_he_weapon
from .utility_smoke import collect_smoke_events, load_smoke_targets, match_smoke_target


INT_KEYS = [
    "total_flash_exposures",
    "attributed_flash_events",
    "unknown_flash_thrower_count",
    "total_smoke_events",
    "attributed_smoke_events",
    "unknown_smoke_thrower_count",
    "total_fire_events",
    "attributed_fire_events",
    "unknown_fire_thrower_count",
    "total_he_events",
    "attributed_he_events",
    "unknown_he_thrower_count",
    "raw_future_damage_entries",
    "unique_damage_events_after_dedup",
    "duplicate_damage_events_removed",
    "total_future_damage_entries",
    "damage_events_found",
    "he_damage_events_found",
    "fire_damage_events_found",
    "he_candidate_events_from_damage",
    "he_candidate_events_from_projectiles",
    "model_impact_clip_count_min",
    "model_impact_clip_count_max",
    "rating_zero_count",
    "rating_hundred_count",
]

DICT_KEYS = [
    "smoke_target_match_counts",
    "fire_attribution_method_counts",
    "round_event_type_counts",
]

LIST_KEYS = [
    "possible_overmatched_smoke_targets",
    "fire_projectile_type_values",
    "fire_entity_grenade_type_values",
    "fire_damage_weapon_values",
    "he_projectile_type_values",
    "he_entity_grenade_type_values",
    "he_damage_weapon_values",
    "damage_weapon_values",
    "projectile_type_values",
    "entity_grenade_type_values",
]


def empty_utility_diagnostics() -> dict[str, Any]:
    diagnostics: dict[str, Any] = {key: 0 for key in INT_KEYS}
    diagnostics.update({key: {} for key in DICT_KEYS})
    diagnostics.update({key: [] for key in LIST_KEYS})
    return diagnostics


def build_round_utility_diagnostics(
    round_context: RoundContext,
    players: list[str],
) -> dict[str, Any]:
    diagnostics = empty_utility_diagnostics()

    flash_exposures = collect_flash_exposures(round_context)
    attributed_flash_keys = set()
    for player in players:
        for exposure in attribute_flash_exposures(player, flash_exposures, round_context):
            attributed_flash_keys.add((exposure.player, exposure.start_tick, exposure.end_tick, exposure.peak_tick))
    diagnostics["total_flash_exposures"] = len(flash_exposures)
    diagnostics["attributed_flash_events"] = len(attributed_flash_keys)
    diagnostics["unknown_flash_thrower_count"] = max(0, len(flash_exposures) - len(attributed_flash_keys))

    smoke_events = collect_smoke_events(round_context)
    diagnostics["total_smoke_events"] = len(smoke_events)
    diagnostics["attributed_smoke_events"] = sum(1 for event in smoke_events if is_attributed(event.thrower, players))
    diagnostics["unknown_smoke_thrower_count"] = sum(1 for event in smoke_events if not is_attributed(event.thrower, players))
    smoke_match_counts = count_smoke_target_matches(round_context, smoke_events)
    diagnostics["smoke_target_match_counts"] = smoke_match_counts
    diagnostics["possible_overmatched_smoke_targets"] = find_overmatched_targets(smoke_match_counts, len(smoke_events))

    fire_events = collect_fire_events(round_context)
    diagnostics["total_fire_events"] = len(fire_events)
    diagnostics["attributed_fire_events"] = sum(1 for event in fire_events if is_attributed(event.thrower, players))
    diagnostics["unknown_fire_thrower_count"] = sum(1 for event in fire_events if not is_attributed(event.thrower, players))
    diagnostics["fire_attribution_method_counts"] = dict(Counter(getattr(event, "attribution_method", "unknown") for event in fire_events))

    he_events = collect_he_events(round_context)
    diagnostics["total_he_events"] = len(he_events)
    diagnostics["attributed_he_events"] = sum(1 for event in he_events if is_attributed(event.thrower, players))
    diagnostics["unknown_he_thrower_count"] = sum(1 for event in he_events if not is_attributed(event.thrower, players))

    diagnostics.update(count_damage_events(round_context))
    raw_entries = sum(len(tick.future_damage) for tick in round_context.ticks)
    diagnostics["raw_future_damage_entries"] = raw_entries
    damage_event_count = diagnostics.get("damage_events_found", 0)
    diagnostics["unique_damage_events_after_dedup"] = damage_event_count
    diagnostics["duplicate_damage_events_removed"] = max(0, raw_entries - damage_event_count)
    diagnostics["total_future_damage_entries"] = raw_entries
    diagnostics.update(collect_unique_field_values(round_context))
    diagnostics["round_event_type_counts"] = dict(Counter(event.event_type.value for event in round_context.events))
    diagnostics["he_candidate_events_from_damage"] = count_he_damage_sources(round_context)
    diagnostics["he_candidate_events_from_projectiles"] = count_he_projectile_sources(round_context)
    return diagnostics


def merge_utility_diagnostics(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = empty_utility_diagnostics()
    for source in (base, update):
        for key in INT_KEYS:
            merged[key] = int(merged.get(key, 0)) + int(source.get(key, 0) or 0)
        for key in DICT_KEYS:
            counter = Counter(merged.get(key, {}))
            counter.update(source.get(key, {}) or {})
            merged[key] = dict(counter)
        for key in LIST_KEYS:
            merged[key] = sorted(set(merged.get(key, [])) | set(source.get(key, []) or []))
    return merged


def add_score_extreme_diagnostics(
    diagnostics: dict[str, Any],
    players: list[PlayerMatchImpact],
) -> dict[str, Any]:
    updated = merge_utility_diagnostics(empty_utility_diagnostics(), diagnostics)
    updated["model_impact_clip_count_min"] = sum(
        1 for player in players
        if player.model_impact_score_raw < -50 and player.model_impact_score_clipped <= -50
    )
    updated["model_impact_clip_count_max"] = sum(
        1 for player in players
        if player.model_impact_score_raw > 50 and player.model_impact_score_clipped >= 50
    )
    return updated


def print_utility_diagnostics(diagnostics: dict[str, Any]) -> None:
    print("Utility diagnostics:")
    print(
        f"  Flash exposures: total={diagnostics.get('total_flash_exposures', 0)}, "
        f"attributed={diagnostics.get('attributed_flash_events', 0)}, "
        f"unknown={diagnostics.get('unknown_flash_thrower_count', 0)}"
    )
    print(
        f"  Smoke events: total={diagnostics.get('total_smoke_events', 0)}, "
        f"attributed={diagnostics.get('attributed_smoke_events', 0)}, "
        f"unknown={diagnostics.get('unknown_smoke_thrower_count', 0)}"
    )
    print(
        f"  Fire events: total={diagnostics.get('total_fire_events', 0)}, "
        f"attributed={diagnostics.get('attributed_fire_events', 0)}, "
        f"unknown={diagnostics.get('unknown_fire_thrower_count', 0)}"
    )
    print(
        f"  HE events: total={diagnostics.get('total_he_events', 0)}, "
        f"attributed={diagnostics.get('attributed_he_events', 0)}, "
        f"unknown={diagnostics.get('unknown_he_thrower_count', 0)}"
    )
    print(
        f"  Damage events: raw={diagnostics.get('raw_future_damage_entries', 0)}, "
        f"unique={diagnostics.get('unique_damage_events_after_dedup', 0)}, "
        f"removed={diagnostics.get('duplicate_damage_events_removed', 0)}, "
        f"HE={diagnostics.get('he_damage_events_found', 0)}, "
        f"fire={diagnostics.get('fire_damage_events_found', 0)}"
    )
    print(f"  Damage weapon values: {diagnostics.get('damage_weapon_values', [])}")
    print(f"  Projectile type values: {diagnostics.get('projectile_type_values', [])}")
    print(f"  Entity grenade type values: {diagnostics.get('entity_grenade_type_values', [])}")
    print(f"  Fire attribution methods: {diagnostics.get('fire_attribution_method_counts', {})}")
    print(
        "  HE candidates: "
        f"damage={diagnostics.get('he_candidate_events_from_damage', 0)}, "
        f"projectiles={diagnostics.get('he_candidate_events_from_projectiles', 0)}"
    )


def count_smoke_target_matches(round_context: RoundContext, smoke_events: list[Any]) -> dict[str, int]:
    targets = load_smoke_targets(round_context)
    counts: Counter[str] = Counter()
    if not targets:
        return {}
    for event in smoke_events:
        target = match_smoke_target(event, round_context, targets)
        if target is not None:
            counts[target.name] += 1
    return dict(counts)


def find_overmatched_targets(match_counts: dict[str, int], total_smoke_events: int) -> list[str]:
    threshold = max(5, int(total_smoke_events * 0.30))
    return sorted(target for target, count in match_counts.items() if count > threshold)


def is_attributed(thrower: str | None, players: list[str]) -> bool:
    return bool(thrower and thrower != "unknown" and thrower in players)


def count_damage_events(round_context: RoundContext) -> dict[str, int]:
    seen: set[tuple[float, str, str, str, int]] = set()
    he_total = 0
    fire_total = 0

    for tick_time, attacker, victim, weapon, damage in iter_damage_records(round_context):
        key = (round(tick_time, 3), attacker, victim, weapon, damage)
        if key in seen:
            continue
        seen.add(key)
        if is_he_weapon(weapon):
            he_total += 1
        if is_fire_weapon(weapon):
            fire_total += 1

    return {
        "damage_events_found": len(seen),
        "he_damage_events_found": he_total,
        "fire_damage_events_found": fire_total,
    }


def collect_unique_field_values(round_context: RoundContext) -> dict[str, Any]:
    projectile_types = sorted({
        str(projectile.get("type"))
        for tick in round_context.ticks
        for projectile in tick.projectiles
        if projectile.get("type") is not None
    })
    entity_types = sorted({
        str(grenade.get("type"))
        for tick in round_context.ticks
        for grenade in tick.entity_grenades
        if grenade.get("type") is not None
    })
    damage_weapons = sorted({
        weapon
        for _, _, _, weapon, _ in iter_damage_records(round_context)
        if weapon
    })
    return {
        "projectile_type_values": projectile_types,
        "entity_grenade_type_values": entity_types,
        "damage_weapon_values": damage_weapons,
        "fire_projectile_type_values": projectile_types,
        "fire_entity_grenade_type_values": entity_types,
        "fire_damage_weapon_values": [weapon for weapon in damage_weapons if is_fire_weapon(weapon)],
        "he_projectile_type_values": projectile_types,
        "he_entity_grenade_type_values": entity_types,
        "he_damage_weapon_values": [weapon for weapon in damage_weapons if is_he_weapon(weapon)],
    }


def count_he_damage_sources(round_context: RoundContext) -> int:
    return sum(1 for _, _, _, weapon, _ in iter_damage_records(round_context) if is_he_weapon(weapon))


def count_he_projectile_sources(round_context: RoundContext) -> int:
    projectile_count = sum(
        1
        for tick in round_context.ticks
        for projectile in tick.projectiles
        if is_he_weapon(projectile.get("type"))
    )
    entity_count = sum(
        1
        for tick in round_context.ticks
        for grenade in tick.entity_grenades
        if is_he_weapon(grenade.get("type") or grenade.get("name"))
    )
    return projectile_count + entity_count


def iter_damage_records(round_context: RoundContext) -> list[tuple[float, str, str, str, int]]:
    records: list[tuple[float, str, str, str, int]] = []
    for event in round_context.events:
        if event.event_type != EventType.DAMAGE:
            continue
        records.append((
            float(event.tick),
            str(event.player or ""),
            str(event.other_player or ""),
            str(event.weapon or ""),
            int(event.damage_health or 0),
        ))
    for tick in round_context.ticks:
        for damage in tick.future_damage:
            records.append((
                safe_float(damage.get("time") or damage.get("tick") or damage.get("round_seconds"), tick.round_seconds),
                str(damage.get("attacker_name") or damage.get("attacker") or damage.get("player") or ""),
                str(damage.get("victim_name") or damage.get("victim") or damage.get("user_name") or damage.get("other_player") or ""),
                str(damage.get("weapon") or ""),
                int(safe_float(damage.get("dmg_health") or damage.get("damage_health") or damage.get("damage"), 0)),
            ))
    return records
