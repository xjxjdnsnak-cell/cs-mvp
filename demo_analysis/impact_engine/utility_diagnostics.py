"""Utility diagnostics for CS2 Impact Engine.

Collects and reports diagnostics about utility data sources,
including projectiles, entity grenades, damage events, and fire attribution.
"""

from collections import Counter
from typing import Any

from .align import is_he_weapon, is_fire_weapon, _normalize_weapon_name, safe_float
from .models import EventType, GameEvent, PlayerMatchImpact, PredictionTick, RoundContext
from .utility_fire import collect_fire_events
from .utility_flash import attribute_flash_exposures, collect_flash_exposures
from .utility_he import collect_he_events
from .utility_smoke import collect_smoke_events, load_smoke_targets, match_smoke_target


INT_DIAGNOSTIC_KEYS = [
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
    "damage_events_found",
    "he_damage_events_found",
    "fire_damage_events_found",
    "he_candidate_events_from_damage",
    "he_candidate_events_from_projectiles",
    "he_candidate_events_from_kills",
    "model_impact_clip_count_min",
    "model_impact_clip_count_max",
    "rating_zero_count",
    "rating_hundred_count",
    "raw_future_damage_entries",
    "unique_damage_events_after_dedup",
    "duplicate_damage_events_removed",
    "damage_raw_count",
    "damage_dedup_count",
]
FLOAT_DIAGNOSTIC_KEYS = ["dedup_ratio"]

DICT_DIAGNOSTIC_KEYS = [
    "round_event_type_counts",
    "smoke_target_match_counts",
    "fire_attribution_method_counts",
]

LIST_DIAGNOSTIC_KEYS = [
    "possible_overmatched_smoke_targets",
    "fire_projectile_type_values",
    "fire_entity_grenade_type_values",
    "fire_damage_weapon_values",
    "he_projectile_type_values",
    "he_entity_grenade_type_values",
    "he_damage_weapon_values",
    "projectile_type_values",
    "entity_grenade_type_values",
    "damage_weapon_values",
]


