"""Risk assessment for player deaths."""

from typing import Any

from .align import (
    find_nearest_tick,
    find_nearest_teammate,
    get_alive_count_at_tick,
    get_duel_probability,
    get_name_to_idx,
    safe_float,
    was_bomb_planted_before_tick,
)
from .config import get_weight
from .models import (
    EventType,
    GameEvent,
    PredictionTick,
    RiskAssessment,
    RiskType,
    RoundContext,
)


def assess_death_risk(
    event: GameEvent,
    before_tick: PredictionTick | None,
    risk_window_ticks: list[PredictionTick],
    round_context: RoundContext,
) -> RiskAssessment:
    """
    Assess the risk type for a player's death.

    Returns a RiskAssessment with:
    - risk_type: forced_risk | self_created_risk | unknown_risk
    - confidence: 0-1
    - reasons: list of explanation strings
    - alive_prob_drop: how much alive probability dropped
    - nearest_teammate_distance: distance to nearest alive teammate
    - trade_available: whether a teammate could trade
    - objective_pressure: whether player was under objective pressure
    - team_alive_advantage: team alive count difference
    """
    player_name = event.player
    team1_players = round_context.team1_players
    team2_players = round_context.team2_players

    name_to_idx = get_name_to_idx(round_context.ticks)

    self_created_score = 0
    forced_score = 0
    reasons: list[str] = []

    if before_tick is None:
        return RiskAssessment(
            risk_type=RiskType.UNKNOWN_RISK,
            confidence=0.0,
            reasons=["无法获取死亡前预测数据"],
            alive_prob_drop=0.0,
            nearest_teammate_distance=None,
            trade_available=False,
            objective_pressure=False,
            team_alive_advantage=0,
        )

    team1_alive, team2_alive = get_alive_count_at_tick(
        before_tick, team1_players, team2_players
    )
    team_alive_advantage = team1_alive - team2_alive

    _, nearest_teammate_dist = find_nearest_teammate(
        player_name, before_tick, team1_players, team2_players
    )

    alive_prob_drop = 0.0
    if risk_window_ticks and name_to_idx.get(player_name) is not None:
        player_idx = name_to_idx[player_name]
        for tick in risk_window_ticks:
            if player_idx < len(tick.alive_pred):
                alive_prob = tick.alive_pred[player_idx]
                if tick.round_seconds < before_tick.round_seconds:
                    alive_prob_drop = max(alive_prob_drop, 0.0)

        early_ticks = [t for t in risk_window_ticks if abs(t.round_seconds - before_tick.round_seconds) > 5]
        late_ticks = [t for t in risk_window_ticks if abs(t.round_seconds - before_tick.round_seconds) <= 2]

        early_alive_prob = 0.0
        late_alive_prob = 0.0

        if early_ticks and player_idx < len(early_ticks[0].alive_pred):
            early_alive_prob = early_ticks[0].alive_pred[player_idx]
        if late_ticks and player_idx < len(late_ticks[0].alive_pred):
            late_alive_prob = late_ticks[0].alive_pred[player_idx]

        if early_ticks:
            alive_prob_drop = early_alive_prob - late_alive_prob

    risk_cfg = get_weight("risk_assessment.self_created_risk", {})
    forced_cfg = get_weight("risk_assessment.forced_risk", {})

    distance_threshold = risk_cfg.get("nearest_teammate_distance_threshold", 1200)
    alive_prob_high = risk_cfg.get("alive_prob_high_threshold", 0.70)
    alive_prob_low = risk_cfg.get("alive_prob_low_threshold", 0.40)
    alive_prob_window = risk_cfg.get("alive_prob_window_seconds", 8)

    early_ticks = [t for t in risk_window_ticks if (before_tick.round_seconds - t.round_seconds) <= alive_prob_window]
    early_alive = 0.75
    late_alive = 0.75

    if early_ticks and name_to_idx.get(player_name) is not None:
        player_idx = name_to_idx[player_name]
        probs = [t.alive_pred[player_idx] for t in early_ticks if player_idx < len(t.alive_pred)]
        if probs:
            early_alive = probs[0]
            late_alive = probs[-1] if len(probs) > 1 else probs[0]

    early_high_late_low = early_alive >= alive_prob_high and late_alive <= alive_prob_low

    player_is_on_team1 = player_name in team1_players
    teammate_count = team1_alive if player_is_on_team1 else team2_alive
    enemy_count = team2_alive if player_is_on_team1 else team1_alive
    teammate_count_incl_player = teammate_count + 1

    players_dead = 10 - (team1_alive + team2_alive)
    enemies_killed = (5 - enemy_count)

    team_has_advantage = teammate_count_incl_player >= enemy_count
    distant_from_team = nearest_teammate_dist > distance_threshold

    bomb_was_planted = was_bomb_planted_before_tick(round_context.ticks, event.tick)
    is_bomb_carrier = False
    for p in before_tick.players_info:
        if p.get("name") == player_name and "C4" in (p.get("inventory") or []):
            is_bomb_carrier = True
            break

    objective_pressure = bomb_was_planted or is_bomb_carrier or (round_context.bomb_planted_time is not None)

    was_entry = False
    if team_alive_advantage >= 1 and distant_from_team and not bomb_was_planted:
        if (player_is_on_team1 and round_context.team1_on_ct) or (not player_is_on_team1 and not round_context.team1_on_ct):
            was_entry = True

    trade_available = nearest_teammate_dist < distance_threshold

    if distant_from_team and team_has_advantage and not bomb_was_planted:
        self_created_score += 3
        reasons.append(f"人数优势({teammate_count_incl_player}v{enemy_count})时远离队友({nearest_teammate_dist:.0f}单位)单摸")

    if early_high_late_low and distant_from_team:
        self_created_score += 2
        reasons.append(f"死亡前存活概率从 {early_alive:.0%} 骤降至 {late_alive:.0%}，且远离队友")

    if team_has_advantage and distant_from_team and players_dead >= 4:
        self_created_score += 2
        reasons.append("中期优势局面主动离开团队暴露位置")

    if was_entry and not trade_available:
        self_created_score += 1
        reasons.append("作为进攻方进入危险区域但无队友支援")

    if is_bomb_carrier and distant_from_team and bomb_was_planted:
        self_created_score += 2
        reasons.append("持包者远离队友在危险位置被击杀")

    if team_alive_advantage <= -1:
        forced_score += 2
        reasons.append("人数劣势被迫接敌")

    if bomb_was_planted and teammate_count_incl_player <= 2:
        forced_score += 2
        reasons.append("残局时间紧迫必须主动接敌")

    if trade_available and nearest_teammate_dist < 800:
        forced_score += 1
        reasons.append("附近有队友准备支援")

    if team_alive_advantage >= 0 and not distant_from_team:
        forced_score += 1
        reasons.append("正常站位死亡，属于合理风险")

    if not trade_available and not distant_from_team:
        forced_score += 1
        reasons.append("位置合理但被意外击杀")

    if early_high_late_low and not distant_from_team:
        forced_score += 1
        reasons.append("存活概率骤降但位置无明显问题")

    if self_created_score >= 3:
        confidence = min(0.6 + (self_created_score - 3) * 0.1, risk_cfg.get("max_confidence", 0.95))
        return RiskAssessment(
            risk_type=RiskType.SELF_CREATED_RISK,
            confidence=confidence,
            reasons=reasons,
            alive_prob_drop=alive_prob_drop,
            nearest_teammate_distance=nearest_teammate_dist,
            trade_available=trade_available,
            objective_pressure=objective_pressure,
            team_alive_advantage=team_alive_advantage,
        )

    elif forced_score >= 2:
        confidence = min(0.6 + (forced_score - 2) * 0.1, forced_cfg.get("max_confidence", 0.95))
        return RiskAssessment(
            risk_type=RiskType.FORCED_RISK,
            confidence=confidence,
            reasons=reasons,
            alive_prob_drop=alive_prob_drop,
            nearest_teammate_distance=nearest_teammate_dist,
            trade_available=trade_available,
            objective_pressure=objective_pressure,
            team_alive_advantage=team_alive_advantage,
        )

    else:
        return RiskAssessment(
            risk_type=RiskType.UNKNOWN_RISK,
            confidence=0.5,
            reasons=reasons if reasons else ["无法明确判断风险来源"],
            alive_prob_drop=alive_prob_drop,
            nearest_teammate_distance=nearest_teammate_dist,
            trade_available=trade_available,
            objective_pressure=objective_pressure,
            team_alive_advantage=team_alive_advantage,
        )


