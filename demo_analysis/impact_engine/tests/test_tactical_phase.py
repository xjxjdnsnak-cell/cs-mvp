import unittest

from demo_analysis.impact_engine.models import RoundContext, PredictionTick, GameEvent, EventType
from demo_analysis.impact_engine.tactical_phase import detect_round_phase, get_alive_counts


def tick(seconds, players=None, projectiles=None, bomb_planted=False):
    return PredictionTick(
        round_seconds=seconds,
        ct_win_rate=0.5,
        alive_pred=[],
        next_kill=[],
        next_death=[],
        duel=None,
        players_info=players or [],
        is_bomb_planted=bomb_planted,
        projectiles=projectiles or [],
        entity_grenades=[],
    )


def player(name, x, y, alive=True, team="ct"):
    return {"name": name, "X": x, "Y": y, "Z": 0.0, "is_alive": alive, "team": team}


class TestTacticalPhase(unittest.TestCase):
    def test_bomb_planted_is_post_plant(self):
        ticks = [
            tick(20.0, [player("A", -423, -2173), player("E", 0, 0)], bomb_planted=True),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["A"],
            team2_players=["E"], team1_on_ct=True, winner="team1",
            bomb_planted_time=15.0, map_name="de_mirage",
        )
        phase = detect_round_phase(rc, 0)
        self.assertIn(phase, ("post_plant", "retake", "exit_phase"))

    def test_early_default(self):
        ticks = [tick(5.0, [player("A", 0, 0), player("E", 0, 0)])]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["A"],
            team2_players=["E"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        phase = detect_round_phase(rc, 0)
        self.assertEqual(phase, "early_default")

    def test_site_execute_t_near_a_site(self):
        t_players = [
            player("T1", -423, -2173, team="t"),
            player("T2", -500, -2100, team="t"),
            player("T3", -350, -2200, team="t"),
        ]
        ct_player = player("CT1", 0, 0, team="ct")
        smoke_proj = {"x": -423, "y": -2173, "z": 0, "type": "smoke"}
        ticks = [tick(25.0, t_players + [ct_player], projectiles=[smoke_proj])]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2", "T3"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        phase = detect_round_phase(rc, 0)
        self.assertEqual(phase, "site_execute")

    def test_save_phase(self):
        t_player = player("T1", 700, 500, alive=True, team="t")
        ct_players = [player("CT1", 0, 0, team="ct"), player("CT2", 100, 0, team="ct"), player("CT3", 200, 0, team="ct")]
        ticks = [tick(85.0, [t_player] + ct_players)]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1", "CT2", "CT3"],
            team2_players=["T1"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        phase = detect_round_phase(rc, 0)
        self.assertEqual(phase, "save")

    def test_map_control_default(self):
        ticks = [tick(20.0, [player("A", 0, 0), player("E", 0, 0)])]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["A"],
            team2_players=["E"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        phase = detect_round_phase(rc, 0)
        self.assertEqual(phase, "map_control")

    def test_get_alive_counts(self):
        players = [
            player("A", 0, 0, alive=True),
            player("B", 0, 0, alive=True),
            player("E", 0, 0, alive=False),
        ]
        ticks = [tick(10.0, players)]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["A", "B"],
            team2_players=["E"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        t1, t2 = get_alive_counts(rc, 0)
        self.assertEqual(t1, 2)
        self.assertEqual(t2, 0)


if __name__ == "__main__":
    unittest.main()
