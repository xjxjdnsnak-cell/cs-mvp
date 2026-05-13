#!/usr/bin/env python3
"""
模拟复杂场景对道具和战术评分的影响：
1. 多个闪光在1秒内同时扔出
2. 多人在短时间内连续死亡
3. 中路控制场景
"""

import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, List, Dict

# 模拟必要的数据结构
@dataclass
class PredictionTick:
    round_seconds: float
    ct_win_rate: float
    alive_pred: List[float] = field(default_factory=list)
    next_kill: List[float] = field(default_factory=list)
    next_death: List[float] = field(default_factory=list)
    duel: Any = None
    players_info: List[dict] = field(default_factory=list)
    projectiles: List[dict] = field(default_factory=list)
    entity_grenades: List[dict] = field(default_factory=list)
    future_kills: List[dict] = field(default_factory=list)
    future_damage: List[dict] = field(default_factory=list)
    is_bomb_planted: bool = False
    bomb_planted_time: Any = None
    bomb_position: Any = None


@dataclass
class GameEvent:
    event_type: str
    tick: float
    player: str
    other_player: str | None = None
    weapon: str | None = None
    assister: str | None = None
    headshot: bool = False
    assisted_flash: bool = False
    attacker_blind: bool = False
    attacker_in_air: bool = False
    through_smoke: bool = False
    damage_health: int | None = None
    team_num: str | None = None


@dataclass
class RoundContext:
    round_id: int
    ticks: List[PredictionTick]
    events: List[GameEvent]
    team1_players: List[str]
    team2_players: List[str]
    team1_on_ct: bool
    winner: str
    bomb_planted_time: float | None = None
    bomb_defused_time: float | None = None
    team1_alive_count: int = 5
    team2_alive_count: int = 5
    map_name: str = "de_mirage"
    full_ticks: List[Dict[str, Any]] = field(default_factory=list)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def simulate_multi_flash_scenario() -> None:
    """
    场景 1: 多个闪光在1秒内同时扔出
    """
    print("=" * 80)
    print("场景 1: 多个闪光在1秒内同时扔出")
    print("=" * 80)
    print()

    # 模拟数据：两个闪光在 0.5秒内扔出
    flash_data = [
        {
            "thrower": "Player1_T_1",
            "tick": 12.3,
            "affected_enemy": "Player1_CT_1",
            "effective_blind": 2.8,
            "score": 0.6,
            "reason": "Player1_CT_1 2.8s 半白/视野受损"
        },
        {
            "thrower": "Player1_T_1",
            "tick": 12.7,
            "affected_enemy": "Player2_CT_2",
            "effective_blind": 3.5,
            "score": 1.0,
            "reason": "Player2_CT_2 3.5s 高质量全白"
        },
        {
            "thrower": "Player1_T_1",
            "tick": 13.1,
            "affected_teammate": "Player2_T_2",
            "effective_blind": 2.5,
            "score": -0.6,
            "reason": "队友 Player2_T_2 2.5s 半白/视野受损"
        }
    ]

    print("原始闪光事件（未合并）：")
    print("-" * 40)
    total_score = 0.0
    for f in flash_data:
        score = f.get("score", 0.0)
        total_score += score
        print(f"  {f['thrower']} 在 {f['tick']}s 扔出:")
        if "affected_enemy" in f:
            print(f"    闪白敌人 {f['affected_enemy']}: {f['effective_blind']}s, 得分 +{score}")
        else:
            print(f"    闪白队友 {f['affected_teammate']}: {f['effective_blind']}s, 得分 {score}")

    print()
    print("合并策略（1秒内多个闪光合并）：")
    print("-" * 40)
    print("""
  merge_flash_impacts 逻辑：
    - 将时间差 <=1.0 秒的闪光合并
    - 敌人得分上限 3.0，队友得分下限 -3.0
    - 去重标签和理由
    """)

    # 模拟合并过程
    enemy_score = sum(f["score"] for f in flash_data if f["score"] > 0)
    team_score = sum(f["score"] for f in flash_data if f["score"] < 0)
    max_enemy = 3.0
    min_team = -3.0
    merged_score = clamp(enemy_score, 0.0, max_enemy) + max(team_score, min_team)

    print()
    print(f"  敌人得分总和: {enemy_score}")
    print(f"  队友得分总和: {team_score}")
    print(f"  合并后最终得分: {merged_score}")
    print()
    print("""
  影响说明：
    1. 短时间内连续闪光会被合并计算，避免重复计分
    2. 敌人部分有上限(3.0)，防止极端高分
    3. 队友误伤有下限(-3.0)，防止极端惩罚
    4. 合并时会累积所有受影响的敌人和队友信息
    """)


