"""Tests for Molotov / Incendiary utility scoring."""

import unittest

from demo_analysis.impact_engine.models import (
    EventType,
    FireImpact,
    GameEvent,
    PlayerMatchImpact,
    PlayerRoundImpact,
    PredictionTick,
    RoundContext,
)
from demo_analysis.impact_engine.report import generate_player_report
from demo_analysis.impact_engine.utility_fire import FireEvent, FireTarget, score_fire_event


def player(name: str, x: float, y: float, alive: bool = True) -> dict:
    return {"name": name, "is_alive": alive, "X": x, "Y": y, "Z": 0.0}


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


def fire(
    x: float = 500.0,
    y: float = 0.0,
    start: float = 10.0,
    end: float = 16.0,
    thrower: str = "A",
) -> FireEvent:
    return FireEvent(
        entityid=1,
        start_tick=start,
        end_tick=end,
        position=(x, y, 0.0),
        thrower=thrower,
        fire_type="inferno",
    )


def target(
    intent: str = "anti_rush_fire",
    kind: str = "choke",
    center: tuple[float, float] = (500.0, 0.0),
    radius: float = 190.0,
) -> FireTarget:
    return FireTarget(
        name="test_fire_target",
        map_name="de_test",
        intent=intent,
        target_area="test_area",
        center=center,
        radius=radius,
        kind=kind,
    )


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
            tick(10.0, [player("A", 0, 0), player("B", -600, 0), player("E", 1200, 0), player("F", 1300, 50)]),
            tick(13.0, [player("A", 0, 0), player("B", -600, 0), player("E", 1200, 0), player("F", 1300, 50)]),
        ],
        events=events or [],
        team1_players=["A", "B"],
        team2_players=["E", "F"],
        team1_on_ct=team1_on_ct,
        winner="team1",
        bomb_planted_time=bomb_planted_time,
        map_name="de_test",
    )


class TestFireDamage(unittest.TestCase):
    def test_normal_damage(self):
        damage = GameEvent(
            event_type=EventType.DAMAGE,
            tick=10.5,
            player="A",
            other_player="E",
            weapon="inferno",
            damage_health=30,
        )
        impact = score_fire_event(fire(), context(events=[damage]), {})
        self.assertIn("damage_fire", impact.labels)
        self.assertGreater(impact.score, 0.0)

    def test_kill_fire(self):
        damage = GameEvent(
            event_type=EventType.DAMAGE,
            tick=10.0,
            player="A",
            other_player="E",
            weapon="inferno",
            damage_health=30,
        )
        kill = GameEvent(event_type=EventType.KILL, tick=10.1, player="A", other_player="E", weapon="inferno")
        normal = score_fire_event(fire(), context(events=[damage]), {})
        lethal = score_fire_event(fire(), context(events=[damage, kill]), {})
        self.assertIn("kill_fire", lethal.labels)
        self.assertGreater(lethal.score, normal.score)

    def test_team_damage_fire(self):
        damage = GameEvent(
            event_type=EventType.DAMAGE,
            tick=10.5,
            player="A",
            other_player="B",
            weapon="inferno",
            damage_health=12,
        )
        impact = score_fire_event(fire(), context(events=[damage]), {})
        self.assertIn("team_damage_fire", impact.labels)
        self.assertLess(impact.score, 0.0)

    def test_harmful_fire(self):
        damage = GameEvent(
            event_type=EventType.DAMAGE,
            tick=10.0,
            player="A",
            other_player="B",
            weapon="inferno",
            damage_health=90,
        )
        death = GameEvent(event_type=EventType.KILL, tick=10.1, player="E", other_player="B")
        impact = score_fire_event(fire(), context(events=[damage, death]), {})
        self.assertIn("harmful_fire", impact.labels)
        self.assertLess(impact.score, -1.0)


