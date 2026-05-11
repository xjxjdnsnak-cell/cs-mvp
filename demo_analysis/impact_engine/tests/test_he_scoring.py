"""Tests for HE grenade utility scoring."""

import unittest

from demo_analysis.impact_engine.models import (
    EventType,
    GameEvent,
    HEImpact,
    PlayerMatchImpact,
    PlayerRoundImpact,
    PredictionTick,
    RoundContext,
)
from demo_analysis.impact_engine.report import generate_player_report
from demo_analysis.impact_engine.utility_he import HEEvent, score_he_event


def p(name: str, x: float, y: float, health: int = 100) -> dict:
    return {"name": name, "is_alive": True, "X": x, "Y": y, "Z": 0.0, "health": health}


def tick(
    seconds: float,
    players: list[dict] | None = None,
    projectiles: list[dict] | None = None,
    bomb_position: tuple[float, float, float] | None = None,
) -> PredictionTick:
    return PredictionTick(
        round_seconds=seconds,
        ct_win_rate=0.5,
        alive_pred=[],
        next_kill=[],
        next_death=[],
        duel=None,
        players_info=players or [],
        projectiles=projectiles or [],
        bomb_position=bomb_position,
    )


def he(x: float = 500.0, y: float = 0.0, thrower: str = "A", t: float = 10.0) -> HEEvent:
    return HEEvent(entityid=f"he-{thrower}-{t}", tick=t, position=(x, y, 0.0), thrower=thrower)


def damage(victim: str, amount: int, attacker: str = "A", t: float = 10.0) -> GameEvent:
    return GameEvent(
        event_type=EventType.DAMAGE,
        tick=t,
        player=attacker,
        other_player=victim,
        weapon="hegrenade",
        damage_health=amount,
    )


def kill(victim: str, attacker: str = "A", weapon: str = "hegrenade", t: float = 10.1) -> GameEvent:
    return GameEvent(event_type=EventType.KILL, tick=t, player=attacker, other_player=victim, weapon=weapon)


def context(
    events: list[GameEvent] | None = None,
    ticks: list[PredictionTick] | None = None,
    bomb_planted_time: float | None = None,
    team1_on_ct: bool = True,
) -> RoundContext:
    return RoundContext(
        round_id=1,
        ticks=ticks
        or [
            tick(9.8, [p("A", 0, 0), p("B", -500, 0), p("E", 520, 0), p("F", 570, 40)]),
            tick(12.0, [p("A", 0, 0), p("B", -500, 0), p("E", 520, 0), p("F", 570, 40)]),
        ],
        events=events or [],
        team1_players=["A", "B"],
        team2_players=["E", "F"],
        team1_on_ct=team1_on_ct,
        winner="team1",
        bomb_planted_time=bomb_planted_time,
        map_name="de_test",
    )


def smoke_projectile(x: float = 500.0, y: float = 0.0) -> dict:
    return {"type": "smokegrenade", "position": (x, y, 0.0), "duration": 5.0}


def route_map() -> dict:
    return {
        "smoke_targets": {
            "mirage_window_smoke": {
                "target_center": [0.0, 0.0],
                "smoke_radius": 170.0,
                "counter_he_zones": [
                    {
                        "name": "top_mid_cross",
                        "polygon": [[900, -200], [1300, -200], [1300, 200], [900, 200]],
                    }
                ],
            }
        },
        "he_cross_zones": [],
        "plant_zones": [],
    }


