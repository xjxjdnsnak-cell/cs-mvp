"""Characterization tests for demoparser_utils.state_extract.

These tests pin the EXACT dict output of extract_states / extract_states_by_group
on a fully synthetic match: a FakeParser stands in for demoparser2.DemoParser and
serves small pandas DataFrames shaped like the real parser's outputs (ticks /
players / inventory / grenades / death_ticks / damage_ticks with the real column
names). They must pass unchanged before and after the performance refactor of the
per-tick filtering (audit P-2) so any output drift is caught immediately.

Synthetic match layout (all game_time values are exact tick/64 fractions so float
comparisons are deterministic):
  - round 0: freeze_end tick 100, sampled ticks [116, 132, 148], bomb planted at
    tick 160 (game_time 2.5), round_end tick 180.
  - round 1: freeze_end tick 200, sampled ticks [216, 232], bomb planted exactly
    at sampled tick 216 (game_time 3.375), round_end tick 280.
  - player 6 (T side) carries the C4 over [100, 160] and [200, 216] inclusive.
"""
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# state_extract imports snappy / demoparser2 at module import time; provide
# lightweight stubs when they are not installed (the real parser is faked below).
for _stub_name in ("snappy", "demoparser2"):
    try:
        __import__(_stub_name)
    except ImportError:
        _stub = types.ModuleType(_stub_name)
        if _stub_name == "demoparser2":
            _stub.DemoParser = object
        else:
            _stub.compress = lambda data: data
        sys.modules[_stub_name] = _stub

import demoparser_utils.state_extract as state_extract  # noqa: E402


MAP_NAME = "de_testmap"
FREEZE_TICKS = [100, 200]
ROUND_END_EVENTS = [(180, "CT", "Elimination"), (280, "T", "Elimination")]
CARRY_WINDOWS = [(100, 160), (200, 216)]  # inclusive: player 6 holds C4 there
PLANT_GAME_TIME = {0: 2.5, 1: 3.375}
SMOKE_PRE_ROUND = {"game_time": 1.0, "round": 0, "x": 1.0, "y": 1.0, "z": 1.0, "entityid": 100}
SMOKE_R0 = {"game_time": 1.875, "round": 0, "x": 5.0, "y": 6.0, "z": 7.0, "entityid": 101}
SMOKE_R0_END = {"game_time": 3.875, "round": 0, "entityid": 101}
SMOKE_R1 = {"game_time": 3.25, "round": 1, "x": 8.0, "y": 9.0, "z": 10.0, "entityid": 102}
SMOKE_R1_END = {"game_time": 3.5, "round": 1, "entityid": 102}
INFERNO_R0 = {"game_time": 2.125, "round": 0, "x": 11.0, "y": 12.0, "z": 13.0, "entityid": 200}
INFERNO_R0_END = {"game_time": 2.375, "round": 0, "entityid": 200}


def _event_row(event: dict) -> dict:
    """smoke/inferno/bomb event rows carry the parse_events `other` columns."""
    return {
        "game_start_time": 0.0,
        "total_rounds_played": event["round"],
        **event,
    }


PLAYER_COLUMNS = [
    "tick", "steamid", "name", "X", "Y", "Z", "game_time", "game_start_time",
    "total_rounds_played", "weapon_name", "inventory", "inventory_as_ids",
    "pitch", "yaw", "is_alive", "health", "flash_duration", "flash_max_alpha",
    "team_num", "last_place_name", "armor", "has_helmet", "has_defuser",
    "is_bomb_planted", "is_bomb_dropped", "approximate_spotted_by",
    "velocity", "velocity_X", "velocity_Y", "velocity_Z",
]

GRENADE_COLUMNS = ["tick", "name", "steamid", "grenade_entity_id", "grenade_type", "x", "y", "z"]
GRENADE_ROWS = [
    {"tick": 132, "name": "Player6", "steamid": "1006", "grenade_entity_id": 9001,
     "grenade_type": "smoke", "x": 1.5, "y": 2.5, "z": 64.0},
    # NaN position -> must be skipped by the per-tick filtering
    {"tick": 132, "name": "Player7", "steamid": "1007", "grenade_entity_id": 9002,
     "grenade_type": "flashbang", "x": 1.5, "y": 2.5, "z": float("nan")},
    {"tick": 216, "name": "Player8", "steamid": "1008", "grenade_entity_id": 9003,
     "grenade_type": "molotov", "x": 3.5, "y": 4.5, "z": 64.0},
]

