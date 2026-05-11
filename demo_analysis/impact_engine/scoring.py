"""Impact scoring engine for CS2 match analysis."""

from typing import Any

from .align import (
    find_death_trade_kill,
    find_nearest_tick,
    find_ticks_before,
    find_ticks_after,
    get_alive_count_at_tick,
    get_duel_probability,
    get_name_to_idx,
    get_player_side_win_rate,
    safe_float,
    was_bomb_planted_before_tick,
)
from .config import get_weight
from .models import (
    EventImpact,
    EventType,
    GameEvent,
    PlayerMatchImpact,
    PlayerRoundImpact,
    PredictionTick,
    RiskAssessment,
    RiskType,
    RoundContext,
)
from .risk import assess_death_risk
from .rules import (
    EventLabels,
    label_event,
)
from .utility_flash import calculate_player_flash_impact
from .utility_fire import calculate_player_fire_impact
from .utility_he import calculate_player_he_impact
from .utility_smoke import calculate_player_smoke_impact


def calculate_win_rate_delta(
    event: GameEvent,
    before_tick: PredictionTick | None,
    after_tick: PredictionTick | None,
    team1_players: list[str],
    team1_on_ct: bool
) -> tuple[float, float, float]:
    """
    Calculate win rate delta for an event.
    Returns (before_wr, after_wr, delta).
    """
    if before_tick is None or after_tick is None:
        return 0.5, 0.5, 0.0

    before_wr = get_player_side_win_rate(
        before_tick.ct_win_rate, event.player, team1_players, team1_on_ct
    )
    after_wr = get_player_side_win_rate(
        after_tick.ct_win_rate, event.player, team1_players, team1_on_ct
    )

    delta = after_wr - before_wr
    return before_wr, after_wr, delta


def calculate_kill_impact(
    event: GameEvent,
    before_tick: PredictionTick | None,
    after_tick: PredictionTick | None,
    risk_window_ticks: list[PredictionTick],
    round_context: RoundContext,
    labels: EventLabels
) -> EventImpact:
    """Calculate impact score for a kill event."""
    impact = EventImpact(
        event=event,
        before_tick=before_tick,
        after_tick=after_tick,
        risk_window_ticks=risk_window_ticks,
    )

    before_wr, after_wr, win_rate_delta = calculate_win_rate_delta(
        event, before_tick, after_tick, round_context.team1_players, round_context.team1_on_ct
    )
    impact.before_win_rate = before_wr
    impact.after_win_rate = after_wr
    impact.win_rate_delta = win_rate_delta

    impact.base_impact = win_rate_delta * get_weight("win_rate_delta_multiplier", 100.0)

    name_to_idx = get_name_to_idx(round_context.ticks)
    duel_prob = get_duel_probability(
        before_tick, event.player, event.other_player, name_to_idx
    ) if before_tick else None
    impact.duel_probability = duel_prob

    hard_duel_threshold = get_weight("duel_thresholds.hard_duel_win_max_prob", 0.45)
    hard_duel_win_bonus = get_weight("kill_impact.hard_duel_win_bonus", 0.8)

    if labels.hard_duel_win and duel_prob is not None and duel_prob < hard_duel_threshold:
        impact.bonus_impact += hard_duel_win_bonus
        impact.labels.append("hard_duel_win")

    trade_window = get_weight("kill_impact.trade_window_seconds", 5.0)
    trade_bonus = get_weight("kill_impact.trade_bonus", 0.8)

    if labels.trade_kill:
        impact.bonus_impact += trade_bonus
        impact.labels.append("trade_kill")

    if labels.opening_kill:
        opening_bonus = get_weight("kill_impact.opening_kill_bonus", 0.5)
        impact.bonus_impact += opening_bonus
        impact.labels.append("opening_kill")

    objective_bonus = get_weight("kill_impact.objective_bonus", 0.5)
    if labels.clutch_kill:
        clutch_bonus = get_weight("kill_impact.clutch_bonus", 1.0)
        impact.bonus_impact += clutch_bonus
        impact.labels.append("clutch_kill")

    if labels.low_impact_kill:
        penalty_mult = get_weight("kill_impact.low_impact_penalty_multiplier", 0.5)
        impact.labels.append("low_impact_kill")

    if labels.exit_frag:
        exit_penalty = get_weight("kill_impact.exit_frag_penalty_multiplier", 0.5)
        impact.labels.append("exit_frag")

    if labels.low_impact_kill:
        impact.total_impact = impact.base_impact * get_weight("kill_impact.low_impact_penalty_multiplier", 0.5)
    elif labels.exit_frag:
        impact.total_impact = impact.base_impact * get_weight("kill_impact.exit_frag_penalty_multiplier", 0.5)
    else:
        impact.total_impact = impact.base_impact

    impact.total_impact += impact.bonus_impact

    return impact