def simulate_multi_death_scenario() -> None:
    """
    场景 2: 多人在短时间内连续死亡
    """
    print()
    print("=" * 80)
    print("场景 2: 多人在短时间内连续死亡")
    print("=" * 80)
    print()

    print("死亡事件链：")
    print("-" * 40)

    deaths = [
        {
            "victim": "Player1_CT_1",
            "tick": 25.2,
            "site": "a_ramp",
            "traded": True
        },
        {
            "victim": "Player2_T_1",
            "tick": 25.8,
            "site": "a_ramp",
            "traded": False
        },
        {
            "victim": "Player3_CT_2",
            "tick": 26.3,
            "site": "a_ramp",
            "traded": True
        },
        {
            "victim": "Player4_T_2",
            "tick": 27.0,
            "site": "a_site",
            "traded": False
        }
    ]

    for death in deaths:
        print(f"  {death['victim']} 在 {death['tick']}s 死于 {death['site']}",
              end="")
        if death['traded']:
            print(" → 有队友补枪（valid_entry_sacrifice）")
        else:
            print(" → 无队友补枪（failed_entry_no_trade）")

    print()
    print("""
  evaluate_site_execute 评分逻辑：
    - 死亡在进点区域 → 检查5秒内是否有队友补枪
    - 有补枪 → valid_entry_sacrifice (+0.5分)
    - 无补枪 → failed_entry_no_trade (-0.6分)
    """)

    print()
    print("评分计算结果：")
    print("-" * 40)
    total_score = 0.0
    for death in deaths:
        score = 0.5 if death['traded'] else -0.6
        total_score += score
        status = "有效牺牲" if death['traded'] else "无效死亡"
        print(f"  {death['victim']}: {score} ({status})")
    print(f"  合计: {total_score}")
    print()
    print("""
  关键区域死亡逻辑 (evaluate_mid_control)：
    - 死亡在关键区域（如 connector, window）
    - 检查死前是否有队友在附近
    - 孤身死亡 → key_area_isolated_death (-0.8分)
    - 即使有补枪，中路控制仍然受影响
    """)


def simulate_mid_control_scenario() -> None:
    """
    场景 3: 中路控制场景
    """
    print()
    print("=" * 80)
    print("场景 3: 中路控制场景")
    print("=" * 80)
    print()

    print("Mirage 中路区域配置：")
    print("-" * 40)
    print("  T 控制区域：top_mid, mid_boxes, connector")
    print("  CT 控制区域：window, short, connector")
    print("  关键区域：connector, window, short, top_mid")
    print()

    print("判定逻辑：")
    print("-" * 40)
    print("""
  1. 检查玩家在特定时间窗口内（5-40秒）的位置
  2. 检查附近是否有队友（半径800单位）
  3. 有队友时：
     - T 在 top_mid → mid_control_success (+0.3分)
     - CT 在 window → mid_control_hold (+0.3分)
  4. 关键区域孤身死亡 → key_area_isolated_death (-0.8分)
    """)

    print()
    print("场景A：T 双人推进中路")
    print("-" * 40)
    print("  Player1_T_1 在 top_mid")
    print("  Player2_T_2 在 top_mid（距离800单位内）")
    print("  结果：两人都获得 mid_control_success (+0.3分/人)")

    print()
    print("场景B：CT 在关键区域防守")
    print("-" * 40)
    print("  Player1_CT_1 在 window")
    print("  Player2_CT_2 在 window（距离800单位内）")
    print("  结果：两人都获得 mid_control_hold (+0.3分/人)")

    print()
    print("场景C：关键区域孤身死亡")
    print("-" * 40)
    print("  Player1_CT_1 在 connector")
    print("  死前附近没有队友（1000单位范围内无活人）")
    print("  结果：key_area_isolated_death (-0.8分)")
    print("  理由：玩家在connector孤身接敌死亡，关键区域压力下降")


def summarize_changes() -> None:
    """
    总结完整的评分逻辑
    """
    print()
    print("=" * 80)
    print("综合场景评分总结")
    print("=" * 80)
    print()

    print("道具评分关键要素：")
    print("-" * 40)
    print("""
  闪光弹：
    - 单个敌人：0.1（弱）~1.0（全白）
    - 有击杀转化 +0.8
    - forced_turn +0.4
    - 1秒内多个闪光合并，上限3.0
    - 队友白：-0.6~-1.5

  烟雾弹：
    - 成功隔断 +0.5~+1.0
    - 漏烟 -0.5
    - 队友堵烟 -0.3

  燃烧弹：
    - 区域控制 +0.3~+0.8
    - 击杀 +0.5
    - 队友伤害 -0.4
    """)

    print()
    print("战术评分关键要素：")
    print("-" * 40)
    print("""
  map_control:
    - 中路控制成功/防守：+0.3
    - 关键区域孤身死亡：-0.8

  site_execute:
    - 有补枪的牺牲：+0.5
    - 无补枪的死亡：-0.6

  post_plant:
    - 守包强位联动：+0.4
    - 纪律失误/前压死：-0.5~-1.0

  retake:
    - 团队回防：+0.3
    - 单人白给：-0.8

  save:
    - 正确保枪：+0.15
    - 主动送枪：-0.4
    """)

    print()
    print("结合策略建议：")
    print("-" * 40)
    print("""
  1. 多个闪光不要在1秒内连续扔（会被合并计算，效果可能打折）
  2. 进点尽量保证有补枪，否则扣分很重
  3. 关键区域（如connector）尽量不要孤身送
  4. 下包后待在强位，和队友形成联动
  5. 回防尽量和队友一起
  6. 保枪阶段尽量不要白给
    """)


def main() -> None:
    simulate_multi_flash_scenario()
    simulate_multi_death_scenario()
    simulate_mid_control_scenario()
    summarize_changes()


if __name__ == "__main__":
    main()
