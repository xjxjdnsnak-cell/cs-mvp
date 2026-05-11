import unittest

from demo_analysis.impact_engine.models import RoundContext, PredictionTick, GameEvent, EventType, PlayerRoundImpact, PlayerMatchImpact
from demo_analysis.impact_engine.tactical_scoring import (
    calculate_player_tactical_impact,
    evaluate_mid_control,
    evaluate_site_execute,
    TacticalEvent,
    aggregate_tactical_events,
)
from demo_analysis.impact_engine.tactical_phase import detect_round_phase
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


class TestTacticalEventAggregation(unittest.TestCase):
    def test_aggregate_10_consecutive_ticks(self):
        """连续10个tick的connector mid_control_success应聚合成1个事件"""
        events = []
        for i in range(10):
            events.append(TacticalEvent(
                player="T1",
                round_id=1,
                tick=10.0 + i * 1.0,
                label="mid_control_success",
                score=0.3,
                reason="test",
                area="connector",
                area_cn="拱门",
                phase="map_control",
            ))
        aggregated = aggregate_tactical_events(events)
        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[0]["label"], "mid_control_success")
        self.assertEqual(aggregated[0]["area"], "connector")
        self.assertEqual(aggregated[0]["start_tick"], 10.0)
        self.assertEqual(aggregated[0]["end_tick"], 19.0)

    def test_aggregate_impact_capped_at_0_5(self):
        """聚合事件impact不超过0.5"""
        events = []
        for i in range(10):
            events.append(TacticalEvent(
                player="T1",
                round_id=1,
                tick=10.0 + i * 1.0,
                label="mid_control_success",
                score=0.3,
                reason="test",
                area="connector",
                area_cn="拱门",
                phase="map_control",
            ))
        aggregated = aggregate_tactical_events(events)
        self.assertLessEqual(aggregated[0]["impact"], 0.5)

    def test_different_labels_not_aggregated(self):
        """不同label不应聚合"""
        events = [
            TacticalEvent(player="T1", round_id=1, tick=10.0, label="mid_control_success", score=0.3, reason="r1", area="connector", phase="map_control"),
            TacticalEvent(player="T1", round_id=1, tick=11.0, label="key_area_control", score=0.3, reason="r2", area="connector", phase="map_control"),
        ]
        aggregated = aggregate_tactical_events(events)
        self.assertEqual(len(aggregated), 2)

    def test_different_areas_not_aggregated(self):
        """不同area不应聚合"""
        events = [
            TacticalEvent(player="T1", round_id=1, tick=10.0, label="mid_control_success", score=0.3, reason="r1", area="connector", phase="map_control"),
            TacticalEvent(player="T1", round_id=1, tick=11.0, label="mid_control_success", score=0.3, reason="r2", area="top_mid", phase="map_control"),
        ]
        aggregated = aggregate_tactical_events(events)
        self.assertEqual(len(aggregated), 2)

    def test_gap_over_2_seconds_not_aggregated(self):
        """间隔超过2秒不应聚合"""
        events = [
            TacticalEvent(player="T1", round_id=1, tick=10.0, label="mid_control_success", score=0.3, reason="r1", area="connector", phase="map_control"),
            TacticalEvent(player="T1", round_id=1, tick=13.0, label="mid_control_success", score=0.3, reason="r2", area="connector", phase="map_control"),
        ]
        aggregated = aggregate_tactical_events(events)
        self.assertEqual(len(aggregated), 2)

    def test_gap_under_2_seconds_aggregated(self):
        """间隔小于2秒应聚合"""
        events = [
            TacticalEvent(player="T1", round_id=1, tick=10.0, label="mid_control_success", score=0.3, reason="r1", area="connector", phase="map_control"),
            TacticalEvent(player="T1", round_id=1, tick=11.5, label="mid_control_success", score=0.3, reason="r2", area="connector", phase="map_control"),
        ]
        aggregated = aggregate_tactical_events(events)
        self.assertEqual(len(aggregated), 1)

    def test_aggregate_has_duration(self):
        """聚合事件应有duration字段"""
        events = [
            TacticalEvent(player="T1", round_id=1, tick=10.0, label="mid_control_success", score=0.3, reason="r1", area="connector", phase="map_control"),
            TacticalEvent(player="T1", round_id=1, tick=12.0, label="mid_control_success", score=0.3, reason="r2", area="connector", phase="map_control"),
        ]
        aggregated = aggregate_tactical_events(events)
        self.assertIn("duration", aggregated[0])
        self.assertEqual(aggregated[0]["duration"], 12.0 - 10.0)

    def test_negative_events_also_aggregated(self):
        """负分事件也应聚合"""
        events = [
            TacticalEvent(player="T1", round_id=1, tick=10.0, label="key_area_isolated_death", score=-0.8, reason="r1", area="connector", phase="map_control"),
            TacticalEvent(player="T1", round_id=1, tick=11.0, label="key_area_isolated_death", score=-0.8, reason="r2", area="connector", phase="map_control"),
        ]
        aggregated = aggregate_tactical_events(events)
        self.assertEqual(len(aggregated), 1)
        self.assertGreaterEqual(aggregated[0]["impact"], -0.5)