DEATH_COLUMNS = [
    "tick", "total_rounds_played", "game_time",
    "attacker_name", "attacker_steamid", "assister_name", "assister_steamid",
    "user_name", "user_steamid", "assistedflash", "attackerblind", "attackerinair",
    "dmg_health", "headshot", "thrusmoke", "weapon",
]
DEATH_ROWS = [
    {"tick": 125, "total_rounds_played": 0, "game_time": 125 / 64,
     "attacker_name": "Player6", "attacker_steamid": "1006",
     "assister_name": "Player10", "assister_steamid": "1010",
     "user_name": "Player1", "user_steamid": "1001",
     "assistedflash": False, "attackerblind": False, "attackerinair": True,
     "dmg_health": 100, "headshot": True, "thrusmoke": False, "weapon": "ak47"},
    {"tick": 140, "total_rounds_played": 0, "game_time": 140 / 64,
     "attacker_name": "Player7", "attacker_steamid": "1007",
     "assister_name": "", "assister_steamid": "",
     "user_name": "Player2", "user_steamid": "1002",
     "assistedflash": False, "attackerblind": False, "attackerinair": False,
     "dmg_health": 100, "headshot": False, "thrusmoke": False, "weapon": "deagle"},
    {"tick": 220, "total_rounds_played": 1, "game_time": 220 / 64,
     "attacker_name": "Player8", "attacker_steamid": "1008",
     "assister_name": "", "assister_steamid": "",
     "user_name": "Player9", "user_steamid": "1009",
     "assistedflash": False, "attackerblind": False, "attackerinair": False,
     "dmg_health": 100, "headshot": False, "thrusmoke": False, "weapon": "awp"},
]

DAMAGE_COLUMNS = [
    "tick", "total_rounds_played", "game_time",
    "attacker_name", "attacker_steamid", "user_name", "user_steamid",
    "dmg_health", "weapon",
]
DAMAGE_ROWS = [
    {"tick": 122, "total_rounds_played": 0, "game_time": 122 / 64,
     "attacker_name": "Player6", "attacker_steamid": "1006",
     "user_name": "Player1", "user_steamid": "1001", "dmg_health": 30, "weapon": "ak47"},
    # same tick as the previous row: pins within-tick ordering of future_damage
    {"tick": 122, "total_rounds_played": 0, "game_time": 122 / 64,
     "attacker_name": "Player7", "attacker_steamid": "1007",
     "user_name": "Player2", "user_steamid": "1002", "dmg_health": 25, "weapon": "deagle"},
    {"tick": 138, "total_rounds_played": 0, "game_time": 138 / 64,
     "attacker_name": "Player6", "attacker_steamid": "1006",
     "user_name": "Player3", "user_steamid": "1003", "dmg_health": 40, "weapon": "ak47"},
    {"tick": 224, "total_rounds_played": 1, "game_time": 224 / 64,
     "attacker_name": "Player6", "attacker_steamid": "1006",
     "user_name": "Player1", "user_steamid": "1001", "dmg_health": 10, "weapon": "glock"},
]


def round_of(tick: int) -> int:
    return 0 if tick < 200 else 1


def game_time_of(tick: int) -> float:
    return tick / 64.0


def carries_c4(tick: int, player: int) -> bool:
    return player == 6 and any(lo <= tick <= hi for lo, hi in CARRY_WINDOWS)


def is_bomb_planted_at(tick: int) -> bool:
    return tick >= 160 if round_of(tick) == 0 else tick >= 216