def calculate_death_impact(
    event: GameEvent,
    before_tick: PredictionTick | None,
    after_tick: PredictionTick | None,
    risk_window_ticks: list[PredictionTick],
    round_context: RoundContext,
    risk_assessment: RiskAssessment,
    labels: EventLabels
) -> EventImpact:
    """Calculate impact score for a death event."""
    impact = EventImpact(
        event=event,
        before_tick=before_tick,
        after_tick=after_tick,
        risk_window_ticks=risk_window_ticks,
    )

    before_wr, after_wr, win_rate_delta = calculate_win_rate_delta(
        event, before_tick, after_tick, round_context.team1_players, round_context.team1_on_ct
    )
    impact.before_win_rate = before_wr
    impact.after_win_rate = after_wr
    impact.win_rate_delta = win_rate_delta

    impact.base_impact = win_rate_delta * get_weight("death_impact.win_rate_delta_multiplier", 1.0)

    risk_type = risk_assessment.risk_type
    confidence = risk_assessment.confidence

    forced_risk_bonus = get_weight("death_impact.forced_risk_bonus", 0.6)
    self_created_risk_penalty = get_weight("death_impact.self_created_risk_penalty", -1.2)

    if risk_type == RiskType.FORCED_RISK:
        impact.bonus_impact += forced_risk_bonus * confidence
        impact.labels.append("forced_risk_death")
    elif risk_type == RiskType.SELF_CREATED_RISK:
        impact.bonus_impact += self_created_risk_penalty * confidence
        impact.labels.append("self_created_risk_death")

    trade_window = get_weight("trade_impact.trade_window_seconds", 5.0)
    traded_death_bonus = get_weight("death_impact.traded_death_bonus", 0.8)
    trade_available_no_trade_penalty = get_weight("death_impact.trade_available_no_trade_penalty", -0.4)
    no_trade_no_info_penalty = get_weight("death_impact.no_trade_no_info_penalty", -0.2)

    victim = event.player
    killer = event.other_player

    if labels.traded_death:
        impact.bonus_impact += traded_death_bonus
        impact.labels.append("traded_death")
    elif risk_assessment.trade_available:
        impact.penalty += trade_available_no_trade_penalty
        impact.labels.append("trade_available_untraded")
    else:
        impact.penalty += no_trade_no_info_penalty

    post_plant_penalty = get_weight("death_impact.post_plant_throw_death_penalty", -1.2)
    if labels.post_plant_throw_death:
        impact.penalty += post_plant_penalty
        impact.labels.append("post_plant_throw_death")

    bomb_carrier_penalty = get_weight("death_impact.bomb_carrier_died_alone_penalty", -1.5)
    if labels.bomb_carrier_died_alone:
        impact.penalty += bomb_carrier_penalty
        impact.labels.append("bomb_carrier_died_alone")

    if labels.opening_death and risk_type == RiskType.SELF_CREATED_RISK:
        opening_death_self_penalty = get_weight("death_impact.opening_death_self_created_penalty", -0.8)
        impact.penalty += opening_death_self_penalty

    if labels.unexpected_death:
        unexpected_penalty = get_weight("death_impact.unexpected_death_penalty", -0.5)
        impact.penalty += unexpected_penalty
        impact.labels.append("unexpected_death")

    impact.total_impact = impact.base_impact + impact.bonus_impact + impact.penalty

    return impact


