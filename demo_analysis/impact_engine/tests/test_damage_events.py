"""Tests for DAMAGE/future_damage/future_kills event extraction."""

import unittest

from demo_analysis.impact_engine.align import (
    extract_damage_events,
    extract_future_kill_events,
    is_he_weapon,
    is_fire_weapon,
    _normalize_weapon_name,
)
from demo_analysis.impact_engine.models import EventType


class TestWeaponNormalization(unittest.TestCase):
    """Test weapon name normalization functions."""

    def test_normalize_weapon_name(self):
        self.assertEqual(_normalize_weapon_name("HE Grenade"), "hegrenade")
        self.assertEqual(_normalize_weapon_name("weapon_hegrenade"), "hegrenade")
        self.assertEqual(_normalize_weapon_name("Molotov"), "molotov")
        self.assertEqual(_normalize_weapon_name("weapon_molotov"), "molotov")
        self.assertEqual(_normalize_weapon_name("Smoke Grenade"), "smokegrenade")

    def test_is_he_weapon(self):
        self.assertTrue(is_he_weapon("HE Grenade"))
        self.assertTrue(is_he_weapon("hegrenade"))
        self.assertTrue(is_he_weapon("weapon_hegrenade"))
        self.assertFalse(is_he_weapon("Flashbang"))
        self.assertFalse(is_he_weapon("Molotov"))
        self.assertFalse(is_he_weapon("Smoke Grenade"))
        self.assertFalse(is_he_weapon(None))

    def test_is_fire_weapon(self):
        self.assertTrue(is_fire_weapon("Molotov"))
        self.assertTrue(is_fire_weapon("Incendiary"))
        self.assertTrue(is_fire_weapon("weapon_molotov"))
        self.assertTrue(is_fire_weapon("inferno"))
        self.assertFalse(is_fire_weapon("HE Grenade"))
        self.assertFalse(is_fire_weapon("Flashbang"))
        self.assertFalse(is_fire_weapon("Smoke Grenade"))
        self.assertFalse(is_fire_weapon(None))


