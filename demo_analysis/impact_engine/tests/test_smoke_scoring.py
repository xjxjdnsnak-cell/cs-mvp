"""Tests for smoke grenade utility scoring."""

import unittest

from demo_analysis.impact_engine.models import (
    EventType,
    GameEvent,
    PlayerMatchImpact,
    PlayerRoundImpact,
    PredictionTick,
    RoundContext,
    SmokeImpact,
)
from demo_analysis.impact_engine.report import generate_player_report
from demo_analysis.impact_engine.utility_smoke import (
    SmokeEvent,
    SmokeTarget,
    score_smoke_event,
    score_smoke_quality,
)


def target(
    name: str = "test_smoke",
    intent: str = "execute_smoke",
    center: tuple[float, float] = (500.0, 0.0),
    block_line: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.0), (1000.0, 0.0)),
    teammate_block_lines: list[dict] | None = None,
) -> SmokeTarget:
    return SmokeTarget(
        name=name,
        map_name="de_test",
        intent=intent,
        target_area="test_area",
        target_center=center,
        smoke_radius=170.0,
        required_block_lines=[{
            "name": "main_sightline",
            "from_area": "ct",
            "to_area": "entry",
            "from_xy": list(block_line[0]),
            "to_xy": list(block_line[1]),
        }],
        teammate_cross_routes=["entry_route"],
        teammate_block_lines=teammate_block_lines or [],
    )


def smoke(y: float, thrower: str = "A", tick: float = 10.0) -> SmokeEvent:
    return SmokeEvent(
        entityid=1,
        start_tick=tick,
        end_tick=tick + 5.0,
        position=(500.0, y, 0.0),
        thrower=thrower,
    )


def context(
    events: list[GameEvent] | None = None,
    bomb_planted_time: float | None = None,
    ticks: list[PredictionTick] | None = None,
    team1_on_ct: bool = True,
) -> RoundContext:
    if ticks is None:
        ticks = [
            PredictionTick(
                round_seconds=10.0,
                ct_win_rate=0.5,
                alive_pred=[],
                next_kill=[],
                next_death=[],
                duel=None,
                players_info=[
                    {"name": "A", "is_alive": True, "X": 0.0, "Y": 0.0, "Z": 0.0},
                    {"name": "B", "is_alive": True, "X": 510.0, "Y": 250.0, "Z": 0.0},
                    {"name": "E", "is_alive": True, "X": 900.0, "Y": 0.0, "Z": 0.0},
                ],
            ),
            PredictionTick(
                round_seconds=12.0,
                ct_win_rate=0.5,
                alive_pred=[],
                next_kill=[],
                next_death=[],
                duel=None,
                players_info=[
                    {"name": "A", "is_alive": True, "X": 0.0, "Y": 0.0, "Z": 0.0},
                    {"name": "B", "is_alive": True, "X": 530.0, "Y": 220.0, "Z": 0.0},
                    {"name": "E", "is_alive": True, "X": 900.0, "Y": 0.0, "Z": 0.0},
                ],
            ),
        ]
    return RoundContext(
        round_id=1,
        ticks=ticks,
        events=events or [],
        team1_players=["A", "B"],
        team2_players=["E"],
        team1_on_ct=team1_on_ct,
        winner="team1",
        bomb_planted_time=bomb_planted_time,
        map_name="de_test",
    )


class TestSmokeQuality(unittest.TestCase):
    def test_target_match_only_not_high_score(self):
        smoke_target = target(center=(500.0, 250.0))
        impact = score_smoke_event(
            smoke(250.0),
            context(),
            {"test_smoke": smoke_target},
        )
        self.assertTrue(impact.target_matched)
        self.assertLess(impact.score, 0.5)
        self.assertTrue(any(label in impact.labels for label in ("partial_block_smoke", "leaky_smoke", "missed_smoke")))

    def test_complete_block(self):
        smoke_target = target()
        impact = score_smoke_event(smoke(0.0), context(), {"test_smoke": smoke_target})
        self.assertIn("complete_block_smoke", impact.labels)
        self.assertGreaterEqual(impact.block_score, 0.8)
        self.assertGreater(impact.score, 0.0)

    def test_partial_block(self):
        smoke_target = target()
        complete_score, _, _ = score_smoke_quality(smoke(0.0), smoke_target, context(), {"test_smoke": smoke_target})
        partial_score, labels, _ = score_smoke_quality(smoke(150.0), smoke_target, context(), {"test_smoke": smoke_target})
        self.assertIn("partial_block_smoke", labels)
        self.assertLess(partial_score, complete_score)

    def test_leaky_smoke_no_consequence(self):
        smoke_target = target()
        impact = score_smoke_event(smoke(190.0), context(ticks=[]), {"test_smoke": smoke_target})
        self.assertIn("leaky_smoke", impact.labels)
        self.assertLess(impact.score, 0.0)
        self.assertNotIn("fatal_leaky_smoke", impact.labels)

    def test_fatal_leaky_smoke(self):
        smoke_target = target()
        kill = GameEvent(
            event_type=EventType.KILL,
            tick=12.0,
            player="E",
            other_player="B",
            through_smoke=True,
        )
        impact = score_smoke_event(smoke(190.0), context(events=[kill]), {"test_smoke": smoke_target})
        self.assertIn("false_confidence_smoke", impact.labels)
        self.assertIn("fatal_leaky_smoke", impact.labels)
        self.assertLessEqual(impact.score, -2.0)