class TestFireControlAndObjective(unittest.TestCase):
    def test_anti_rush_fire(self):
        ticks = [
            tick(10.0, [player("A", 0, 0), player("B", -800, 0), player("E", 550, 0), player("F", 600, 50)]),
            tick(12.5, [player("A", 0, 0), player("B", -800, 0), player("E", 1100, 0), player("F", 1150, 50)]),
        ]
        impact = score_fire_event(fire(), context(ticks=ticks), {"choke": target()})
        self.assertIn("anti_rush_fire", impact.labels)
        self.assertIn("successful_delay_fire", impact.labels)
        self.assertGreater(impact.score, 0.0)

    def test_choke_fire_no_enemy(self):
        ticks = [
            tick(10.0, [player("A", 0, 0), player("B", -800, 0), player("E", 2000, 0), player("F", 2100, 0)]),
            tick(12.5, [player("A", 0, 0), player("B", -800, 0), player("E", 2000, 0), player("F", 2100, 0)]),
        ]
        impact = score_fire_event(fire(), context(ticks=ticks), {"choke": target()})
        self.assertNotIn("anti_rush_fire", impact.labels)
        self.assertLessEqual(impact.score, 0.1)

    def test_forced_position(self):
        ticks = [
            tick(10.0, [player("A", 0, 0), player("B", -800, 0), player("E", 510, 0)]),
            tick(13.0, [player("A", 0, 0), player("B", -800, 0), player("E", 1100, 0)]),
        ]
        kill = GameEvent(event_type=EventType.KILL, tick=14.0, player="B", other_player="E")
        impact = score_fire_event(
            fire(),
            context(events=[kill], ticks=ticks),
            {"pos": target(intent="clear_position_fire", kind="strong_position")},
        )
        self.assertIn("forced_position_fire", impact.labels)
        self.assertGreater(impact.score, 0.0)

    def test_post_plant_area_fire_no_evidence(self):
        ticks = [
            tick(10.0, [player("A", 0, 0), player("E", 1200, 0)], bomb_position=(500.0, 0.0, 0.0)),
            tick(13.0, [player("A", 0, 0), player("E", 1200, 0)], bomb_position=(500.0, 0.0, 0.0)),
        ]
        impact = score_fire_event(
            fire(),
            context(ticks=ticks, bomb_planted_time=8.0, team1_on_ct=False),
            {"obj": target(intent="post_plant_fire", kind="objective")},
        )
        self.assertIn("post_plant_area_fire", impact.labels)
        self.assertNotIn("anti_defuse_fire", impact.labels)
        self.assertLessEqual(impact.score, 0.3)

    def test_anti_defuse_fire_with_ct_damage(self):
        damage = GameEvent(
            event_type=EventType.DAMAGE,
            tick=10.5,
            player="A",
            other_player="E",
            weapon="inferno",
            damage_health=30,
        )
        ticks = [
            tick(10.0, [player("A", 0, 0), player("E", 520, 0)], bomb_position=(500.0, 0.0, 0.0)),
            tick(13.0, [player("A", 0, 0), player("E", 520, 0)], bomb_position=(500.0, 0.0, 0.0)),
        ]
        impact = score_fire_event(
            fire(),
            context(events=[damage], ticks=ticks, bomb_planted_time=8.0, team1_on_ct=False),
            {"obj": target(intent="anti_defuse_fire", kind="objective")},
        )
        self.assertIn("anti_defuse_fire", impact.labels)
        self.assertGreaterEqual(impact.score, 1.0)

    def test_anti_defuse_fire_with_ct_near(self):
        ticks = [
            tick(10.0, [player("A", 0, 0), player("E", 520, 0)], bomb_position=(500.0, 0.0, 0.0)),
            tick(13.0, [player("A", 0, 0), player("E", 520, 0)], bomb_position=(500.0, 0.0, 0.0)),
        ]
        impact = score_fire_event(
            fire(),
            context(ticks=ticks, bomb_planted_time=8.0, team1_on_ct=False),
            {"obj": target(intent="anti_defuse_fire", kind="objective")},
        )
        self.assertIn("anti_defuse_fire", impact.labels)
        self.assertGreaterEqual(impact.score, 1.0)

    def test_anti_plant_fire(self):
        impact = score_fire_event(
            fire(),
            context(),
            {"obj": target(intent="anti_plant_fire", kind="objective")},
        )
        self.assertIn("anti_plant_fire", impact.labels)
        self.assertGreater(impact.score, 0.0)