class TestHEDamage(unittest.TestCase):
    def test_normal_damage(self):
        impact = score_he_event(he(), context(events=[damage("E", 40)]), {})
        self.assertIn("normal_he_damage", impact.labels)
        self.assertGreater(impact.score, 0.0)

    def test_high_damage(self):
        normal = score_he_event(he(), context(events=[damage("E", 40)]), {})
        high = score_he_event(he(), context(events=[damage("E", 60)]), {})
        self.assertIn("high_damage_he", high.labels)
        self.assertGreater(high.score, normal.score)

    def test_kill_he(self):
        impact = score_he_event(he(), context(events=[damage("E", 45), kill("E")]), {})
        self.assertIn("kill_he", impact.labels)
        self.assertGreater(impact.score, 1.0)

    def test_assist_he(self):
        assist_kill = GameEvent(event_type=EventType.KILL, tick=13.0, player="B", other_player="E", weapon="ak47")
        impact = score_he_event(he(), context(events=[damage("E", 35), assist_kill]), {})
        self.assertIn("assist_he", impact.labels)
        self.assertGreater(impact.score, 0.5)

    def test_finishing_he(self):
        ticks = [
            tick(9.8, [p("A", 0, 0), p("B", -500, 0), p("E", 520, 0, health=20)]),
            tick(12.0, [p("A", 0, 0), p("B", -500, 0), p("E", 520, 0, health=0)]),
        ]
        finishing = score_he_event(he(), context(events=[damage("E", 20), kill("E")], ticks=ticks), {})
        high_kill = score_he_event(he(), context(events=[damage("E", 60), kill("E")]), {})
        self.assertIn("finishing_he", finishing.labels)
        self.assertLess(finishing.score, high_kill.score)


class TestAntiSmokeHE(unittest.TestCase):
    def test_anti_smoke_he_direct(self):
        ticks = [tick(10.0, [p("A", 0, 0), p("E", 560, 0)], [smoke_projectile(500, 0)])]
        impact = score_he_event(he(520, 0), context(events=[damage("E", 35)], ticks=ticks), {})
        self.assertIn("anti_smoke_he_direct", impact.labels)
        self.assertGreater(impact.score, 0.5)

    def test_anti_smoke_he_direct_kill(self):
        ticks = [tick(10.0, [p("A", 0, 0), p("E", 560, 0)], [smoke_projectile(500, 0)])]
        impact = score_he_event(he(520, 0), context(events=[damage("E", 45), kill("E")], ticks=ticks), {})
        self.assertIn("anti_smoke_he_direct_kill", impact.labels)
        self.assertGreaterEqual(impact.score, 2.5)

    def test_anti_smoke_route_he(self):
        ticks = [tick(10.0, [p("A", 0, 0), p("E", 1120, 0)], [smoke_projectile(0, 0)])]
        impact = score_he_event(he(1100, 0), context(events=[damage("E", 30)], ticks=ticks), route_map())
        self.assertIn("anti_smoke_route_he", impact.labels)
        self.assertNotIn("anti_smoke_he_direct", impact.labels)

    def test_anti_smoke_route_he_kill(self):
        ticks = [tick(10.0, [p("A", 0, 0), p("E", 1120, 0)], [smoke_projectile(0, 0)])]
        route = score_he_event(he(1100, 0), context(events=[damage("E", 45), kill("E")], ticks=ticks), route_map())
        direct_ticks = [tick(10.0, [p("A", 0, 0), p("E", 560, 0)], [smoke_projectile(500, 0)])]
        direct = score_he_event(he(520, 0), context(events=[damage("E", 45), kill("E")], ticks=direct_ticks), {})
        self.assertIn("anti_smoke_route_he_kill", route.labels)
        self.assertGreater(route.score, 1.5)
        self.assertLess(route.score, direct.score)

    def test_no_active_smoke_no_route_label(self):
        impact = score_he_event(he(1100, 0), context(events=[damage("E", 30)]), route_map())
        self.assertNotIn("anti_smoke_route_he", impact.labels)


