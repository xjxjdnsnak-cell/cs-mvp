"""Compare sparse tick vs full tick impact scoring precision."""

import unittest
from demo_analysis.impact_engine.align import (
    build_round_context,
    find_exact_tick,
    find_nearest_tick,
    find_ticks_before,
)
from demo_analysis.impact_engine.models import PredictionTick, RoundContext
from demo_analysis.impact_engine.scoring import calculate_player_round_impact


class TestFullTickPrecision(unittest.TestCase):
    """Test that full tick data improves event alignment precision."""

    def _build_sparse_ticks(self, interval=0.5):
        """Build sparse ticks every 0.5 seconds."""
        ticks = []
        for i in range(121):  # 0 to 60 seconds
            t = i * interval
            ticks.append(PredictionTick(
                round_seconds=t,
                ct_win_rate=0.5 + 0.1 * (t / 60),
                alive