def collect_round_diagnostics(round_context: RoundContext) -> dict[str, Any]:
    """Collect diagnostics for a single round from RoundContext."""
    diagnostics: dict[str, Any] = {
        "round_id": round_context.round_id,
        "total_ticks": len(round_context.ticks),
        "total_events": len(round_context.events),
        "event_type_counts": {},
        "projectile_type_values": set(),
        "entity_grenade_type_values": set(),
        "damage_weapon_values": set(),
        "fire_damage_weapon_values": set(),
        "he_damage_weapon_values": set(),
        "future_damage_count": 0,
        "future_kill_count": 0,
        "damage_events_found": 0,
        "fire_attribution_method_counts": {},
        "he_candidate_events_from_damage": 0,
        "he_candidate_events_from_projectiles": 0,
        "he_candidate_events_from_kills": 0,
        "he_projectile_type_values": set(),
        "he_entity_grenade_type_values": set(),
        "he_damage_weapon_values": set(),
        "fire_projectile_type_values": set(),
        "fire_entity_grenade_type_values": set(),
        "fire_damage_weapon_values": set(),
        "smoke_target_match_counts": {},
        "possible_overmatched_smoke_targets": [],
    }

    # Count event types from RoundContext.events
    for event in round_context.events:
        et = event.event_type.value
        diagnostics["event_type_counts"][et] = diagnostics["event_type_counts"].get(et, 0) + 1

    # Collect from ticks
    for tick in round_context.ticks:
        # Projectiles (from tick.projectiles directly)
        for p in tick.projectiles:
            ptype = p.get("type")
            if ptype:
                diagnostics["projectile_type_values"].add(str(ptype))
                if is_he_weapon(ptype):
                    diagnostics["he_projectile_type_values"].add(str(ptype))
                if is_fire_weapon(ptype):
                    diagnostics["fire_projectile_type_values"].add(str(ptype))

        # Entity grenades (from tick.entity_grenades directly)
        for eg in tick.entity_grenades:
            egtype = eg.get("type") or eg.get("grenade_type")
            if egtype:
                diagnostics["entity_grenade_type_values"].add(str(egtype))
                if is_he_weapon(egtype):
                    diagnostics["he_entity_grenade_type_values"].add(str(egtype))
                if is_fire_weapon(egtype):
                    diagnostics["fire_entity_grenade_type_values"].add(str(egtype))

        # Future damage
        future_damage = tick.future_damage
        diagnostics["future_damage_count"] += len(future_damage)
        for dmg in future_damage:
            weapon = dmg.get("weapon")
            if weapon:
                diagnostics["damage_weapon_values"].add(str(weapon))
                if is_fire_weapon(weapon):
                    diagnostics["fire_damage_weapon_values"].add(str(weapon))
                if is_he_weapon(weapon):
                    diagnostics["he_damage_weapon_values"].add(str(weapon))

        # Future kills
        future_kills = tick.future_kills
        diagnostics["future_kill_count"] += len(future_kills)

    # Count DAMAGE events from RoundContext.events and deduplicate with tick future_damage
    damage_events = [e for e in round_context.events if e.event_type == EventType.DAMAGE]
    diagnostics["damage_events_found"] = len(damage_events)

    # Check for HE candidates from damage events
    for event in damage_events:
        if is_he_weapon(event.weapon):
            diagnostics["he_candidate_events_from_damage"] += 1
        if is_fire_weapon(event.weapon):
            method = "damage_attacker"
            diagnostics["fire_attribution_method_counts"][method] = (
                diagnostics["fire_attribution_method_counts"].get(method, 0) + 1
            )

    # Check for HE candidates from future_kills in ticks
    for tick in round_context.ticks:
        for fk in tick.future_kills:
            if is_he_weapon(fk.get("weapon")):
                diagnostics["he_candidate_events_from_kills"] += 1

    # HE candidates from projectiles
    for tick in round_context.ticks:
        for p in tick.projectiles:
            if is_he_weapon(p.get("type")):
                diagnostics["he_candidate_events_from_projectiles"] += 1

    # Convert sets to sorted lists for JSON serialization
    diagnostics["projectile_type_values"] = sorted(diagnostics["projectile_type_values"])
    diagnostics["entity_grenade_type_values"] = sorted(diagnostics["entity_grenade_type_values"])
    diagnostics["damage_weapon_values"] = sorted(diagnostics["damage_weapon_values"])
    diagnostics["fire_damage_weapon_values"] = sorted(diagnostics["fire_damage_weapon_values"])
    diagnostics["he_damage_weapon_values"] = sorted(diagnostics["he_damage_weapon_values"])
    diagnostics["he_projectile_type_values"] = sorted(diagnostics["he_projectile_type_values"])
    diagnostics["he_entity_grenade_type_values"] = sorted(diagnostics["he_entity_grenade_type_values"])
    diagnostics["he_damage_weapon_values"] = sorted(diagnostics["he_damage_weapon_values"])
    diagnostics["fire_projectile_type_values"] = sorted(diagnostics["fire_projectile_type_values"])
    diagnostics["fire_entity_grenade_type_values"] = sorted(diagnostics["fire_entity_grenade_type_values"])
    diagnostics["fire_damage_weapon_values"] = sorted(diagnostics["fire_damage_weapon_values"])

    return diagnostics


def empty_utility_diagnostics() -> dict[str, Any]:
    """Return the flat diagnostics shape expected by ImpactEngine."""
    diagnostics: dict[str, Any] = {key: 0 for key in INT_DIAGNOSTIC_KEYS}
    diagnostics.update({key: 0.0 for key in FLOAT_DIAGNOSTIC_KEYS})
    diagnostics.update({key: {} for key in DICT_DIAGNOSTIC_KEYS})
    diagnostics.update({key: [] for key in LIST_DIAGNOSTIC_KEYS})
    return diagnostics