def player_rows_for_tick(tick: int) -> list[dict]:
    rows = []
    r = round_of(tick)
    for i in range(1, 11):
        ct = i <= 5
        carry = carries_c4(tick, i)
        rows.append({
            "tick": tick,
            "steamid": str(1000 + i),
            "name": f"Player{i}",
            "X": tick + i,
            "Y": 2 * tick + i,
            "Z": 3.0,
            "game_time": game_time_of(tick),
            "game_start_time": 0.0,
            "total_rounds_played": r,
            "weapon_name": "knife",
            "inventory": ["Knife", "C4 Explosive"] if carry else ["Knife"],
            "inventory_as_ids": [1, 49] if carry else [1],
            "pitch": 0.0,
            "yaw": 90.0,
            "is_alive": True,
            "health": 100,
            "flash_duration": 0.0,
            "flash_max_alpha": 0.0,
            "team_num": 3 if ct else 2,
            "last_place_name": "Area",
            "armor": 100,
            "has_helmet": True,
            "has_defuser": ct,
            "is_bomb_planted": is_bomb_planted_at(tick),
            "is_bomb_dropped": False,
            "approximate_spotted_by": ["1002", "1006"],
            # NaN velocity paths must be normalized to 0 by the implementation
            "velocity": float("nan") if i == 1 else 1.5,
            "velocity_X": 1.0,
            "velocity_Y": 2.0,
            "velocity_Z": float("nan") if i == 2 else 3.0,
        })
    return rows


class FakeParser:
    """Stand-in for demoparser2.DemoParser serving the synthetic match."""

    def __init__(self, demo_path: str):
        self.demo_path = demo_path

    def parse_header(self) -> dict:
        return {"map_name": MAP_NAME}

    def parse_event(self, name: str, other=None) -> pd.DataFrame:
        return self._event_frames()[name].copy()

    def parse_events(self, names, other=None):
        frames = self._event_frames()
        return [(name, frames[name].copy()) for name in names]

    def parse_grenades(self, grenades: bool = False) -> pd.DataFrame:
        return pd.DataFrame(GRENADE_ROWS, columns=GRENADE_COLUMNS)

    def parse_ticks(self, wanted_props, ticks=None) -> pd.DataFrame:
        if ticks is None:
            # dense per-tick frame used for round start times
            max_tick = max(t for window in CARRY_WINDOWS for t in window)
            rows = [
                {"tick": t, "game_time": game_time_of(t),
                 "total_rounds_played": round_of(t)}
                for t in range(0, max_tick + 1)
            ]
            return pd.DataFrame(rows)
        rows = [row for tick in ticks for row in player_rows_for_tick(tick)]
        return pd.DataFrame(rows, columns=PLAYER_COLUMNS)

    @staticmethod
    def _event_frames() -> dict:
        return {
            "round_freeze_end": pd.DataFrame({"tick": FREEZE_TICKS}),
            "round_end": pd.DataFrame(
                [{"tick": t, "winner": w, "reason": reason}
                 for t, w, reason in ROUND_END_EVENTS]
            ),
            "smokegrenade_detonate": pd.DataFrame(
                [_event_row(SMOKE_PRE_ROUND), _event_row(SMOKE_R0), _event_row(SMOKE_R1)]),
            "smokegrenade_expired": pd.DataFrame(
                [_event_row(SMOKE_R0_END), _event_row(SMOKE_R1_END)]),
            "inferno_startburn": pd.DataFrame([_event_row(INFERNO_R0)]),
            "inferno_expire": pd.DataFrame([_event_row(INFERNO_R0_END)]),
            "bomb_planted": pd.DataFrame([
                _event_row({"game_time": PLANT_GAME_TIME[0], "round": 0}),
                _event_row({"game_time": PLANT_GAME_TIME[1], "round": 1}),
            ]),
            "player_death": pd.DataFrame(DEATH_ROWS, columns=DEATH_COLUMNS),
            "player_hurt": pd.DataFrame(DAMAGE_ROWS, columns=DAMAGE_COLUMNS),
        }


# ---------------------------------------------------------------------------
# Expected-output builders (written from the synthetic spec above, independently
# of the implementation under test).
# ---------------------------------------------------------------------------

