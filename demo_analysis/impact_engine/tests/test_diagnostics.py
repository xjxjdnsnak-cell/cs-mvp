"""Tests for diagnostic fields and score calibration visibility."""

import unittest

from demo_analysis.impact_engine.models import PlayerMatchImpact, PlayerRoundImpact
from demo_analysis.impact_engine.scoring import (
    calculate_model_impact_score_raw,
    calculate_rule_quality_score_raw,
)
from demo_analysis.impact_engine.report import report_to_json
from demo_analysis.impact_engine.models import ImpactReport


class TestModelImpactScoreRaw(unittest.TestCase):
    """Test raw vs clipped model impact score calculation."""

    def test_normal_score_no_clipping(self):
        round_impacts = [
            PlayerRoundImpact(player_name="P1", round_id=1, team="team1", round_total_impact=2.0)
        ]
        labels = []
        raw, clipped = calculate_model_impact_score_raw(round_impacts, labels)
        self.assertEqual(raw, 20.0)  # 2.0 * 10
        self.assertEqual(clipped, 20.0)

    def test_high_score_clipped_at_max(self):
        round_impacts = [
            PlayerRoundImpact(player_name="P1", round_id=1, team="team1", round_total_impact=10.0)
        ]
        labels = ["hard_duel_win"] * 10
        raw, clipped = calculate_model_impact_score_raw(round_impacts, labels)
        self.assertGreater(raw, 50.0)  # Should be > 50
        self.assertEqual(clipped, 50.0)  # Clipped at max

    def test_low_score_clipped_at_min(self):
        round_impacts = [
            PlayerRoundImpact(player_name="P1", round_id=1, team="team1", round_total_impact=-10.0)
        ]
        labels = ["easy_duel_loss"] * 10
        raw, clipped = calculate_model_impact_score_raw(round_impacts, labels)
        self.assertLess(raw, -50.0)  # Should be < -50
        self.assertEqual(clipped, -50.0)  # Clipped at min


class TestRuleQualityScoreRaw(unittest.TestCase):
    """Test raw vs clipped rule quality score calculation."""

    def test_normal_score_no_clipping(self):
        round_impacts = []
        labels = []
        raw, clipped = calculate_rule_quality_score_raw(
            round_impacts, labels, effective_trades=5, trades_taken=0,
            bad_deaths=0, self_created_risk_deaths=0, forced_risk_deaths=0
        )
        self.assertEqual(raw, 2.5)  # 5 * 0.5
        self.assertEqual(clipped, 2.5)

    def test_high_penalty_clipped_at_min(self):
        round_impacts = []
        labels = []
        raw, clipped = calculate_rule_quality_score_raw(
            round_impacts, labels, effective_trades=0, trades_taken=0,
            bad_deaths=50, self_created_risk_deaths=50, forced_risk_deaths=0
        )
        self.assertLess(raw, -50.0)
        self.assertEqual(clipped, -50.0)


class TestReportDiagnostics(unittest.TestCase):
    """Test report_to_json includes diagnostics."""

    def test_player_diagnostics_fields(self):
        player = PlayerMatchImpact(
            player_name="TestPlayer",
            team="team1",
            avg_round_impact=1.5,
            total_round_impact=15.0,
            model_impact_score_raw=25.0,
            model_impact_score_clipped=25.0,
            rule_quality_score_raw=10.0,
            rule_quality_score_clipped=10.0,
            kill_impact_total=20.0,
            death_impact_total=-5.0,
        )
        report = ImpactReport(
            match_info={},
            player_impacts=[player],
            total_rounds=10,
        )
        json_data = report_to_json(report)

        self.assertIn("diagnostics", json_data)
        self.assertIn("players", json_data)
        self.assertEqual(len(json_data["players"]), 1)

        player_data = json_data["players"][0]
        self.assertIn("diagnostics", player_data)
        diag = player_data["diagnostics"]

        self.assertEqual(diag["avg_round_impact"], 1.5)
        self.assertEqual(diag["total_round_impact"], 15.0)
        self.assertEqual(diag["model_impact_score_raw"], 25.0)
        self.assertEqual(diag["model_impact_score_clipped"], 25.0)
        self.assertEqual(diag["rule_quality_score_raw"], 10.0)
        self.assertEqual(diag["rule_quality_score_clipped"], 10.0)
        self.assertEqual(diag["kill_impact_total"], 20.0)
        self.assertEqual(diag["death_impact_total"], -5.0)

    def test_report_level_diagnostics(self):
        player = PlayerMatchImpact(
            player_name="TestPlayer",
            team="team1",
            model_impact_score_raw=60.0,  # Clipped
            model_impact_score_clipped=50.0,
            rating_0_100=100.0,  # At max
        )
        report = ImpactReport(
            match_info={},
            player_impacts=[player],
            total_rounds=1,
        )
        json_data = report_to_json(report)

        diag = json_data["diagnostics"]
        self.assertEqual(diag["model_impact_clip_count_max"], 1)
        self.assertEqual(diag["model_impact_clip_count_min"], 0)
        self.assertEqual(diag["rating_zero_count"], 0)
        self.assertEqual(diag["rating_hundred_count"], 1)

    def test_heavy_clip_warning(self):
        players = [
            PlayerMatchImpact(
                player_name=f"P{i}",
                team="team1",
                model_impact_score_raw=60.0,
                model_impact_score_clipped=50.0,
            )
            for i in range(5)
        ]
        report = ImpactReport(
            match_info={},
            player_impacts=players,
            total_rounds=1,
        )
        json_data = report_to_json(report)

        # 5/5 = 100% clipped, should trigger warning
        self.assertTrue(
            any("heavily clipped" in w for w in json_data["warnings"]),
            "Should add clipping warning when >30% clipped"
        )


if __name__ == "__main__":
    unittest.main()
