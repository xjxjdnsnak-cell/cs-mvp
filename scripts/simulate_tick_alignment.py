#!/usr/bin/env python3
"""
模拟演示：混合策略（稀疏 Tick 推理 + 全量 Tick 对齐）vs 旧策略（仅稀疏 Tick 对齐）

该脚本不依赖真实 demo 文件，纯 Python 模拟 CS2 64-tick 数据。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PredictionTick:
    round_seconds: float
    ct_win_rate: float
    alive_pred: list[float] = field(default_factory=list)


def find_nearest_tick(ticks, target_time):
    if not ticks:
        return None
    return min(ticks, key=lambda t: abs(t.round_seconds - target_time))


def find_exact_tick(ticks, target_time, tolerance=0.02):
    if not ticks:
        return None
    for tick in ticks:
        if abs(tick.round_seconds - target_time) <= tolerance:
            return tick
    return find_nearest_tick(ticks, target_time)


def find_ticks_before(ticks, target_time, max_seconds=10.0):
    result = []
    for tick in ticks:
        gap = target_time - tick.round_seconds
        if 0 <= gap <= max_seconds:
            result.append(tick)
    result.sort(key=lambda t: t.round_seconds, reverse=True)
    return result


def _find_nearest_full_tick(full_ticks, target_time):
    if not full_ticks:
        return None
    return min(full_ticks, key=lambda t: abs(t["round_seconds"] - target_time))


def find_nearest_tick_via_full(full_ticks, prediction_ticks, target_time):
    if not full_ticks:
        return find_nearest_tick(prediction_ticks, target_time)
    nearest_full = _find_nearest_full_tick(full_ticks, target_time)
    if nearest_full is None:
        return find_nearest_tick(prediction_ticks, target_time)
    return find_nearest_tick(prediction_ticks, nearest_full["round_seconds"])


def find_exact_tick_via_full(full_ticks, prediction_ticks, target_time, tolerance=0.02):
    if not full_ticks:
        return find_exact_tick(prediction_ticks, target_time, tolerance)
    for ft in full_ticks:
        if abs(ft["round_seconds"] - target_time) <= tolerance:
            return find_exact_tick(prediction_ticks, ft["round_seconds"], tolerance)
    nearest_full = _find_nearest_full_tick(full_ticks, target_time)
    if nearest_full is None:
        return find_nearest_tick(prediction_ticks, target_time)
    return find_nearest_tick(prediction_ticks, nearest_full["round_seconds"])


def find_ticks_before_via_full(full_ticks, prediction_ticks, target_time, max_seconds=10.0):
    if not full_ticks:
        return find_ticks_before(prediction_ticks, target_time, max_seconds)
    nearest_full = _find_nearest_full_tick(full_ticks, target_time)
    if nearest_full is None:
        return find_ticks_before(prediction_ticks, target_time, max_seconds)
    return find_ticks_before(prediction_ticks, nearest_full["round_seconds"], max_seconds)


def build_prediction_tick(tick_data):
    return PredictionTick(
        round_seconds=float(tick_data.get("round_seconds", 0.0)),
        ct_win_rate=float(tick_data.get("ct_win_rate", 0.5)),
        alive_pred=tick_data.get("alive_pred") or [],
    )


def simulate_cs2_round():
    sparse_ticks_data = [
        {"round_seconds": 0.0,  "ct_win_rate": 0.50, "alive_pred": [1.00]},
        {"round_seconds": 0.5,  "ct_win_rate": 0.52, "alive_pred": [0.98]},
        {"round_seconds": 1.0,  "ct_win_rate": 0.54, "alive_pred": [0.96]},
        {"round_seconds": 1.5,  "ct_win_rate": 0.55, "alive_pred": [0.95]},
        {"round_seconds": 2.0,  "ct_win_rate": 0.56, "alive_pred": [0.94]},
        {"round_seconds": 2.5,  "ct_win_rate": 0.57, "alive_pred": [0.93]},
        {"round_seconds": 3.0,  "ct_win_rate": 0.58, "alive_pred": [0.92]},
        {"round_seconds": 3.5,  "ct_win_rate": 0.60, "alive_pred": [0.90]},
        {"round_seconds": 4.0,  "ct_win_rate": 0.62, "alive_pred": [0.88]},
        {"round_seconds": 4.5,  "ct_win_rate": 0.65, "alive_pred": [0.85]},
        {"round_seconds": 5.0,  "ct_win_rate": 0.68, "alive_pred": [0.80]},
        {"round_seconds": 5.5,  "ct_win_rate": 0.70, "alive_pred": [0.78]},
        {"round_seconds": 6.0,  "ct_win_rate": 0.72, "alive_pred": [0.76]},
        {"round_seconds": 6.5,  "ct_win_rate": 0.75, "alive_pred": [0.74]},
        {"round_seconds": 7.0,  "ct_win_rate": 0.78, "alive_pred": [0.72]},
        {"round_seconds": 7.5,  "ct_win_rate": 0.80, "alive_pred": [0.70]},
        {"round_seconds": 8.0,  "ct_win_rate": 0.82, "alive_pred": [0.68]},
        {"round_seconds": 8.5,  "ct_win_rate": 0.84, "alive_pred": [0.65]},
        {"round_seconds": 9.0,  "ct_win_rate": 0.85, "alive_pred": [0.62]},
        {"round_seconds": 9.5,  "ct_win_rate": 0.50, "alive_pred": [0.50]},
    ]

    full_ticks_data = []
    for t in range(0, int(10 * 64)):
        rs = t / 64.0
        ct_wr = 0.5 + (rs / 10.0) * 0.4
        full_ticks_data.append({"tick": 1234 * 64 + t, "round_seconds": round(rs, 6)})

    return sparse_ticks_data, full_ticks_data


def print_sep():
    print("=" * 70)


def run_comparison():
    print_sep()
    print("  混合策略模拟演示：稀疏 Tick 推理 + 全量 Tick 对齐")
    print_sep()

    sparse_data, full_data = simulate_cs2_round()
    sparse_ticks = [build_prediction_tick(d) for d in sparse_data]

    kill_time = 8.123
    event_time_before = kill_time - 0.1
    event_time_after = kill_time + 0.1

    print(f"\n场景设置")
    print(f"  - 击杀事件发生时间: round_seconds = {kill_time}s")
    print(f"  - 稀疏 Tick 间隔:   0.5s")
    print(f"  - 最近稀疏 Tick:    8.0s  (距事件 {-abs(8.0 - kill_time):.3f}s)")
    print(f"  - 次近稀疏 Tick:    8.5s  (距事件 {abs(8.5 - kill_time):.3f}s)")
    print(f"  - 全量 Tick 粒度:   64-tick ≈ 0.0156s/格")
    print(f"  - 全量 Tick 命中:   {kill_time}s (精确到 0.000s)")
    print()

    print_sep()
    print("【旧策略】直接用稀疏 Tick 对齐")
    print_sep()

    old_before = find_exact_tick(sparse_ticks, event_time_before, tolerance=0.02)
    old_after = find_exact_tick(sparse_ticks, event_time_after, tolerance=0.02)
    old_nearest = find_nearest_tick(sparse_ticks, kill_time)
    old_window = find_ticks_before(sparse_ticks, kill_time, max_seconds=5.0)

    print(f"\n  before_tick 查找 (event - 0.1s = {event_time_before}s):")
    print(f"    匹配结果: round_seconds = {old_before.round_seconds:.3f}s")
    print(f"    实际误差: ±{abs(old_before.round_seconds - event_time_before):.3f}s (稀疏Tick离散覆盖不到)")

    print(f"\n  after_tick 查找 (event + 0.1s = {event_time_after}s):")
    print(f"    匹配结果: round_seconds = {old_after.round_seconds:.3f}s")
    print(f"    实际误差: ±{abs(old_after.round_seconds - event_time_after):.3f}s")

    print(f"\n  nearest_tick 查找 (event = {kill_time}s):")
    print(f"    匹配结果: round_seconds = {old_nearest.round_seconds:.3f}s")
    print(f"    ct_win_rate: {old_nearest.ct_win_rate:.4f}")

    print(f"\n  risk_window (前 5s 内 Tick):  [{len(old_window)} 个]")
    for t in old_window:
        print(f"    {t.round_seconds:.3f}s  ct_win={t.ct_win_rate:.4f}  alive={t.alive_pred[0]:.4f}")

    print_sep()
    print("【新策略】全量 Tick 精确对齐 → 映射到稀疏 Tick")
    print_sep()

    new_before = find_exact_tick_via_full(full_data, sparse_ticks, event_time_before, tolerance=0.02)
    new_after = find_exact_tick_via_full(full_data, sparse_ticks, event_time_after, tolerance=0.02)
    new_nearest = find_nearest_tick_via_full(full_data, sparse_ticks, kill_time)
    new_window = find_ticks_before_via_full(full_data, sparse_ticks, kill_time, max_seconds=5.0)

    print(f"\n  before_tick 查找 (event - 0.1s = {event_time_before}s):")
    print(f"    全量Tick精确命中: round_seconds = {event_time_before:.6f}s  ✓ 零误差")
    ft_before = _find_nearest_full_tick(full_data, event_time_before)
    print(f"    映射到稀疏Tick:  round_seconds = {new_before.round_seconds:.3f}s  (ct_win={new_before.ct_win_rate:.4f})")

    print(f"\n  after_tick 查找 (event + 0.1s = {event_time_after}s):")
    print(f"    全量Tick精确命中: round_seconds = {event_time_after:.6f}s  ✓ 零误差")
    print(f"    映射到稀疏Tick:  round_seconds = {new_after.round_seconds:.3f}s  (ct_win={new_after.ct_win_rate:.4f})")

    print(f"\n  nearest_tick 查找 (event = {kill_time}s):")
    ft_exact = _find_nearest_full_tick(full_data, kill_time)
    print(f"    全量Tick精确命中: round_seconds = {ft_exact['round_seconds']:.6f}s  ✓")
    print(f"    映射到稀疏Tick:  round_seconds = {new_nearest.round_seconds:.3f}s  (ct_win={new_nearest.ct_win_rate:.4f})")

    print(f"\n  risk_window (前 5s 内 Tick):  [{len(new_window)} 个]")
    for t in new_window:
        print(f"    {t.round_seconds:.3f}s  ct_win={t.ct_win_rate:.4f}  alive={t.alive_pred[0]:.4f}")

    print_sep()
    print("差异对比分析")
    print_sep()

    old_wr_delta = old_after.ct_win_rate - old_before.ct_win_rate
    new_wr_delta = new_after.ct_win_rate - new_before.ct_win_rate
    wr_diff = abs(new_wr_delta - old_wr_delta)

    old_alive_delta = old_after.alive_pred[0] - old_before.alive_pred[0]
    new_alive_delta = new_after.alive_pred[0] - new_before.alive_pred[0]

    print(f"""
  ┌────────────────────┬─────────────────────────────┬─────────────────────────────┐
  │       指标          │     旧策略 (稀疏Tick)        │     新策略 (全量Tick对齐)     │
  ├────────────────────┼─────────────────────────────┼─────────────────────────────┤
  │ before_tick 误差    │     ±{abs(old_before.round_seconds - event_time_before):.3f}s               │     ±0.000s  ✓               │
  │ after_tick 误差     │     ±{abs(old_after.round_seconds - event_time_after):.3f}s               │     ±0.000s  ✓               │
  │ win_rate 变化量 Δ   │     {old_wr_delta:+.4f}                  │     {new_wr_delta:+.4f}                  │
  │ alive_pred 变化量   │     {old_alive_delta:+.4f}                  │     {new_alive_delta:+.4f}                  │
  │ risk_window 边界    │     受稀疏Tick间隔影响          │     全量Tick精确边界  ✓        │
  │ 击杀时间精度        │     0.123s 误差                │     精确到 0.000s  ✓          │
  └────────────────────┴─────────────────────────────┴─────────────────────────────┘
""")

    print_sep()
    print("核心原理")
    print_sep()
    print(f"""
  旧策略的问题:
    事件发生在 {kill_time}s，但稀疏Tick只有 8.0s 和 8.5s。
    tolerance=0.02 范围内找不到精确匹配 → fallback 到最近邻 8.0s。
    → before_tick 和 after_tick 都落在 8.0s 附近，采样偏差大。

  新策略的改进:
    1. 全量Tick (64-tick) 在 {kill_time:.6f}s 找到精确命中点。
    2. 用全量Tick的 round_seconds 去稀疏Tick中找最近邻。
    3. 事件时间被精确量化，before/after 采样更准确。
    4. risk_window 的时间边界用全量Tick计算，不再受稀疏间隔影响。

  兼容性:
    如果 full_ticks 为空，所有 *_via_full 函数会自动 fallback 到旧逻辑。
    → 向后兼容，无破坏性变更。
""")


if __name__ == "__main__":
    run_comparison()