def calculate_objective_impact(
    event: GameEvent,
    round_context: RoundContext
) -> float:
    """Calculate bonus for objective play (bomb plant/defuse)."""
    if event.event_type == EventType.BOMB_PLANT:
        return get_weight("objective_impact.bomb_plant_bonus", 0.8)
    elif event.event_type == EventType.BOMB_DEFUSE:
        return get_weight("objective_impact.bomb_defuse_bonus", 1.0)
    return 0.0


def determine_round_label(round_impact: float) -> str:
    """Determine the round impact label based on score."""
    thresholds = get_weight("round_impact_thresholds", {})
    if round_impact >= thresholds.get("carry", 3.0):
        return "Carry Round"
    elif round_impact >= thresholds.get("high_impact", 1.5):
        return "High Impact Round"
    elif round_impact >= thresholds.get("positive", 0.5):
        return "Positive Round"
    elif round_impact > thresholds.get("negative", -0.5):
        return "Neutral Round"
    elif round_impact > thresholds.get("throw", -1.5):
        return "Negative Round"
    else:
        return "Throw Round"


def calculate_player_round_impact(
    player_name: str,
    round_context: RoundContext,
    events: list[GameEvent],
    player_risk_assessments: dict[str, RiskAssessment]
) -> PlayerRoundImpact:
    """Calculate complete impact for a player in a round."""
    player_events = [e for e in events if e.player == player_name]

    kills = []
    deaths = []
    objectives = []

    for event in player_events:
        if event.event_type == EventType.KILL:
            kills.append(event)
        elif event.event_type == EventType.DEATH:
            deaths.append(event)
        elif event.event_type in (EventType.BOMB_PLANT, EventType.BOMB_DEFUSE):
            objectives.append(event)

    kill_impacts: list[EventImpact] = []
    death_impacts: list[EventImpact] = []
    objective_impacts: list[EventImpact] = []
    risk_assessments: list[RiskAssessment] = []

    name_to_idx = get_name_to_idx(round_context.ticks)

    for kill in kills:
        before_tick = find_nearest_tick(round_context.ticks, kill.tick - 0.1)
        after_tick = find_nearest_tick(round_context.ticks, kill.tick + 0.1)
        risk_window = find_ticks_before(round_context.ticks, kill.tick, max_seconds=10.0)

        labels = label_event(
            kill, before_tick, after_tick, risk_window, round_context,
            player_risk_assessments.get(kill.player)
        )

        impact = calculate_kill_impact(
            kill, before_tick, after_tick, risk_window, round_context, labels
        )
        kill_impacts.append(impact)

    for death in deaths:
        before_tick = find_nearest_tick(round_context.ticks, death.tick - 0.1)
        after_tick = find_nearest_tick(round_context.ticks, death.tick + 0.1)
        risk_window = find_ticks_before(round_context.ticks, death.tick, max_seconds=10.0)

        risk_assessment = player_risk_assessments.get(death.player)
        if risk_assessment is None:
            risk_assessment = assess_death_risk(
                death, before_tick, risk_window, round_context
            )
        risk_assessments.append(risk_assessment)

        labels = label_event(
            death, before_tick, after_tick, risk_window, round_context, risk_assessment
        )

        impact = calculate_death_impact(
            death, before_tick, after_tick, risk_window, round_context,
            risk_assessment, labels
        )
        death_impacts.append(impact)

    for obj in objectives:
        obj_impact = calculate_objective_impact(obj, round_context)
        objective_impacts.append(EventImpact(
            event=obj,
            base_impact=obj_impact,
            total_impact=obj_impact,
        ))

    kill_impact_total = sum(ki.total_impact for ki in kill_impacts)
    death_impact_total = sum(di.total_impact for di in death_impacts)
    objective_impact_total = sum(oi.total_impact for oi in objective_impacts)

    trade_impact_total = 0.0
    for ki in kill_impacts:
        if "trade_kill" in ki.labels:
            trade_impact_total += get_weight("trade_impact.effective_trade_bonus", 0.6)

    clutch_impact_total = 0.0
    for ki in kill_impacts:
        if "clutch_kill" in ki.labels:
            clutch_impact_total += get_weight("objective_impact.clutch_win_bonus", 1.5)

    flash_impact_total, flash_events = calculate_player_flash_impact(player_name, round_context)
    smoke_impact_total, smoke_events = calculate_player_smoke_impact(player_name, round_context)
    fire_impact_total, fire_events = calculate_player_fire_impact(player_name, round_context)
    he_impact_total, he_events = calculate_player_he_impact(player_name, round_context)
    utility_impact_total = flash_impact_total + smoke_impact_total + fire_impact_total + he_impact_total

    round_total = (
        kill_impact_total
        + death_impact_total
        + trade_impact_total
        + objective_impact_total
        + clutch_impact_total
        + utility_impact_total
    )

    round_label = determine_round_label(round_total)

    player_team = "team1" if player_name in round_context.team1_players else "team2"

    player_round = PlayerRoundImpact(
        player_name=player_name,
        round_id=round_context.round_id,
        team=player_team,
        kills=kill_impacts,
        deaths=death_impacts,
        objectives=objective_impacts,
        risk_assessments=risk_assessments,
        kill_impact=kill_impact_total,
        death_impact=death_impact_total,
        trade_impact=trade_impact_total,
        objective_impact=objective_impact_total,
        clutch_impact=clutch_impact_total,
        utility_impact=utility_impact_total,
        flash_impact=flash_impact_total,
        flash_events=flash_events,
        smoke_impact=smoke_impact_total,
        smoke_events=smoke_events,
        fire_impact=fire_impact_total,
        fire_events=fire_events,
        he_impact=he_impact_total,
        he_events=he_events,
        round_total_impact=round_total,
        round_label=round_label,
    )

    if round_total >= get_weight("round_impact_thresholds.carry", 3.0):
        player_round.carry_round = True
    elif round_total <= get_weight("round_impact_thresholds.throw", -1.5):
        player_round.throw_round = True

    if round_context.ticks:
        first_tick = round_context.ticks[0]
        last_tick = round_context.ticks[-1]
        player_round.round_win_rate_start = get_player_side_win_rate(
            first_tick.ct_win_rate, player_name, round_context.team1_players, round_context.team1_on_ct
        )
        player_round.round_win_rate_end = get_player_side_win_rate(
            last_tick.ct_win_rate, player_name, round_context.team1_players, round_context.team1_on_ct
        )

    return player_round


