"""Rule-based event labeling for impact analysis."""

from typing import Any

from .align import (
    find_death_trade_kill,
    find_nearest_tick,
    find_ticks_after,
    find_ticks_before,
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


LABEL_OPENING_KILL = "opening_kill"
LABEL_OPENING_DEATH = "opening_death"
LABEL_TRADE_KILL = "trade_kill"
LABEL_TRADED_DEATH = "traded_death"
LABEL_UNTRADED_DEATH = "untraded_death"
LABEL_BAD_DEATH = "bad_death"
LABEL_ENTRY_SACRIFICE_DEATH = "entry_sacrifice_death"
LABEL_POST_PLANT_THROW_DEATH = "post_plant_throw_death"
LABEL_BOMB_CARRIER_DIED_ALONE = "bomb_carrier_died_alone"
LABEL_CLUTCH_KILL = "clutch_kill"
LABEL_CLUTCH_ATTEMPT_DEATH = "clutch_attempt_death"
LABEL_EXIT_FRAG = "exit_frag"
LABEL_LOW_IMPACT_KILL = "low_impact_kill"
LABEL_HARD_DUEL_WIN = "hard_duel_win"
LABEL_EASY_DUEL_LOSS = "easy_duel_loss"
LABEL_HIGH_WINRATE_SWING = "high_winrate_swing"
LABEL_UNEXPECTED_DEATH = "unexpected_death"
LABEL_RISK_CREATED_DEATH = "risk_created_death"
LABEL_FORCED_RISK_DEATH = "forced_risk_death"


class EventLabels:
    """Container for event labels."""
    opening_kill: bool = False
    opening_death: bool = False
    trade_kill: bool = False
    traded_death: bool = False
    untraded_death: bool = False
    bad_death: bool = False
    entry_sacrifice_death: bool = False
    post_plant_throw_death: bool = False
    bomb_carrier_died_alone: bool = False
    clutch_kill: bool = False
    clutch_attempt_death: bool = False
    exit_frag: bool = False
    low_impact_kill: bool = False
    hard_duel_win: bool = False
    easy_duel_loss: bool = False
    high_winrate_swing: bool = False
    unexpected_death: bool = False
    risk_created_death: bool = False
    forced_risk_death: bool = False

    def to_list(self) -> list[str]:
        """Convert labels to list of strings."""
        labels = []
        for attr, value in vars(EventLabels).items():
            if attr.startswith("_") or callable(value):
                continue
            if isinstance(value, bool) and getattr(self, attr, False):
                labels.append(attr)
        return labels

    def get_all_labels(self) -> list[str]:
        """Get all active labels."""
        labels = []
        for attr in dir(self):
            if attr.startswith("_"):
                continue
            val = getattr(self, attr)
            if isinstance(val, bool) and val:
                labels.append(attr)
        return labels


def is_opening_event(
    event: GameEvent,
    ticks: list[PredictionTick],
    team1_players: list[str],
    team2_players: list[str],
    window_seconds: float = 5.0
) -> bool:
    """Check if this is an opening kill (both players alive at round start)."""
    if event.event_type == EventType.DEATH:
        return False

    if not ticks:
        return False

    start_tick = ticks[0]
    team1_alive, team2_alive = get_alive_count_at_tick(start_tick, team1_players, team2_players)

    if team1_alive + team2_alive < 9:
        return False

    if event.tick > window_seconds:
        return False

    killer = event.player
    victim = event.other_player

    killer_alive = False
    victim_alive = False
    for p in start_tick.players_info:
        name = p.get("name")
        if name == killer and p.get("is_alive", False):
            killer_alive = True
        if name == victim and p.get("is_alive", False):
            victim_alive = True

    return killer_alive and victim_alive


def check_trade(
    death_event: GameEvent,
    all_events: list[GameEvent],
    team1_players: list[str],
    team2_players: list[str],
    trade_window: float = 5.0
) -> tuple[bool, bool]:
    """
    Check if death was traded (someone avenged within window).
    Returns (was_traded, is_trade_kill_for_this_event).
    
    Note: For a death event, is_trade_kill_for_this_event will always be False.
    """
    if death_event.event_type != EventType.DEATH:
        return False, False

    victim = death_event.player
    killer = death_event.other_player

    if not killer:
        return False, False

    trade_kill_event = find_death_trade_kill(
        death_event.tick, victim, killer, all_events, trade_window
    )

    was_traded = trade_kill_event is not None

    return was_traded, False


def is_trade_kill(
    kill_event: GameEvent,
    all_events: list[GameEvent],
    team1_players: list[str],
    team2_players: list[str],
    trade_window: float = 5.0
) -> bool:
    """
    Check if this kill is a trade kill (killer avenged a teammate within window).
    A trade kill happens when a killer kills someone after a teammate was killed by that person.
    """
    if kill_event.event_type != EventType.KILL:
        return False

    killer = kill_event.player
    victim = kill_event.other_player

    if not victim:
        return False

    killer_team = "team1" if killer in team1_players else "team2"

    # Find a recent death of a teammate, killed by the victim we're now killing
    for event in all_events:
        if event.event_type != EventType.DEATH:
            continue
        
        dead_player = event.player
        dead_player_team = "team1" if dead_player in team1_players else "team2"
        
        if dead_player_team != killer_team:
            continue  # Not a teammate
        
        time_gap = kill_event.tick - event.tick
        if 0 < time_gap <= trade_window:
            if event.other_player == victim:
                # Teammate was killed by the same guy we're now killing - this is a trade!
                return True

    return False


def is_opening_death(
    event: GameEvent,
    ticks: list[PredictionTick],
    team1_players: list[str],
    team2_players: list[str],
    window_seconds: float = 5.0
) -> bool:
    """Check if this is an opening death (both players alive at round start)."""
    if event.event_type != EventType.DEATH:
        return False

    if not ticks:
        return False

    start_tick = ticks[0]
    team1_alive, team2_alive = get_alive_count_at_tick(start_tick, team1_players, team2_players)

    if team1_alive + team2_alive < 9:
        return False

    if event.tick > window_seconds:
        return False

    victim = event.player
    killer = event.other_player

    if not killer:
        return False

    victim_alive = False
    killer_alive = False
    for p in start_tick.players_info:
        name = p.get("name")
        if name == victim and p.get("is_alive", False):
            victim_alive = True
        if name == killer and p.get("is_alive", False):
            killer_alive = True

    return victim_alive and killer_alive


def is_exit_frag(
    event: GameEvent,
    before_tick: PredictionTick | None,
    round_context: RoundContext
) -> bool:
    """Check if this is an exit frag (killing someone when their team already won)."""
    if event.event_type != EventType.KILL:
        return False

    if before_tick is None:
        return False

    bomb_planted = was_bomb_planted_before_tick(round_context.ticks, event.tick)
    if not bomb_planted:
        return False

    plant_time = round_context.bomb_planted_time
    if plant_time is None:
        return False

    time_since_plant = event.tick - plant_time
    if time_since_plant < 35:
        return False

    victim = event.other_player
    victim_team = "team1" if victim in round_context.team1_players else "team2"

    winner = round_context.winner
    if winner == victim_team:
        return True

    return False


def is_low_impact_kill(
    event: GameEvent,
    before_tick: PredictionTick | None,
    round_context: RoundContext,
    name_to_idx: dict[str, int]
) -> bool:
    """
    Check if a kill is low impact (eco round, man advantage, exit frag situation).
    """
    if event.event_type != EventType.KILL:
        return False

    victim = event.other_player
    if victim is None:
        return False

    if before_tick is None:
        return False

    victim_team = "team1" if victim in round_context.team1_players else "team2"

    team1_alive, team2_alive = get_alive_count_at_tick(
        before_tick, round_context.team1_players, round_context.team2_players
    )

    player_is_on_team1 = event.player in round_context.team1_players
    player_team_alive = team1_alive if player_is_on_team1 else team2_alive
    enemy_team_alive = team2_alive if player_is_on_team1 else team1_alive

    man_advantage = player_team_alive - enemy_team_alive
    man_threshold = get_weight("kill_impact.man_advantage_threshold", 3)

    if man_advantage >= man_threshold:
        return True

    if exit_frag := is_exit_frag(event, before_tick, round_context):
        return True

    start_inv = getattr(round_context, "start_inventory", None)
    if start_inv:
        victim_inv = None
        for inv in start_inv:
            if inv.get("player") == victim:
                victim_inv = inv
                break

        if victim_inv:
            inventory = victim_inv.get("inventory") or []
            if not any(w in inventory for w in ["AK-47", "M4A4", "M4A1-S", "AWP", "Galil AR", "FAMAS"]):
                return True

    return False


def check_hard_duel_win(
    event: GameEvent,
    before_tick: PredictionTick | None,
    name_to_idx: dict[str, int],
    threshold: float = 0.45
) -> bool:
    """Check if this is a hard duel win (duel prob < threshold)."""
    if event.event_type != EventType.KILL:
        return False

    if before_tick is None:
        return False

    duel_prob = get_duel_probability(
        before_tick, event.player, event.other_player, name_to_idx
    )

    if duel_prob is not None and duel_prob < threshold:
        return True

    return False


def check_easy_duel_loss(
    event: GameEvent,
    before_tick: PredictionTick | None,
    name_to_idx: dict[str, int],
    threshold: float = 0.65
) -> bool:
    """Check if this is an easy duel loss (duel prob > threshold)."""
    if event.event_type != EventType.DEATH:
        return False

    if before_tick is None:
        return False

    duel_prob = get_duel_probability(
        before_tick, event.other_player, event.player, name_to_idx
    )

    if duel_prob is not None and duel_prob > threshold:
        return True

    return False


def is_clutch_kill(
    event: GameEvent,
    before_tick: PredictionTick | None,
    round_context: RoundContext
) -> bool:
    """Check if this is a clutch situation kill."""
    if event.event_type != EventType.KILL:
        return False

    if before_tick is None:
        return False

    player = event.player
    player_is_on_team1 = player in round_context.team1_players

    team1_alive, team2_alive = get_alive_count_at_tick(
        before_tick, round_context.team1_players, round_context.team2_players
    )

    player_alive = team1_alive if player_is_on_team1 else team2_alive
    enemy_alive = team2_alive if player_is_on_team1 else team1_alive

    if player_alive <= 1 and enemy_alive <= 2 and (player_alive + enemy_alive) <= 3:
        return True

    return False


def is_post_plant_throw_death(
    event: GameEvent,
    before_tick: PredictionTick | None,
    round_context: RoundContext
) -> bool:
    """Check if death occurred after plant in a bad position."""
    if event.event_type != EventType.DEATH:
        return False

    if not was_bomb_planted_before_tick(round_context.ticks, event.tick):
        return False

    team1_alive, team2_alive = get_alive_count_at_tick(
        before_tick, round_context.team1_players, round_context.team2_players
    )

    player_is_on_team1 = event.player in round_context.team1_players
    
    if round_context.team1_on_ct:
        # team1 是 CT，team2 是 T
        t_side = "team2"
        ct_side = "team1"
    else:
        # team1 是 T，team2 是 CT
        t_side = "team1"
        ct_side = "team2"
        
    player_is_t = (t_side == "team1" and player_is_on_team1) or (t_side == "team2" and not player_is_on_team1)

    t_alive = team1_alive if t_side == "team1" else team2_alive
    ct_alive = team1_alive if ct_side == "team1" else team2_alive

    if player_is_t and ct_alive <= 2 and t_alive >= ct_alive:
        return True

    return False


def is_bomb_carrier_died_alone(
    event: GameEvent,
    before_tick: PredictionTick | None,
    round_context: RoundContext,
    name_to_idx: dict[str, int]
) -> bool:
    """Check if bomb carrier died alone without plant."""
    if event.event_type != EventType.DEATH:
        return False

    if before_tick is None:
        return False

    player = event.player

    is_carrier = False
    for p in before_tick.players_info:
        if p.get("name") == player:
            inventory = p.get("inventory") or []
            if "C4" in inventory:
                is_carrier = True
                break

    if not is_carrier:
        return False

    bomb_planted = was_bomb_planted_before_tick(round_context.ticks, event.tick)
    if bomb_planted:
        return False

    return True


def label_event(
    event: GameEvent,
    before_tick: PredictionTick | None,
    after_tick: PredictionTick | None,
    risk_window_ticks: list[PredictionTick],
    round_context: RoundContext,
    risk_assessment: RiskAssessment | None = None
) -> EventLabels:
    """Apply all labels to an event."""
    labels = EventLabels()
    name_to_idx = get_name_to_idx(round_context.ticks)

    labels.opening_kill = is_opening_event(
        event, round_context.ticks, round_context.team1_players, round_context.team2_players
    )

    labels.opening_death = is_opening_death(
        event, round_context.ticks, round_context.team1_players, round_context.team2_players
    )

    if event.event_type == EventType.DEATH:
        was_traded, _ = check_trade(
            event, 
            round_context.events, 
            round_context.team1_players,
            round_context.team2_players,
            get_weight("trade_impact.trade_window_seconds", 5.0)
        )
        labels.traded_death = was_traded
        labels.untraded_death = not was_traded
    if event.event_type == EventType.KILL:
        labels.trade_kill = is_trade_kill(
            event, 
            round_context.events, 
            round_context.team1_players,
            round_context.team2_players,
            get_weight("trade_impact.trade_window_seconds", 5.0)
        )

    labels.exit_frag = is_exit_frag(event, before_tick, round_context)

    labels.low_impact_kill = is_low_impact_kill(event, before_tick, round_context, name_to_idx)

    hard_duel_threshold = get_weight("duel_thresholds.hard_duel_win_max_prob", 0.45)
    easy_duel_threshold = get_weight("duel_thresholds.easy_duel_loss_min_prob", 0.65)

    labels.hard_duel_win = check_hard_duel_win(event, before_tick, name_to_idx, hard_duel_threshold)
    labels.easy_duel_loss = check_easy_duel_loss(event, before_tick, name_to_idx, easy_duel_threshold)

    labels.clutch_kill = is_clutch_kill(event, before_tick, round_context)

    labels.post_plant_throw_death = is_post_plant_throw_death(event, before_tick, round_context)

    labels.bomb_carrier_died_alone = is_bomb_carrier_died_alone(event, before_tick, round_context, name_to_idx)

    if before_tick is not None:
        early_ticks = risk_window_ticks[:3] if len(risk_window_ticks) >= 3 else risk_window_ticks
        if early_ticks:
            player_idx = name_to_idx.get(event.player)
            if player_idx is not None and player_idx < len(early_ticks[0].alive_pred):
                early_prob = early_ticks[0].alive_pred[player_idx]
                if early_prob > 0.70 and event.event_type == EventType.DEATH:
                    labels.unexpected_death = True

    if risk_assessment is not None:
        if risk_assessment.risk_type == RiskType.SELF_CREATED_RISK:
            labels.risk_created_death = True
            labels.bad_death = True
        elif risk_assessment.risk_type == RiskType.FORCED_RISK:
            labels.forced_risk_death = True

    if before_tick is not None and after_tick is not None:
        wr_delta = abs(after_tick.ct_win_rate - before_tick.ct_win_rate)
        if wr_delta > 0.15:
            labels.high_winrate_swing = True

    return labels


def get_opening_death_risk_labels(
    labels: EventLabels,
    risk_assessment: RiskAssessment | None
) -> list[str]:
    """Get additional risk-related labels for opening deaths."""
    additional = []
    if labels.opening_death:
        if risk_assessment and risk_assessment.risk_type == RiskType.SELF_CREATED_RISK:
            additional.append("opening_death_self_created")
        elif risk_assessment and risk_assessment.risk_type == RiskType.FORCED_RISK:
            additional.append("opening_death_forced")
    return additional
