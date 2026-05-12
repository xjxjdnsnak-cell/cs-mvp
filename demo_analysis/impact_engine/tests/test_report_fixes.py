"""Tests for report formatting fixes."""

import unittest
from unittest.mock import MagicMock

from demo_analysis.impact_engine.report import generate_match_report
from demo_analysis.impact_engine.models import (
    PlayerMatchImpact,
    PlayerRoundImpact,
    ImpactReport,
)
from demo_analysis.impact_engine.timeline import (
    generate_player_timeline,
    generate_match_timeline_markdown,
)


def create_mock_player_round_impact(round_id: int, tactical_events: list = None) -> PlayerRoundImpact:
    """Create a mock PlayerRoundImpact with tactical events."""
    ri = PlayerRoundImpact(
        player_name="TestPlayer",
        round_id=round_id,
        team="team1",
        round_total_impact=0.0,
        player_side="CT",
    )
    ri.tactical_events = tactical_events or []
    return ri


class TestTeamNameFormatting(unittest.TestCase):
    """Test that team names use Team 1 / Team 2 instead of player names."""

    def test_team_names_are_not_player_names(self):
        """Markdown team titles should be Team 1 / Team 2, not player names."""
        match_info = {
            "team1_round_wins": 10,
            "team2_round_wins": 8,
            "winner": "team1",
            "team1_players": ["PlayerA", "PlayerB"],
            "team2_players": ["PlayerC", "PlayerD"],
        }

        ri = PlayerRoundImpact(
            player_name="PlayerA",
            round_id=1,
            team="team1",
            round_total_impact=0.0,
            player_side="CT",
        )
        player = PlayerMatchImpact(
            player_name="PlayerA",
            team="team1",
            round_impacts=[ri],
            rating_0_100=70.0,
        )
        player.kda = (5, 3, 0)

        report = ImpactReport(
            match_info=match_info,
            player_impacts=[player],
            team1_name="Team 1",
            team2_name="Team 2",
            match_winner="team1",
            total_rounds=18,
            map_name="de_mirage",
        )

        markdown = generate_match_report(report)
        lines = markdown.split("\n")

        team1_line = next((l for l in lines if l.startswith("### Team")), None)
        self.assertIsNotNone(team1_line, "Should have Team header")

        team_headers = [l for l in lines if l.startswith("###")]
        for header in team_headers:
            self.assertNotIn("PlayerA", header, "Team header should not be player name")
            self.assertNotIn("PlayerC", header, "Team header should not be player name")


class TestTimelineColons(unittest.TestCase):
    """Test that timeline player names don't have extra colons."""

    def test_match_timeline_has_no_player_colons(self):
        """Match timeline tactical events should not have 'player: reason' format."""
        ri = PlayerRoundImpact(
            player_name="TestPlayer",
            round_id=1,
            team="team1",
            round_total_impact=0.0,
            player_side="CT",
            tactical_events=[
                {
                    "player": "TestPlayer",
                    "round_id": 1,
                    "tick": 20.0,
                    "label": "key_area_isolated_death",
                    "score": -0.8,
                    "reason": "独自前压拱门死亡",
                    "area": "connector",
                    "area_cn": "拱门",
                    "phase": "map_control",
                }
            ],
        )
        player = PlayerMatchImpact(
            player_name="TestPlayer",
            team="team1",
            round_impacts=[ri],
            rating_0_100=50.0,
        )
        player.kda = (1, 1, 0)

        report = ImpactReport(
            match_info={},
            player_impacts=[player],
            team1_name="Team 1",
            team2_name="Team 2",
            match_winner="team1",
            total_rounds=1,
            map_name="de_mirage",
        )

        lines = generate_match_timeline_markdown(report)
        for line in lines:
            self.assertNotIn(": ", line, f"Tactical event should not have 'player: reason' format: {line}")


class TestMarkdownRawScoreHidden(unittest.TestCase):
    """Test that model_impact_score_raw is not shown in Markdown."""

    def test_markdown_does_not_show_raw_score(self):
        """Markdown should not display model_impact_score_raw."""
        ri = PlayerRoundImpact(
            player_name="TestPlayer",
            round_id=1,
            team="team1",
            round_total_impact=0.0,
            player_side="CT",
        )
        player = PlayerMatchImpact(
            player_name="TestPlayer",
            team="team1",
            round_impacts=[ri],
            rating_0_100=50.0,
            model_impact_score=5.0,
            model_impact_score_raw=999.0,
            rule_quality_score=50.0,
        )
        player.kda = (1, 1, 0)

        report = ImpactReport(
            match_info={},
            player_impacts=[player],
            team1_name="Team 1",
            team2_name="Team 2",
            match_winner="team1",
            total_rounds=1,
            map_name="de_mirage",
        )

        markdown = generate_match_report(report)

        self.assertNotIn("999", markdown, "Markdown should not show raw score 999")
        self.assertNotIn("raw", markdown.lower(), "Markdown should not mention 'raw' score")


class TestTacticalCopyDowngrade(unittest.TestCase):
    """Test that tactical copy uses softer language."""

    def test_mid_control_copy_does_not_say_获得控制(self):
        """Tactical events should not say '获得控制' unless confirmed."""
        tactical_events = [
            {
                "player": "TestPlayer",
                "round_id": 1,
                "tick": 20.0,
                "label": "mid_control_success",
                "score": 0.3,
                "reason": "玩家在中路参与中路控制",
                "area": "mid_boxes",
                "area_cn": "中路箱",
                "phase": "map_control",
            }
        ]

        timeline = generate_player_timeline(
            PlayerMatchImpact(
                player_name="TestPlayer",
                team="team1",
                round_impacts=[
                    create_mock_player_round_impact(1, tactical_events)
                ],
                rating_0_100=50.0,
            )
        )

        for entry in timeline:
            for event in entry.get("events", []):
                self.assertNotIn("获得控制", event, "Should not say '获得控制' for mid_control_success")
                self.assertNotIn("失去控制", event, "Should not say '失去控制'")


class TestTacticalEventLimit(unittest.TestCase):
    """Test that tactical events are limited to 3 per round."""

    def test_tactical_events_limited_to_3(self):
        """Timeline should limit tactical events to 3 per round with +N more."""
        tactical_events = [
            {
                "player": "TestPlayer",
                "round_id": 1,
                "tick": 10.0 + i,
                "label": "post_plant_discipline_error",
                "score": -0.5,
                "reason": f"战术事件{i}",
                "area": "a_site",
                "area_cn": "A点",
                "phase": "post_plant",
            }
            for i in range(5)
        ]

        timeline = generate_player_timeline(
            PlayerMatchImpact(
                player_name="TestPlayer",
                team="team1",
                round_impacts=[
                    create_mock_player_round_impact(1, tactical_events)
                ],
                rating_0_100=50.0,
            )
        )

        self.assertEqual(len(timeline), 1)
        entry = timeline[0]

        tactical_event_count = sum(1 for e in entry.get("events", []) if isinstance(e, str) and ("战术事件" in e))
        self.assertLessEqual(tactical_event_count, 3, "Should have at most 3 tactical events per round")

        if len(entry.get("events", [])) > 3:
            events_str = "; ".join(entry.get("events", []))
            self.assertIn("(+", events_str, "Should show +N more when events are truncated")


if __name__ == "__main__":
    unittest.main()