def calculate_player_match_impact(
    player_name: str,
    team: str,
    round_impacts: list[PlayerRoundImpact],
    all_labels: dict[str, list[str]]
) -> PlayerMatchImpact:
    """Calculate complete match impact for a player."""
    thresholds = get_weight("round_impact_thresholds", {})
    round_count = len(round_impacts) if len(round_impacts) > 0 else 1

    high_impact_rounds = sum(1 for ri in round_impacts if ri.round_total_impact >= thresholds.get("high_impact", 1.5))
    positive_rounds = sum(1 for ri in round_impacts if ri.round_total_impact >= thresholds.get("positive", 0.5))
    neutral_rounds = sum(1 for ri in round_impacts if thresholds.get("positive", 0.5) > ri.round_total_impact >= thresholds.get("negative", -0.5))
    negative_rounds = sum(1 for ri in round_impacts if thresholds.get("negative", -0.5) > ri.round_total_impact >= thresholds.get("throw", -1.5))
    throw_rounds = sum(1 for ri in round_impacts if ri.round_total_impact < thresholds.get("throw", -1.5))

    player_labels = all_labels.get(player_name, [])

    hard_duel_wins = sum(1 for l in player_labels if l == "hard_duel_win")
    easy_duel_losses = sum(1 for l in player_labels if l == "easy_duel_loss")
    effective_trades = sum(1 for l in player_labels if l == "trade_kill")
    trades_taken = sum(1 for l in player_labels if l == "traded_death")
    opening_kills = sum(1 for l in player_labels if l == "opening_kill")
    opening_deaths = sum(1 for l in player_labels if l == "opening_death")
    clutch_kills = sum(1 for l in player_labels if l == "clutch_kill")
    exit_frags = sum(1 for l in player_labels if l == "exit_frag")
    low_impact_kills = sum(1 for l in player_labels if l == "low_impact_kill")
    bad_deaths = sum(1 for l in player_labels if l == "bad_death" or l == "self_created_risk_death")
    self_created_risk_deaths = sum(1 for l in player_labels if l == "self_created_risk_death")
    forced_risk_deaths = sum(1 for l in player_labels if l == "forced_risk_death")
    unexpected_deaths = sum(1 for l in player_labels if l == "unexpected_death")
    post_plant_throw_deaths = sum(1 for l in player_labels if l == "post_plant_throw_death")
    bomb_carrier_died_alone = sum(1 for l in player_labels if l == "bomb_carrier_died_alone")
    flash_labels = [label for ri in round_impacts for flash in ri.flash_events for label in flash.labels]
    flash_score = sum(ri.flash_impact for ri in round_impacts)
    effective_flashes = sum(
        1 for ri in round_impacts for flash in ri.flash_events
        if any(label in flash.labels for label in ("effective_team_flash", "converted_flash", "strong_blind", "full_blind", "forced_turn_kill"))
    )
    converted_flashes = sum(1 for l in flash_labels if l == "converted_flash")
    forced_turn_kills = sum(1 for l in flash_labels if l == "forced_turn_kill")
    severe_team_flashes = sum(1 for l in flash_labels if l == "severe_team_flash")
    harmless_team_flashes = sum(1 for l in flash_labels if l == "harmless_team_flash")
    team_flash_with_conversions = sum(1 for l in flash_labels if l == "team_flash_with_conversion")
    smoke_labels = [label for ri in round_impacts for smoke in ri.smoke_events for label in smoke.labels]
    smoke_score = sum(ri.smoke_impact for ri in round_impacts)
    successful_fake_smokes = sum(1 for l in smoke_labels if l == "successful_fake_smoke")
    fatal_leaky_smokes = sum(1 for l in smoke_labels if l == "fatal_leaky_smoke")
    blocking_teammate_smokes = sum(1 for l in smoke_labels if l == "blocking_teammate_smoke")
    converted_execute_smokes = sum(1 for l in smoke_labels if l == "converted_execute_smoke")
    fire_labels = [label for ri in round_impacts for fire in ri.fire_events for label in fire.labels]
    fire_score = sum(ri.fire_impact for ri in round_impacts)
    anti_rush_fires = sum(1 for l in fire_labels if l == "anti_rush_fire")
    post_plant_fires = sum(1 for l in fire_labels if l == "post_plant_fire")
    anti_defuse_fires = sum(1 for l in fire_labels if l == "anti_defuse_fire")
    forced_position_fires = sum(1 for l in fire_labels if l == "forced_position_fire")
    kill_fires = sum(1 for l in fire_labels if l == "kill_fire")
    harmful_fires = sum(1 for l in fire_labels if l == "harmful_fire")
    forced_smoke_extinguishes = sum(1 for l in fire_labels if l == "forced_smoke_extinguish")
    he_labels = [label for ri in round_impacts for he in ri.he_events for label in he.labels]
    he_score = sum(ri.he_impact for ri in round_impacts)
    he_damage_total = sum(
        int(damage.get("damage", 0))
        for ri in round_impacts
        for he in ri.he_events
        for damage in he.damage_events
        if not damage.get("team_damage", False)
    )
    he_kills = sum(1 for l in he_labels if l == "kill_he")
    anti_smoke_he_kills = sum(1 for l in he_labels if l in ("anti_smoke_he_direct_kill", "anti_smoke_route_he_kill"))
    anti_smoke_route_hes = sum(1 for l in he_labels if l == "anti_smoke_route_he")
    anti_defuse_hes = sum(1 for l in he_labels if l == "anti_defuse_he")
    anti_plant_hes = sum(1 for l in he_labels if l == "anti_plant_he")
    anti_rush_hes = sum(1 for l in he_labels if l == "anti_rush_he")
    nade_stack_hits = sum(1 for l in he_labels if l == "nade_stack_damage")
    low_value_hes = sum(1 for l in he_labels if l == "low_value_he")
    harmful_hes = sum(1 for l in he_labels if l == "harmful_he")

    model_impact_score = calculate_model_impact_score(round_impacts, player_labels)
    rule_quality_score = calculate_rule_quality_score(
        round_impacts, player_labels,
        effective_trades, trades_taken, bad_deaths,
        self_created_risk_deaths, forced_risk_deaths
    )

    model_weight = get_weight("model_vs_rule_weight.model_impact", 0.65)
    rule_weight = get_weight("model_vs_rule_weight.rule_quality", 0.35)

    total_score = model_impact_score * model_weight + rule_quality_score * rule_weight

    rating = total_score
    # 使用按回合数归一化的方法
    total_round_impact = sum(ri.round_total_impact for ri in round_impacts)
    avg_round_impact = total_round_impact / round_count

    # 基础 50 分，加上平均回合影响放大
    rating_0_100 = 50 + avg_round_impact * 10
    
    # 加上高影响回合和送人头回合的修正
    rating_0_100 += high_impact_rounds * 3
    rating_0_100 -= throw_rounds * 3
    rating_0_100 -= self_created_risk_deaths * 1
    
    # 限制在 0-100 之间
    rating_0_100 = max(0.0, min(100.0, rating_0_100))

    kills_total = sum(len(ri.kills) for ri in round_impacts)
    deaths_total = sum(len(ri.deaths) for ri in round_impacts)

    positive_events = []
    negative_events = []

    for ri in round_impacts:
        for ki in ri.kills:
            if ki.total_impact > 1.0 or "hard_duel_win" in ki.labels or "trade_kill" in ki.labels:
                positive_events.append({
                    "round": ri.round_id,
                    "type": "kill",
                    "impact": ki.total_impact,
                    "win_rate_delta": ki.win_rate_delta,
                    "labels": ki.labels,
                    "opponent": ki.event.other_player,
                })

        for di in ri.deaths:
            if di.total_impact < -0.5 or "bad_death" in di.labels or "self_created_risk_death" in di.labels:
                negative_events.append({
                    "round": ri.round_id,
                    "type": "death",
                    "impact": di.total_impact,
                    "win_rate_delta": di.win_rate_delta,
                    "labels": di.labels,
                    "opponent": di.event.other_player,
                })

    positive_flash_events = []
    negative_flash_events = []
    positive_smoke_events = []
    negative_smoke_events = []
    positive_fire_events = []
    negative_fire_events = []
    positive_he_events = []
    negative_he_events = []
    for ri in round_impacts:
        for flash in ri.flash_events:
            event_data = {
                "round": ri.round_id,
                "type": "flash",
                "tick": flash.tick,
                "impact": flash.score,
                "labels": flash.labels,
                "affected_enemies": flash.affected_enemies,
                "affected_teammates": flash.affected_teammates,
                "converted_kills": flash.converted_kills,
                "reasons": flash.reasons,
            }
            if flash.score > 0:
                positive_flash_events.append(event_data)
            elif flash.score < 0 or any(l in flash.labels for l in ("severe_team_flash", "harmful_team_flash", "no_flash_effect")):
                negative_flash_events.append(event_data)
        for smoke in ri.smoke_events:
            event_data = {
                "round": ri.round_id,
                "type": "smoke",
                "tick": smoke.tick,
                "impact": smoke.score,
                "intent": smoke.intent,
                "labels": smoke.labels,
                "reasons": smoke.reasons,
                "target_matched": smoke.target_matched,
                "block_score": smoke.block_score,
                "leak_risk": smoke.leak_risk,
                "conversion_score": smoke.conversion_score,
                "teammate_dependency": smoke.teammate_dependency,
                "enemy_exploitation": smoke.enemy_exploitation,
            }
            if smoke.score > 0:
                positive_smoke_events.append(event_data)
            elif smoke.score < 0 or any(l in smoke.labels for l in ("fatal_leaky_smoke", "blocking_teammate_smoke", "missed_smoke", "leaky_smoke")):
                negative_smoke_events.append(event_data)
        for fire in ri.fire_events:
            event_data = {
                "round": ri.round_id,
                "type": "fire",
                "tick": fire.tick,
                "impact": fire.score,
                "fire_type": fire.fire_type,
                "intent": fire.intent,
                "labels": fire.labels,
                "damage_events": fire.damage_events,
                "forced_movements": fire.forced_movements,
                "conversions": fire.conversions,
                "reasons": fire.reasons,
            }
            if fire.score > 0:
                positive_fire_events.append(event_data)
            elif fire.score < 0 or any(l in fire.labels for l in ("harmful_fire", "teammate_blocking_fire", "team_damage_fire", "wasted_fire")):
                negative_fire_events.append(event_data)
        for he in ri.he_events:
            event_data = {
                "round": ri.round_id,
                "type": "he",
                "tick": he.tick,
                "impact": he.score,
                "labels": he.labels,
                "damage_events": he.damage_events,
                "kill_events": he.kill_events,
                "smoke_context": he.smoke_context,
                "objective_context": he.objective_context,
                "reasons": he.reasons,
            }
            if he.score > 0:
                positive_he_events.append(event_data)
            elif he.score < 0 or any(l in he.labels for l in ("harmful_he", "team_damage_he", "low_value_he", "wasted_he")):
                negative_he_events.append(event_data)

    positive_events.sort(key=lambda x: x["impact"], reverse=True)
    negative_events.sort(key=lambda x: x["impact"])
    positive_flash_events.sort(key=lambda x: x["impact"], reverse=True)
    negative_flash_events.sort(key=lambda x: x["impact"])
    positive_smoke_events.sort(key=lambda x: x["impact"], reverse=True)
    negative_smoke_events.sort(key=lambda x: x["impact"])
    positive_fire_events.sort(key=lambda x: x["impact"], reverse=True)
    negative_fire_events.sort(key=lambda x: x["impact"])
    positive_he_events.sort(key=lambda x: x["impact"], reverse=True)
    negative_he_events.sort(key=lambda x: x["impact"])

    return PlayerMatchImpact(
        player_name=player_name,
        team=team,
        round_impacts=round_impacts,
        total_score=total_score,
        model_impact_score=model_impact_score,
        rule_quality_score=rule_quality_score,
        high_impact_rounds=high_impact_rounds,
        positive_rounds=positive_rounds,
        neutral_rounds=neutral_rounds,
        negative_rounds=negative_rounds,
        throw_rounds=throw_rounds,
        hard_duel_wins=hard_duel_wins,
        easy_duel_losses=easy_duel_losses,
        effective_trades=effective_trades,
        trades_taken=trades_taken,
        opening_kills=opening_kills,
        opening_deaths=opening_deaths,
        clutch_kills=clutch_kills,
        exit_frags=exit_frags,
        low_impact_kills=low_impact_kills,
        bad_deaths=bad_deaths,
        self_created_risk_deaths=self_created_risk_deaths,
        forced_risk_deaths=forced_risk_deaths,
        unexpected_deaths=unexpected_deaths,
        post_plant_throw_deaths=post_plant_throw_deaths,
        bomb_carrier_died_alone=bomb_carrier_died_alone,
        effective_flashes=effective_flashes,
        converted_flashes=converted_flashes,
        forced_turn_kills=forced_turn_kills,
        severe_team_flashes=severe_team_flashes,
        harmless_team_flashes=harmless_team_flashes,
        team_flash_with_conversions=team_flash_with_conversions,
        flash_score=flash_score,
        smoke_score=smoke_score,
        successful_fake_smokes=successful_fake_smokes,
        fatal_leaky_smokes=fatal_leaky_smokes,
        blocking_teammate_smokes=blocking_teammate_smokes,
        converted_execute_smokes=converted_execute_smokes,
        fire_score=fire_score,
        anti_rush_fires=anti_rush_fires,
        post_plant_fires=post_plant_fires,
        anti_defuse_fires=anti_defuse_fires,
        forced_position_fires=forced_position_fires,
        kill_fires=kill_fires,
        harmful_fires=harmful_fires,
        forced_smoke_extinguishes=forced_smoke_extinguishes,
        he_score=he_score,
        he_damage_total=he_damage_total,
        he_kills=he_kills,
        anti_smoke_he_kills=anti_smoke_he_kills,
        anti_smoke_route_hes=anti_smoke_route_hes,
        anti_defuse_hes=anti_defuse_hes,
        anti_plant_hes=anti_plant_hes,
        anti_rush_hes=anti_rush_hes,
        nade_stack_hits=nade_stack_hits,
        low_value_hes=low_value_hes,
        harmful_hes=harmful_hes,
        positive_kill_events=positive_events[:5],
        negative_death_events=negative_events[:5],
        positive_flash_events=positive_flash_events[:5],
        negative_flash_events=negative_flash_events[:5],
        positive_smoke_events=positive_smoke_events[:5],
        negative_smoke_events=negative_smoke_events[:5],
        positive_fire_events=positive_fire_events[:5],
        negative_fire_events=negative_fire_events[:5],
        positive_he_events=positive_he_events[:5],
        negative_he_events=negative_he_events[:5],
        kda=(kills_total, deaths_total, sum(1 for ri in round_impacts for _ in ri.deaths)),
        rating=rating,
        rating_0_100=rating_0_100,
    )


