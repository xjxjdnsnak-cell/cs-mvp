"""Tests for flashbang utility scoring."""

import unittest

from demo_analysis.impact_engine.models import (
    EventType,
    FlashImpact,
    GameEvent,
    PlayerMatchImpact,
    PlayerRoundImpact,
    PredictionTick,
    RoundContext,
)
from demo_analysis.impact_engine.report import generate_player_report
from demo_analysis.impact_engine.utility_flash import (
    calculate_player_flash_impact,
    compute_effective_blind,
    detect_forced_turn,
    score_enemy_flash,
    score_team_flash,
)


class TestEffectiveBlind(unittest.TestCase):
    def test_full_alpha(self):
        self.assertEqual(compute_effective_blind(3.0, 255), 3.0)

    def test_partial_alpha(self):
        self.assertAlmostEqual(compute_effective_blind(3.0, 85), 1.0)

    def test_missing_alpha(self):
        self.assertEqual(compute_effective_blind(2.2, None), 2.2)


class TestEnemyFlashScoring(unittest.TestCase):
    def test_enemy_weak_flash_no_effect(self):
        impact = score_enemy_flash("A", 1, 10.0, "E", 0.5)
        self.assertIn("weak_flash", impact.labels)
        self.assertIn("no_flash_effect", impact.labels)
        self.assertAlmostEqual(impact.score, 0.0)

    def test_partial_blind_without_conversion_is_low_value(self):
        impact = score_enemy_flash("A", 1, 10.0, "E", 2.0)
        self.assertIn("partial_blind", impact.labels)
        self.assertNotIn("full_blind", impact.labels)
        self.assertNotIn("direct_blind", impact.labels)
        self.assertLessEqual(impact.score, 0.2)

    def test_partial_blind_with_conversion(self):
        impact = score_enemy_flash(
            "A",
            1,
            10.0,
            "E",
            2.0,
            converted_kills=[{"killer": "B", "victim": "E", "tick": 12.0}],
        )
        self.assertIn("partial_blind", impact.labels)
        self.assertIn("converted_flash", impact.labels)
        self.assertGreaterEqual(impact.score, 0.4)
        self.assertLess(impact.score, 1.0)

    def test_strong_blind(self):
        impact = score_enemy_flash("A", 1, 10.0, "E", 2.9)
        self.assertIn("strong_blind", impact.labels)
        self.assertIn("direct_blind", impact.labels)
        self.assertGreaterEqual(impact.score, 0.8)

    def test_full_blind(self):
        impact = score_enemy_flash("A", 1, 10.0, "E", 3.6)
        self.assertIn("full_blind", impact.labels)
        self.assertIn("direct_blind", impact.labels)
        self.assertGreaterEqual(impact.score, 1.0)

    def test_forced_turn_kill(self):
        forced, strong, _ = detect_forced_turn(0.2, 10.0, 140.0)
        impact = score_enemy_flash(
            "A",
            1,
            10.0,
            "E",
            0.2,
            converted_kills=[{"killer": "A", "victim": "E", "tick": 12.0}],
            forced_turn=forced,
            strong_forced_turn=strong,
            forced_turn_kill=True,
        )
        self.assertIn("forced_turn", impact.labels)
        self.assertIn("strong_forced_turn", impact.labels)
        self.assertIn("forced_turn_kill", impact.labels)
        self.assertGreaterEqual(impact.score, 0.8)

    def test_no_effect_low_yaw(self):
        forced, strong, _ = detect_forced_turn(0.2, 10.0, 30.0)
        impact = score_enemy_flash(
            "A",
            1,
            10.0,
            "E",
            0.2,
            forced_turn=forced,
            strong_forced_turn=strong,
        )
        self.assertIn("no_flash_effect", impact.labels)
        self.assertAlmostEqual(impact.score, 0.0)

    def test_missing_yaw_does_not_force_turn(self):
        forced, strong, yaw_delta = detect_forced_turn(0.2, None, 130.0)
        self.assertFalse(forced)
        self.assertFalse(strong)
        self.assertIsNone(yaw_delta)


