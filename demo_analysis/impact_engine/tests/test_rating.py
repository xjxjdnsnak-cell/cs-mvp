"""Tests for rating normalization system."""

import unittest

from demo_analysis.impact_engine.models import PlayerMatchImpact, PlayerRoundImpact
from demo_analysis.impact_engine.rating import normalize_player_ratings


def create_player(name: str, avg_impact: float, high_impact: int = 0, throw: int = 0,
                  self_risk_deaths: int = 0, post_plant_errors: int = 0,
                  effective_trades: int = 0, forced_risk_deaths: int = 0,
                  utility_impact: float = 0.0, tactical_score: float = 0.0,
                  rounds: int = 10) -> PlayerMatchImpact:
    """Create a player with specified attributes for testing."""
    round_impacts = []
    for i in range(rounds):
        ri = PlayerRoundImpact(
            player_name=name,
            round_id=i + 1,
            team="team1",
            player_side="CT",
            round_total_impact=avg_impact,
            utility_impact=utility_impact / rounds if rounds > 0 else 0.0,
        )
        round_impacts.append(ri)
    
    player = PlayerMatchImpact(
        player_name=name,
        team="team1",
        round_impacts=round_impacts,
    )
    player.high_impact_rounds = high_impact
    player.throw_rounds = throw
    player.self_created_risk_deaths = self_risk_deaths
    player.post_plant_errors = post_plant_errors
    player.effective_trades = effective_trades
    player.forced_risk_deaths = forced_risk_deaths
    player.tactical_discipline_score = tactical_score
    
    total_impact = avg_impact * rounds
    player.avg_round_impact = avg_impact
    player.total_round_impact = total_impact
    
    return player