class TestSiteExecutePhaseDetection(unittest.TestCase):
    def test_b_site_traded_death_phase_site_execute(self):
        """b_site可交易死亡应phase=site_execute"""
        events = [
            GameEvent(event_type=EventType.DEATH, tick=25.0, player="T1", other_player="CT1"),
            GameEvent(event_type=EventType.KILL, tick=27.0, player="T2", other_player="CT1"),
        ]
        smoke_proj = {"x": -423, "y": -2173, "z": 0, "type": "smoke"}
        ticks = [
            tick(20.0, [
                player("T1", -423, -2173), player("T2", -500, -2100),
                player("T3", -350, -2200), player("CT1", -400, -2000)
            ], projectiles=[smoke_proj]),
            tick(25.0, [
                player("T1", -423, -2173, alive=False), player("T2", -500, -2100),
                player("T3", -350, -2200), player("CT1", -400, -2000)
            ]),
        ]
        rc = RoundContext(
            round_id=14, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2", "T3"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        result = evaluate_site_execute("T1", rc)
        labels = [e.label for e in result]
        self.assertIn("valid_entry_sacrifice", labels)
        # 找到对应的事件并检查phase
        for ev in result:
            if ev.label == "valid_entry_sacrifice":
                self.assertEqual(ev.phase, "site_execute")

    def test_detect_round_phase_multiple_t_near_site(self):
        """多个T接近包点应识别为site_execute"""
        t_players = [
            player("T1", -423, -2173),
            player("T2", -500, -2100),
            player("T3", -350, -2200),
        ]
        ct_player = player("CT1", -400, -2000)
        smoke_proj = {"x": -423, "y": -2173, "z": 0, "type": "smoke"}
        ticks = [tick(25.0, t_players + [ct_player], projectiles=[smoke_proj])]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2", "T3"], team1_on_ct=True, winner="team1",
            map_name="de_mirage",
        )
        phase = detect_round_phase(rc, 0)
        self.assertEqual(phase, "site_execute")

    def test_detect_round_phase_traded_death_in_site(self):
        """包点内可交易死亡应修正phase为site_execute"""
        events = [
            GameEvent(event_type=EventType.DEATH, tick=25.0, player="T1", other_player="CT1"),
            GameEvent(event_type=EventType.KILL, tick=27.0, player="T2", other_player="CT1"),
        ]
        ticks = [
            tick(20.0, [player("T1", -423, -2173), player("T2", -500, -2100), player("CT1", -400, -2000)]),
            tick(25.0, [player("T1", -423, -2173, alive=False), player("T2", -500, -2100), player("CT1", -400, -2000)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        phase = detect_round_phase(rc, 1)
        self.assertEqual(phase, "site_execute")

    def test_detect_round_phase_bomb_plant_approaching(self):
        """bomb_planted_time即将出现前10秒应site_execute"""
        events = [
            GameEvent(event_type=EventType.BOMB_PLANT, tick=35.0, player="T1"),
        ]
        ticks = [
            tick(25.0, [player("T1", -423, -2173), player("T2", -500, -2100), player("CT1", -400, -2000)]),
            tick(35.0, [player("T1", -423, -2173), player("T2", -500, -2100), player("CT1", -400, -2000)]),
        ]
        rc = RoundContext(
            round_id=1, ticks=ticks, events=events, team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_mirage", bomb_planted_time=35.0,
        )
        phase = detect_round_phase(rc, 0)
        # When bomb is already planted, phase should be site_execute if within 10s of plant
        # But current logic: bomb_planted_time is not None -> goes to post_plant branch first
        # We need to check that the new condition triggers BEFORE post_plant
        self.assertEqual(phase, "site_execute")


class TestTacticalEventsCountReduction(unittest.TestCase):
    def test_aggregated_events_fewer_than_raw(self):
        """tactical_events数量应明显少于raw tick events"""
        ticks = []
        for i in range(10):
            ticks.append(tick(10.0 + i * 1.0, [
                player("T1", -150, -700), player("T2", -200, -600)
            ]))
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        map_control, tactical_discipline, tactical_events = calculate_player_tactical_impact("T1", rc)
        # 聚合后应该只有1个事件（mid_control_success聚合）
        self.assertLess(len(tactical_events), 10)
        self.assertGreaterEqual(len(tactical_events), 1)

    def test_no_duplicate_round_area_label(self):
        """report中不应出现同一round/area/label连续重复5次以上"""
        ticks = []
        for i in range(10):
            ticks.append(tick(10.0 + i * 1.0, [
                player("T1", -150, -700), player("T2", -200, -600)
            ]))
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        map_control, tactical_discipline, tactical_events = calculate_player_tactical_impact("T1", rc)
        # 检查同一round/area/label组合不超过5个
        counts = {}
        for ev in tactical_events:
            key = (ev.get("round"), ev.get("area"), ev.get("label"))
            counts[key] = counts.get(key, 0) + 1
        for count in counts.values():
            self.assertLessEqual(count, 5)


class TestAggregatedEventFields(unittest.TestCase):
    def test_aggregated_event_has_all_required_fields(self):
        """聚合事件应包含所有必要字段"""
        events = [
            TacticalEvent(player="T1", round_id=1, tick=10.0, label="mid_control_success", score=0.3, reason="r1", area="connector", area_cn="拱门", phase="map_control"),
            TacticalEvent(player="T1", round_id=1, tick=11.0, label="mid_control_success", score=0.3, reason="r2", area="connector", area_cn="拱门", phase="map_control"),
        ]
        aggregated = aggregate_tactical_events(events)
        ev = aggregated[0]
        required_fields = {"round", "start_tick", "end_tick", "phase", "area", "area_cn", "label", "impact", "reason", "duration"}
        self.assertTrue(required_fields.issubset(set(ev.keys())))


class TestMapControlScoreFromAggregated(unittest.TestCase):
    def test_raw_map_control_from_aggregated(self):
        """raw_map_control_score应来自聚合事件"""
        ticks = []
        for i in range(10):
            ticks.append(tick(10.0 + i * 1.0, [
                player("T1", -150, -700), player("T2", -200, -600)
            ]))
        rc = RoundContext(
            round_id=1, ticks=ticks, events=[], team1_players=["CT1"],
            team2_players=["T1", "T2"], team1_on_ct=True, winner="team2",
            map_name="de_mirage",
        )
        map_control, tactical_discipline, tactical_events = calculate_player_tactical_impact("T1", rc)
        # 聚合后impact应被cap，不会简单累加10个0.3
        self.assertLessEqual(map_control, 0.5)
        self.assertGreater(map_control, 0)


if __name__ == "__main__":
    unittest.main()
