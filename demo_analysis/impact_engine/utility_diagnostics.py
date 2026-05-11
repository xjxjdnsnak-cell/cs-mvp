"""Utility diagnostics for CS2 Impact Engine.

Collects and reports diagnostics about utility data sources,
including projectiles, entity grenades, damage events, and fire attribution.
"""

from typing import Any

from .align import is_he_weapon, is_fire_weapon, _normalize_weapon_name
from .models import EventType, GameEvent, PredictionTick, RoundContext


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
    }

    # Count event types
    for event in round_context.events:
        et = event.event_type.value
        diagnostics["event_type_counts"][et] = diagnostics["event_type_counts"].get(et, 0) + 1

    # Collect from ticks
    for tick in round_context.ticks:
        # Projectiles
        projectiles = tick.players_info[0].get("projectiles") if tick.players_info else None
        if projectiles:
            for p in projectiles:
                ptype = p.get("type")
                if ptype:
                    diagnostics["projectile_type_values"].add(str(ptype))

        # Entity grenades
        entity_grenades = tick.players_info[0].get("entity_grenades") if tick.players_info else None
        if entity_grenades:
            for eg in entity_grenades:
                egtype = eg.get("type") or eg.get("grenade_type")
                if egtype:
                    diagnostics["entity_grenade_type_values"].add(str(egtype))

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

    # Count DAMAGE events from RoundContext.events
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

    # Convert sets to sorted lists for JSON serialization
    diagnostics["projectile_type_values"] = sorted(diagnostics["projectile_type_values"])
    diagnostics["entity_grenade_type_values"] = sorted(diagnostics["entity_grenade_type_values"])
    diagnostics["damage_weapon_values"] = sorted(diagnostics["damage_weapon_values"])
    diagnostics["fire_damage_weapon_values"] = sorted(diagnostics["fire_damage_weapon_values"])
    diagnostics["he_damage_weapon_values"] = sorted(diagnostics["he_damage_weapon_values"])

    return diagnostics


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

        for method, count in rd["fire_attribution_method_counts"].items():
            aggregated["fire_attribution_method_counts"][method] = (
                aggregated["fire_attribution_method_counts"].get(method, 0) + count
            )

    # Convert sets to sorted lists
    aggregated["all_projectile_type_values"] = sorted(aggregated["all_projectile_type_values"])
    aggregated["all_entity_grenade_type_values"] = sorted(aggregated["all_entity_grenade_type_values"])
    aggregated["all_damage_weapon_values"] = sorted(aggregated["all_damage_weapon_values"])
    aggregated["all_fire_damage_weapon_values"] = sorted(aggregated["all_fire_damage_weapon_values"])
    aggregated["all_he_damage_weapon_values"] = sorted(aggregated["all_he_damage_weapon_values"])

    return {
        "aggregated": aggregated,
        "per_round": all_round_diagnostics,
    }


def format_utility_diagnostics(diagnostics: dict[str, Any]) -> str:
    """Format utility diagnostics as a human-readable string."""
    lines: list[str] = []
    agg = diagnostics.get("aggregated", {})

    lines.append("=" * 50)
    lines.append("Utility Diagnostics Summary")
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

    return "\n".join(lines)
