"""Data models for the CS2 Impact Engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskType(Enum):
    """Risk classification for player deaths."""
    FORCED_RISK = "forced_risk"
    SELF_CREATED_RISK = "self_created_risk"
    UNKNOWN_RISK = "unknown_risk"


class EventType(Enum):
    """Types of game events."""
    KILL = "kill"
    DEATH = "death"
    BOMB_PLANT = "bomb_plant"
    BOMB_DEFUSE = "bomb_defuse"
    DAMAGE = "damage"


@dataclass
class PredictionTick:
    """Single tick prediction from CS-NET model."""
    round_seconds: float
    ct_win_rate: float
    alive_pred: list[float]
    next_kill: list[float]
    next_death: list[float]
    duel: list[list[float | str]] | None
    players_info: list[dict[str, Any]]
    is_bomb_planted: bool = False
    bomb_planted_time: float | None = None
    # Utility scoring / raw tick context
    projectiles: list[dict[str, Any]] = field(default_factory=list)
    entity_grenades: list[dict[str, Any]] = field(default_factory=list)
    future_kills: list[dict[str, Any]] = field(default_factory=list)
    future_damage: list[dict[str, Any]] = field(default_factory=list)
    bomb_position: Any = None

    def get_player_side_win_rate(
        self, 
        player_name: str, 
        team1_players: list[str],
        team1_on_ct: bool
    ) -> float:
        """Get win rate from player's perspective.
        
        Args:
            player_name: Player name
            team1_players: List of team1 players
            team1_on_ct: If True, team1 is playing as CT in this round
        """
        player_on_team1 = player_name in team1_players
        
        if team1_on_ct:
            # team1 is CT, team2 is T
            if player_on_team1:
                return self.ct_win_rate  # player is CT
            else:
                return 1.0 - self.ct_win_rate  # player is T
        else:
            # team1 is T, team2 is CT
            if player_on_team1:
                return 1.0 - self.ct_win_rate  # player is T
            else:
                return self.ct_win_rate  # player is CT

    def get_alive_pred_for_player(self, player_name: str, name_to_idx: dict[str, int]) -> float:
        """Get alive prediction probability for a player."""
        idx = name_to_idx.get(player_name)
        if idx is None or idx >= len(self.alive_pred):
            return 0.5
        return self.alive_pred[idx]


@dataclass
class GameEvent:
    """A game event (kill, death, plant, defuse)."""
    event_type: EventType
    tick: float
    player: str
    other_player: str | None = None
    weapon: str | None = None
    assister: str | None = None
    headshot: bool = False
    assisted_flash: bool = False
    attacker_blind: bool = False
    attacker_in_air: bool = False
    through_smoke: bool = False
    damage_health: int | None = None
    team_num: str | None = None


@dataclass
class EventImpact:
    """Impact score for a single event."""
    event: GameEvent
    before_tick: PredictionTick | None = None
    after_tick: PredictionTick | None = None
    risk_window_ticks: list[PredictionTick] = field(default_factory=list)

    before_win_rate: float = 0.5
    after_win_rate: float = 0.5
    win_rate_delta: float = 0.0

    duel_probability: float | None = None

    labels: list[str] = field(default_factory=list)

    base_impact: float = 0.0
    bonus_impact: float = 0.0
    penalty: float = 0.0
    total_impact: float = 0.0


@dataclass
class FlashImpact:
    """Impact score for a single attributed flashbang."""
    thrower: str
    round_id: int
    tick: float
    score: float
    labels: list[str]
    affected_enemies: list[dict[str, Any]]
    affected_teammates: list[dict[str, Any]]
    converted_kills: list[dict[str, Any]]
    reasons: list[str]


@dataclass
class SmokeImpact:
    """Impact score for a single attributed smoke grenade."""
    thrower: str
    round_id: int
    tick: float
    intent: str
    score: float
    labels: list[str]
    reasons: list[str]
    target_matched: bool
    block_score: float
    leak_risk: str
    conversion_score: float
    teammate_dependency: float
    enemy_exploitation: float


@dataclass
class FireImpact:
    """Impact score for a single attributed fire grenade."""
    thrower: str
    round_id: int
    tick: float
    fire_type: str
    intent: str
    score: float
    labels: list[str]
    damage_events: list[dict[str, Any]]
    forced_movements: list[dict[str, Any]]
    conversions: list[dict[str, Any]]
    reasons: list[str]


@dataclass
class HEImpact:
    """Impact score for a single attributed HE grenade."""
    thrower: str
    round_id: int
    tick: float
    score: float
    labels: list[str]
    damage_events: list[dict[str, Any]]
    kill_events: list[dict[str, Any]]
    smoke_context: dict[str, Any] | None
    objective_context: dict[str, Any] | None
    reasons: list[str]


@dataclass
class RiskAssessment:
    """Assessment of death risk for a player."""
    risk_type: RiskType
    confidence: float
    reasons: list[str]
    alive_prob_drop: float
    nearest_teammate_distance: float | None
    trade_available: bool
    objective_pressure: bool
    team_alive_advantage: int
    player_position: tuple[float, float, float] | None = None
    teammate_positions: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class PlayerRoundImpact:
    """Impact analysis for a player in a single round."""
    player_name: str
    round_id: int
    team: str

    kills: list[EventImpact] = field(default_factory=list)
    deaths: list[EventImpact] = field(default_factory=list)
    trades: list[EventImpact] = field(default_factory=list)
    objectives: list[EventImpact] = field(default_factory=list)
    clutch_attempts: list[EventImpact] = field(default_factory=list)

    risk_assessments: list[RiskAssessment] = field(default_factory=list)

    kill_impact: float = 0.0
    death_impact: float = 0.0
    trade_impact: float = 0.0
    objective_impact: float = 0.0
    clutch_impact: float = 0.0
    utility_impact: float = 0.0
    flash_impact: float = 0.0
    flash_events: list[FlashImpact] = field(default_factory=list)
    smoke_impact: float = 0.0
    smoke_events: list[SmokeImpact] = field(default_factory=list)
    fire_impact: float = 0.0
    fire_events: list[FireImpact] = field(default_factory=list)
    he_impact: float = 0.0
    he_events: list[HEImpact] = field(default_factory=list)

    round_total_impact: float = 0.0
    round_label: str = "Neutral Round"

    round_win_rate_start: float = 0.5
    round_win_rate_end: float = 0.5

    carry_round: bool = False
    throw_round: bool = False

    key_positives: list[str] = field(default_factory=list)
    key_negatives: list[str] = field(default_factory=list)


@dataclass
class PlayerMatchImpact:
    """Complete impact analysis for a player across all rounds."""
    player_name: str
    team: str

    round_impacts: list[PlayerRoundImpact] = field(default_factory=list)

    total_score: float = 0.0
    model_impact_score: float = 0.0
    rule_quality_score: float = 0.0

    high_impact_rounds: int = 0
    positive_rounds: int = 0
    neutral_rounds: int = 0
    negative_rounds: int = 0
    throw_rounds: int = 0

    bad_deaths: int = 0
    self_created_risk_deaths: int = 0
    forced_risk_deaths: int = 0
    unexpected_deaths: int = 0

    hard_duel_wins: int = 0
    easy_duel_losses: int = 0
    effective_trades: int = 0
    trades_taken: int = 0

    opening_kills: int = 0
    opening_deaths: int = 0
    clutch_kills: int = 0
    clutch_attempt_deaths: int = 0
    exit_frags: int = 0
    low_impact_kills: int = 0

    post_plant_throw_deaths: int = 0
    bomb_carrier_died_alone: int = 0

    effective_flashes: int = 0
    converted_flashes: int = 0
    forced_turn_kills: int = 0
    severe_team_flashes: int = 0
    harmless_team_flashes: int = 0
    team_flash_with_conversions: int = 0
    flash_score: float = 0.0

    smoke_score: float = 0.0
    successful_fake_smokes: int = 0
    fatal_leaky_smokes: int = 0
    blocking_teammate_smokes: int = 0
    converted_execute_smokes: int = 0

    fire_score: float = 0.0
    anti_rush_fires: int = 0
    post_plant_fires: int = 0
    anti_defuse_fires: int = 0
    forced_position_fires: int = 0
    kill_fires: int = 0
    harmful_fires: int = 0
    forced_smoke_extinguishes: int = 0

    he_score: float = 0.0
    he_damage_total: int = 0
    he_kills: int = 0
    anti_smoke_he_kills: int = 0
    anti_smoke_route_hes: int = 0
    anti_defuse_hes: int = 0
    anti_plant_hes: int = 0
    anti_rush_hes: int = 0
    nade_stack_hits: int = 0
    low_value_hes: int = 0
    harmful_hes: int = 0

    positive_kill_events: list[dict[str, Any]] = field(default_factory=list)
    negative_death_events: list[dict[str, Any]] = field(default_factory=list)
    positive_flash_events: list[dict[str, Any]] = field(default_factory=list)
    negative_flash_events: list[dict[str, Any]] = field(default_factory=list)
    positive_smoke_events: list[dict[str, Any]] = field(default_factory=list)
    negative_smoke_events: list[dict[str, Any]] = field(default_factory=list)
    positive_fire_events: list[dict[str, Any]] = field(default_factory=list)
    negative_fire_events: list[dict[str, Any]] = field(default_factory=list)
    positive_he_events: list[dict[str, Any]] = field(default_factory=list)
    negative_he_events: list[dict[str, Any]] = field(default_factory=list)

    # Diagnostic fields for score calibration visibility
    avg_round_impact: float = 0.0
    total_round_impact: float = 0.0
    model_impact_score_raw: float = 0.0
    model_impact_score_clipped: float = 0.0
    rule_quality_score_raw: float = 0.0
    rule_quality_score_clipped: float = 0.0
    kill_impact_total: float = 0.0
    death_impact_total: float = 0.0

    kda: tuple[int, int, int] = (0, 0, 0)
    rating: float = 0.0
    rating_0_100: float = 0.0

    confidence: str = "high"


@dataclass
class ImpactReport:
    """Complete impact report for all players."""
    match_info: dict[str, Any]
    player_impacts: list[PlayerMatchImpact]
    team1_name: str = "Team 1"
    team2_name: str = "Team 2"
    match_winner: str = "Unknown"
    total_rounds: int = 0
    map_name: str = "Unknown"

    confidence: str = "high"
    warnings: list[str] = field(default_factory=list)


@dataclass
class RoundContext:
    """Context information for a round."""
    round_id: int
    ticks: list[PredictionTick]
    events: list[GameEvent]
    team1_players: list[str]
    team2_players: list[str]
    team1_on_ct: bool
    winner: str
    bomb_planted_time: float | None = None
    bomb_defused_time: float | None = None
    team1_alive_count: int = 5
    team2_alive_count: int = 5
    map_name: str = "Unknown"
