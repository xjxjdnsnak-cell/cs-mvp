"""Align game events with CS-NET tick predictions."""

from typing import Any

from .models import (
    EventType,
    GameEvent,
    PredictionTick,
    RoundContext,
)


def find_nearest_tick(ticks: list[PredictionTick], target_time: float) -> PredictionTick | None:
    """Find the nearest tick to a target time."""
    if not ticks:
        return None
    nearest = min(ticks, key=lambda t: abs(t.round_seconds - target_time))
    return nearest


def find_ticks_before(
    ticks: list[PredictionTick],
    target_time: float,
    max_seconds: float = 10.0
) -> list[PredictionTick]:
    """Find all ticks before target_time within max_seconds window."""
    result = []
    for tick in ticks:
        gap = target_time - tick.round_seconds
        if 0 <= gap <= max_seconds:
            result.append(tick)
    result.sort(key=lambda t: t.round_seconds, reverse=True)
    return result


def find_ticks_after(
    ticks: list[PredictionTick],
    target_time: float,
    max_seconds: float = 5.0
) -> list[PredictionTick]:
    """Find all ticks after target_time within max_seconds window."""
    result = []
    for tick in ticks:
        gap = tick.round_seconds - target_time
        if 0 <= gap <= max_seconds:
            result.append(tick)
    result.sort(key=lambda t: t.round_seconds)
    return result


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_prediction_tick(tick_data: dict[str, Any]) -> PredictionTick:
    """Build a PredictionTick from tick data."""
    return PredictionTick(
        round_seconds=safe_float(tick_data.get("round_seconds", 0.0)),
        ct_win_rate=safe_float(tick_data.get("ct_win_rate", 0.5)),
        alive_pred=tick_data.get("alive_pred") or [],
        next_kill=tick_data.get("next_kill") or [],
        next_death=tick_data.get("next_death") or [],
        duel=tick_data.get("duel"),
        players_info=tick_data.get("players_info") or [],
        is_bomb_planted=bool(tick_data.get("is_bomb_planted", False)),
        bomb_planted_time=safe_float(tick_data.get("bomb_planted_time")),
    )


def extract_kill_events(
    round_data: dict[str, Any],
    team1_players: list[str],
    team2_players: list[str],
    team1_on_ct: bool = True
) -> list[GameEvent]:
    """Extract kill events from round data."""
    events = []
    kills = round_data.get("kills", [])
    for kill in kills:
        killer = kill.get("killer", "")
        victim = kill.get("victim", "")
        if not killer or not victim:
            continue

        # 根据 team1_on_ct 正确判断 CT/T
        killer_is_team1 = killer in team1_players
        if team1_on_ct:
            attacker_team = "CT" if killer_is_team1 else "T"
        else:
            attacker_team = "T" if killer_is_team1 else "CT"

        event = GameEvent(
            event_type=EventType.KILL,
            tick=safe_float(kill.get("round_seconds", 0.0)),
            player=killer,
            other_player=victim,
            weapon=kill.get("weapon"),
            assister=kill.get("assister"),
            headshot=bool(kill.get("headshot", False)),
            assisted_flash=bool(kill.get("assistedflash", False)),
            attacker_blind=bool(kill.get("attackerblind", False)),
            attacker_in_air=bool(kill.get("attackerinair", False)),
            through_smoke=bool(kill.get("thrusmoke", False)),
            damage_health=safe_int(kill.get("dmg_health")),
            team_num=attacker_team,
        )
        events.append(event)

        # 死亡事件的 team_num 也同样处理
        victim_is_team1 = victim in team1_players
        if team1_on_ct:
            victim_team = "CT" if victim_is_team1 else "T"
        else:
            victim_team = "T" if victim_is_team1 else "CT"

        death_event = GameEvent(
            event_type=EventType.DEATH,
            tick=safe_float(kill.get("round_seconds", 0.0)),
            player=victim,
            other_player=killer,
            weapon=kill.get("weapon"),
            team_num=victim_team,
        )
        events.append(death_event)

    return events


def extract_bomb_plant_events(
    round_data: dict[str, Any],
    team1_players: list[str],
    team2_players: list[str]
) -> list[GameEvent]:
    """Extract bomb plant events from round data."""
    events = []
    ticks = round_data.get("ticks", [])
    team1_on_ct = round_data.get("team1_on_ct", True)

    for tick in ticks:
        if tick.get("is_bomb_planted") and tick.get("bomb_planted_time") is not None:
            plant_time = safe_float(tick.get("bomb_planted_time"))
            if plant_time > 0:
                is_team1 = team1_on_ct
                planter_team = team1_players if is_team1 else team2_players

                if tick.get("bomb_position"):
                    events.append(GameEvent(
                        event_type=EventType.BOMB_PLANT,
                        tick=plant_time,
                        player="unknown",
                        team_num="T",
                    ))
                break

    return events


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_round_context(
    round_data: dict[str, Any],
    team1_players: list[str],
    team2_players: list[str]
) -> RoundContext:
    """Build a RoundContext from round data."""
    ticks = round_data.get("ticks", [])
    prediction_ticks = [build_prediction_tick(t) for t in ticks]

    team1_on_ct = round_data.get("team1_on_ct", True)
    winner = round_data.get("winner", "Unknown")

    events = []
    events.extend(extract_kill_events(round_data, team1_players, team2_players, team1_on_ct))
    events.extend(extract_bomb_plant_events(round_data, team1_players, team2_players))

    events.sort(key=lambda e: e.tick)

    bomb_planted_time = None
    bomb_defused_time = None
    for tick in ticks:
        if tick.get("is_bomb_planted") and tick.get("bomb_planted_time") is not None:
            bomb_planted_time = safe_float(tick.get("bomb_planted_time"))
            break

    first_tick_players = ticks[0].get("players_info", []) if ticks else []
    team1_alive = sum(1 for p in first_tick_players if p.get("is_alive") and p.get("name") in team1_players)
    team2_alive = sum(1 for p in first_tick_players if p.get("is_alive") and p.get("name") in team2_players)

    return RoundContext(
        round_id=round_data.get("round_id", 0),
        ticks=prediction_ticks,
        events=events,
        team1_players=team1_players,
        team2_players=team2_players,
        team1_on_ct=team1_on_ct,
        winner=winner,
        bomb_planted_time=bomb_planted_time,
        bomb_defused_time=bomb_defused_time,
        team1_alive_count=team1_alive,
        team2_alive_count=team2_alive,
    )


