import unittest

from demo_analysis.impact_engine.event_evaluation import EventEvalSample, evaluate_event_samples
from demo_analysis.impact_engine.models import EventType, GameEvent


class TestEventDetectionMetrics(unittest.TestCase):
    def test_event_level_metrics_time_map_and_attribution(self):
        sample = EventEvalSample(
            map_name="de_mirage",
            predicted=[
                GameEvent(EventType.KILL, 10.2, "A", "B", weapon="AK-47"),
                GameEvent(EventType.DEATH, 10.2, "B", "A", weapon="AK-47"),
                GameEvent(EventType.DAMAGE, 11.0, "A", "C", weapon="HE Grenade", damage_health=40),
                GameEvent(EventType.KILL, 20.0, "X", "Y", weapon="M4A1"),
            ],
            truth=[
                GameEvent(EventType.KILL, 10.0, "A", "B", weapon="AK-47"),
                GameEvent(EventType.DEATH, 10.0, "B", "A", weapon="AK-47"),
                GameEvent(EventType.DAMAGE, 11.3, "A", "C", weapon="HE Grenade", damage_health=40),
                GameEvent(EventType.KILL, 20.2, "X", "Z", weapon="M4A1"),
            ],
        )

        result = evaluate_event_samples([sample])

        self.assertIn("KILL", result["metrics"])
        self.assertIn("DEATH", result["metrics"])
        self.assertIn("DAMAGE", result["metrics"])
        self.assertGreater(result["time_error_distribution"]["mean_abs_error"], 0)
        self.assertIn("de_mirage", result["map_bucket_performance"])
        self.assertIn("precision", result["map_bucket_performance"]["de_mirage"]["kill"])

        reasons = [x["reason"] for x in result["error_attribution"]]
        self.assertIn("player_name_mismatch", reasons)


if __name__ == "__main__":
    unittest.main()
