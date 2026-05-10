"""Unit tests for the CS2 Impact Engine."""

import unittest
from unittest.mock import MagicMock

from demo_analysis.impact_engine.models import (
    EventType,
    GameEvent,
    PredictionTick,
    RiskAssessment,
    RiskType,
    RoundContext,
)
from demo_analysis.impact_engine.align import (
    find_nearest_tick,
    find_ticks_before,
    safe_float,
    get_player_side_win_rate,
    calculate_distance_2d,
)
from demo_analysis.impact_engine.risk import (
    assess_death_risk,
    is_unexpected_death,
)
from demo_analysis.impact_engine.rules import (
    is_opening_event,
    check_hard_duel_win,
    check_easy_duel_loss,
    is_low_impact_kill,
)
from demo_analysis.impact_engine.scoring import (
    calculate_win_rate_delta,
    determine_round_label,
)
from demo_analysis.impact_engine.config import get_weight


class TestSafeFloat(unittest.TestCase):
    """Test safe_float utility function."""

    def test_valid_float(self):
        self.assertEqual(safe_float(1.5), 1.5)

    def test_valid_int(self):
        self.assertEqual(safe_float(5), 5.0)

    def test_string_number(self):
        self.assertEqual(safe_float("3.14"), 3.14)

    def test_invalid_value(self):
        self.assertEqual(safe_float("invalid"), 0.0)

    def test_none_value(self):
        self.assertEqual(safe_float(None), 0.0)

    def test_default_value(self):
        self.assertEqual(safe_float("invalid", default=5.0), 5.0)


class TestDistanceCalculation(unittest.TestCase):
    """Test distance calculation functions."""

    def test_same_point(self):
        self.assertEqual(calculate_distance_2d(0, 0, 0, 0), 0.0)

    def test_horizontal_distance(self):
        dist = calculate_distance_2d(0, 0, 3, 0)
        self.assertAlmostEqual(dist, 3.0)

    def test_vertical_distance(self):
        dist = calculate_distance_2d(0, 0, 0, 4)
        self.assertAlmostEqual(dist, 4.0)

    def test_diagonal_distance(self):
        dist = calculate_distance_2d(0, 0, 3, 4)
        self.assertAlmostEqual(dist, 5.0)