class TestSmokeConversionAndFake(unittest.TestCase):
    def test_random_smoke_no_free_conversion(self):
        impact = score_smoke_event(smoke(0.0), context(bomb_planted_time=12.0), {})
        self.assertIn("random_smoke", impact.labels)
        self.assertNotIn("converted_execute_smoke", impact.labels)
        self.assertLess(impact.conversion_score, 0.1)

    def test_execute_smoke_conversion(self):
        smoke_target = target()
        impact = score_smoke_event(
            smoke(0.0),
            context(bomb_planted_time=12.0),
            {"test_smoke": smoke_target},
        )
        self.assertIn("converted_execute_smoke", impact.labels)
        self.assertGreater(impact.conversion_score, 0.0)
        self.assertGreater(impact.score, 1.0)

    def test_blocking_teammate_smoke(self):
        smoke_target = target(
            teammate_block_lines=[{
                "name": "friendly_trade_line",
                "from_xy": [0.0, 0.0],
                "to_xy": [1000.0, 0.0],
            }]
        )
        impact = score_smoke_event(smoke(0.0), context(), {"test_smoke": smoke_target})
        self.assertIn("blocking_teammate_smoke", impact.labels)
        self.assertLess(impact.score, 1.0)

    def test_successful_fake_smoke(self):
        smoke_target = target(name="fake", intent="fake_smoke", center=(500.0, 0.0))
        ticks = [
            PredictionTick(
                round_seconds=10.0,
                ct_win_rate=0.5,
                alive_pred=[],
                next_kill=[],
                next_death=[],
                duel=None,
                players_info=[
                    {"name": "A", "is_alive": True, "X": 0.0, "Y": 0.0, "Z": 0.0},
                    {"name": "B", "is_alive": True, "X": 300.0, "Y": 0.0, "Z": 0.0},
                    {"name": "E", "is_alive": True, "X": 1000.0, "Y": 0.0, "Z": 0.0},
                ],
                bomb_position=(0.0, 0.0, 0.0),
            ),
            PredictionTick(
                round_seconds=18.0,
                ct_win_rate=0.5,
                alive_pred=[],
                next_kill=[],
                next_death=[],
                duel=None,
                players_info=[
                    {"name": "A", "is_alive": True, "X": 0.0, "Y": 0.0, "Z": 0.0},
                    {"name": "B", "is_alive": True, "X": 300.0, "Y": 0.0, "Z": 0.0},
                    {"name": "E", "is_alive": True, "X": 1700.0, "Y": 0.0, "Z": 0.0},
                ],
                bomb_position=(1400.0, 0.0, 0.0),
            ),
        ]
        impact = score_smoke_event(
            smoke(0.0),
            context(bomb_planted_time=20.0, ticks=ticks, team1_on_ct=False),
            {"fake": smoke_target},
        )
        self.assertIn("successful_fake_smoke", impact.labels)
        self.assertGreater(impact.score, 0.0)

    def test_unconverted_fake_smoke(self):
        smoke_target = target(name="fake", intent="fake_smoke", center=(500.0, 0.0))
        impact = score_smoke_event(smoke(0.0), context(), {"fake": smoke_target})
        self.assertIn("unconverted_fake_smoke", impact.labels)
        self.assertGreaterEqual(impact.score, 0.0)


class TestSmokeReport(unittest.TestCase):
    def test_fatal_leaky_report_wording(self):
        smoke_impact = SmokeImpact(
            thrower="A",
            round_id=1,
            tick=10.0,
            intent="execute_smoke",
            score=-3.3,
            labels=["leaky_smoke", "false_confidence_smoke", "fatal_leaky_smoke"],
            reasons=["队友依赖这颗漏缝烟行动，存在错误安全感"],
            target_matched=True,
            block_score=-0.5,
            leak_risk="fatal",
            conversion_score=0.0,
            teammate_dependency=1.0,
            enemy_exploitation=1.0,
        )
        player = PlayerMatchImpact(
            player_name="A",
            team="team1",
            round_impacts=[
                PlayerRoundImpact(
                    player_name="A",
                    round_id=1,
                    team="team1",
                    smoke_impact=-3.3,
                    utility_impact=-3.3,
                    smoke_events=[smoke_impact],
                )
            ],
            smoke_score=-3.3,
            fatal_leaky_smokes=1,
            negative_smoke_events=[{
                "round": 1,
                "tick": 10.0,
                "impact": -3.3,
                "intent": "execute_smoke",
                "labels": smoke_impact.labels,
                "reasons": smoke_impact.reasons,
                "target_matched": True,
                "block_score": -0.5,
                "leak_risk": "fatal",
                "conversion_score": 0.0,
                "teammate_dependency": 1.0,
                "enemy_exploitation": 1.0,
            }],
        )
        markdown = generate_player_report(player)
        self.assertIn("错误安全感", markdown)
        self.assertTrue("缝隙" in markdown or "抽死" in markdown)
        self.assertNotIn("烟无效", markdown)


if __name__ == "__main__":
    unittest.main()