class TestExtinguishHarmAndFake(unittest.TestCase):
    def test_extinguished_no_value(self):
        smoke_projectile = {"type": "smokegrenade", "position": (500.0, 0.0, 0.0)}
        ticks = [
            tick(10.0, [player("A", 0, 0), player("B", -800, 0), player("E", 2000, 0)]),
            tick(10.5, [player("A", 0, 0), player("B", -800, 0), player("E", 2000, 0)], [smoke_projectile]),
        ]
        impact = score_fire_event(fire(end=11.0), context(ticks=ticks), {})
        self.assertIn("extinguished_no_value", impact.labels)
        self.assertLessEqual(impact.score, 0.1)

    def test_extinguished_but_forced_smoke(self):
        smoke_projectile = {"type": "smokegrenade", "position": (500.0, 0.0, 0.0)}
        ticks = [
            tick(10.0, [player("A", 0, 0), player("B", -800, 0), player("E", 550, 0)]),
            tick(10.5, [player("A", 0, 0), player("B", -800, 0), player("E", 550, 0)], [smoke_projectile]),
        ]
        impact = score_fire_event(fire(end=11.0), context(ticks=ticks), {})
        self.assertIn("forced_smoke_extinguish", impact.labels)
        self.assertGreater(impact.score, 0.0)

    def test_teammate_blocking_fire(self):
        ticks = [
            tick(10.0, [player("A", 0, 0), player("B", -800, 0), player("E", 2000, 0)]),
            tick(11.0, [player("A", 0, 0), player("B", 510, 0), player("E", 2000, 0)]),
        ]
        impact = score_fire_event(fire(), context(ticks=ticks), {})
        self.assertIn("teammate_blocking_fire", impact.labels)
        self.assertLess(impact.score, 0.0)

    def test_fake_pressure_fire(self):
        ticks = [
            tick(10.0, [player("A", 0, 0), player("B", -800, 0), player("E", 1000, 0)], bomb_position=(0.0, 0.0, 0.0)),
            tick(18.0, [player("A", 0, 0), player("B", -800, 0), player("E", 1700, 0)], bomb_position=(1500.0, 0.0, 0.0)),
        ]
        impact = score_fire_event(
            fire(),
            context(ticks=ticks, bomb_planted_time=20.0, team1_on_ct=False),
            {"fake": target(intent="fake_pressure_fire", kind="objective")},
        )
        self.assertIn("fake_pressure_fire", impact.labels)
        self.assertGreater(impact.score, 0.0)


class TestFireReport(unittest.TestCase):
    def test_report_wording_for_delay_without_damage(self):
        fire_impact = FireImpact(
            thrower="A",
            round_id=1,
            tick=10.0,
            fire_type="inferno",
            intent="anti_rush_fire",
            score=1.6,
            labels=["anti_rush_fire", "successful_delay_fire"],
            damage_events=[],
            forced_movements=[],
            conversions=[],
            reasons=["阻止 rush / 拖延进攻"],
        )
        player_match = PlayerMatchImpact(
            player_name="A",
            team="team1",
            round_impacts=[
                PlayerRoundImpact(
                    player_name="A",
                    round_id=1,
                    team="team1",
                    fire_impact=1.6,
                    fire_events=[fire_impact],
                    utility_impact=1.6,
                    round_total_impact=1.6,
                )
            ],
            fire_score=1.6,
            anti_rush_fires=1,
            positive_fire_events=[{
                "round": 1,
                "tick": 10.0,
                "impact": 1.6,
                "labels": ["anti_rush_fire", "successful_delay_fire"],
            }],
        )
        markdown = generate_player_report(player_match)
        self.assertNotIn("没伤害所以没用", markdown)
        self.assertTrue("阻止 rush" in markdown or "拖延进攻" in markdown)


if __name__ == "__main__":
    unittest.main()