def is_unexpected_death(
    event: GameEvent,
    before_tick: PredictionTick | None,
    risk_window_ticks: list[PredictionTick],
    name_to_idx: dict[str, int],
    threshold: float = 0.70
) -> tuple[bool, float]:
    """
    Check if a death was unexpected (high alive probability before death).
    Returns (is_unexpected, last_alive_prob).
    """
    if before_tick is None or not risk_window_ticks:
        return False, 0.5

    player_idx = name_to_idx.get(event.player)
    if player_idx is None:
        return False, 0.5

    early_ticks = risk_window_ticks[:3] if len(risk_window_ticks) >= 3 else risk_window_ticks
    if not early_ticks or player_idx >= len(early_ticks[0].alive_pred):
        return False, 0.5

    last_alive_prob = early_ticks[0].alive_pred[player_idx]

    if last_alive_prob >= threshold:
        return True, last_alive_prob

    return False, last_alive_prob


def calculate_surprise_factor(
    risk_window_ticks: list[PredictionTick],
    player_name: str,
    name_to_idx: dict[str, int],
    window_seconds: float = 5.0
) -> float:
    """
    Calculate how surprising a death was based on alive probability trends.
    Returns a value from -1.0 (very expected) to 1.0 (very surprising).
    """
    player_idx = name_to_idx.get(player_name)
    if player_idx is None or not risk_window_ticks:
        return 0.0

    probs = []
    for tick in risk_window_ticks:
        if player_idx < len(tick.alive_pred):
            probs.append(tick.alive_pred[player_idx])

    if len(probs) < 2:
        return 0.0

    start_prob = probs[0]
    end_prob = probs[-1]

    prob_drop = start_prob - end_prob

    if start_prob > 0.6 and end_prob < 0.3:
        return -0.5
    elif start_prob > 0.7 and end_prob > 0.5:
        return 0.7
    elif start_prob < 0.4 and end_prob < 0.2:
        return -0.8
    elif start_prob < 0.5 and end_prob > 0.3:
        return 0.4

    return prob_drop
