"""Rating normalization using match-relative z-score."""

import math
from typing import Any

from .models import PlayerMatchImpact


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def normalize_player_ratings(player_impacts: list[PlayerMatchImpact]) -> None:
    if not player_impacts:
        return

    avg_impacts = [p.avg_round_impact for p in player_impacts]
    mean_val = sum(avg_impacts) / len(avg_impacts)

    variance = sum((x - mean_val) ** 2 for x in avg_impacts) / len(avg_impacts)
    std_val = math.sqrt(variance)

    ratings = []
    for player in player_impacts:
        if std_val < 0.01:
            z_score = 0.0
        else:
            z_score = (player.avg_round_impact - mean_val) / std_val

        clamped_z = _clamp(z_score, -2.0, 2.0)
        base_rating = 50.0 + clamped_z * 12.0

        utility_impact = sum(ri.utility_impact for ri in player.round_impacts)
        tactical_score = player.tactical_discipline_score

        rating = base_rating
        rating += player.high_impact_rounds * 0.6
        rating -= player.throw_rounds * 0.8
        rating -= player.self_created_risk_deaths * 1.0
        rating -= player.post_plant_errors * 0.8
        rating += player.effective_trades * 0.4
        rating += player.forced_risk_deaths * 0.1
        rating += _clamp(utility_impact, -6.0, 6.0) * 0.35
        rating += _clamp(tactical_score, -8.0, 8.0) * 0.4

        final_rating = _clamp(rating, 5.0, 95.0)

        player.rating_0_100 = final_rating
        player.model_impact_score = _clamp(clamped_z * 25.0, -50.0, 50.0)

        player.rating_components = {
            "base_rating": round(base_rating, 2),
            "z_score": round(z_score, 3),
            "avg_round_impact": round(player.avg_round_impact, 3),
            "high_impact_bonus": round(player.high_impact_rounds * 0.6, 2),
            "throw_penalty": round(player.throw_rounds * 0.8, 2),
            "self_created_risk_penalty": round(player.self_created_risk_deaths * 1.0, 2),
            "trade_bonus": round(player.effective_trades * 0.4, 2),
            "utility_bonus": round(_clamp(utility_impact, -6.0, 6.0) * 0.35, 2),
            "tactical_bonus": round(_clamp(tactical_score, -8.0, 8.0) * 0.4, 2),
            "final_rating": round(final_rating, 2),
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
        "rating_zero_count": sum(1 for r in ratings if r <= 0),
        "rating_hundred_count": sum(1 for r in ratings if r >= 100),
        "rating_clamped_low_count": sum(1 for r in ratings if r <= 5.0),
        "rating_clamped_high_count": sum(1 for r in ratings if r >= 95.0),
    }