def expected_player_row(i: int, tick: int) -> dict:
    ct = i <= 5
    carry = carries_c4(tick, i)
    return {
        "steamid": str(1000 + i),
        "name": f"Player{i}",
        "X": tick + i,
        "Y": 2 * tick + i,
        "Z": 3.0,
        "last_place_name": "Area",
        "weapon_name": "knife",
        "inventory": ["Knife", "C4 Explosive"] if carry else ["Knife"],
        "inventory_as_ids": [1, 49] if carry else [1],
        "pitch": 0.0,
        "yaw": 90.0,
        "is_alive": True,
        "health": 100,
        "flash_duration": 0.0,
        "flash_max_alpha": 0.0,
        "armor": 100,
        "has_helmet": True,
        "has_defuser": ct,
        "team_num": "CT" if ct else "T",
        "spotted_by": ["1006"] if ct else ["1002"],
        "velocity": 0 if i == 1 else 1.5,
        "velocity_X": 1.0,
        "velocity_Y": 2.0,
        "velocity_Z": 0 if i == 2 else 3.0,
    }


def expected_bomb_position(tick: int):
    """[X, Y, Z] at the nearest tick <= `tick` where a player carried the C4."""
    r = round_of(tick)
    t = tick
    while t >= 0:
        if any(lo <= t <= hi for lo, hi in CARRY_WINDOWS):
            if round_of(t) == r:
                return [t + 6, 2 * t + 6, 3.0]
            return None
        t -= 1
    return None


def expected_entity_grenades(tick: int) -> list:
    if tick == 132:
        return [{"name": "Player6", "steamid": "1006", "entityid": 9001,
                 "type": "smoke", "position": (1.5, 2.5, 64.0)}]
    if tick == 216:
        return [{"name": "Player8", "steamid": "1008", "entityid": 9003,
                 "type": "molotov", "position": (3.5, 4.5, 64.0)}]
    return []


def expected_projectiles(tick: int) -> list:
    gt = game_time_of(tick)
    if tick == 132:
        return [{"type": "smokegrenade", "entityid": 101,
                 "position": (5.0, 6.0, 7.0), "duration": gt - 1.875}]
    if tick == 148:
        return [
            {"type": "smokegrenade", "entityid": 101,
             "position": (5.0, 6.0, 7.0), "duration": gt - 1.875},
            {"type": "inferno", "entityid": 200,
             "position": (11.0, 12.0, 13.0), "duration": gt - 2.125},
        ]
    if tick == 216:
        return [{"type": "smokegrenade", "entityid": 102,
                 "position": (8.0, 9.0, 10.0), "duration": gt - 3.25}]
    return []


def expected_future_kills(tick: int) -> list:
    r = round_of(tick)
    round_start = game_time_of(FREEZE_TICKS[r])
    out = []
    for death in DEATH_ROWS:
        if death["tick"] > tick and death["total_rounds_played"] == r:
            out.append({
                "attacker_name": death["attacker_name"],
                "attacker_steamid": death["attacker_steamid"],
                "assister_name": death["assister_name"],
                "assister_steamid": death["assister_steamid"],
                "victim_name": death["user_name"],
                "victim_steamid": death["user_steamid"],
                "assistedflash": death["assistedflash"],
                "attackerblind": death["attackerblind"],
                "attackerinair": death["attackerinair"],
                "dmg_health": death["dmg_health"],
                "headshot": death["headshot"],
                "thrusmoke": death["thrusmoke"],
                "weapon": death["weapon"],
                "time": death["game_time"] - round_start,
            })
    return out


def expected_future_damage(tick: int) -> list:
    r = round_of(tick)
    round_start = game_time_of(FREEZE_TICKS[r])
    out = []
    for dmg in DAMAGE_ROWS:
        if dmg["tick"] > tick and dmg["total_rounds_played"] == r:
            out.append({
                "attacker_name": dmg["attacker_name"],
                "attacker_steamid": dmg["attacker_steamid"],
                "victim_name": dmg["user_name"],
                "victim_steamid": dmg["user_steamid"],
                "dmg_health": dmg["dmg_health"],
                "weapon": dmg["weapon"],
                "time": dmg["game_time"] - round_start,
            })
    return out