def calculate_model_impact_score(
    round_impacts: list[PlayerRoundImpact],
    player_labels: list[str]
) -> float:
    """Calculate the model-based impact score."""
    if not round_impacts:
        return 0.0

    total_rwi = sum(ri.round_total_impact for ri in round_impacts)

    hard_duel_wins = sum(1 for l in player_labels if l == "hard_duel_win")
    easy_duel_losses = sum(1 for l in player_labels if l == "easy_duel_loss")
    unexpected_deaths = sum(1 for l in player_labels if l == "unexpected_death")

    base_score = total_rwi * 10

    hard_duel_bonus = hard_duel_wins * 0.8
    easy_duel_penalty = easy_duel_losses * 0.6
    unexpected_penalty = unexpected_deaths * 0.4

    model_score = base_score + hard_duel_bonus - easy_duel_penalty - unexpected_penalty

    return max(-50, min(50, model_score))


def calculate_rule_quality_score(
    round_impacts: list[PlayerRoundImpact],
    player_labels: list[str],
    effective_trades: int,
    trades_taken: int,
    bad_deaths: int,
    self_created_risk_deaths: int,
    forced_risk_deaths: int
) -> float:
    """Calculate the rule-based quality score."""
    trade_bonus = effective_trades * 0.5
    trade_penalty = trades_taken * 0.3
    bad_death_penalty = bad_deaths * 0.8
    self_created_penalty = self_created_risk_deaths * 0.6
    forced_risk_bonus = forced_risk_deaths * 0.3

    rule_score = trade_bonus + forced_risk_bonus - trade_penalty - bad_death_penalty - self_created_penalty

    return max(-50, min(50, rule_score))
