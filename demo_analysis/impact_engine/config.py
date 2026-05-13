"""Configuration for the CS2 Impact Engine scoring weights."""

from typing import Any

import os
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


FLASH_THRESHOLDS = {
    "ignore": 0.7,
    "minor": 1.5,
    "partial": 2.8,
    "strong": 3.5,
}


SMOKE_INTENTS = [
    "execute_smoke",
    "cross_smoke",
    "isolation_smoke",
    "defensive_smoke",
    "retake_smoke",
    "fake_smoke",
    "oneway_smoke",
    "random_smoke",
    "unknown_smoke",
]


FIRE_INTENTS = [
    "anti_rush_fire",
    "choke_control_fire",
    "clear_position_fire",
    "post_plant_fire",
    "anti_defuse_fire",
    "anti_plant_fire",
    "retake_delay_fire",
    "defensive_delay_fire",
    "fake_pressure_fire",
    "random_fire",
    "harmful_fire",
    "unknown_fire",
]


FIRE_SCORING = {
    "damage_multiplier": 0.015,
    "kill_bonus": 0.8,
    "assist_bonus": 0.3,
    "forced_position_bonus": 0.4,
    "choke_control_bonus": 0.5,
    "anti_rush_bonus": 0.7,
    "post_plant_bonus": 0.8,
    "anti_defuse_bonus": 1.0,
    "anti_plant_bonus": 0.8,
    "forced_smoke_bonus": 0.5,
    "teammate_block_penalty": -0.8,
    "team_damage_multiplier": -0.02,
    "harmful_fire_penalty": -1.2,
    "max_fire_score_per_fire": 3.0,
    "min_fire_score_per_fire": -3.0,
}


HE_SCORING = {
    "damage_multiplier": 0.015,
    "high_damage_threshold": 50,
    "high_damage_bonus": 0.3,
    "kill_bonus": 0.8,
    "assist_bonus": 0.3,
    "finishing_he_bonus": 0.4,
    "anti_smoke_direct_bonus": 0.5,
    "anti_smoke_route_bonus": 0.4,
    "anti_smoke_direct_kill_bonus": 1.2,
    "anti_smoke_route_kill_bonus": 1.0,
    "anti_cross_bonus": 0.8,
    "anti_plant_bonus": 0.8,
    "anti_defuse_bonus": 1.0,
    "anti_rush_bonus": 0.7,
    "nade_stack_bonus": 0.4,
    "team_damage_multiplier": -0.02,
    "harmful_he_penalty": -1.2,
    "max_he_score_per_grenade": 3.0,
    "min_he_score_per_grenade": -2.0,
}