def expected_state(tick: int) -> dict:
    r = round_of(tick)
    round_start = game_time_of(FREEZE_TICKS[r])
    round_seconds = game_time_of(tick) - round_start
    planted = is_bomb_planted_at(tick)
    planted_time = PLANT_GAME_TIME[r] - round_start
    return {
        "round": r,
        "tick": tick,
        "round_label": {"round_info": {
            "winner": ROUND_END_EVENTS[r][1],
            "reason": ROUND_END_EVENTS[r][2],
        }},
        "map_name": MAP_NAME,
        "round_seconds": round_seconds,
        "is_bomb_planted": planted,
        "is_bomb_dropped": False,
        "bomb_planted_time": planted_time,
        "bomb_planted_duration": (round_seconds - planted_time) if planted else None,
        "entity_grenades": expected_entity_grenades(tick),
        "bomb_position": expected_bomb_position(tick),
        "players_info": [expected_player_row(i, tick) for i in range(1, 11)],
        "projectiles": expected_projectiles(tick),
        "future_kills": expected_future_kills(tick),
        "future_damage": expected_future_damage(tick),
    }


ALL_SAMPLE_TICKS = [116, 132, 148, 216, 232]


@pytest.fixture
def faked_parser(monkeypatch):
    monkeypatch.setattr(state_extract, "DemoParser", FakeParser)
    return FakeParser


def test_extract_states_exact_output(faked_parser):
    ticks = [232, 116, 216, 148, 132]  # deliberately unsorted; output must be ascending
    results = state_extract.extract_states("fake.dem", ticks)

    assert [state["tick"] for state in results] == ALL_SAMPLE_TICKS
    assert results == [expected_state(tick) for tick in ALL_SAMPLE_TICKS]


def test_extract_states_full_literal_tick_116(faked_parser):
    """Fully literal anchor for one tick (guards the expected_* builders)."""
    results = state_extract.extract_states("fake.dem", [116])
    assert len(results) == 1
    state = results[0]
    assert state["round"] == 0
    assert state["tick"] == 116
    assert state["map_name"] == "de_testmap"
    assert state["round_label"] == {"round_info": {"winner": "CT", "reason": "Elimination"}}
    assert state["round_seconds"] == pytest.approx(0.25)
    assert not state["is_bomb_planted"]
    assert not state["is_bomb_dropped"]
    assert state["bomb_planted_time"] == pytest.approx(0.9375)
    assert state["bomb_planted_duration"] is None
    assert state["entity_grenades"] == []
    assert state["bomb_position"] == [122, 238, 3.0]
    assert state["projectiles"] == []
    assert len(state["players_info"]) == 10
    assert state["players_info"][0] == {
        "steamid": "1001", "name": "Player1", "X": 117, "Y": 233, "Z": 3.0,
        "last_place_name": "Area", "weapon_name": "knife",
        "inventory": ["Knife"], "inventory_as_ids": [1],
        "pitch": 0.0, "yaw": 90.0, "is_alive": True, "health": 100,
        "flash_duration": 0.0, "flash_max_alpha": 0.0,
        "armor": 100, "has_helmet": True, "has_defuser": True,
        "team_num": "CT", "spotted_by": ["1006"],
        "velocity": 0, "velocity_X": 1.0, "velocity_Y": 2.0, "velocity_Z": 3.0,
    }
    assert state["players_info"][5] == {
        "steamid": "1006", "name": "Player6", "X": 122, "Y": 238, "Z": 3.0,
        "last_place_name": "Area", "weapon_name": "knife",
        "inventory": ["Knife", "C4 Explosive"], "inventory_as_ids": [1, 49],
        "pitch": 0.0, "yaw": 90.0, "is_alive": True, "health": 100,
        "flash_duration": 0.0, "flash_max_alpha": 0.0,
        "armor": 100, "has_helmet": True, "has_defuser": False,
        "team_num": "T", "spotted_by": ["1002"],
        "velocity": 1.5, "velocity_X": 1.0, "velocity_Y": 2.0, "velocity_Z": 3.0,
    }
    assert state["future_kills"] == [
        {
            "attacker_name": "Player6", "attacker_steamid": "1006",
            "assister_name": "Player10", "assister_steamid": "1010",
            "victim_name": "Player1", "victim_steamid": "1001",
            "assistedflash": False, "attackerblind": False, "attackerinair": True,
            "dmg_health": 100, "headshot": True, "thrusmoke": False,
            "weapon": "ak47", "time": pytest.approx(0.390625),
        },
        {
            "attacker_name": "Player7", "attacker_steamid": "1007",
            "assister_name": "", "assister_steamid": "",
            "victim_name": "Player2", "victim_steamid": "1002",
            "assistedflash": False, "attackerblind": False, "attackerinair": False,
            "dmg_health": 100, "headshot": False, "thrusmoke": False,
            "weapon": "deagle", "time": pytest.approx(0.625),
        },
    ]
    assert state["future_damage"] == [
        {
            "attacker_name": "Player6", "attacker_steamid": "1006",
            "victim_name": "Player1", "victim_steamid": "1001",
            "dmg_health": 30, "weapon": "ak47", "time": pytest.approx(0.34375),
        },
        {
            "attacker_name": "Player7", "attacker_steamid": "1007",
            "victim_name": "Player2", "victim_steamid": "1002",
            "dmg_health": 25, "weapon": "deagle", "time": pytest.approx(0.34375),
        },
        {
            "attacker_name": "Player6", "attacker_steamid": "1006",
            "victim_name": "Player3", "victim_steamid": "1003",
            "dmg_health": 40, "weapon": "ak47", "time": pytest.approx(0.59375),
        },
    ]


