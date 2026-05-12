"""Tests for utility scoring diagnostics."""

import io
import unittest
from contextlib import redirect_stdout

from demo_analysis.impact_engine.models import (
    EventType,
    GameEvent,
    ImpactReport,
    PlayerMatchImpact,
    PlayerRoundImpact,
    PredictionTick,
    RoundContext,
)
from demo_analysis.impact_engine.report import report_to_json
from demo_analysis.impact_engine.align import build_round_context
from demo_analysis.impact_engine.utility_fire import collect_fire_events
from demo_analysis.impact_engine.utility_he import collect_he_events, score_he_event
from demo_analysis.impact_engine.utility_diagnostics import (
    build_round_utility_diagnostics,
    print_utility_diagnostics,
)


def tick(
    seconds: float,
    projectiles: list[dict] | None = None,
    players_info: list[dict] | None = None,
    entity_grenades: list[dict] | None = None,
    future_damage: list[dict] | None = None,
    future_kills: list[dict] | None = None,
) -> PredictionTick:
    return PredictionTick(
        round_seconds=seconds,
        ct_win_rate=0.5,
        alive_pred=[],
        next_kill=[],
        next_death=[],
        duel=None,
        players_info=players_info or [
            {"name": "A", "is_alive": True, "X": 0.0, "Y": 0.0, "Z": 0.0},
            {"name": "E", "is_alive": True, "X": 500.0, "Y": 0.0, "Z": 0.0},
        ],
        projectiles=projectiles or [],
        entity_grenades=entity_grenades or [],
        future_damage=future_damage or [],
        future_kills=future_kills or [],
    )


def context(
    events: list[GameEvent] | None = None,
    ticks: list[PredictionTick] | None = None,
) -> RoundContext:
    return RoundContext(
        round_id=1,
        ticks=ticks or [tick(10.0)],
        events=events or [],
        team1_players=["A"],
        team2_players=["E"],
        team1_on_ct=True,
        winner="team1",
        map_name="de_test",
    )