class TestFindNearestTick(unittest.TestCase):
    """Test find_nearest_tick function."""

    def setUp(self):
        self.ticks = [
            PredictionTick(round_seconds=1.0, ct_win_rate=0.5, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=2.0, ct_win_rate=0.6, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=3.0, ct_win_rate=0.7, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=4.0, ct_win_rate=0.4, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
        ]

    def test_exact_match(self):
        result = find_nearest_tick(self.ticks, 2.0)
        self.assertEqual(result.round_seconds, 2.0)

    def test_between_ticks(self):
        result = find_nearest_tick(self.ticks, 2.5)
        self.assertEqual(result.round_seconds, 2.0)

    def test_empty_ticks(self):
        result = find_nearest_tick([], 2.0)
        self.assertIsNone(result)


class TestFindTicksBefore(unittest.TestCase):
    """Test find_ticks_before function."""

    def setUp(self):
        self.ticks = [
            PredictionTick(round_seconds=1.0, ct_win_rate=0.5, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=3.0, ct_win_rate=0.6, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=5.0, ct_win_rate=0.7, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=7.0, ct_win_rate=0.4, alive_pred=[], next_kill=[], next_death=[], duel=None, players_info=[]),
        ]

    def test_within_window(self):
        result = find_ticks_before(self.ticks, 6.0, max_seconds=5.0)
        self.assertEqual(len(result), 3)

    def test_empty_result(self):
        result = find_ticks_before(self.ticks, 0.5, max_seconds=5.0)
        self.assertEqual(len(result), 0)

    def test_sorted_reverse(self):
        result = find_ticks_before(self.ticks, 8.0, max_seconds=10.0)
        self.assertGreater(result[0].round_seconds, result[-1].round_seconds)


class TestGetPlayerSideWinRate(unittest.TestCase):
    """Test get_player_side_win_rate function."""

    def test_team1_player(self):
        result = get_player_side_win_rate(0.6, "player1", ["player1", "player2"])
        self.assertEqual(result, 0.6)

    def test_team2_player(self):
        result = get_player_side_win_rate(0.6, "player3", ["player1", "player2"])
        self.assertEqual(result, 0.4)


class TestDetermineRoundLabel(unittest.TestCase):
    """Test determine_round_label function."""

    def test_carry_round(self):
        self.assertEqual(determine_round_label(3.5), "Carry Round")

    def test_high_impact_round(self):
        self.assertEqual(determine_round_label(2.0), "High Impact Round")

    def test_positive_round(self):
        self.assertEqual(determine_round_label(0.8), "Positive Round")

    def test_neutral_round(self):
        self.assertEqual(determine_round_label(0.0), "Neutral Round")

    def test_negative_round(self):
        self.assertEqual(determine_round_label(-1.0), "Negative Round")

    def test_throw_round(self):
        self.assertEqual(determine_round_label(-2.0), "Throw Round")


class TestGetWeight(unittest.TestCase):
    """Test get_weight function."""

    def test_nested_path(self):
        result = get_weight("kill_impact.hard_duel_win_bonus")
        self.assertIsNotNone(result)

    def test_invalid_path(self):
        result = get_weight("invalid.path")
        self.assertIsNone(result)

    def test_default_value(self):
        result = get_weight("invalid.path", default=42)
        self.assertEqual(result, 42)


class TestRiskAssessment(unittest.TestCase):
    """Test risk assessment logic."""

    def test_assess_death_risk_missing_data(self):
        """Test with no before_tick data."""
        event = GameEvent(
            event_type=EventType.DEATH,
            tick=5.0,
            player="player1",
            other_player="player2",
        )

        result = assess_death_risk(
            event,
            before_tick=None,
            risk_window_ticks=[],
            round_context=RoundContext(
                round_id=1,
                ticks=[],
                events=[event],
                team1_players=["player1", "player2"],
                team2_players=["player3", "player4"],
                team1_on_ct=True,
                winner="team1",
            )
        )

        self.assertEqual(result.risk_type, RiskType.UNKNOWN_RISK)
        self.assertEqual(result.confidence, 0.0)


class TestHardDuelWin(unittest.TestCase):
    """Test hard duel win detection."""

    def setUp(self):
        self.tick = PredictionTick(
            round_seconds=5.0,
            ct_win_rate=0.5,
            alive_pred=[0.9, 0.9, 0.8, 0.8, 0.7, 0.7, 0.6, 0.6, 0.5, 0.5],
            next_kill=[0.1] * 11,
            next_death=[0.1] * 11,
            duel=[
                ["/", 0.3, "/", "/", "/", "/", "/", "/", "/", "/"],
                [0.7, "/", 0.4, "/", "/", "/", "/", "/", "/", "/"],
                ["/", 0.6, "/", 0.35, "/", "/", "/", "/", "/", "/"],
                ["/", "/", 0.65, "/", 0.3, "/", "/", "/", "/", "/"],
                ["/", "/", "/", 0.7, "/", 0.25, "/", "/", "/", "/"],
                ["/", "/", "/", "/", 0.75, "/", 0.4, "/", "/", "/"],
                ["/", "/", "/", "/", "/", 0.6, "/", 0.3, "/", "/"],
                ["/", "/", "/", "/", "/", "/", 0.7, "/", 0.35, "/"],
                ["/", "/", "/", "/", "/", "/", "/", 0.65, "/", 0.4],
                ["/", "/", "/", "/", "/", "/", "/", "/", 0.6, "/"],
            ],
            players_info=[
                {"name": "p1", "is_alive": True},
                {"name": "p2", "is_alive": True},
                {"name": "p3", "is_alive": True},
                {"name": "p4", "is_alive": True},
                {"name": "p5", "is_alive": True},
                {"name": "p6", "is_alive": True},
                {"name": "p7", "is_alive": True},
                {"name": "p8", "is_alive": True},
                {"name": "p9", "is_alive": True},
                {"name": "p10", "is_alive": True},
            ],
        )
        self.name_to_idx = {"p1": 0, "p2": 1, "p3": 2, "p4": 3, "p5": 4,
                           "p6": 5, "p7": 6, "p8": 7, "p9": 8, "p10": 9}

    def test_hard_duel_win_detected(self):
        """Player with duel prob < 0.45 wins the duel."""
        event = GameEvent(
            event_type=EventType.KILL,
            tick=5.0,
            player="p3",
            other_player="p4",
        )

        result = check_hard_duel_win(event, self.tick, self.name_to_idx, threshold=0.45)
        self.assertTrue(result)

    def test_normal_duel_not_hard(self):
        """Player with duel prob > 0.45 doesn't get hard duel win."""
        event = GameEvent(
            event_type=EventType.KILL,
            tick=5.0,
            player="p3",
            other_player="p2",
        )

        result = check_hard_duel_win(event, self.tick, self.name_to_idx, threshold=0.45)
        self.assertFalse(result)


class TestEasyDuelLoss(unittest.TestCase):
    """Test easy duel loss detection."""

    def setUp(self):
        self.tick = PredictionTick(
            round_seconds=5.0,
            ct_win_rate=0.5,
            alive_pred=[0.9, 0.9, 0.8, 0.8, 0.7, 0.7, 0.6, 0.6, 0.5, 0.5],
            next_kill=[0.1] * 11,
            next_death=[0.1] * 11,
            duel=[
                ["/", 0.8, "/", "/", "/", "/", "/", "/", "/", "/"],
                [0.2, "/", 0.7, "/", "/", "/", "/", "/", "/", "/"],
                ["/", 0.3, "/", 0.75, "/", "/", "/", "/", "/", "/"],
                ["/", "/", 0.25, "/", 0.8, "/", "/", "/", "/", "/"],
                ["/", "/", "/", 0.2, "/", 0.7, "/", "/", "/", "/"],
                ["/", "/", "/", "/", 0.3, "/", 0.75, "/", "/", "/"],
                ["/", "/", "/", "/", "/", 0.25, "/", 0.8, "/", "/"],
                ["/", "/", "/", "/", "/", "/", 0.2, "/", 0.7, "/"],
                ["/", "/", "/", "/", "/", "/", "/", 0.3, "/", 0.75],
                ["/", "/", "/", "/", "/", "/", "/", "/", 0.25, "/"],
            ],
            players_info=[
                {"name": "p1", "is_alive": True},
                {"name": "p2", "is_alive": True},
                {"name": "p3", "is_alive": True},
                {"name": "p4", "is_alive": True},
                {"name": "p5", "is_alive": True},
                {"name": "p6", "is_alive": True},
                {"name": "p7", "is_alive": True},
                {"name": "p8", "is_alive": True},
                {"name": "p9", "is_alive": True},
                {"name": "p10", "is_alive": True},
            ],
        )
        self.name_to_idx = {"p1": 0, "p2": 1, "p3": 2, "p4": 3, "p5": 4,
                           "p6": 5, "p7": 6, "p8": 7, "p9": 8, "p10": 9}

    def test_easy_duel_loss_detected(self):
        """Player with duel prob > 0.65 loses the duel."""
        event = GameEvent(
            event_type=EventType.DEATH,
            tick=5.0,
            player="p2",
            other_player="p1",
        )

        result = check_easy_duel_loss(event, self.tick, self.name_to_idx, threshold=0.65)
        self.assertTrue(result)

    def test_normal_duel_not_easy_loss(self):
        """Player with duel prob < 0.65 doesn't get easy duel loss."""
        event = GameEvent(
            event_type=EventType.DEATH,
            tick=5.0,
            player="p3",
            other_player="p4",
        )

        result = check_easy_duel_loss(event, self.tick, self.name_to_idx, threshold=0.65)
        self.assertFalse(result)


class TestUnexpectedDeath(unittest.TestCase):
    """Test unexpected death detection."""

    def test_unexpected_death_with_high_alive_prob(self):
        """Death when player had high alive probability should be unexpected."""
        risk_window = [
            PredictionTick(round_seconds=2.0, ct_win_rate=0.5, alive_pred=[0.85], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=3.0, ct_win_rate=0.5, alive_pred=[0.80], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=4.0, ct_win_rate=0.5, alive_pred=[0.75], next_kill=[], next_death=[], duel=None, players_info=[]),
        ]

        name_to_idx = {"player1": 0}
        is_unexpected, prob = is_unexpected_death(
            event=GameEvent(event_type=EventType.DEATH, tick=5.0, player="player1"),
            before_tick=risk_window[-1],
            risk_window_ticks=risk_window,
            name_to_idx=name_to_idx,
            threshold=0.70
        )

        self.assertTrue(is_unexpected)
        self.assertGreaterEqual(prob, 0.70)


class TestSelfCreatedRiskScenario(unittest.TestCase):
    """Test self-created risk scenario (5v4 advantage, solo push)."""

    def test_self_created_risk_death(self):
        """5v4 advantage with player solo pushing far from team should be self-created risk."""
        event = GameEvent(
            event_type=EventType.DEATH,
            tick=45.0,
            player="player1",
            other_player="player6",
        )

        before_tick = PredictionTick(
            round_seconds=44.9,
            ct_win_rate=0.72,
            alive_pred=[0.8, 0.8, 0.7, 0.7, 0.6, 0.5, 0.5, 0.4, 0.3, 0.2],
            next_kill=[],
            next_death=[],
            duel=None,
            players_info=[
                {"name": "player1", "is_alive": True, "X": -2000, "Y": -1000, "Z": 0},
                {"name": "player2", "is_alive": True, "X": -100, "Y": -100, "Z": 0},
                {"name": "player3", "is_alive": True, "X": -100, "Y": -100, "Z": 0},
                {"name": "player4", "is_alive": True, "X": -100, "Y": -100, "Z": 0},
                {"name": "player5", "is_alive": True, "X": -100, "Y": -100, "Z": 0},
                {"name": "player6", "is_alive": True, "X": -2100, "Y": -1100, "Z": 0},
                {"name": "player7", "is_alive": True, "X": 0, "Y": 0, "Z": 0},
                {"name": "player8", "is_alive": True, "X": 0, "Y": 0, "Z": 0},
                {"name": "player9", "is_alive": False, "X": 0, "Y": 0, "Z": 0},
                {"name": "player10", "is_alive": False, "X": 0, "Y": 0, "Z": 0},
            ],
        )

        risk_window = [
            PredictionTick(round_seconds=35.0, ct_win_rate=0.7, alive_pred=[0.85], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=40.0, ct_win_rate=0.72, alive_pred=[0.82], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=44.0, ct_win_rate=0.74, alive_pred=[0.75], next_kill=[], next_death=[], duel=None, players_info=[]),
        ]

        round_context = RoundContext(
            round_id=9,
            ticks=[before_tick],
            events=[event],
            team1_players=["player1", "player2", "player3", "player4", "player5"],
            team2_players=["player6", "player7", "player8", "player9", "player10"],
            team1_on_ct=False,
            winner="team1",
            team1_alive_count=5,
            team2_alive_count=4,
        )

        result = assess_death_risk(
            event,
            before_tick,
            risk_window,
            round_context
        )

        self.assertEqual(result.risk_type, RiskType.SELF_CREATED_RISK)
        self.assertGreater(result.confidence, 0.5)


class TestForcedRiskScenario(unittest.TestCase):
    """Test forced risk scenario (entry frag with team support)."""

    def test_forced_risk_death(self):
        """Entry frag with team support should be forced risk."""
        event = GameEvent(
            event_type=EventType.DEATH,
            tick=15.0,
            player="player1",
            other_player="player6",
        )

        before_tick = PredictionTick(
            round_seconds=14.9,
            ct_win_rate=0.48,
            alive_pred=[0.35, 0.4, 0.5, 0.5, 0.5, 0.6, 0.6, 0.6, 0.6, 0.6],
            next_kill=[],
            next_death=[],
            duel=None,
            players_info=[
                {"name": "player1", "is_alive": True, "X": 100, "Y": 100, "Z": 0},
                {"name": "player2", "is_alive": True, "X": 200, "Y": 150, "Z": 0},
                {"name": "player3", "is_alive": True, "X": 150, "Y": 200, "Z": 0},
                {"name": "player4", "is_alive": True, "X": 120, "Y": 180, "Z": 0},
                {"name": "player5", "is_alive": True, "X": 180, "Y": 120, "Z": 0},
                {"name": "player6", "is_alive": True, "X": 400, "Y": 400, "Z": 0},
                {"name": "player7", "is_alive": True, "X": 500, "Y": 500, "Z": 0},
                {"name": "player8", "is_alive": True, "X": 450, "Y": 550, "Z": 0},
                {"name": "player9", "is_alive": True, "X": 550, "Y": 450, "Z": 0},
                {"name": "player10", "is_alive": True, "X": 600, "Y": 600, "Z": 0},
            ],
        )

        risk_window = [
            PredictionTick(round_seconds=10.0, ct_win_rate=0.45, alive_pred=[0.45], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=12.0, ct_win_rate=0.46, alive_pred=[0.42], next_kill=[], next_death=[], duel=None, players_info=[]),
            PredictionTick(round_seconds=14.0, ct_win_rate=0.47, alive_pred=[0.38], next_kill=[], next_death=[], duel=None, players_info=[]),
        ]

        round_context = RoundContext(
            round_id=4,
            ticks=[before_tick],
            events=[event],
            team1_players=["player1", "player2", "player3", "player4", "player5"],
            team2_players=["player6", "player7", "player8", "player9", "player10"],
            team1_on_ct=True,
            winner="team2",
            team1_alive_count=5,
            team2_alive_count=5,
        )

        result = assess_death_risk(
            event,
            before_tick,
            risk_window,
            round_context
        )

        self.assertEqual(result.risk_type, RiskType.FORCED_RISK)
        self.assertGreater(result.confidence, 0.5)


class TestLowImpactKill(unittest.TestCase):
    """Test low impact kill detection."""

    def test_exit_frag_is_low_impact(self):
        """Exit frag should be marked as low impact."""
        event = GameEvent(
            event_type=EventType.KILL,
            tick=80.0,
            player="player1",
            other_player="player6",
        )

        plant_tick = PredictionTick(
            round_seconds=40.0,
            ct_win_rate=0.5,
            alive_pred=[],
            next_kill=[],
            next_death=[],
            duel=None,
            players_info=[],
            is_bomb_planted=True,
            bomb_planted_time=40.0,
        )

        kill_tick = PredictionTick(
            round_seconds=80.0,
            ct_win_rate=0.9,
            alive_pred=[],
            next_kill=[],
            next_death=[],
            duel=None,
            players_info=[],
            is_bomb_planted=True,
            bomb_planted_time=40.0,
        )

        round_context = RoundContext(
            round_id=1,
            ticks=[plant_tick, kill_tick],
            events=[event],
            team1_players=["player1", "player2", "player3", "player4", "player5"],
            team2_players=["player6", "player7", "player8", "player9", "player10"],
            team1_on_ct=False,
            winner="team2",
            bomb_planted_time=40.0,
            team1_alive_count=2,
            team2_alive_count=4,
        )

        name_to_idx = {"player1": 0, "player6": 5}

        result = is_low_impact_kill(event, kill_tick, round_context, name_to_idx)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