def test_extract_states_by_group_exact_output(faked_parser):
    ticks_group = [[148, 132, 116], [232, 216]]  # unsorted per group on purpose
    results_group = state_extract.extract_states_by_group("fake.dem", ticks_group)

    assert len(results_group) == 2
    assert [state["tick"] for state in results_group[0]] == [116, 132, 148]
    assert [state["tick"] for state in results_group[1]] == [216, 232]
    assert results_group == [
        [expected_state(tick) for tick in (116, 132, 148)],
        [expected_state(tick) for tick in (216, 232)],
    ]


def test_find_last_carrier_tick_sparse_map():
    """Pins the lookup semantics the bounded C4 search relies on.

    Scanning backwards from the target tick, the first recorded tick decides:
    same round -> its carrier; different round -> search stops with None.
    Ticks without a record are skipped.
    """
    carrier_map = {
        100: ("a", 1.0, 2.0, 3.0, 0),
        150: ("b", 4.0, 5.0, 6.0, 0),
        160: ("c", 7.0, 8.0, 9.0, 1),
        300: ("d", 10.0, 11.0, 12.0, 1),
    }
    # exact hit
    assert state_extract.find_last_carrier_tick(150, carrier_map, 0) == [4.0, 5.0, 6.0]
    # skips ticks without a record, stops at the previous same-round record
    assert state_extract.find_last_carrier_tick(200, carrier_map, 1) == [7.0, 8.0, 9.0]
    assert state_extract.find_last_carrier_tick(302, carrier_map, 1) == [10.0, 11.0, 12.0]
    # first record backwards belongs to another round -> None
    assert state_extract.find_last_carrier_tick(200, carrier_map, 0) is None
    assert state_extract.find_last_carrier_tick(310, carrier_map, 0) is None
    # no record at or before the target
    assert state_extract.find_last_carrier_tick(90, carrier_map, 0) is None
    assert state_extract.find_last_carrier_tick(90, carrier_map, 1) is None
    # empty map
    assert state_extract.find_last_carrier_tick(150, {}, 0) is None


# ---------------------------------------------------------------------------
# Focused tests for the bounded C4 lookup and pre-indexing helpers.
# ---------------------------------------------------------------------------

def _legacy_carrier_scan(target_tick, mapping, rnd):
    """Independent oracle: the original integer-scan implementation."""
    for t in range(target_tick, -1, -1):
        if t in mapping:
            if rnd != mapping[t][4]:
                break
            return [mapping[t][1], mapping[t][2], mapping[t][3]]
    return None


