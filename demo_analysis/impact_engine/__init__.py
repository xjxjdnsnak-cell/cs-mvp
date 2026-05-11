"""CS2 个人回合影响力评分引擎 (Impact Engine).

该模块对 CS2 比赛进行深度影响力分析，评估每名玩家在每一回合中的真实影响力。

主要功能:
- 计算每名玩家的 RWI (Round Win Impact)
- 评估死亡风险来源 (自造风险 vs 合理高风险)
- 识别关键行为标签 (首杀、补枪、残局等)
- 生成中文复盘报告

使用方法:
    from demo_analysis.impact_engine import ImpactEngine

    engine = ImpactEngine()
    engine.load_from_file("analysis.json")
    report = engine.analyze()

或者使用命令行:
    python -m demo_analysis.impact_engine.cli -i analysis.json -o report.md
"""

from .align import (
    build_prediction_tick,
    build_round_context,
    extract_kill_events,
    find_nearest_tick,
    find_ticks_before,
    find_ticks_after,
    get_name_to_idx,
    get_player_side_win_rate,
    get_duel_probability,
    get_alive_count_at_tick,
    find_nearest_teammate,
)
from .config import IMPACT_WEIGHTS, get_weight, get_threshold
from .engine import ImpactEngine, analyze_file
from .models import (
    EventImpact,
    EventType,
    GameEvent,
    ImpactReport,
    PlayerMatchImpact,
    PlayerRoundImpact,
    PredictionTick,
    RiskAssessment,
    RiskType,
    RoundContext,
)
from .rules import EventLabels
from .report import (
    generate_match_report,
    generate_player_report,
    generate_conclusion,
    generate_improvement_suggestions,
    report_to_json,
)
from .risk import assess_death_risk, is_unexpected_death
from .rules import (
    label_event,
    EventLabels,
    LABEL_OPENING_KILL,
    LABEL_TRADE_KILL,
    LABEL_HARD_DUEL_WIN,
    LABEL_EASY_DUEL_LOSS,
    LABEL_BAD_DEATH,
)
from .scoring import (
    calculate_kill_impact,
    calculate_death_impact,
    calculate_player_round_impact,
    calculate_player_match_impact,
    determine_round_label,
)

__version__ = "1.0.0"

__all__ = [
    "ImpactEngine",
    "analyze_file",
    "build_prediction_tick",
    "build_round_context",
    "extract_kill_events",
    "find_nearest_tick",
    "find_ticks_before",
    "find_ticks_after",
    "get_name_to_idx",
    "get_player_side_win_rate",
    "get_duel_probability",
    "get_alive_count_at_tick",
    "find_nearest_teammate",
    "assess_death_risk",
    "is_unexpected_death",
    "label_event",
    "calculate_kill_impact",
    "calculate_death_impact",
    "calculate_player_round_impact",
    "calculate_player_match_impact",
    "determine_round_label",
    "generate_match_report",
    "generate_player_report",
    "generate_conclusion",
    "generate_improvement_suggestions",
    "report_to_json",
    "IMPACT_WEIGHTS",
    "get_weight",
    "get_threshold",
    "EventImpact",
    "EventLabels",
    "EventType",
    "GameEvent",
    "ImpactReport",
    "PlayerMatchImpact",
    "PlayerRoundImpact",
    "PredictionTick",
    "RiskAssessment",
    "RiskType",
    "RoundContext",
    "LABEL_OPENING_KILL",
    "LABEL_TRADE_KILL",
    "LABEL_HARD_DUEL_WIN",
    "LABEL_EASY_DUEL_LOSS",
    "LABEL_BAD_DEATH",
]