class TestRatingNormalization(unittest.TestCase):
    def test_extreme_low_impact_rating_not_zero(self):
        """极端低 avg_round_impact 不应产生 0 分"""
        player = create_player("BadPlayer", avg_impact=-5.0)
        players = [player]
        normalize_player_ratings(players)
        self.assertGreaterEqual(player.rating_0_100, 5.0)

    def test_extreme_high_impact_rating_not_hundred(self):
        """极端高 avg_round_impact 不应产生 100 分"""
        player = create_player("GoodPlayer", avg_impact=5.0)
        players = [player]
        normalize_player_ratings(players)
        self.assertLessEqual(player.rating_0_100, 95.0)

    def test_ten_players_no_clip_to_extremes(self):
        """10 个不同表现玩家不应全部 clip 到 0/100"""
        players = [
            create_player(f"Player{i}", avg_impact=0.5 * (i - 5))
            for i in range(10)
        ]
        normalize_player_ratings(players)
        
        ratings = [p.rating_0_100 for p in players]
        clipped_low = sum(1 for r in ratings if r <= 5.0)
        clipped_high = sum(1 for r in ratings if r >= 95.0)
        
        self.assertEqual(clipped_low, 0, "不应有玩家 rating <= 5")
        self.assertEqual(clipped_high, 0, "不应有玩家 rating >= 95")

    def test_same_avg_different_rounds_similar_rating(self):
        """同样平均表现、不同回合数的玩家评分应接近"""
        player1 = create_player("Player10Rounds", avg_impact=1.0, rounds=10)
        player2 = create_player("Player20Rounds", avg_impact=1.0, rounds=20)
        players = [player1, player2]
        normalize_player_ratings(players)
        
        diff = abs(player1.rating_0_100 - player2.rating_0_100)
        self.assertLess(diff, 15.0, "相同 avg_impact 的玩家评分差异应小于15")

    def test_utility_cannot_drive_low_player_to_90(self):
        """utility_impact 很高不能把低影响玩家推到 90+"""
        player = create_player("LowPlayer", avg_impact=-2.0, utility_impact=100.0)
        players = [player]
        normalize_player_ratings(players)
        self.assertLess(player.rating_0_100, 90.0)

    def test_death_impact_cannot_drive_player_to_zero(self):
        """差劲的 death_impact 不能直接把玩家打成 0"""
        player = create_player("BadDeathPlayer", avg_impact=-1.5, self_risk_deaths=3)
        players = [player]
        normalize_player_ratings(players)
        self.assertGreater(player.rating_0_100, 0.0)

    def test_rating_components_populated(self):
        """rating_components 应正确填充"""
        player = create_player("TestPlayer", avg_impact=1.0, high_impact=2,
                               effective_trades=3, utility_impact=5.0)
        players = [player]
        normalize_player_ratings(players)
        
        self.assertIn("base_rating", player.rating_components)
        self.assertIn("z_score", player.rating_components)
        self.assertIn("avg_round_impact", player.rating_components)
        self.assertIn("high_impact_bonus", player.rating_components)
        self.assertIn("throw_penalty", player.rating_components)
        self.assertIn("self_created_penalty", player.rating_components)
        self.assertIn("trade_bonus", player.rating_components)
        self.assertIn("utility_bonus", player.rating_components)
        self.assertIn("tactical_bonus", player.rating_components)
        self.assertIn("final_rating_before_clamp", player.rating_components)
        self.assertIn("rating_0_100", player.rating_components)

    def test_z_score_calculation(self):
        """z_score 应正确计算"""
        players = [
            create_player("Low", avg_impact=-1.0),
            create_player("Mid", avg_impact=0.0),
            create_player("High", avg_impact=1.0),
        ]
        normalize_player_ratings(players)
        
        low_player = next(p for p in players if p.player_name == "Low")
        high_player = next(p for p in players if p.player_name == "High")
        
        self.assertLess(low_player.rating_components["z_score"], 0)
        self.assertGreater(high_player.rating_components["z_score"], 0)

    def test_high_impact_bonus_applied(self):
        """高影响回合加成应正确应用"""
        players = [
            create_player("NoHighImpact", avg_impact=0.5, high_impact=0),
            create_player("WithHighImpact", avg_impact=0.5, high_impact=5),
        ]
        normalize_player_ratings(players)
        
        no_high = next(p for p in players if p.player_name == "NoHighImpact")
        with_high = next(p for p in players if p.player_name == "WithHighImpact")
        
        self.assertGreater(
            with_high.rating_0_100, no_high.rating_0_100,
            "有高影响回合的玩家评分应更高"
        )

    def test_throw_penalty_applied(self):
        """失误回合惩罚应正确应用"""
        players = [
            create_player("NoThrow", avg_impact=0.5, throw=0),
            create_player("WithThrow", avg_impact=0.5, throw=5),
        ]
        normalize_player_ratings(players)
        
        no_throw = next(p for p in players if p.player_name == "NoThrow")
        with_throw = next(p for p in players if p.player_name == "WithThrow")
        
        self.assertLess(
            with_throw.rating_0_100, no_throw.rating_0_100,
            "有失误回合的玩家评分应更低"
        )

    def test_returns_rating_statistics(self):
        """normalize_player_ratings 应返回评分统计"""
        players = [
            create_player(f"Player{i}", avg_impact=i * 0.5 - 2.5)
            for i in range(10)
        ]
        stats = normalize_player_ratings(players)
        
        self.assertIn("rating_mean", stats)
        self.assertIn("rating_std", stats)
        self.assertIn("rating_min", stats)
        self.assertIn("rating_max", stats)
        self.assertIn("rating_clamped_low_count", stats)
        self.assertIn("rating_clamped_high_count", stats)
        self.assertEqual(stats["rating_clamped_low_count"], 0)
        self.assertEqual(stats["rating_clamped_high_count"], 0)

    def test_empty_player_list(self):
        """空玩家列表应返回空的统计字典"""
        players = []
        result = normalize_player_ratings(players)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["rating_zero_count"], 0)
        self.assertEqual(result["rating_hundred_count"], 0)

    def test_utility_bonus_clamped(self):
        """utility_bonus 应在 [-2.1, 2.1] 范围内"""
        player = create_player("HighUtility", avg_impact=0.0, utility_impact=100.0)
        players = [player]
        normalize_player_ratings(players)
        
        utility_bonus = player.rating_components["utility_bonus"]
        self.assertGreaterEqual(utility_bonus, -2.1)
        self.assertLessEqual(utility_bonus, 2.1)

    def test_tactical_bonus_clamped(self):
        """tactical_bonus 应在 [-3.2, 3.2] 范围内"""
        player = create_player("HighTactical", avg_impact=0.0, tactical_score=100.0)
        players = [player]
        normalize_player_ratings(players)
        
        tactical_bonus = player.rating_components["tactical_bonus"]
        self.assertGreaterEqual(tactical_bonus, -3.2)
        self.assertLessEqual(tactical_bonus, 3.2)


if __name__ == "__main__":
    unittest.main()
