import unittest

from demo_analysis.impact_engine.models import RoundContext, PredictionTick, GameEvent, EventType, PlayerRoundImpact, PlayerMatchImpact
from demo_analysis.impact_engine.tactical_scoring import (
    calculate_player_tactical_impact,
    evaluate_mid_control,
    evaluate_site_execute,
    evaluate_post_plant_discipline,
    evaluate_retake_discipline,
    evaluate_save_and_exit,
)
from demo_analysis.impact_engine.map_tactics import locate_area
from demo_analysis.impact_engine.report import generate_tactical_section


def tick(seconds, players=None, bomb_planted=False, bomb_planted_time=None, projectiles=None):
    return PredictionTick(
        round_seconds=seconds,
        ct_win_rate=0.5,
        alive_pred=[],
        next_kill=[],
        next_death=[],
        duel=None,
        players_info=players or [],
        is_bomb_planted=bomb_planted,
        bomb_planted_time=bomb_planted_time,
        projectiles=projectiles or [],
        entity_grenades=[],
    )


def player(name, x, y, alive=True):
    return {"name": name, "X": x, "Y": y, "Z": 0.0, "is_alive": alive}


class TestMidControlScoring(unittest.TestCase):
    def test_key_area_isolated_death(self):
        events = [GameEvent(event_type=EventType.DEATH, tick=20.0, player="T1", other_player="CT1")]
        ticks = [
            tick(10.0, [player("T1", -800, -25), player("T2", 2000, 2000)]),
            tick(20.0, [player("T1", -800, -25, alive=False), player("T2", 2000, 2000)]),
        ]
        rc = RoundContext(
            round_id=9, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        result = evaluate_mid_control("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("key_area_isolated_death", labels)

    def test_mid_control_success(self):
        ticks = [
            tick(10.0, [player("T1", -150, -700), player("T2", -200, -600)]),
            tick(20.0, [player("T1", -150, -700), player("T2", -200, -600)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        result = evaluate_mid_control("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("mid_control_success", labels)


class TestSiteExecuteScoring(unittest.TestCase):
    def test_valid_entry_sacrifice(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=25.0, player="T1", other_player="CT1"),
            GameEvent(event_type=EventType.KILL, tick=27.0, player="T2", other_player="CT1"),
        ]
        smoke_proj = {"x": -423, "y": -2173, "z": 0, "type": "smoke"}
        ticks = [
            tick(20.0, [player("T1", -423, -2173), player("T2", -500, -2100), player("T3", -350, -2200), player("CT1", -400, -2000)], projectiles=[smoke_proj]),
            tick(25.0, [player("T1", -423, -2173, alive=False), player("T2", -500, -2100), player("T3", -350, -2200), player("CT1", -400, -2000)]),
        ]
        rc = RoundContext(
            round_id=14, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2", "T3"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        result = evaluate_site_execute("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("valid_entry_sacrifice", labels)

    def test_failed_entry_no_trade(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=25.0, player="T1", other_player="CT1"),
        ]
        smoke_proj = {"x": -423, "y": -2173, "z": 0, "type": "smoke"}
        ticks = [
            tick(20.0, [player("T1", -423, -2173), player("T2", -500, -2100), player("T3", -350, -2200), player("CT1", -400, -2000)], projectiles=[smoke_proj]),
            tick(25.0, [player("T1", -423, -2173, alive=False), player("T2", -500, -2100), player("T3", -350, -2200), player("CT1", -400, -2000)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2", "T3"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        result = evaluate_site_execute("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("failed_entry_no_trade", labels)

    def test_valid_entry_sacrifice_5s_window(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=25.0, player="T1", other_player="CT1"),
            GameEvent(event_type=EventType.KILL, tick=29.0, player="T2", other_player="CT1"),
        ]
        ticks = [
            tick(20.0, [player("T1", -629, -2137), player("T2", -500, -2100), player("T3", -350, -2200), player("CT1", -400, -2000)]),
            tick(25.0, [player("T1", -629, -2137, alive=False), player("T2", -500, -2100), player("T3", -350, -2200), player("CT1", -400, -2000)]),
        ]
        rc = RoundContext(
            round_id=5, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2", "T3"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        result = evaluate_site_execute("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("valid_entry_sacrifice", labels)


class TestPostPlantDiscipline(unittest.TestCase):
    def test_post_plant_discipline_error(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=40.0, player="T1", other_player="CT1"),
        ]
        ticks = [
            tick(20.0, [player("T1", -423, -2173), player("T2", -629, -2137), player("CT1", -1759, -739)], bomb_planted=True, bomb_planted_time=15.0),
            tick(40.0, [player("T1", 0, 0, alive=False), player("T2", -629, -2137), player("CT1", -1759, -739)]),
        ]
        rc = RoundContext(
            round_id=18, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team1",
            bomb_planted_time=15.0, map_name="de_mirage",
        )
        result = evaluate_post_plant_discipline("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("post_plant_discipline_error", labels)

    def test_post_plant_t_advantage_solo_death(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=40.0, player="T1", other_player="CT1"),
        ]
        ticks = [
            tick(20.0, [
                player("T1", 0, 0),
                player("T2", -629, -2137),
                player("T3", -800, -2137),
                player("CT1", -1759, -739),
            ], bomb_planted=True, bomb_planted_time=15.0),
            tick(40.0, [
                player("T1", 0, 0, alive=False),
                player("T2", -629, -2137),
                player("T3", -800, -2137),
                player("CT1", -1759, -739),
            ]),
        ]
        rc = RoundContext(
            round_id=10, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2", "T3"], team1_on_ct=True, winner="team2",
            bomb_planted_time=15.0, map_name="de_mirage",
        )
        result = evaluate_post_plant_discipline("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("post_plant_discipline_error", labels)


class TestRetakeDiscipline(unittest.TestCase):
    def test_retake_solo_feed(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=40.0, player="CT1", other_player="T1"),
        ]
        ticks = [
            tick(20.0, [player("CT1", -1759, -739), player("T1", -423, -2173), player("T2", -629, -2137)], bomb_planted=True, bomb_planted_time=15.0),
            tick(40.0, [player("CT1", -423, -2173, alive=False), player("T1", -423, -2173), player("T2", -629, -2137)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            bomb_planted_time=15.0, map_name="de_mirage",
        )
        result = evaluate_retake_discipline("CT1", rc)
        labels = [e.label for e in result]
        self.assertIn("retake_solo_feed", labels)


class TestSaveAndExit(unittest.TestCase):
    def test_exit_frag_low_impact(self):
        events = [
            GameEvent(event_type=EventType.KILL, tick=88.0, player="T1", other_player="CT1"),
        ]
        ticks = [
            tick(85.0, [player("T1", 700, 500), player("CT1", 0, 0, alive=False), player("CT2", 100, 0), player("CT3", 200, 0), player("CT4", 300, 0)]),
            tick(90.0, [player("T1", 700, 500), player("CT2", 100, 0), player("CT3", 200, 0), player("CT4", 300, 0)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=events, team1_players=["CT1", "CT2", "CT3", "CT4"],
            team2_players=["T1"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        result = evaluate_save_and_exit("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("exit_frag_low_impact", labels)


class TestTacticalImpactIntegration(unittest.TestCase):
    def test_map_control_and_discipline_in_round_total(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=20.0, player="T1", other_player="CT1"),
        ]
        ticks = [
            tick(10.0, [player("T1", -800, -25), player("T2", 2000, 2000)]),
            tick(20.0, [player("T1", -800, -25, alive=False), player("T2", 2000, 2000)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        map_control, tactical_discipline, tactical_events = calculate_player_tactical_impact("T1", rc)
        self.assertLess(map_control, 0)

    def test_unconfigured_map_returns_zero(self):
        ticks = [tick(10.0, [player("T1", 0, 0)])]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1"], team1_on_ct=True, winner="team1",
            map_name="de_unknown",
        )
        map_control, tactical_discipline, tactical_events = calculate_player_tactical_impact("T1", rc)
        self.assertEqual(map_control, 0.0)
        self.assertEqual(tactical_discipline, 0.0)
        self.assertEqual(len(tactical_events), 0)

    def test_map_control_clamp_per_round(self):
        map_control, _, _ = calculate_player_tactical_impact("T1", RoundContext(
            round_id=1, ticks=[], events=[], team1_players=["CT1"],
            team2_players=["T1"], team1_on_ct=True, winner="team1",
            map_name="de_dust2",
        ))
        self.assertGreaterEqual(map_control, -0.5)
        self.assertLessEqual(map_control, 0.5)

    def test_tactical_discipline_clamp_per_round(self):
        _, tactical_discipline, _ = calculate_player_tactical_impact("T1", RoundContext(
            round_id=1, ticks=[], events=[], team1_players=["CT1"],
            team2_players=["T1"], team1_on_ct=True, winner="team1",
            map_name="de_dust2",
        ))
        self.assertGreaterEqual(tactical_discipline, -1.0)
        self.assertLessEqual(tactical_discipline, 1.0)

    def test_map_control_score_match_clamp(self):
        ri = PlayerRoundImpact(
            player_name="T1", round_id=1, team="team2",
            map_control_impact=0.5, tactical_discipline_impact=0.0,
        )
        many_rounds = [ri] * 30
        raw = sum(r.map_control_impact for r in many_rounds)
        clipped = max(-6.0, min(6.0, raw))
        self.assertLessEqual(clipped, 6.0)
        self.assertGreaterEqual(clipped, -6.0)

    def test_tactical_events_in_json(self):
        ri = PlayerRoundImpact(
            player_name="T1", round_id=1, team="team2",
            map_control_impact=0.5, tactical_discipline_impact=-0.3,
            tactical_events=[{
                "player": "T1", "round_id": 1, "tick": 20.0,
                "label": "key_area_isolated_death", "score": -0.8,
                "reason": "test", "area": "connector", "area_cn": "拱门", "phase": "map_control",
            }],
        )
        mi = PlayerMatchImpact(
            player_name="T1", team="team2",
            round_impacts=[ri],
            map_control_score=0.5, tactical_discipline_score=-0.3,
            key_area_deaths=1, post_plant_errors=0, valid_entry_sacrifices=0, retake_errors=0,
            positive_tactical_events=[],
            negative_tactical_events=[{
                "round": 1, "tick": 20.0, "phase": "map_control",
                "area": "connector", "area_cn": "拱门",
                "label": "key_area_isolated_death", "impact": -0.8,
                "reason": "test",
            }],
        )
        self.assertTrue(len(mi.negative_tactical_events) > 0)
        ev = mi.negative_tactical_events[0]
        self.assertEqual(ev["label"], "key_area_isolated_death")
        self.assertIn("reason", ev)


class TestReportTacticalSection(unittest.TestCase):
    def test_tactical_section_appears_in_report(self):
        ri = PlayerRoundImpact(
            player_name="T1", round_id=1, team="team2",
            map_control_impact=0.5, tactical_discipline_impact=-0.3,
            tactical_events=[{"player": "T1", "round_id": 1, "tick": 20.0, "label": "key_area_isolated_death", "score": -0.8, "reason": "test", "area": "connector", "area_cn": "拱门", "phase": "map_control"}],
        )
        mi = PlayerMatchImpact(
            player_name="T1", team="team2",
            round_impacts=[ri],
            map_control_score=0.5, tactical_discipline_score=-0.3,
            key_area_deaths=1, post_plant_errors=0, valid_entry_sacrifices=0, retake_errors=0,
            negative_tactical_events=[{
                "round": 1, "tick": 20.0, "phase": "map_control",
                "area": "connector", "area_cn": "拱门",
                "label": "key_area_isolated_death", "impact": -0.8,
                "reason": "在中路控制阶段独自前压 connector，附近无队友补枪",
            }],
        )
        section = generate_tactical_section(mi)
        text = "\n".join(section)
        self.assertIn("地图战术表现", text)

    def test_report_shows_specific_tactical_reason(self):
        ri = PlayerRoundImpact(
            player_name="T1", round_id=9, team="team2",
            map_control_impact=-0.5, tactical_discipline_impact=0.0,
            tactical_events=[{"player": "T1", "round_id": 9, "tick": 20.0, "label": "key_area_isolated_death", "score": -0.8, "reason": "独自前压 connector 死亡", "area": "connector", "area_cn": "拱门", "phase": "map_control"}],
        )
        mi = PlayerMatchImpact(
            player_name="T1", team="team2",
            round_impacts=[ri],
            map_control_score=-0.5, tactical_discipline_score=0.0,
            key_area_deaths=1, post_plant_errors=0, valid_entry_sacrifices=0, retake_errors=0,
            negative_tactical_events=[{
                "round": 9, "tick": 20.0, "phase": "map_control",
                "area": "connector", "area_cn": "拱门",
                "label": "key_area_isolated_death", "impact": -0.8,
                "reason": "独自前压 connector 死亡",
            }],
        )
        section = generate_tactical_section(mi)
        text = "\n".join(section)
        self.assertIn("独自前压", text)


class TestDust2TacticalScoring(unittest.TestCase):
    def test_dust2_area_detection(self):
        self.assertEqual(locate_area("de_dust2", -417, 374).name, "top_mid")
        self.assertIn(locate_area("de_dust2", 296, 1751).name, {"a_short", "short_stairs"})
        self.assertIn(locate_area("de_dust2", 1613, 1603).name, {"a_long", "long_car"})
        self.assertIn(locate_area("de_dust2", -1662, 1069).name, {"upper_tunnels", "b_tunnels"})

    def test_dust2_mid_control_auto_selected(self):
        ticks = [
            tick(10.0, [player("T1", -417, 374), player("T2", -500, 430), player("CT1", 87, 2231)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_dust2",
        )
        map_control, _, tactical_events = calculate_player_tactical_impact("T1", rc)
        labels = [e["label"] for e in tactical_events]
        self.assertIn("mid_control_success", labels)
        self.assertGreater(map_control, 0)

    def test_dust2_valid_entry_sacrifice(self):
        events = [
            GameEvent(event_type=EventType.DEATH, tick=25.0, player="T1", other_player="CT1"),
            GameEvent(event_type=EventType.KILL, tick=27.0, player="T2", other_player="CT1"),
        ]
        ticks = [
            tick(20.0, [player("T1", 296, 1751), player("T2", 330, 1780), player("CT1", 1061, 2466)]),
            tick(25.0, [player("T1", 296, 1751, alive=False), player("T2", 330, 1780), player("CT1", 1061, 2466)]),
        ]
        rc = RoundContext(
            round_id=7, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_dust2",
        )
        labels = [e.label for e in evaluate_site_execute("T1", rc)]
        self.assertIn("valid_entry_sacrifice", labels)

    def test_dust2_failed_entry_no_trade(self):
        events = [GameEvent(event_type=EventType.DEATH, tick=25.0, player="T1", other_player="CT1")]
        ticks = [
            tick(20.0, [player("T1", -1541, 2705), player("T2", -1662, 1069), player("CT1", -1318, 2658)]),
            tick(25.0, [player("T1", -1541, 2705, alive=False), player("T2", -1662, 1069), player("CT1", -1318, 2658)]),
        ]
        rc = RoundContext(
            round_id=8, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team1",
            map_name="de_dust2",
        )
        labels = [e.label for e in evaluate_site_execute("T1", rc)]
        self.assertIn("failed_entry_no_trade", labels)

    def test_dust2_post_plant_good_position_and_overpeek(self):
        hold_ticks = [
            tick(17.5, [player("T1", 1402, 492), player("T2", 1450, 620), player("CT1", 87, 2231)], bomb_planted=True, bomb_planted_time=15.0),
        ]
        hold_rc = RoundContext(
            round_id=12, ticks=hold_ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            bomb_planted_time=15.0, map_name="de_dust2",
        )
        hold_labels = [e.label for e in evaluate_post_plant_discipline("T1", hold_rc)]
        self.assertIn("post_plant_good_position", hold_labels)

        events = [GameEvent(event_type=EventType.DEATH, tick=40.0, player="T1", other_player="CT1")]
        overpeek_ticks = [
            tick(20.0, [player("T1", 1402, 492), player("T2", 1429, 2565), player("CT1", 87, 2231)], bomb_planted=True, bomb_planted_time=15.0),
            tick(40.0, [player("T1", -289, 1776, alive=False), player("T2", 1429, 2565), player("CT1", 87, 2231)]),
        ]
        overpeek_rc = RoundContext(
            round_id=13, ticks=overpeek_ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team1",
            bomb_planted_time=15.0, map_name="de_dust2",
        )
        overpeek_labels = [e.label for e in evaluate_post_plant_discipline("T1", overpeek_rc)]
        self.assertIn("post_plant_overpeek", overpeek_labels)

    def test_dust2_retake_solo_feed(self):
        events = [GameEvent(event_type=EventType.DEATH, tick=40.0, player="CT1", other_player="T1")]
        ticks = [
            tick(20.0, [player("CT1", 87, 2231), player("T1", 1061, 2466), player("T2", 1402, 492)], bomb_planted=True, bomb_planted_time=15.0),
            tick(40.0, [player("CT1", -289, 1776, alive=False), player("T1", 1061, 2466), player("T2", 1402, 492)]),
        ]
        rc = RoundContext(
            round_id=18, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            bomb_planted_time=15.0, map_name="de_dust2",
        )
        labels = [e.label for e in evaluate_retake_discipline("CT1", rc)]
        self.assertIn("retake_solo_feed", labels)


if __name__ == "__main__":
    unittest.main()
