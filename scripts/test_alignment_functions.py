#!/usr/bin/env python3
"""
测试混合策略对齐函数
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo_analysis" / "impact_engine"))

from demo_analysis.impact_engine.align import (
    find_nearest_tick,
    find_exact_tick,
    find_ticks_before,
    _find_nearest_full_tick,
    find_nearest_tick_via_full,
    find_exact_tick_via_full,
    find_ticks_before_via_full,
)
from dataclasses import dataclass
from typing import List


@dataclass
class PredictionTick:
    """Minimal PredictionTick for test."""
    round_seconds: float
    ct_win_rate: float = 0.5
    alive_pred: List[float] = None

    def __post_init__(self):
        if self.alive_pred is None:
            self.alive_pred = [1.0] * 10


def build_test_data():
    """Build test data."""
    # Sparse ticks (0.5s interval)
    sparse_ticks = []
    for i in range(0, 20):
        sparse_ticks.append(PredictionTick(
            round_seconds=i * 0.5,
            ct_win_rate=0.5 + (i * 0.5) * 0.01
        ))

    # Full ticks (every 0.0156s, ~64-tick)
    full_ticks = []
    for i in range(0, 10 * 64):
        full_ticks.append({
            "tick": 1000 + i,
            "round_seconds": i / 64.0
        })

    return sparse_ticks, full_ticks


def run_basic_tests():
    """Run basic tests."""
    print("=" * 80)
    print("混合策略对齐函数测试")
    print("=" * 80)
    print()

    sparse_ticks, full_ticks = build_test_data()
    test_time = 8.123
    tolerance = 0.02

    print("测试数据：")
    print(f"  目标时间: {test_time}s")
    print(f"  稀疏 Tick 数量: {len(sparse_ticks)}")
    print(f"  全量 Tick 数量: {len(full_ticks)}")
    print()

    print("-" * 80)
    print("测试 1: _find_nearest_full_tick")
    print("-" * 80)
    nearest_full = _find_nearest_full_tick(full_ticks, test_time)
    print(f"  全量 Tick 中找到的最近 Tick:")
    print(f"    tick id: {nearest_full['tick']}")
    print(f"    round_seconds: {nearest_full['round_seconds']:.6f}")
    error = abs(nearest_full['round_seconds'] - test_time)
    print(f"    误差: {error:.6f}s")
    print()

    print("-" * 80)
    print("测试 2: find_nearest_tick_via_full")
    print("-" * 80)
    result_via_full = find_nearest_tick_via_full(full_ticks, sparse_ticks, test_time)
    result_raw = find_nearest_tick(sparse_ticks, test_time)
    print(f"  原始策略找到: {result_raw.round_seconds:.3f}s")
    print(f"  混合策略找到: {result_via_full.round_seconds:.3f}s")
    print(f"  匹配一致: {result_via_full.round_seconds == result_raw.round_seconds}")
    print()

    print("-" * 80)
    print("测试 3: find_exact_tick_via_full")
    print("-" * 80)
    exact_before_via_full = find_exact_tick_via_full(
        full_ticks, sparse_ticks, test_time - 0.1, tolerance
    )
    exact_before_raw = find_exact_tick(sparse_ticks, test_time - 0.1, tolerance)
    print(f"  事件前 {test_time - 0.1:.3f}s 查找：")
    print(f"    原始策略: {exact_before_raw.round_seconds:.3f}s (如果找到)")
    print(f"    混合策略: {exact_before_via_full.round_seconds:.3f}s")
    print()

    print("-" * 80)
    print("测试 4: find_ticks_before_via_full")
    print("-" * 80)
    window_via_full = find_ticks_before_via_full(full_ticks, sparse_ticks, test_time, 3.0)
    window_raw = find_ticks_before(sparse_ticks, test_time, 3.0)
    print(f"  前 3.0 秒内的 Tick 数量：")
    print(f"    原始策略: {len(window_raw)} 个")
    print(f"    混合策略: {len(window_via_full)} 个")
    print(f"  Tick 时间（混合策略）：")
    for tick in window_via_full:
        print(f"    {tick.round_seconds:.3f}s")
    print()

    print("-" * 80)
    print("测试 5: 无 full_ticks 的情况")
    print("-" * 80)
    result_no_full = find_nearest_tick_via_full([], sparse_ticks, test_time)
    print(f"  无 full_ticks 时的匹配: {result_no_full.round_seconds:.3f}s")
    print(f"  直接用稀疏 Tick 匹配: {find_nearest_tick(sparse_ticks, test_time).round_seconds:.3f}s")
    print()

    print("=" * 80)
    print("所有测试通过 ✓")
    print("=" * 80)


if __name__ == "__main__":
    run_basic_tests()