def test_find_last_carrier_tick_matches_legacy_scan():
    """The sorted-keys lookup is equivalent to the legacy backwards scan."""
    carrier_map = {
        0: ("p0", 0.0, 0.5, 1.0, 0),
        100: ("a", 1.0, 2.0, 3.0, 0),
        150: ("b", 4.0, 5.0, 6.0, 0),
        160: ("c", 7.0, 8.0, 9.0, 1),
        161: ("c2", 7.5, 8.5, 9.5, 1),
        300: ("d", 10.0, 11.0, 12.0, 1),
    }
    sorted_ticks = sorted(carrier_map)
    for target in (-5, 0, 1, 90, 100, 120, 149, 150, 151, 160, 161, 200, 299, 300, 301):
        for rnd in (0, 1, 2):
            assert state_extract.find_last_carrier_tick(target, carrier_map, rnd, sorted_ticks) \
                == _legacy_carrier_scan(target, carrier_map, rnd)
            # the None path (sorts internally) must agree too
            assert state_extract.find_last_carrier_tick(target, carrier_map, rnd) \
                == _legacy_carrier_scan(target, carrier_map, rnd)


def test_build_bomb_carrier_map():
    rows = [
        {"tick": 100, "steamid": "a", "X": 1.0, "Y": 2.0, "Z": 3.0,
         "total_rounds_played": 0, "inventory": ["Knife"]},
        # two carriers in one tick: the last parsed row wins
        {"tick": 100, "steamid": "b", "X": 4.0, "Y": 5.0, "Z": 6.0,
         "total_rounds_played": 0, "inventory": ["Knife", "C4 Explosive"]},
        # non-list inventory (NaN/None cell) must be ignored
        {"tick": 101, "steamid": "c", "X": 7.0, "Y": 8.0, "Z": 9.0,
         "total_rounds_played": 0, "inventory": None},
        {"tick": 102, "steamid": "d", "X": 10.0, "Y": 11.0, "Z": 12.0,
         "total_rounds_played": 0, "inventory": ["C4 Explosive"]},
        # C4 need not be the last inventory item; rounds are recorded
        {"tick": 200, "steamid": "e", "X": 13.0, "Y": 14.0, "Z": 15.0,
         "total_rounds_played": 1, "inventory": ["C4 Explosive", "Knife"]},
    ]
    mapping = state_extract.build_bomb_carrier_map(pd.DataFrame(rows))
    assert mapping == {
        100: ("b", 4.0, 5.0, 6.0, 0),
        102: ("d", 10.0, 11.0, 12.0, 0),
        200: ("e", 13.0, 14.0, 15.0, 1),
    }


def test_rows_at_tick_matches_boolean_mask():
    rows = [
        {"tick": 10, "total_rounds_played": 0, "v": "b"},
        {"tick": 10, "total_rounds_played": 0, "v": "c"},
        {"tick": 10, "total_rounds_played": 1, "v": "e"},
        {"tick": 20, "total_rounds_played": 1, "v": "d"},
        {"tick": 30, "total_rounds_played": 1, "v": "a"},
        {"tick": 40, "total_rounds_played": 1, "v": "f"},
    ]
    df = pd.DataFrame(rows)
    df_indexed, tick_values = state_extract._per_tick_index(df)
    for tick in (5, 10, 20, 30, 40, 50):
        expected = df[df["tick"] == tick]["v"].tolist()
        actual = state_extract._rows_at_tick(df_indexed, tick_values, tick)["v"].tolist()
        assert actual == expected, f"tick {tick}"


def test_round_event_index_matches_boolean_mask():
    rows = [
        {"tick": 10, "total_rounds_played": 0, "v": "b"},
        {"tick": 10, "total_rounds_played": 0, "v": "c"},
        {"tick": 10, "total_rounds_played": 1, "v": "e"},
        {"tick": 20, "total_rounds_played": 1, "v": "d"},
        {"tick": 30, "total_rounds_played": 1, "v": "a"},
        {"tick": 40, "total_rounds_played": 1, "v": "f"},
    ]
    df = pd.DataFrame(rows)  # chronological, as parse_event guarantees
    index = state_extract._round_event_index(df)
    empty = df.iloc[0:0]
    for tick in (5, 10, 15, 20, 30, 40):
        for rnd in (0, 1, 2):
            expected = df[(df["tick"] > tick) & (df["total_rounds_played"] == rnd)]["v"].tolist()
            actual = state_extract._future_events(index, empty, rnd, tick)["v"].tolist()
            assert actual == expected, f"round {rnd} tick {tick}"