class TestExtractDamageEvents(unittest.TestCase):
    """Test extract_damage_events function."""

    def test_extract_from_future_damage(self):
        round_data = {
            "ticks": [
                {
                    "round_seconds": 10.0,
                    "future_damage": [
                        {
                            "attacker_name": "Player1",
                            "victim_name": "Player2",
                            "time": 10.5,
                            "weapon": "HE Grenade",
                            "dmg_health": 50,
                        }
                    ]
                }
            ]
        }
        events = extract_damage_events(round_data, ["Player1"], ["Player2"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, EventType.DAMAGE)
        self.assertEqual(events[0].player, "Player1")
        self.assertEqual(events[0].other_player, "Player2")
        self.assertEqual(events[0].weapon, "HE Grenade")
        self.assertEqual(events[0].damage_health, 50)

    def test_extract_with_alternative_fields(self):
        round_data = {
            "ticks": [
                {
                    "round_seconds": 5.0,
                    "future_damage": [
                        {
                            "attacker": "PlayerA",
                            "victim": "PlayerB",
                            "round_seconds": 5.5,
                            "weapon": "Molotov",
                            "damage": 25,
                        }
                    ]
                }
            ]
        }
        events = extract_damage_events(round_data, ["PlayerA"], ["PlayerB"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].player, "PlayerA")
        self.assertEqual(events[0].weapon, "Molotov")
        self.assertEqual(events[0].damage_health, 25)

    def test_deduplication(self):
        round_data = {
            "ticks": [
                {
                    "round_seconds": 10.0,
                    "future_damage": [
                        {
                            "attacker_name": "Player1",
                            "victim_name": "Player2",
                            "time": 10.5,
                            "weapon": "HE Grenade",
                            "dmg_health": 50,
                        },
                        {
                            "attacker_name": "Player1",
                            "victim_name": "Player2",
                            "time": 10.5,
                            "weapon": "HE Grenade",
                            "dmg_health": 50,
                        }
                    ]
                }
            ]
        }
        events = extract_damage_events(round_data, ["Player1"], ["Player2"])
        self.assertEqual(len(events), 1)  # Should deduplicate

    def test_no_damage(self):
        round_data = {"ticks": [{"round_seconds": 0.0}]}
        events = extract_damage_events(round_data, ["Player1"], ["Player2"])
        self.assertEqual(len(events), 0)

    def test_dedup_key_uses_extended_fields(self):
        round_data = {
            "ticks": [{
                "round_seconds": 10.0,
                "future_damage": [
                    {"attacker_name": "A", "victim_name": "E", "time": 10.5, "weapon": "ak47", "damage": 35, "hitgroup": "chest"},
                    {"attacker_name": "A", "victim_name": "E", "time": 10.5, "weapon": "ak47", "damage": 35, "hitgroup": "head"},
                ],
            }]
        }
        events = extract_damage_events(round_data, ["A"], ["E"])
        self.assertEqual(len(events), 2)

    def test_fire_damage_uses_short_window_merge(self):
        round_data = {
            "ticks": [{
                "round_seconds": 10.0,
                "future_damage": [
                    {"attacker_name": "A", "victim_name": "E", "time": 10.50, "weapon": "molotov", "damage": 4},
                    {"attacker_name": "A", "victim_name": "E", "time": 10.51, "weapon": "molotov", "damage": 4},
                ],
            }]
        }
        events = extract_damage_events(round_data, ["A"], ["E"])
        self.assertEqual(len(events), 1)


class TestExtractFutureKillEvents(unittest.TestCase):
    """Test extract_future_kill_events function."""

    def test_extract_future_kill(self):
        round_data = {
            "kills": [],  # No real kills
            "ticks": [
                {
                    "round_seconds": 15.0,
                    "future_kills": [
                        {
                            "killer": "Player1",
                            "victim": "Player2",
                            "time": 15.5,
                            "weapon": "HE Grenade",
                        }
                    ]
                }
            ]
        }
        events = extract_future_kill_events(round_data, ["Player1"], ["Player2"], team1_on_ct=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, EventType.KILL)
        self.assertEqual(events[0].player, "Player1")
        self.assertEqual(events[0].other_player, "Player2")
        self.assertEqual(events[0].weapon, "HE Grenade")

    def test_skip_duplicate_real_kills(self):
        round_data = {
            "kills": [
                {"killer": "Player1", "victim": "Player2", "round_seconds": 10.0}
            ],
            "ticks": [
                {
                    "round_seconds": 10.0,
                    "future_kills": [
                        {
                            "killer": "Player1",
                            "victim": "Player2",
                            "time": 10.5,
                        }
                    ]
                }
            ]
        }
        events = extract_future_kill_events(round_data, ["Player1"], ["Player2"])
        self.assertEqual(len(events), 0)  # Should skip duplicate

    def test_team_mapping_ct(self):
        round_data = {
            "kills": [],
            "ticks": [
                {
                    "round_seconds": 5.0,
                    "future_kills": [
                        {"killer": "Player1", "victim": "Player2", "time": 5.5}
                    ]
                }
            ]
        }
        events = extract_future_kill_events(round_data, ["Player1"], ["Player2"], team1_on_ct=True)
        self.assertEqual(events[0].team_num, "CT")

    def test_team_mapping_t(self):
        round_data = {
            "kills": [],
            "ticks": [
                {
                    "round_seconds": 5.0,
                    "future_kills": [
                        {"killer": "Player1", "victim": "Player2", "time": 5.5}
                    ]
                }
            ]
        }
        events = extract_future_kill_events(round_data, ["Player1"], ["Player2"], team1_on_ct=False)
        self.assertEqual(events[0].team_num, "T")


if __name__ == "__main__":
    unittest.main()
