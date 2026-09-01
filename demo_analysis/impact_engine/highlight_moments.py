"""Rule-based detection of highlight moments (multi-kills, clutches, etc.)."""

from typing import Any

from .align import get_alive_count_at_tick
from .models import (
    HighlightMoment,
    PlayerRoundImpact,
    PredictionTick,
    RoundContext,
)


# Multi-kill subtype names by kill count (>= 5 is an ace).
MULTI_KILL_SUBTYPES = {
    2: "double_kill",
    3: "triple_kill",
    4: "quadra_kill",
}
MULTI_KILL_ACE_SUBTYPE = "ace"
MULTI_KILL_SCORES = {
    "double_kill": 1.0,
    "triple_kill": 1.5,
    "quadra_kill": 2.0,
    "ace": 3.0,
}

# Quick multi-kill windows (seconds).
QUICK_KILL_WINDOW_SECONDS = 5.0
QUICK_KILL_SCORES = {
    "quick_2_kill": 0.8,
    "quick_3_kill": 1.2,
}

# Clutch scoring: base + per extra enemy after the first (1v2 -> 1.5, 1v3 -> 2.0, ...).
CLUTCH_BASE_SCORE = 1.0
CLUTCH_SCORE_PER_ENEMY = 0.5

HE_MULTI_HIT_SUBTYPES = {
    2: "he_2_hit",
    3: "he_3_hit",
}
HE_MULTI_HIT_SCORES = {
    "he_2_hit": 0.8,
    "he_3_hit": 1.2,
}

HARD_DUEL_SCORE = 0.8
IMPACTFUL_OPENING_MIN_IMPACT = 1.0
IMPACTFUL_OPENING_SCORE = 1.0


def _is_player_alive(tick: PredictionTick, player_name: str) -> bool:
    """Check if a player is alive at a tick."""
    for player in tick.players_info:
        if player.get("name") == player_name:
            return bool(player.get("is_alive", False))
    return False


def _multi_kill_subtype(kill_count: int) -> str:
    """Get the multi-kill subtype for a kill count."""
    return MULTI_KILL_SUBTYPES.get(kill_count, MULTI_KILL_ACE_SUBTYPE)


def _detect_multi_kill(player_name: str, round_impact: PlayerRoundImpact) -> HighlightMoment | None:
    """Detect a multi-kill round (2+ kills by the same player)."""
    kill_count = len(round_impact.kills)
    if kill_count < 2:
        return None

    kills = sorted(round_impact.kills, key=lambda ki: ki.event.tick)
    victims = [ki.event.other_player or "" for ki in kills if ki.event.other_player]
    subtype = _multi_kill_subtype(kill_count)

    return HighlightMoment(
        round_id=round_impact.round_id,
        tick=kills[-1].event.tick,
        type="multi_kill",
        subtype=subtype,
        description=f"第 {round_impact.round_id} 回合斩获{kill_count}杀",
        score=MULTI_KILL_SCORES[subtype],
        details={"kills": kill_count, "victims": victims},
    )


def _detect_quick_multi_kill(
    player_name: str, round_impact: PlayerRoundImpact
) -> HighlightMoment | None:
    """Detect a quick multi-kill (2+ kills within a short time window)."""
    if len(round_impact.kills) < 2:
        return None

    kill_times = sorted(ki.event.tick for ki in round_impact.kills)

    # Largest number of kills inside any sliding window.
    def max_kills_in_window(window_seconds: float) -> int:
        best = 0
        start = 0
        for end in range(len(kill_times)):
            while kill_times[end] - kill_times[start] > window_seconds:
                start += 1
            best = max(best, end - start + 1)
        return best

    if max_kills_in_window(QUICK_KILL_WINDOW_SECONDS * 2) >= 3:
        subtype = "quick_3_kill"
    elif max_kills_in_window(QUICK_KILL_WINDOW_SECONDS) >= 2:
        subtype = "quick_2_kill"
    else:
        return None

    return HighlightMoment(
        round_id=round_impact.round_id,
        tick=kill_times[-1],
        type="quick_multi_kill",
        subtype=subtype,
        description=f"第 {round_impact.round_id} 回合快速连杀 ({subtype})",
        score=QUICK_KILL_SCORES[subtype],
        details={"kills": len(kill_times)},
    )


