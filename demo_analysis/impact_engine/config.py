"""Configuration for the CS2 Impact Engine scoring weights."""

from typing import Any


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
    """Get a weight value by dot-notation path."""
    keys = path.split(".")
    value = IMPACT_WEIGHTS
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def get_threshold(category: str, name: str) -> float:
    """Get a threshold value."""
    return get_weight(f"{category}.{name}", 0.0)


DEFAULT_CONFIG = IMPACT_WEIGHTS