class TestContextualHE(unittest.TestCase):
    def test_anti_cross_he(self):
        map_knowledge = {"he_cross_zones": [{"name": "cross", "center": [500, 0], "radius": 250}], "plant_zones": [], "smoke_targets": {}}
        impact = score_he_event(he(), context(events=[damage("E", 30)]), map_knowledge)
        self.assertIn("anti_cross_he", impact.labels)

    def test_anti_plant_he(self):
        map_knowledge = {"he_cross_zones": [], "plant_zones": [{"name": "default", "center": [500, 0], "radius": 250}], "smoke_targets": {}}
        impact = score_he_event(he(), context(events=[damage("E", 20)]), map_knowledge)
        self.assertIn("anti_plant_he", impact.labels)

    def test_anti_defuse_he(self):
        ticks = [
            tick(10.0, [p("A", 0, 0), p("E", 520, 0)], bomb_position=(500, 0, 0)),
            tick(12.0, [p("A", 0, 0), p("E", 520, 0)], bomb_position=(500, 0, 0)),
        ]
        impact = score_he_event(
            he(),
            context(events=[damage("E", 20)], ticks=ticks, bomb_planted_time=8.0, team1_on_ct=False),
            {},
        )
        self.assertIn("anti_defuse_he", impact.labels)
        self.assertGreaterEqual(impact.score, 1.0)

    def test_anti_rush_he(self):
        impact = score_he_event(he(), context(events=[damage("E", 35), damage("F", 35)]), {})
        self.assertIn("anti_rush_he", impact.labels)

    def test_nade_stack_damage(self):
        he_a = he(500, 0, "A", 10.0)
        he_b = he(530, 0, "B", 11.0)
        impact = score_he_event(
            he_a,
            context(events=[damage("E", 40, "A", 10.0), damage("F", 45, "B", 11.0)]),
            {},
            all_he_events=[he_a, he_b],
        )
        self.assertIn("nade_stack_damage", impact.labels)

    def test_low_value_he(self):
        impact = score_he_event(he(), context(events=[damage("E", 6)]), {})
        self.assertIn("low_value_he", impact.labels)
        self.assertLess(impact.score, 0.2)

    def test_team_damage_he(self):
        impact = score_he_event(he(), context(events=[damage("B", 15)]), {})
        self.assertIn("team_damage_he", impact.labels)
        self.assertLess(impact.score, 0.0)

    def test_harmful_he(self):
        teammate_death = GameEvent(event_type=EventType.KILL, tick=10.5, player="E", other_player="B", weapon="ak47")
        impact = score_he_event(he(), context(events=[damage("B", 70), teammate_death]), {})
        self.assertIn("harmful_he", impact.labels)
        self.assertLess(impact.score, -1.0)


class TestHEReport(unittest.TestCase):
    def test_report_wording_for_route_he(self):
        he_impact = HEImpact(
            thrower="A",
            round_id=1,
            tick=10.0,
            score=2.3,
            labels=["normal_he_damage", "kill_he", "anti_smoke_route_he", "anti_smoke_route_he_kill"],
            damage_events=[{"victim": "E", "damage": 45, "team_damage": False}],
            kill_events=[{"victim": "E", "team_kill": False}],
            smoke_context={"type": "route", "smoke_target": "mirage_window_smoke", "zone": "top_mid_cross"},
            objective_context=None,
            reasons=["HE 命中烟后默认路线的预判区域"],
        )
        match = PlayerMatchImpact(
            player_name="A",
            team="team1",
            round_impacts=[
                PlayerRoundImpact(
                    player_name="A",
                    round_id=1,
                    team="team1",
                    he_impact=2.3,
                    he_events=[he_impact],
                    utility_impact=2.3,
                    round_total_impact=2.3,
                )
            ],
            he_score=2.3,
            he_damage_total=45,
            he_kills=1,
            anti_smoke_he_kills=1,
            anti_smoke_route_hes=1,
            positive_he_events=[{
                "round": 1,
                "tick": 10.0,
                "impact": 2.3,
                "labels": ["normal_he_damage", "kill_he", "anti_smoke_route_he", "anti_smoke_route_he_kill"],
                "damage_events": [{"victim": "E", "damage": 45, "team_damage": False}],
            }],
        )
        markdown = generate_player_report(match)
        self.assertIn("针对烟后默认路线的预判雷", markdown)
        self.assertNotIn("炸到烟里的人", markdown)


if __name__ == "__main__":
    unittest.main()