def _detect_clutch(
    player_name: str, round_impact: PlayerRoundImpact, round_context: RoundContext | None
) -> HighlightMoment | None:
    """Detect a clutch win (last alive player winning the round)."""
    if round_context is None or not round_context.ticks:
        return None

    player_is_team1 = player_name in round_context.team1_players
    player_team = "team1" if player_is_team1 else "team2"
    if round_context.winner != player_team:
        return None

    clutch_tick = None
    clutch_enemies = 0
    for tick in round_context.ticks:
        team1_alive, team2_alive = get_alive_count_at_tick(
            tick, round_context.team1_players, round_context.team2_players
        )
        own_alive = team1_alive if player_is_team1 else team2_alive
        enemy_alive = team2_alive if player_is_team1 else team1_alive
        if own_alive == 1 and enemy_alive >= 2 and _is_player_alive(tick, player_name):
            clutch_tick = tick.round_seconds
            clutch_enemies = enemy_alive
            break

    if clutch_tick is None:
        return None

    # The player must still be alive when the round is won.
    if not _is_player_alive(round_context.ticks[-1], player_name):
        return None

    return HighlightMoment(
        round_id=round_impact.round_id,
        tick=clutch_tick,
        type="clutch",
        subtype=f"1v{clutch_enemies}_clutch",
        description=f"第 {round_impact.round_id} 回合 1v{clutch_enemies} 残局获胜",
        score=CLUTCH_BASE_SCORE + CLUTCH_SCORE_PER_ENEMY * (clutch_enemies - 1),
        details={"enemies": clutch_enemies},
    )


def _detect_hard_duels(player_name: str, round_impact: PlayerRoundImpact) -> list[HighlightMoment]:
    """Detect hard duel wins (kill with the hard_duel_win label)."""
    moments = []
    for ki in round_impact.kills:
        if "hard_duel_win" not in ki.labels:
            continue
        opponent = ki.event.other_player or ""
        details: dict[str, Any] = {"opponent": opponent}
        if ki.duel_probability is not None:
            details["duel_probability"] = ki.duel_probability
        moments.append(HighlightMoment(
            round_id=round_impact.round_id,
            tick=ki.event.tick,
            type="hard_duel",
            subtype="hard_duel_win",
            description=f"第 {round_impact.round_id} 回合劣势对枪击杀 {opponent}",
            score=HARD_DUEL_SCORE,
            details=details,
        ))
    return moments


def _detect_he_multi_hit(
    player_name: str, round_impact: PlayerRoundImpact
) -> list[HighlightMoment]:
    """Detect HE grenades hitting multiple enemies."""
    moments = []
    for he in round_impact.he_events:
        victims = {
            damage.get("victim")
            for damage in he.damage_events
            if damage.get("victim") and not damage.get("team_damage", False)
        }
        hit_count = len(victims)
        if hit_count < 2:
            continue
        subtype = HE_MULTI_HIT_SUBTYPES.get(min(hit_count, 3), HE_MULTI_HIT_SUBTYPES[3])
        moments.append(HighlightMoment(
            round_id=round_impact.round_id,
            tick=he.tick,
            type="he_multi_hit",
            subtype=subtype,
            description=f"第 {round_impact.round_id} 回合手雷命中 {hit_count} 名敌人",
            score=HE_MULTI_HIT_SCORES[subtype],
            details={"victims": sorted(str(v) for v in victims)},
        ))
    return moments


def _detect_impactful_opening_kills(
    player_name: str, round_impact: PlayerRoundImpact
) -> list[HighlightMoment]:
    """Detect impactful opening kills (first bloods with a significant win rate swing)."""
    moments = []
    for ki in round_impact.kills:
        if "opening_kill" not in ki.labels:
            continue
        if ki.total_impact < IMPACTFUL_OPENING_MIN_IMPACT:
            continue
        opponent = ki.event.other_player or ""
        moments.append(HighlightMoment(
            round_id=round_impact.round_id,
            tick=ki.event.tick,
            type="impactful_opening_kill",
            subtype="high_impact_opening",
            description=f"第 {round_impact.round_id} 回合关键首杀击杀 {opponent}",
            score=IMPACTFUL_OPENING_SCORE,
            details={"opponent": opponent, "impact": ki.total_impact},
        ))
    return moments


def detect_highlight_moments(
    player_name: str,
    round_impacts: list[PlayerRoundImpact],
    round_contexts: list[RoundContext]
) -> list[HighlightMoment]:
    """Detect highlight moments for a player across all rounds.

    Args:
        player_name: Player to detect highlights for.
        round_impacts: Per-round impact results for the player.
        round_contexts: Round contexts matching the round ids (used for clutch detection).

    Returns:
        List of HighlightMoment sorted by (round_id, tick).
    """
    context_by_round: dict[int, RoundContext] = {
        rc.round_id: rc for rc in round_contexts
    }

    moments: list[HighlightMoment] = []
    for round_impact in round_impacts:
        round_context = context_by_round.get(round_impact.round_id)

        for moment in (
            _detect_multi_kill(player_name, round_impact),
            _detect_quick_multi_kill(player_name, round_impact),
            _detect_clutch(player_name, round_impact, round_context),
            *_detect_hard_duels(player_name, round_impact),
            *_detect_he_multi_hit(player_name, round_impact),
            *_detect_impactful_opening_kills(player_name, round_impact),
        ):
            if moment is not None:
                moments.append(moment)

    moments.sort(key=lambda m: (m.round_id, m.tick))
    return moments
