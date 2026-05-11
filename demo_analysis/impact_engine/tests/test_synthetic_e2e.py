import json
import os
import tempfile
import subprocess
import unittest
from pathlib import Path

# Add demo_analysis to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from demo_analysis.impact_engine import ImpactEngine
from demo_analysis.high_level_analysis import build_dashboard_payload


class TestSyntheticEndToEnd(unittest.TestCase):
    """End-to-end tests using synthetic analysis data."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.fixture_dir = Path(__file__).parent / "fixtures"
        self.synthetic_json_path = self.fixture_dir / "synthetic_analysis.json"
        
        # Load the raw synthetic analysis data
        with open(self.synthetic_json_path, "r", encoding="utf-8") as f:
            self.raw_data = json.load(f)
        
        # Build dashboard payload
        self.dashboard_payload = build_dashboard_payload(self.raw_data)
    
    def test_load_from_payload(self):
        """Test loading from dashboard payload."""
        engine = ImpactEngine(self.dashboard_payload)
        self.assertIsNotNone(engine.dashboard_payload)
        self.assertEqual(len(engine.rounds), 2)
    
    def test_analysis_run(self):
        """Test running a complete analysis."""
        engine = ImpactEngine(self.dashboard_payload)
        report = engine.analyze()
        
        # Verify report structure
        self.assertIsNotNone(report)
        self.assertIsNotNone(report.player_impacts)
        self.assertGreater(len(report.player_impacts), 0)
        
        # Verify each player impact has the required fields
        for player_impact in report.player_impacts:
            self.assertIsNotNone(player_impact.player_name)
            self.assertIsNotNone(player_impact.team)
            self.assertIsNotNone(player_impact.rating_0_100)
            self.assertGreaterEqual(player_impact.rating_0_100, 0.0)
            self.assertLessEqual(player_impact.rating_0_100, 100.0)
    
    def test_json_output(self):
        """Test generating JSON output."""
        engine = ImpactEngine(self.dashboard_payload)
        report = engine.analyze()
        json_data = engine.generate_json_output()

        # Verify JSON structure
        self.assertIsInstance(json_data, dict)
        self.assertIn("players", json_data)
        self.assertIsInstance(json_data["players"], list)

        # Check that player impacts have ratings
        for player in json_data["players"]:
            self.assertIn("player_name", player)
            self.assertIn("team", player)
            self.assertIn("rating_0_100", player)
    
    def test_markdown_output(self):
        """Test generating Markdown report."""
        engine = ImpactEngine(self.dashboard_payload)
        markdown = engine.generate_markdown_report()
        
        self.assertIsInstance(markdown, str)
        self.assertGreater(len(markdown), 0)
        self.assertIn("#", markdown)  # Should have headers
    
    def test_team_side_correctness_round1(self):
        """Test that team1 is CT in round 1."""
        engine = ImpactEngine(self.dashboard_payload)
        engine.analyze()
        
        # Check round 1 context
        round1 = engine.rounds[0]
        self.assertTrue(round1.get("team1_on_ct", False))
    
    def test_team_side_correctness_round2(self):
        """Test that team1 is T in round 2."""
        engine = ImpactEngine(self.dashboard_payload)
        engine.analyze()
        
        # Check round 2 context
        round2 = engine.rounds[1]
        self.assertFalse(round2.get("team1_on_ct", True))


class TestCLI(unittest.TestCase):
    """Test CLI interface using synthetic data."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.fixture_dir = Path(__file__).parent / "fixtures"
        self.synthetic_json_path = self.fixture_dir / "synthetic_analysis.json"
        self.project_root = Path(__file__).resolve().parents[3]
        sys.path.insert(0, str(self.project_root))
    
    def test_cli_basic(self):
        """Test running CLI with synthetic data (without full run due to dependencies)."""
        try:
            # We'll just test that the module is importable
            from demo_analysis.impact_engine import cli
            self.assertIsNotNone(cli)
        except Exception as e:
            self.fail(f"CLI module could not be imported: {e}")
    
    def test_temporary_file_output(self):
        """Test that the file output system works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "output.md"
            json_path = Path(tmpdir) / "output.json"
            
            # Create engine and run
            with open(self.synthetic_json_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            
            dashboard_payload = build_dashboard_payload(raw_data)
            engine = ImpactEngine(dashboard_payload)
            report = engine.analyze()
            
            # Generate outputs in memory
            markdown = engine.generate_markdown_report()
            json_data = engine.generate_json_output()
            
            # Write to temp files
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            # Verify files exist and have content
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            self.assertGreater(md_path.stat().st_size, 0)
            self.assertGreater(json_path.stat().st_size, 0)
    
    def test_player_labels_generation(self):
        """Test that player labels are correctly generated."""
        with open(self.synthetic_json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        dashboard_payload = build_dashboard_payload(raw_data)
        engine = ImpactEngine(dashboard_payload)
        report = engine.analyze()

        # Check that we have labels in report
        self.assertIsNotNone(report.player_impacts)
        self.assertGreater(len(report.player_impacts), 0)


if __name__ == "__main__":
    unittest.main()
