"""Tests for rule-based highlight moment detection."""

import unittest

from demo_analysis.impact_engine.highlight_moments import detect_highlight_moments
from demo_analysis.impact_engine.models import (
    EventImpact,
    EventType,
    GameEvent,
    HEImpact,
    PlayerRoundImpact,
    PredictionTick,
    RoundContext,
)


def p(name: str, is_alive: bool = True) -> dict:
    return {"name": name, "is_alive": is_alive, "X": 0.0, "Y": 0.0, "Z": 0.0}


def tick(seconds: float, players: list[dict] | None = None) -> PredictionTick:
    return PredictionTick(
        round_seconds=seconds,
        ct_win_rate=0.5,
        alive_pred=[],
        next_kill=[],
        next_death=[],
        duel=None,
        players_info=players or [],
    )


def kill(victim: str, attacker: str = "A", t: float = 10.0, labels: list[str] | None = None) -> EventImpact:
    event = GameEvent(
        event_type=EventType.KILL,
        tick=t,
        player=attacker,
        other_player=victim,
        weapon="ak47",
    )
    return EventImpact(event=event, labels=labels or [], total_impact=0.5)


def round_impact(
    round_id: int,
    kills: list[EventImpact] | None = None,
    he_events: list[HEImpact] | None = None,
) -> PlayerRoundImpact:
    return PlayerRoundImpact(
        player_name="A",
        round_id=round_id,
        team="team1",
        kills=kills or [],
        he_events=he_events or [],
    )


def context(
    round_id: int = 1,
    ticks: list[PredictionTick] | None = None,
    winner: str = "team1",
) -> RoundContext:
    return RoundContext(
        round_id=round_id,
        ticks=ticks or [],
        events=[],
        team1_players=["A", "B", "C"],
        team2_players=["X", "Y", "Z"],
        team1_on_ct=True,
        winner=winner,
    )


class TestHighlightMoments(unittest.TestCase):
    """Test detect_highlight_moments."""

    def test_empty_inputs_produce_no_highlights(self):
        self.assertEqual(detect_highlight_moments("A", [], []), [])

    def test_single_kill_produces_no_highlights(self):
        moments = detect_highlight_moments("A", [round_impact(1, kills=[kill("X")])], [])
        self.assertEqual(moments, [])

    def test_multi_kill_detection(self):
        moments = detect_highlight_moments(
            "A",
            [round_impact(3, kills=[kill("X", t=10.0), kill("Y", t=20.0), kill("Z", t=30.0)])],
            [],
        )
        multi = [m for m in moments if m.type == "multi_kill"]
        self.assertEqual(len(multi), 1)
        self.assertEqual(multi[0].subtype, "triple_kill")
        self.assertEqual(multi[0].round_id, 3)
        self.assertAlmostEqual(multi[0].tick, 30.0)
        self.assertGreater(multi[0].score, 0.0)

    def test_ace_detection(self):
        moments = detect_highlight_moments(
            "A",
            [round_impact(1, kills=[kill(f"X{i}", t=float(i)) for i in range(5)])],
            [],
        )
        multi = [m for m in moments if m.type == "multi_kill"]
        self.assertEqual(len(multi), 1)
        self.assertEqual(multi[0].subtype, "ace")

    def test_quick_multi_kill_detection(self):
        moments = detect_highlight_moments(
            "A",
            [round_impact(1, kills=[kill("X", t=10.0), kill("Y", t=12.0), kill("Z", t=14.0)])],
            [],
        )
        quick = [m for m in moments if m.type == "quick_multi_kill"]
        self.assertEqual(len(quick), 1)
        self.assertEqual(quick[0].subtype, "quick_3_kill")

    def test_clutch_win_detection(self):
        ticks = [
            # Both teams full strength.
            tick(1.0, [p("A"), p("B"), p("C"), p("X"), p("Y"), p("Z")]),
            # Teammates die, A left alone vs 3 enemies.
            tick(30.0, [p("A"), p("B", False), p("C", False), p("X"), p("Y"), p("Z")]),
            # A wins the round.
            tick(60.0, [p("A"), p("B", False), p("C", False), p("X", False), p("Y", False), p("Z", False)]),
        ]
        moments = detect_highlight_moments(
            "A",
            [round_impact(7)],
            [context(round_id=7, ticks=ticks, winner="team1")],
        )
        clutch = [m for m in moments if m.type == "clutch"]
        self.assertEqual(len(clutch), 1)
        self.assertEqual(clutch[0].subtype, "1v3_clutch")
        self.assertAlmostEqual(clutch[0].tick, 30.0)
        self.assertAlmostEqual(clutch[0].score, 2.0)

    def test_no_clutch_when_round_lost(self):
        ticks = [
            tick(30.0, [p("A"), p("B", False), p("C", False), p("X"), p("Y"), p("Z")]),
            tick(60.0, [p("A", False), p("B", False), p("C", False), p("X"), p("Y"), p("Z")]),
        ]
        moments = detect_highlight_moments(
            "A",
            [round_impact(1)],
            [context(round_id=1, ticks=ticks, winner="team2")],
        )
        self.assertEqual([m for m in moments if m.type == "clutch"], [])

    def test_hard_duel_detection(self):
        moments = detect_highlight_moments(
            "A",
            [round_impact(1, kills=[kill("X", t=15.0, labels=["hard_duel_win"])])],
            [],
        )
        duels = [m for m in moments if m.type == "hard_duel"]
        self.assertEqual(len(duels), 1)
        self.assertEqual(duels[0].subtype, "hard_duel_win")
        self.assertEqual(duels[0].details.get("opponent"), "X")

    def test_he_multi_hit_detection(self):
        he = HEImpact(
            thrower="A",
            round_id=1,
            tick=12.0,
            score=1.0,
            labels=[],
            damage_events=[
                {"victim": "X", "damage": 40, "team_damage": False},
                {"victim": "Y", "damage": 55, "team_damage": False},
            ],
            kill_events=[],
            smoke_context=None,
            objective_context=None,
            reasons=[],
        )
        moments = detect_highlight_moments("A", [round_impact(1, he_events=[he])], [])
        he_hits = [m for m in moments if m.type == "he_multi_hit"]
        self.assertEqual(len(he_hits), 1)
        self.assertEqual(he_hits[0].subtype, "he_2_hit")

    def test_impactful_opening_kill_detection(self):
        opening = kill("X", t=8.0, labels=["opening_kill"])
        opening.total_impact = 1.5
        moments = detect_highlight_moments("A", [round_impact(1, kills=[opening])], [])
        openings = [m for m in moments if m.type == "impactful_opening_kill"]
        self.assertEqual(len(openings), 1)
        self.assertEqual(openings[0].subtype, "high_impact_opening")


if __name__ == "__main__":
    unittest.main()