def build_round_utility_diagnostics(round_context: RoundContext, players: list[str]) -> dict[str, Any]:
    """Compatibility wrapper for the older flat per-round diagnostics API."""
    round_diag = collect_round_diagnostics(round_context)
    diagnostics = empty_utility_diagnostics()

    flash_exposures = collect_flash_exposures(round_context)
    attributed_flash_keys: set[tuple[Any, ...]] = set()
    for player in players:
        for exposure in attribute_flash_exposures(player, flash_exposures, round_context):
            attributed_flash_keys.add((exposure.player, exposure.start_tick, exposure.end_tick, exposure.peak_tick))
    diagnostics["total_flash_exposures"] = len(flash_exposures)
    diagnostics["attributed_flash_events"] = len(attributed_flash_keys)
    diagnostics["unknown_flash_thrower_count"] = max(0, len(flash_exposures) - len(attributed_flash_keys))

    smoke_events = collect_smoke_events(round_context)
    diagnostics["total_smoke_events"] = len(smoke_events)
    diagnostics["attributed_smoke_events"] = sum(1 for event in smoke_events if _is_attributed(event.thrower, players))
    diagnostics["unknown_smoke_thrower_count"] = sum(1 for event in smoke_events if not _is_attributed(event.thrower, players))

    smoke_targets = load_smoke_targets(round_context)
    smoke_match_counts: Counter[str] = Counter()
    for smoke in smoke_events:
        target = match_smoke_target(smoke, round_context, smoke_targets) if smoke_targets else None
        if target is not None:
            smoke_match_counts[target.name] += 1
    diagnostics["smoke_target_match_counts"] = dict(smoke_match_counts)
    overmatch_threshold = max(5, int(len(smoke_events) * 0.30))
    diagnostics["possible_overmatched_smoke_targets"] = sorted(
        target for target, count in smoke_match_counts.items() if count > overmatch_threshold
    )

    fire_events = collect_fire_events(round_context)
    diagnostics["total_fire_events"] = len(fire_events)
    diagnostics["attributed_fire_events"] = sum(1 for event in fire_events if _is_attributed(event.thrower, players))
    diagnostics["unknown_fire_thrower_count"] = sum(1 for event in fire_events if not _is_attributed(event.thrower, players))
    diagnostics["fire_attribution_method_counts"] = dict(
        Counter(getattr(event, "attribution_method", "unknown") for event in fire_events)
    )

    he_events = collect_he_events(round_context)
    diagnostics["total_he_events"] = len(he_events)
    diagnostics["attributed_he_events"] = sum(1 for event in he_events if _is_attributed(event.thrower, players))
    diagnostics["unknown_he_thrower_count"] = sum(1 for event in he_events if not _is_attributed(event.thrower, players))

    diagnostics["damage_events_found"] = round_diag["damage_events_found"]
    diagnostics["he_damage_events_found"] = _count_weapon_matches(round_context, is_he_weapon)
    diagnostics["fire_damage_events_found"] = _count_weapon_matches(round_context, is_fire_weapon)
    diagnostics["he_candidate_events_from_damage"] = diagnostics["he_damage_events_found"]
    diagnostics["he_candidate_events_from_projectiles"] = (
        round_diag["he_candidate_events_from_projectiles"] + len(round_diag["he_entity_grenade_type_values"])
    )
    diagnostics["he_candidate_events_from_kills"] = round_diag["he_candidate_events_from_kills"]
    diagnostics["round_event_type_counts"] = dict(round_diag["event_type_counts"])

    damage_stats = _damage_dedup_stats(round_context)
    diagnostics.update(damage_stats)
    diagnostics["damage_events_found"] = damage_stats["unique_damage_events_after_dedup"]

    diagnostics["damage_weapon_values"] = _damage_weapon_values(round_context)
    diagnostics["he_damage_weapon_values"] = [weapon for weapon in diagnostics["damage_weapon_values"] if is_he_weapon(weapon)]
    diagnostics["fire_damage_weapon_values"] = [weapon for weapon in diagnostics["damage_weapon_values"] if is_fire_weapon(weapon)]

    for key in LIST_DIAGNOSTIC_KEYS:
        if key in round_diag and not diagnostics.get(key):
            diagnostics[key] = list(round_diag[key])
    return diagnostics