IMPACT_WEIGHTS = {
    "round_impact_thresholds": {
        "carry": 3.0,
        "high_impact": 1.5,
        "positive": 0.5,
        "negative": -0.5,
        "throw": -1.5,
    },
    "win_rate_delta_multiplier": 100.0,
    "model_vs_rule_weight": {
        "model_impact": 0.65,
        "rule_quality": 0.35,
    },
    "kill_impact": {
        "base_multiplier": 1.0,
        "hard_duel_win_bonus": 0.8,
        "hard_duel_threshold": 0.45,
        "trade_bonus": 0.8,
        "trade_window_seconds": 5.0,
        "opening_kill_bonus": 0.5,
        "opening_kill_player_count": 10,
        "objective_bonus": 0.5,
        "clutch_bonus": 1.0,
        "low_impact_penalty_multiplier": 0.5,
        "exit_frag_penalty_multiplier": 0.5,
        "eco_round_penalty_multiplier": 0.3,
        "man_advantage_threshold": 3,
    },
    "death_impact": {
        "win_rate_delta_multiplier": 100.0,
        "forced_risk_bonus": 0.6,
        "self_created_risk_penalty": -1.2,
        "traded_death_bonus": 0.8,
        "trade_available_no_trade_penalty": -0.4,
        "no_trade_no_info_penalty": -0.2,
        "post_plant_throw_death_penalty": -1.2,
        "bomb_carrier_died_alone_penalty": -1.5,
        "opening_death_self_created_penalty": -0.8,
        "unexpected_death_penalty": -0.5,
    },
    "trade_impact": {
        "effective_trade_bonus": 0.6,
        "trade_window_seconds": 5.0,
    },
    "objective_impact": {
        "bomb_plant_bonus": 0.8,
        "bomb_defuse_bonus": 1.0,
        "clutch_win_bonus": 1.5,
        "clutch_attempt_bonus": 0.5,
    },
    "flash_impact": {
        "thresholds": FLASH_THRESHOLDS,
        "conversion_window_seconds": 3.0,
        "plant_support_window_seconds": 5.0,
        "forced_turn_window_seconds": 0.8,
        "forced_position_window_seconds": 2.0,
        "forced_position_distance": 250.0,
        "forced_turn_yaw": 80.0,
        "strong_forced_turn_yaw": 120.0,
        "max_enemy_flash_score_per_flash": 3.0,
        "min_team_flash_score_per_flash": -3.0,
    },
    "smoke_impact": {
        "target_match_score": 0.2,
        "complete_block_score": 0.8,
        "partial_block_score": 0.3,
        "leaky_smoke_score": -0.5,
        "missed_smoke_score": -0.8,
        "false_confidence_penalty": -1.0,
        "fatal_leak_penalty": -2.0,
        "blocking_teammate_penalty": -0.8,
        "site_entry_success": 0.4,
        "bomb_planted": 0.5,
        "key_area_control_gained": 0.3,
        "fake_rotation_score": 0.6,
        "fake_success_score": 0.8,
        "unconverted_fake_score": 0.1,
        "dependency_window_seconds": 5.0,
        "conversion_window_seconds": 8.0,
        "fake_window_seconds": 20.0,
        "smoke_radius": 170.0,
        "target_match_radius_multiplier": 1.6,
    },
    "fire_impact": {
        **FIRE_SCORING,
        "default_radius": 180.0,
        "default_duration": 6.0,
        "damage_window_seconds": 6.0,
        "assist_window_seconds": 5.0,
        "forced_position_window_seconds": 3.0,
        "objective_window_seconds": 6.0,
        "fake_window_seconds": 20.0,
        "enemy_near_radius": 650.0,
        "choke_radius": 220.0,
        "rush_enemy_count": 2,
        "delay_distance_threshold": 450.0,
        "high_damage_threshold": 40,
    },
    "he_impact": {
        **HE_SCORING,
        "damage_window_seconds": 2.0,
        "assist_window_seconds": 5.0,
        "smoke_active_window_seconds": 8.0,
        "smoke_radius": 170.0,
        "smoke_tolerance": 80.0,
        "objective_radius": 350.0,
        "cross_radius": 250.0,
        "enemy_near_radius": 650.0,
        "rush_enemy_count": 2,
        "nade_stack_window_seconds": 3.0,
        "nade_stack_radius": 260.0,
        "low_value_damage_threshold": 10,
    },
    "duel_thresholds": {
        "hard_duel_win_max_prob": 0.45,
        "easy_duel_loss_min_prob": 0.65,
    },
    "risk_assessment": {
        "self_created_risk": {
            "nearest_teammate_distance_threshold": 1200,
            "alive_prob_high_threshold": 0.70,
            "alive_prob_low_threshold": 0.40,
            "alive_prob_window_seconds": 8,
            "death_prob_window_seconds": 5,
            "confidence_base": 0.6,
            "max_confidence": 0.95,
        },
        "forced_risk": {
            "first_contact_distance_threshold": 1000,
            "trade_window_seconds": 5,
            "confidence_base": 0.6,
            "max_confidence": 0.95,
        },
    },
    "rating_bounds": {
        "min": 0.0,
        "max": 100.0,
    },
}


def get_weight(path: str, default: Any = None) -> Any:
    """Get a weight value by dot-notation path.

    Lookup order: map+phase layered config -> global layered config -> built-in IMPACT_WEIGHTS.
    """
    layered = _load_layered_config()
    map_name = _CONTEXT.get("map_name")
    phase = _CONTEXT.get("phase")

    if map_name and phase:
        scoped = _nested_get(layered, f"maps.{map_name}.{phase}")
        if isinstance(scoped, dict):
            alias_map = {
                "kill_impact.trade_window_seconds": "trade_window_seconds",
                "duel_thresholds.hard_duel_win_max_prob": "hard_duel_win_max_prob",
                "align.tolerance_seconds": "align_tolerance_seconds",
            }
            alias_key = alias_map.get(path)
            if alias_key in scoped:
                return scoped[alias_key]

    global_cfg = layered.get("global", {}) if isinstance(layered, dict) else {}
    alias_map = {
        "kill_impact.trade_window_seconds": "trade_window_seconds",
        "duel_thresholds.hard_duel_win_max_prob": "hard_duel_win_max_prob",
        "align.tolerance_seconds": "align_tolerance_seconds",
    }
    alias_key = alias_map.get(path)
    if alias_key and alias_key in global_cfg:
        return global_cfg[alias_key]

    keys = path.split(".")
    value = IMPACT_WEIGHTS
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


_CONTEXT = {"map_name": None, "phase": None}
_LAYERED_CACHE = None


def set_context(map_name: str | None = None, phase: str | None = None) -> None:
    """Set optional map/phase context for layered threshold lookup."""
    _CONTEXT["map_name"] = map_name
    _CONTEXT["phase"] = phase


def _nested_get(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split('.'):
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value


def _load_layered_config() -> dict[str, Any]:
    global _LAYERED_CACHE
    if _LAYERED_CACHE is not None:
        return _LAYERED_CACHE
    cfg_path = Path(os.getenv("IMPACT_LAYERED_CONFIG", "config/impact_thresholds.yaml"))
    if yaml is None or not cfg_path.exists():
        _LAYERED_CACHE = {}
    else:
        _LAYERED_CACHE = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return _LAYERED_CACHE


def get_threshold(category: str, name: str) -> float:
    """Get a threshold value."""
    return get_weight(f"{category}.{name}", 0.0)


DEFAULT_CONFIG = IMPACT_WEIGHTS
