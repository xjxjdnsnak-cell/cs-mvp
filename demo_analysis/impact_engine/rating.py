"""Rating normalization using match-relative z-score."""

import math
from typing import Any

from .models import PlayerMatchImpact


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def normalize_match_ratings(player_impacts: list[PlayerMatchImpact]) -> dict[str, Any]:
    if not player_impacts:
        return {
            "rating_mean": 0.0, "rating_std": 0.0,
            "rating_min": 0.0, "rating_max": 0.0,
            "rating_zero_count": 0, "rating_hundred_count": 0,
            "rating_clamped_low_count": 0, "rating_clamped_high_count": 0,
            "avg_round_impact_mean": 0.0, "avg_round_impact_std": 0.0,
        }

    avg_impacts = []
    for p in player_impacts:
        rounds_played = len(p.round_impacts)
        p.avg_round_impact = p.total_round_impact / max(1, rounds_played)
        avg_impacts.append(p.avg_round_impact)

    mean_val = sum(avg_impacts) / len(avg_impacts)
    variance = sum((x - mean_val) ** 2 for x in avg_impacts) / len(avg_impacts)
    std_val = math.sqrt(variance) if variance > 0 else 0.0

    utility_impacts = {}
    for p in player_impacts:
        utility_impacts[p.player_name] = sum(ri.utility_impact for ri in p.round_impacts)

    ratings = []
    for p in player_impacts:
        if std_val < 0.01:
            z_score = 0.0
        else:
            z_score = (p.avg_round_impact - mean_val) / std_val

        clamped_z = _clamp(z_score, -2.0, 2.0)
        base_rating = 50.0 + clamped_z * 12.0

        high_impact_bonus = p.high_impact_rounds * 0.4
        throw_penalty = p.throw_rounds * -0.5
        self_created_penalty = p.self_created_risk_deaths * -0.8
        post_plant_penalty = p.post_plant_errors * -0.6
        trade_bonus = p.effective_trades * 0.3

        utility_impact = utility_impacts[p.player_name]
        utility_bonus = _clamp(utility_impact, -6.0, 6.0) * 0.25

        tactical_bonus = _clamp(p.tactical_discipline_score, -8.0, 8.0) * 0.3

        final_rating = (
            base_rating
            + high_impact_bonus
            + throw_penalty
            + self_created_penalty
            + post_plant_penalty
            + trade_bonus
            + utility_bonus
            + tactical_bonus
        )

        final_rating_before_clamp = final_rating
        final_rating = _clamp(final_rating, 5.0, 95.0)

        p.rating_0_100 = final_rating

        p.rating_components = {
            "base_rating": round(base_rating, 2),
            "z_score": round(z_score, 3),
            "avg_round_impact": round(p.avg_round_impact, 3),
            "high_impact_bonus": round(high_impact_bonus, 2),
            "throw_penalty": round(throw_penalty, 2),
            "self_created_penalty": round(self_created_penalty, 2),
            "post_plant_penalty": round(post_plant_penalty, 2),
            "trade_bonus": round(trade_bonus, 2),
            "utility_bonus": round(utility_bonus, 2),
            "tactical_bonus": round(tactical_bonus, 2),
            "final_rating_before_clamp": round(final_rating_before_clamp, 2),
            "rating_0_100": round(final_rating, 2),
        }
        ratings.append(final_rating)

    if ratings:
        mean_rating = sum(ratings) / len(ratings)
        variance_rating = sum((r - mean_rating) ** 2 for r in ratings) / len(ratings)
        std_rating = math.sqrt(variance_rating) if variance_rating > 0 else 0.0
        min_rating = min(ratings)
        max_rating = max(ratings)
    else:
        mean_rating = 0.0
        std_rating = 0.0
        min_rating = 0.0
        max_rating = 0.0

    return {
        "rating_mean": round(mean_rating, 2),
        "rating_std": round(std_rating, 2),
        "rating_min": round(min_rating, 2),
        "rating_max": round(max_rating, 2),
        "rating_zero_count": 0,
        "rating_hundred_count": 0,
        "rating_clamped_low_count": sum(1 for r in ratings if r <= 5.0),
        "rating_clamped_high_count": sum(1 for r in ratings if r >= 95.0),
        "avg_round_impact_mean": round(mean_val, 3),
        "avg_round_impact_std": round(std_val, 3),
    }


def normalize_player_ratings(player_impacts: list[PlayerMatchImpact]) -> dict[str, Any]:
    return normalize_match_ratings(player_impacts)