class TestTeamFlashScoring(unittest.TestCase):
    def test_harmless_team_flash(self):
        impact = score_team_flash("A", 1, 10.0, "B", 0.5)
        self.assertIn("harmless_team_flash", impact.labels)
        self.assertEqual(impact.score, 0.0)

    def test_team_flash_with_conversion_minor(self):
        impact = score_team_flash(
            "A",
            1,
            10.0,
            "B",
            1.0,
            friendly_kill_within_3s=True,
        )
        self.assertIn("team_flash_with_conversion", impact.labels)
        self.assertIn("effective_team_flash", impact.labels)
        self.assertGreaterEqual(impact.score, 0.0)

    def test_team_flash_with_conversion_partial(self):
        impact = score_team_flash(
            "A",
            1,
            10.0,
            "B",
            2.2,
            friendly_kill_within_3s=True,
        )
        self.assertNotIn("severe_team_flash", impact.labels)
        self.assertIn("effective_team_flash", impact.labels)
        self.assertIn("team_flash_with_conversion", impact.labels)
        self.assertGreater(impact.score, 0.0)

    def test_team_flash_partial_no_conversion(self):
        impact = score_team_flash("A", 1, 10.0, "B", 2.2)
        self.assertNotIn("severe_team_flash", impact.labels)
        self.assertGreaterEqual(impact.score, 0.0)

    def test_severe_team_flash(self):
        impact = score_team_flash(
            "A",
            1,
            10.0,
            "B",
            3.0,
            teammate_died_while_flashed=True,
            teammate_active=True,
        )
        self.assertIn("severe_team_flash", impact.labels)
        self.assertLessEqual(impact.score, -1.0)

    def test_team_flash_strong_with_tradeoff(self):
        impact = score_team_flash(
            "A",
            1,
            10.0,
            "B",
            3.0,
            friendly_kill_within_3s=True,
            teammate_active=True,
        )
        self.assertIn("team_flash_with_conversion", impact.labels)
        self.assertGreater(impact.score, -1.0)


class TestFlashIntegration(unittest.TestCase):
    def test_assisted_flash_attribution_and_missing_position(self):
        context = RoundContext(
            round_id=1,
            ticks=[
                PredictionTick(
                    round_seconds=10.0,
                    ct_win_rate=0.5,
                    alive_pred=[],
                    next_kill=[],
                    next_death=[],
                    duel=None,
                    players_info=[
                        {"name": "A", "is_alive": True, "team_num": "CT", "inventory": ["Flashbang"]},
                        {"name": "B", "is_alive": True, "team_num": "CT"},
                        {"name": "E", "is_alive": True, "team_num": "T", "flash_duration": 2.0},
                    ],
                )
            ],
            events=[
                GameEvent(
                    event_type=EventType.KILL,
                    tick=12.0,
                    player="B",
                    other_player="E",
                    assister="A",
                    assisted_flash=True,
                )
            ],
            team1_players=["A", "B"],
            team2_players=["E"],
            team1_on_ct=True,
            winner="team1",
        )
        score, events = calculate_player_flash_impact("A", context)
        self.assertGreater(score, 0.0)
        self.assertEqual(len(events), 1)
        self.assertIn("partial_blind", events[0].labels)
        self.assertIn("converted_flash", events[0].labels)


class TestFlashReportWording(unittest.TestCase):
    def test_partial_blind_report_wording(self):
        flash = FlashImpact(
            thrower="A",
            round_id=1,
            tick=10.0,
            score=0.6,
            labels=["partial_blind", "converted_flash"],
            affected_enemies=[{"player": "E", "effective_blind": 2.0, "label": "partial_blind"}],
            affected_teammates=[],
            converted_kills=[{"killer": "B", "victim": "E", "tick": 12.0}],
            reasons=[],
        )
        player = PlayerMatchImpact(
            player_name="A",
            team="team1",
            round_impacts=[
                PlayerRoundImpact(
                    player_name="A",
                    round_id=1,
                    team="team1",
                    flash_impact=0.6,
                    utility_impact=0.6,
                    flash_events=[flash],
                )
            ],
            flash_score=0.6,
            converted_flashes=1,
            positive_flash_events=[{
                "round": 1,
                "tick": 10.0,
                "impact": 0.6,
                "labels": flash.labels,
                "affected_enemies": flash.affected_enemies,
                "affected_teammates": [],
                "converted_kills": flash.converted_kills,
                "reasons": [],
            }],
        )
        markdown = generate_player_report(player)
        self.assertNotIn("全白", markdown)
        self.assertTrue("半白" in markdown or "视野受损" in markdown)


if __name__ == "__main__":
    unittest.main()