def merge_utility_diagnostics(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge flat diagnostics dictionaries across rounds."""
    merged = empty_utility_diagnostics()
    for source in (base, update):
        for key in INT_DIAGNOSTIC_KEYS:
            merged[key] = int(merged.get(key, 0)) + int(source.get(key, 0) or 0)
        for key in FLOAT_DIAGNOSTIC_KEYS:
            merged[key] = float(merged.get(key, 0.0)) + float(source.get(key, 0.0) or 0.0)
        for key in DICT_DIAGNOSTIC_KEYS:
            counter = Counter(merged.get(key, {}))
            counter.update(source.get(key, {}) or {})
            merged[key] = dict(counter)
        for key in LIST_DIAGNOSTIC_KEYS:
            merged[key] = sorted(set(merged.get(key, [])) | set(source.get(key, []) or []))
    return merged


def add_score_extreme_diagnostics(
    diagnostics: dict[str, Any],
    player_impacts: list[PlayerMatchImpact],
) -> dict[str, Any]:
    """Add rating/model clipping diagnostics to the flat diagnostics payload."""
    updated = merge_utility_diagnostics(empty_utility_diagnostics(), diagnostics)
    updated["model_impact_clip_count_min"] = sum(
        1 for player in player_impacts
        if player.model_impact_score_raw < -50 and player.model_impact_score_clipped <= -50
    )
    updated["model_impact_clip_count_max"] = sum(
        1 for player in player_impacts
        if player.model_impact_score_raw > 50 and player.model_impact_score_clipped >= 50
    )
    updated["rating_zero_count"] = sum(1 for player in player_impacts if player.rating_0_100 <= 0)
    updated["rating_hundred_count"] = sum(1 for player in player_impacts if player.rating_0_100 >= 100)
    return updated


def print_utility_diagnostics(diagnostics: dict[str, Any]) -> None:
    """Print flat diagnostics for the CLI/debug compatibility path."""
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
        f"  Damage events: total={diagnostics.get('damage_events_found', 0)}, "
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


def collect_match_diagnostics(round_contexts: list[RoundContext]) -> dict[str, Any]:
    """Collect aggregated diagnostics across all rounds."""
    all_round_diagnostics: list[dict[str, Any]] = []
    aggregated: dict[str, Any] = {
        "total_rounds": len(round_contexts),
        "total_events": 0,
        "total_damage_events": 0,
        "total_future_damage_entries": 0,
        "total_future_kill_entries": 0,
        "all_projectile_type_values": set(),
        "all_entity_grenade_type_values": set(),
        "all_damage_weapon_values": set(),
        "all_fire_damage_weapon_values": set(),
        "all_he_damage_weapon_values": set(),
        "fire_attribution_method_counts": {},
        "he_candidate_events_from_damage": 0,
        "he_candidate_events_from_projectiles": 0,
        "he_candidate_events_from_kills": 0,
        "he_projectile_type_values": set(),
        "he_entity_grenade_type_values": set(),
        "he_damage_weapon_values": set(),
        "fire_projectile_type_values": set(),
        "fire_entity_grenade_type_values": set(),
        "fire_damage_weapon_values": set(),
        "smoke_target_match_counts": {},
        "possible_overmatched_smoke_targets": set(),
    }

    for rc in round_contexts:
        rd = collect_round_diagnostics(rc)
        all_round_diagnostics.append(rd)

        aggregated["total_events"] += rd["total_events"]
        aggregated["total_damage_events"] += rd["damage_events_found"]
        aggregated["total_future_damage_entries"] += rd["future_damage_count"]
        aggregated["total_future_kill_entries"] += rd["future_kill_count"]
        aggregated["all_projectile_type_values"].update(rd["projectile_type_values"])
        aggregated["all_entity_grenade_type_values"].update(rd["entity_grenade_type_values"])
        aggregated["all_damage_weapon_values"].update(rd["damage_weapon_values"])
        aggregated["all_fire_damage_weapon_values"].update(rd["fire_damage_weapon_values"])
        aggregated["all_he_damage_weapon_values"].update(rd["he_damage_weapon_values"])
        aggregated["he_candidate_events_from_damage"] += rd["he_candidate_events_from_damage"]
        aggregated["he_candidate_events_from_projectiles"] += rd["he_candidate_events_from_projectiles"]
        aggregated["he_candidate_events_from_kills"] += rd["he_candidate_events_from_kills"]
        aggregated["he_projectile_type_values"].update(rd["he_projectile_type_values"])
        aggregated["he_entity_grenade_type_values"].update(rd["he_entity_grenade_type_values"])
        aggregated["he_damage_weapon_values"].update(rd["he_damage_weapon_values"])
        aggregated["fire_projectile_type_values"].update(rd["fire_projectile_type_values"])
        aggregated["fire_entity_grenade_type_values"].update(rd["fire_entity_grenade_type_values"])
        aggregated["fire_damage_weapon_values"].update(rd["fire_damage_weapon_values"])

        for method, count in rd["fire_attribution_method_counts"].items():
            aggregated["fire_attribution_method_counts"][method] = (
                aggregated["fire_attribution_method_counts"].get(method, 0) + count
            )

        for target, count in rd["smoke_target_match_counts"].items():
            aggregated["smoke_target_match_counts"][target] = (
                aggregated["smoke_target_match_counts"].get(target, 0) + count
            )
        aggregated["possible_overmatched_smoke_targets"].update(rd["possible_overmatched_smoke_targets"])

    # Convert sets to sorted lists
    aggregated["all_projectile_type_values"] = sorted(aggregated["all_projectile_type_values"])
    aggregated["all_entity_grenade_type_values"] = sorted(aggregated["all_entity_grenade_type_values"])
    aggregated["all_damage_weapon_values"] = sorted(aggregated["all_damage_weapon_values"])
    aggregated["all_fire_damage_weapon_values"] = sorted(aggregated["all_fire_damage_weapon_values"])
    aggregated["all_he_damage_weapon_values"] = sorted(aggregated["all_he_damage_weapon_values"])
    aggregated["he_projectile_type_values"] = sorted(aggregated["he_projectile_type_values"])
    aggregated["he_entity_grenade_type_values"] = sorted(aggregated["he_entity_grenade_type_values"])
    aggregated["he_damage_weapon_values"] = sorted(aggregated["he_damage_weapon_values"])
    aggregated["fire_projectile_type_values"] = sorted(aggregated["fire_projectile_type_values"])
    aggregated["fire_entity_grenade_type_values"] = sorted(aggregated["fire_entity_grenade_type_values"])
    aggregated["fire_damage_weapon_values"] = sorted(aggregated["fire_damage_weapon_values"])
    aggregated["possible_overmatched_smoke_targets"] = sorted(aggregated["possible_overmatched_smoke_targets"])

    return {
        "aggregated": aggregated,
        "per_round": all_round_diagnostics,
    }


def format_utility_diagnostics(diagnostics: dict[str, Any]) -> str:
    """Format utility diagnostics as a human-readable string."""
    lines: list[str] = []
    agg = diagnostics.get("aggregated", {})

    lines.append("=" * 50)
    lines.append("Utility diagnostics summary")
    lines.append("=" * 50)
    lines.append(f"Total rounds: {agg.get('total_rounds', 0)}")
    lines.append(f"Total events: {agg.get('total_events', 0)}")
    lines.append(f"Total DAMAGE events: {agg.get('total_damage_events', 0)}")
    lines.append(f"Total future_damage entries: {agg.get('total_future_damage_entries', 0)}")
    lines.append(f"Total future_kill entries: {agg.get('total_future_kill_entries', 0)}")
    lines.append("")

    lines.append("Projectile type values:")
    for v in agg.get("all_projectile_type_values", []):
        lines.append(f"  - {v}")
    if not agg.get("all_projectile_type_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Entity grenade type values:")
    for v in agg.get("all_entity_grenade_type_values", []):
        lines.append(f"  - {v}")
    if not agg.get("all_entity_grenade_type_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Damage weapon values:")
    for v in agg.get("all_damage_weapon_values", []):
        lines.append(f"  - {v}")
    if not agg.get("all_damage_weapon_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Fire damage weapon values:")
    for v in agg.get("all_fire_damage_weapon_values", []):
        lines.append(f"  - {v}")
    if not agg.get("all_fire_damage_weapon_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("HE damage weapon values:")
    for v in agg.get("all_he_damage_weapon_values", []):
        lines.append(f"  - {v}")
    if not agg.get("all_he_damage_weapon_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Fire attribution methods:")
    for method, count in agg.get("fire_attribution_method_counts", {}).items():
        lines.append(f"  - {method}: {count}")
    if not agg.get("fire_attribution_method_counts"):
        lines.append("  (none found)")
    lines.append("")

    lines.append(f"HE candidate events from damage: {agg.get('he_candidate_events_from_damage', 0)}")
    lines.append(f"HE candidate events from projectiles: {agg.get('he_candidate_events_from_projectiles', 0)}")
    lines.append(f"HE candidate events from kills: {agg.get('he_candidate_events_from_kills', 0)}")
    lines.append("")

    lines.append("HE projectile type values:")
    for v in agg.get("he_projectile_type_values", []):
        lines.append(f"  - {v}")
    if not agg.get("he_projectile_type_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("HE entity grenade type values:")
    for v in agg.get("he_entity_grenade_type_values", []):
        lines.append(f"  - {v}")
    if not agg.get("he_entity_grenade_type_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Fire projectile type values:")
    for v in agg.get("fire_projectile_type_values", []):
        lines.append(f"  - {v}")
    if not agg.get("fire_projectile_type_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Fire entity grenade type values:")
    for v in agg.get("fire_entity_grenade_type_values", []):
        lines.append(f"  - {v}")
    if not agg.get("fire_entity_grenade_type_values"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Smoke target match counts:")
    for target, count in agg.get("smoke_target_match_counts", {}).items():
        lines.append(f"  - {target}: {count}")
    if not agg.get("smoke_target_match_counts"):
        lines.append("  (none found)")
    lines.append("")

    lines.append("Possible overmatched smoke targets:")
    for target in agg.get("possible_overmatched_smoke_targets", []):
        lines.append(f"  - {target}")
    if not agg.get("possible_overmatched_smoke_targets"):
        lines.append("  (none found)")
    lines.append("")

    return "\n".join(lines)


def _is_attributed(thrower: str | None, players: list[str]) -> bool:
    return bool(thrower and thrower != "unknown" and thrower in players)


def _count_weapon_matches(round_context: RoundContext, predicate: Any) -> int:
    seen: set[tuple[float, str, str, str, int]] = set()
    count = 0
    for event in round_context.events:
        if event.event_type != EventType.DAMAGE:
            continue
        weapon = str(event.weapon or "")
        key = (
            round(event.tick, 3),
            str(event.player or ""),
            str(event.other_player or ""),
            weapon,
            int(event.damage_health or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        if predicate(weapon):
            count += 1
    for tick in round_context.ticks:
        for damage in tick.future_damage:
            weapon = str(damage.get("weapon") or "")
            tick_time = safe_float(damage.get("time") or damage.get("tick") or damage.get("round_seconds"), tick.round_seconds)
            damage_value = int(safe_float(damage.get("dmg_health") or damage.get("damage_health") or damage.get("damage"), 0))
            key = (
                round(tick_time, 3),
                str(damage.get("attacker_name") or damage.get("attacker") or damage.get("player") or ""),
                str(damage.get("victim_name") or damage.get("victim") or damage.get("user_name") or damage.get("other_player") or ""),
                weapon,
                damage_value,
            )
            if key in seen:
                continue
            seen.add(key)
            if predicate(weapon):
                count += 1
    return count


def _damage_dedup_stats(round_context: RoundContext) -> dict[str, int | float]:
    raw_future_damage = sum(len(tick.future_damage) for tick in round_context.ticks)
    seen: set[tuple[float, str, str, str, int]] = set()
    for event in round_context.events:
        if event.event_type != EventType.DAMAGE:
            continue
        seen.add((
            round(event.tick, 3),
            str(event.player or ""),
            str(event.other_player or ""),
            str(event.weapon or ""),
            int(event.damage_health or 0),
        ))
    for tick in round_context.ticks:
        for damage in tick.future_damage:
            seen.add((
                round(safe_float(damage.get("time") or damage.get("tick") or damage.get("round_seconds"), tick.round_seconds), 3),
                str(damage.get("attacker_name") or damage.get("attacker") or damage.get("player") or ""),
                str(damage.get("victim_name") or damage.get("victim") or damage.get("user_name") or damage.get("other_player") or ""),
                str(damage.get("weapon") or ""),
                int(safe_float(damage.get("dmg_health") or damage.get("damage_health") or damage.get("damage"), 0)),
            ))
    unique_count = len(seen)
    raw_total = raw_future_damage + sum(1 for event in round_context.events if event.event_type == EventType.DAMAGE)
    dedup_ratio = (unique_count / raw_total) if raw_total > 0 else 1.0
    return {
        "raw_future_damage_entries": raw_future_damage,
        "unique_damage_events_after_dedup": unique_count,
        "duplicate_damage_events_removed": max(0, raw_total - unique_count),
        "damage_raw_count": raw_total,
        "damage_dedup_count": unique_count,
        "dedup_ratio": dedup_ratio,
    }


def _damage_weapon_values(round_context: RoundContext) -> list[str]:
    values = {
        str(event.weapon)
        for event in round_context.events
        if event.event_type == EventType.DAMAGE and event.weapon
    }
    for tick in round_context.ticks:
        values.update(str(damage.get("weapon")) for damage in tick.future_damage if damage.get("weapon"))
    return sorted(values)