def get_player_team(player_name: str, team1_players: list[str], team2_players: list[str]) -> str:
    """Get which team a player is on."""
    if player_name in team1_players:
        return "team1"
    elif player_name in team2_players:
        return "team2"
    return "unknown"


def get_player_side_win_rate(
    win_rate: float,
    player_name: str,
    team1_players: list[str],
    team1_on_ct: bool
) -> float:
    """Get win rate from player's perspective (own side = 1.0).
    
    Args:
        win_rate: CT win rate
        player_name: Player name
        team1_players: List of team1 players
        team1_on_ct: If True, team1 is playing as CT in this round
    """
    player_on_team1 = player_name in team1_players
    
    if team1_on_ct:
        # team1 is CT, team2 is T
        if player_on_team1:
            return win_rate  # player is CT
        else:
            return 1.0 - win_rate  # player is T
    else:
        # team1 is T, team2 is CT
        if player_on_team1:
            return 1.0 - win_rate  # player is T
        else:
            return win_rate  # player is CT


def find_death_trade_kill(
    death_time: float,
    victim: str,
    killer: str,
    all_events: list[GameEvent],
    trade_window: float = 5.0
) -> GameEvent | None:
    """Find if someone avenged the victim by killing the killer within trade window."""
    for event in all_events:
        if event.event_type != EventType.KILL:
            continue
        if event.other_player != killer:
            continue
        time_gap = event.tick - death_time
        if 0 < time_gap <= trade_window:
            return event
    return None


def get_alive_count_at_tick(
    tick: PredictionTick,
    team1_players: list[str],
    team2_players: list[str]
) -> tuple[int, int]:
    """Get alive counts for both teams at a tick."""
    team1_alive = 0
    team2_alive = 0

    for player in tick.players_info:
        name = player.get("name")
        if not name:
            continue
        if not player.get("is_alive", False):
            continue
        if name in team1_players:
            team1_alive += 1
        elif name in team2_players:
            team2_alive += 1

    return team1_alive, team2_alive


def calculate_distance_2d(
    x1: float, y1: float,
    x2: float, y2: float
) -> float:
    """Calculate 2D distance between two points."""
    dx = x2 - x1
    dy = y2 - y1
    return (dx * dx + dy * dy) ** 0.5


def find_nearest_teammate(
    player_name: str,
    tick: PredictionTick,
    team1_players: list[str],
    team2_players: list[str]
) -> tuple[str | None, float]:
    """Find nearest teammate distance for a player at a tick."""
    player_team = get_player_team(player_name, team1_players, team2_players)

    player_pos = None
    for p in tick.players_info:
        if p.get("name") == player_name:
            player_pos = (safe_float(p.get("X")), safe_float(p.get("Y")), safe_float(p.get("Z")))
            break

    if player_pos is None:
        return None, float('inf')

    nearest_name = None
    nearest_dist = float('inf')

    for p in tick.players_info:
        name = p.get("name")
        if not name or name == player_name:
            continue

        teammate_team = get_player_team(name, team1_players, team2_players)
        if teammate_team != player_team:
            continue
        if not p.get("is_alive", False):
            continue

        dist = calculate_distance_2d(
            player_pos[0], player_pos[1],
            safe_float(p.get("X")), safe_float(p.get("Y"))
        )
        if dist < nearest_dist:
            nearest_dist = dist
            nearest_name = name

    return nearest_name, nearest_dist


def get_name_to_idx(ticks: list[PredictionTick]) -> dict[str, int]:
    """Build name to index mapping from ticks."""
    if not ticks or not ticks[0].players_info:
        return {}
    name_to_idx = {}
    for idx, player in enumerate(ticks[0].players_info[:10]):
        name = player.get("name")
        if name:
            name_to_idx[name] = idx
    return name_to_idx


def get_duel_probability(
    tick: PredictionTick,
    attacker_name: str,
    victim_name: str,
    name_to_idx: dict[str, int]
) -> float | None:
    """Get duel probability from tick data."""
    duel = tick.duel
    if duel is None:
        return None

    a_idx = name_to_idx.get(attacker_name)
    v_idx = name_to_idx.get(victim_name)

    if a_idx is None or v_idx is None:
        return None

    if a_idx >= len(duel) or v_idx >= len(duel):
        return None

    row = duel[a_idx]
    if isinstance(row, list) and v_idx < len(row):
        val = row[v_idx]
        if val == "/":
            return None
        return safe_float(val, 0.5)

    return None


def was_bomb_planted_before_tick(ticks: list[PredictionTick], target_time: float) -> bool:
    """Check if bomb was planted before a given time."""
    return any(tick.round_seconds <= target_time and tick.is_bomb_planted for tick in ticks)
