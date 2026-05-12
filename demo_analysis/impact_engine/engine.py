"""Main impact engine that orchestrates the analysis pipeline."""

import json
from pathlib import Path
from typing import Any

from .align import (
    build_prediction_tick,
    build_round_context,
    extract_kill_events,
    find_nearest_tick,
    find_ticks_before,
    get_name_to_idx,
)
from .models import (
    EventType,
    GameEvent,
    ImpactReport,
    PlayerMatchImpact,
    PlayerRoundImpact,
    RiskAssessment,
    RoundContext,
)
from .rules import EventLabels
from .report import (
    generate_match_report,
    generate_player_report,
    report_to_json,
)
from .risk import assess_death_risk
from .rules import label_event
from .scoring import (
    calculate_player_match_impact,
    calculate_player_round_impact,
)
from .utility_diagnostics import (
    add_score_extreme_diagnostics,
    build_round_utility_diagnostics,
    empty_utility_diagnostics,
    merge_utility_diagnostics,
)
from .rating import normalize_player_ratings


class ImpactEngine:
    """Main engine for computing player impact scores."""

    def __init__(self, dashboard_payload: dict[str, Any] | None = None):
        """
        Initialize the impact engine.

        Args:
            dashboard_payload: Optional pre-loaded dashboard data from high_level_analysis.build_dashboard_payload()
        """
        self.dashboard_payload = dashboard_payload
        self.rounds: list[dict[str, Any]] = []
        self.match_info: dict[str, Any] = {}
        self.warnings: list[str] = []
        
        if self.dashboard_payload:
            self._extract_data()

    def load_from_file(self, path: str | Path) -> None:
        """Load dashboard payload from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            self.dashboard_payload = json.load(f)
        self._extract_data()

    def load_from_dashboard_payload(self, payload: dict[str, Any]) -> None:
        """Load from a dashboard payload dict."""
        self.dashboard_payload = payload
        self._extract_data()

    def _extract_data(self) -> None:
        """Extract rounds and match info from dashboard payload."""
        if self.dashboard_payload is None:
            return

        self.rounds = self.dashboard_payload.get("rounds", [])
        self.match_info = self.dashboard_payload.get("match", {})
        self.warnings = []

        if not self.rounds:
            self.warnings.append("未找到回合数据")
        if not self.match_info:
            self.warnings.append("未找到比赛信息")

    def analyze(self) -> ImpactReport:
        """Run the complete impact analysis."""
        if self.dashboard_payload is None:
            raise ValueError("No data loaded. Call load_from_file() or load_from_dashboard_payload() first.")

        player_impact_map: dict[str, PlayerMatchImpact] = {}
        all_player_labels: dict[str, list[str]] = {}
        player_risk_map: dict[str, dict[str, RiskAssessment]] = {}
        utility_diagnostics = empty_utility_diagnostics()

        team1_players = self.match_info.get("team1_players", [])
        team2_players = self.match_info.get("team2_players", [])

        for round_data in self.rounds:
            round_id = round_data.get("round_id", 0)
            team1_on_ct = round_data.get("team1_on_ct", True)
            winner = round_data.get("winner", "Unknown")

            round_context = build_round_context(
                round_data,
                team1_players,
                team2_players
            )
            utility_diagnostics = merge_utility_diagnostics(
                utility_diagnostics,
                build_round_utility_diagnostics(round_context, team1_players + team2_players),
            )

            player_risk_assessments: dict[str, RiskAssessment] = {}
            player_events: dict[str, list[GameEvent]] = {}

            for event in round_context.events:
                if event.event_type == EventType.DEATH:
                    before_tick = find_nearest_tick(round_context.ticks, event.tick - 0.1)
                    risk_window = find_ticks_before(round_context.ticks, event.tick, max_seconds=10.0)

                    risk_assessment = assess_death_risk(
                        event, before_tick, risk_window, round_context
                    )
                    player_risk_assessments[event.player] = risk_assessment

            for player in team1_players + team2_players:
                if player not in player_risk_map:
                    player_risk_map[player] = {}

                player_round_impacts: list[PlayerRoundImpact] = []

                if player not in player_events:
                    player_events[player] = []

                player_round_impact = calculate_player_round_impact(
                    player,
                    round_context,
                    round_context.events,
                    player_risk_assessments
                )

                if player not in player_impact_map:
                    team = "team1" if player in team1_players else "team2"
                    player_impact_map[player] = PlayerMatchImpact(
                        player_name=player,
                        team=team,
                    )
                    player_impact_map[player].round_impacts = []

                player_impact_map[player].round_impacts.append(player_round_impact)

                for kill in player_round_impact.kills:
                    for label_name in kill.labels:
                        if player not in all_player_labels:
                            all_player_labels[player] = []
                        all_player_labels[player].append(label_name)

                for death in player_round_impact.deaths:
                    for label_name in death.labels:
                        if player not in all_player_labels:
                            all_player_labels[player] = []
                        all_player_labels[player].append(label_name)

        for player, impact in player_impact_map.items():
            updated = calculate_player_match_impact(
                player,
                impact.team,
                impact.round_impacts,
                all_player_labels
            )
            player_impact_map[player] = updated

        player_impacts = list(player_impact_map.values())

        rating_stats = normalize_player_ratings(player_impacts)
        
        utility_diagnostics = add_score_extreme_diagnostics(utility_diagnostics, player_impacts)
        if rating_stats:
            utility_diagnostics.update(rating_stats)
        
        clip_total = (
            utility_diagnostics.get("model_impact_clip_count_min", 0)
            + utility_diagnostics.get("model_impact_clip_count_max", 0)
        )
        if clip_total >= max(2, len(player_impacts) // 4):
            self.warnings.append("model_impact_score appears heavily clipped; rating calibration may need adjustment.")

        map_name = self.rounds[0].get("map_name", "Unknown") if self.rounds else "Unknown"
        total_rounds = len(self.rounds)

        winner_team = self.match_info.get("winner", "Unknown")

        team1_name = self.match_info.get("team1_players", ["Team 1"])
        team2_name = self.match_info.get("team2_players", ["Team 2"])
        if isinstance(team1_name, list) and team1_name:
            team1_name = team1_name[0]
        if isinstance(team2_name, list) and team2_name:
            team2_name = team2_name[0]

        report = ImpactReport(
            match_info=self.match_info,
            player_impacts=player_impacts,
            team1_name=str(team1_name),
            team2_name=str(team2_name),
            match_winner=winner_team,
            total_rounds=total_rounds,
            map_name=map_name,
            confidence="medium" if len(self.warnings) > 0 else "high",
            warnings=self.warnings,
            utility_diagnostics=utility_diagnostics,
        )

        return report

    def generate_markdown_report(self) -> str:
        """Generate markdown report."""
        report = self.analyze()
        return generate_match_report(report)

    def generate_json_output(self) -> dict[str, Any]:
        """Generate JSON output."""
        report = self.analyze()
        return report_to_json(report)


def analyze_file(
    input_path: str | Path,
    output_md_path: str | Path | None = None,
    output_json_path: str | Path | None = None
) -> ImpactReport:
    """
    Analyze a demo analysis JSON file and generate reports.

    Args:
        input_path: Path to the analysis JSON file
        output_md_path: Optional path for markdown output
        output_json_path: Optional path for JSON output

    Returns:
        ImpactReport object
    """
    from demo_analysis.high_level_analysis import build_dashboard_payload

    with open(input_path, "r", encoding="utf-8") as f:
        raw_results = json.load(f)

    dashboard_payload = build_dashboard_payload(raw_results)

    engine = ImpactEngine(dashboard_payload)
    report = engine.analyze()

    if output_json_path:
        json_output = report_to_json(report)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)

    if output_md_path:
        md_output = generate_match_report(report)
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(md_output)

    return report