class TestUtilityDiagnostics(unittest.TestCase):
    def test_unknown_smoke_thrower_is_counted(self):
        smoke = {"type": "smokegrenade", "entityid": 7, "position": (500.0, 0.0, 0.0), "duration": 3.0}
        diagnostics = build_round_utility_diagnostics(context(ticks=[tick(10.0, [smoke])]), ["A", "E"])

        self.assertEqual(diagnostics["total_smoke_events"], 1)
        self.assertEqual(diagnostics["attributed_smoke_events"], 0)
        self.assertEqual(diagnostics["unknown_smoke_thrower_count"], 1)

    def test_he_damage_event_is_counted(self):
        event = GameEvent(
            event_type=EventType.DAMAGE,
            tick=10.0,
            player="A",
            other_player="E",
            weapon="hegrenade",
            damage_health=35,
        )
        diagnostics = build_round_utility_diagnostics(context(events=[event]), ["A", "E"])

        self.assertEqual(diagnostics["damage_events_found"], 1)
        self.assertEqual(diagnostics["he_damage_events_found"], 1)
        self.assertEqual(diagnostics["fire_damage_events_found"], 0)
        self.assertIn("hegrenade", diagnostics["he_damage_weapon_values"])

    def test_he_detection_from_future_damage_creates_low_confidence_event(self):
        future_damage = [{
            "time": 10.0,
            "attacker_name": "A",
            "victim_name": "E",
            "weapon": "HE Grenade",
            "damage": 35,
        }]
        round_context = context(ticks=[tick(10.0, future_damage=future_damage)])

        he_events = collect_he_events(round_context)
        diagnostics = build_round_utility_diagnostics(round_context, ["A", "E"])

        self.assertGreater(diagnostics["total_he_events"], 0)
        self.assertGreater(diagnostics["he_damage_events_found"], 0)
        self.assertGreater(diagnostics["he_candidate_events_from_damage"], 0)
        self.assertTrue(any(event.low_confidence and event.thrower == "A" for event in he_events))

    def test_he_detection_from_future_kills_scores_kill(self):
        future_kills = [{
            "time": 10.0,
            "killer": "A",
            "victim": "E",
            "weapon": "HE Grenade",
        }]
        round_context = context(ticks=[tick(10.0, future_kills=future_kills)])

        he_events = collect_he_events(round_context)
        impacts = [score_he_event(event, round_context) for event in he_events if event.thrower == "A"]

        self.assertGreater(len(impacts), 0)
        self.assertTrue(any("kill_he" in impact.labels for impact in impacts))

    def test_fire_attribution_via_projectile_position_time(self):
        molotov = {
            "type": "CMolotovProjectile",
            "entityid": 11,
            "name": "A",
            "position": (100.0, 0.0, 0.0),
        }
        inferno = {
            "type": "inferno",
            "entityid": 99,
            "position": (130.0, 0.0, 0.0),
            "duration": 0.2,
        }
        round_context = context(ticks=[
            tick(10.0, entity_grenades=[molotov]),
            tick(10.5, projectiles=[inferno]),
        ])

        fire_events = collect_fire_events(round_context)
        diagnostics = build_round_utility_diagnostics(round_context, ["A", "E"])

        self.assertEqual(fire_events[0].thrower, "A")
        self.assertEqual(fire_events[0].attribution_method, "projectile_position_time")
        self.assertEqual(diagnostics["fire_attribution_method_counts"].get("projectile_position_time"), 1)
        self.assertEqual(diagnostics["unknown_fire_thrower_count"], 0)

    def test_fire_damage_from_future_damage_is_counted_and_attributed(self):
        future_damage = [{
            "time": 10.0,
            "attacker_name": "A",
            "victim_name": "E",
            "weapon": "inferno",
            "damage": 22,
        }]
        round_context = context(ticks=[tick(10.0, future_damage=future_damage)])

        fire_events = collect_fire_events(round_context)
        diagnostics = build_round_utility_diagnostics(round_context, ["A", "E"])

        self.assertGreater(diagnostics["fire_damage_events_found"], 0)
        self.assertTrue(any(event.thrower == "A" and event.attribution_method == "damage_attacker" for event in fire_events))

    def test_smoke_overmatch_diagnostics(self):
        smokes = [
            tick(
                10.0 + i,
                projectiles=[{
                    "type": "smokegrenade",
                    "entityid": i,
                    "name": "A",
                    "position": (-1174.0, -744.0, 0.0),
                    "duration": 1.0,
                }],
            )
            for i in range(6)
        ]
        round_context = context(ticks=smokes)
        round_context.map_name = "de_mirage"

        diagnostics = build_round_utility_diagnostics(round_context, ["A", "E"])

        self.assertGreaterEqual(diagnostics["smoke_target_match_counts"].get("mirage_window_smoke", 0), 6)
        self.assertIn("mirage_window_smoke", diagnostics["possible_overmatched_smoke_targets"])

    def test_build_round_context_extracts_damage_events(self):
        round_data = {
            "round_id": 1,
            "winner": "team1",
            "team1_on_ct": True,
            "ticks": [{
                "round_seconds": 10.0,
                "future_damage": [{
                    "time": 10.0,
                    "attacker_name": "A",
                    "victim_name": "E",
                    "weapon": "HE Grenade",
                    "damage": 35,
                }],
                "players_info": [],
            }],
        }
        round_context = build_round_context(round_data, ["A"], ["E"])

        self.assertTrue(any(event.event_type == EventType.DAMAGE for event in round_context.events))

    def test_future_damage_dedup_removes_duplicates(self):
        round_data = {
            "round_id": 1,
            "winner": "team1",
            "team1_on_ct": True,
            "ticks": [
                {
                    "round_seconds": 10.0,
                    "future_damage": [
                        {
                            "time": 10.5,
                            "attacker_name": "A",
                            "victim_name": "E",
                            "weapon": "ak47",
                            "damage": 35,
                        },
                    ],
                    "players_info": [],
                },
                {
                    "round_seconds": 11.0,
                    "future_damage": [
                        {
                            "time": 10.5,
                            "attacker_name": "A",
                            "victim_name": "E",
                            "weapon": "ak47",
                            "damage": 35,
                        },
                    ],
                    "players_info": [],
                },
            ],
        }
        round_context = build_round_context(round_data, ["A"], ["E"])
        damage_events = [e for e in round_context.events if e.event_type == EventType.DAMAGE]
        self.assertEqual(len(damage_events), 1)
        self.assertEqual(damage_events[0].tick, 10.5)

    def test_future_damage_dedup_uses_damage_time_not_tick_time(self):
        round_data = {
            "round_id": 1,
            "winner": "team1",
            "team1_on_ct": True,
            "ticks": [
                {
                    "round_seconds": 10.0,
                    "future_damage": [
                        {
                            "time": 10.5,
                            "attacker_name": "A",
                            "victim_name": "E",
                            "weapon": "ak47",
                            "damage": 35,
                        },
                    ],
                    "players_info": [],
                },
                {
                    "round_seconds": 11.0,
                    "future_damage": [
                        {
                            "time": 10.6,
                            "attacker_name": "A",
                            "victim_name": "E",
                            "weapon": "ak47",
                            "damage": 35,
                        },
                    ],
                    "players_info": [],
                },
            ],
        }
        round_context = build_round_context(round_data, ["A"], ["E"])
        damage_events = [e for e in round_context.events if e.event_type == EventType.DAMAGE]
        self.assertEqual(len(damage_events), 2)

    def test_diagnostics_counts_raw_and_unique_damage(self):
        future_damage = [
            {
                "time": 10.5,
                "attacker_name": "A",
                "victim_name": "E",
                "weapon": "ak47",
                "damage": 35,
            },
            {
                "time": 10.5,
                "attacker_name": "A",
                "victim_name": "E",
                "weapon": "ak47",
                "damage": 35,
            },
        ]
        round_context = context(ticks=[
            tick(10.0, future_damage=future_damage),
            tick(11.0, future_damage=future_damage),
        ])
        diagnostics = build_round_utility_diagnostics(round_context, ["A", "E"])
        self.assertEqual(diagnostics["raw_future_damage_entries"], 4)
        self.assertEqual(diagnostics["unique_damage_events_after_dedup"], 1)
        self.assertEqual(diagnostics["duplicate_damage_events_removed"], 3)

    def test_utility_debug_does_not_change_report_json(self):
        player = PlayerMatchImpact(
            player_name="A",
            team="team1",
            round_impacts=[
                PlayerRoundImpact(
                    player_name="A",
                    round_id=1,
                    team="team1",
                    flash_impact=1.0,
                    smoke_impact=0.5,
                    fire_impact=0.2,
                    he_impact=0.3,
                    utility_impact=2.0,
                )
            ],
            flash_score=1.0,
            smoke_score=0.5,
            fire_score=0.2,
            he_score=0.3,
        )
        report = ImpactReport(
            match_info={},
            player_impacts=[player],
            utility_diagnostics={"total_smoke_events": 1, "unknown_smoke_thrower_count": 1},
        )

        before = report_to_json(report)
        with redirect_stdout(io.StringIO()):
            print_utility_diagnostics(report.utility_diagnostics)
        after = report_to_json(report)

        self.assertEqual(before, after)
        self.assertIn("utility_diagnostics", after)
        player_json = after["players"][0]
        self.assertEqual(player_json["flash_score"], 1.0)
        self.assertEqual(player_json["smoke_score"], 0.5)
        self.assertEqual(player_json["fire_score"], 0.2)
        self.assertEqual(player_json["he_score"], 0.3)
        self.assertEqual(player_json["utility_impact"], 2.0)
        self.assertEqual(player_json["utility_event_count"], 0)
        self.assertIn("model_impact_score_raw", player_json)
        self.assertIn("model_impact_score_clipped", player_json)


if __name__ == "__main__":
    unittest.main()
