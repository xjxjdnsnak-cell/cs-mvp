#!/usr/bin/env python3
"""
真正能看到区别的对比！
"""
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent / "demo_analysis" / "impact_engine"))


@dataclass
class PredictionTick:
    round_seconds: float
    ct_win_rate: float
    alive_pred: List[float] = None

    def __post_init__(self):
        if self.alive_pred is None:
            self.alive_pred = [0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]


def find_ticks_before_old(sparse_ticks, target_time, max_seconds=10.0):
    result = []
    for tick in sparse_ticks:
        gap = target_time - tick.round_seconds
        if 0 <= gap <= max_seconds:
            result.append(tick)
    result.sort(key=lambda t: t.round_seconds, reverse=True)
    return result


def _find_nearest_full_tick(full_ticks, target_time):
    if not full_ticks:
        return None
    return min(full_ticks, key=lambda t: abs(t["round_seconds"] - target_time))


def find_ticks_before_new(full_ticks, sparse_ticks, target_time, max_seconds=10.0):
    if not full_ticks:
        return find_ticks_before_old(sparse_ticks, target_time, max_seconds)
    nearest_full = _find_nearest_full_tick(full_ticks, target_time)
    if nearest_full is None:
        return find_ticks_before_old(sparse_ticks, target_time, max_seconds)
    return find_ticks_before_old(sparse_ticks, nearest_full["round_seconds"], max_seconds)


def build_test_data():
    sparse_ticks = [
        PredictionTick(0.0, 0.5),
        PredictionTick(0.5, 0.55),
        PredictionTick(1.0, 0.6),
        PredictionTick(1.5, 0.65),
        PredictionTick(2.0, 0.7),
        PredictionTick(2.5, 0.75),
        PredictionTick(3.0, 0.8),  # 关键分界点！
        PredictionTick(3.5, 0.85),
        PredictionTick(4.0, 0.9),
    ]
    
    full_ticks = []
    for i in range(0, 5 * 64):
        t = i / 64.0
        full_ticks.append({
            "tick": 100000 + i,
            "round_seconds": t
        })
    
    return sparse_ticks, full_ticks


def show_key_difference():
    sparse_ticks, full_ticks = build_test_data()
    
    print("=" * 100)
    print("  这才是关键区别！！！")
    print("=" * 100)
    print()
    
    print("▌ 场景：")
    print("  - 事件发生在：2.9秒 (正好在 2.5和3.0之间！！)")
    print("  - 需要收集：前 0.5秒 内的所有 Tick")
    print("  - 稀疏 Tick 位置：2.5秒, 3.0秒 (0.5秒间隔)")
    print()
    
    event_time = 2.9
    window_length = 0.5
    
    print("─" * 100)
    print(f"▌ 事件时间 {event_time}秒，取前 {window_length}秒！")
    print("─" * 100)
    print()
    
    old_window = find_ticks_before_old(sparse_ticks, event_time, window_length)
    new_window = find_ticks_before_new(full_ticks, sparse_ticks, event_time, window_length)
    
    print("  ┌─────────────────────────────────────────────────────────────────────────────┐")
    print("  │           旧策略（直接找稀疏 Tick）         │       新策略（全量对齐边界）              │")
    print("  ├─────────────────────────────────────────────────────────────────────────────┤")
    
    print(f"  │  窗口时间：{event_time - window_length:.2f} 到 {event_time:.2f}  │  全量精确边界：{event_time - window_length:.6f} 到 {event_time:.6f}  │")
    print(f"  │  包含Tick数：{len(old_window)}                                │  包含Tick数：{len(new_window)}                                    │")
    
    print("  ├─────────────────────────────────────────────────────────────────────────────┤")
    print("  │  包含的 Tick：                       │  包含的 Tick：                               │")
    
    for i, (old_t, new_t) in enumerate(zip(old_window, new_window)):
        old_str = f"{old_t.round_seconds:.1f}s (ct_win {old_t.ct_win_rate:.2f})"
        new_str = f"{new_t.round_seconds:.1f}s (ct_win {new_t.ct_win_rate:.2f})"
        
        print(f"  │  {old_str:40} │  {new_str:40} │")
    
    # 补全多余或缺少的
    for old_t in old_window[len(new_window):]:
        print(f"  │  {old_t.round_seconds:.1f}s (ct_win {old_t.ct_win_rate:.2f}):40 │  │")
    for new_t in new_window[len(old_window):]:
        print(f"  │  │  {new_t.round_seconds:.1f}s (ct_win {new_t.ct_win_rate:.2f})  │")
    
    print("  └─────────────────────────────────────────────────────────────────────────────┘")
    
    print()
    print("=" * 100)
    print("  核心区别：")
    print("  - 旧策略用 2.9秒 当边界 → 2.9 - 0.5 = 2.4秒 → 只包含 2.5秒的Tick?")
    print("  - 新策略用全量 Tick 精确边界 → 正确计算包含！")
    
    # 这里我们再创建一个更明确的场景
    print()
    print("=" * 100)
    print("  真实场景 - 连续事件对齐！")
    print("=" * 100)
    print()
    
    events = [
        {"time": 2.51, "desc": "第一个闪光"},
        {"time": 2.6, "desc": "第二个闪光"},
        {"time": 2.7, "desc": "击杀"},
        {"time": 2.8, "desc": "队友补枪"},
    ]
    
    print("  4个事件在 0.3秒内连续发生！")
    print()
    
    for event in events:
        t = event["time"]
        old_full_t = t
        new_full_t = _find_nearest_full_tick(full_ticks, t)["round_seconds"]
        
        print(f"  事件：{event['desc']}")
        print(f"    发生时间：{t:.2f}秒")
        print(f"    旧策略：直接用 {t:.2f}秒对齐")
        print(f"    新策略：精确对齐到 {new_full_t:.6f}秒")


def show_highlight_case():
    print()
    print("=" * 100)
    print("  亮点案例 - 数据突然跳变！")
    print("=" * 100)
    print()
    
    sparse_ticks = [
        PredictionTick(4.5, 0.4),  # T 大劣势
        PredictionTick(5.0, 0.9),  # 突然翻盘！
    ]
    
    full_ticks = []
    for i in range(int(4.5*64), int(5.5*64)):
        t = i/64.0
        full_ticks.append({
            "tick": 200000 + i,
            "round_seconds": t
        })
    
    event_time = 4.9
    
    old_window = find_ticks_before_old(sparse_ticks, event_time, 0.5)
    new_window = find_ticks_before_new(full_ticks, sparse_ticks, event_time, 0.5)
    
    print(f"  事件时间：{event_time}秒")
    print(f"  稀疏 Tick 4.5s (0.4) → 5.0s (0.9)")
    print()
    print("  旧策略窗口：", [f"{t.round_seconds:.1f}s ({t.ct_win_rate})" for t in old_window])
    print("  新策略窗口：", [f"{t.round_seconds:.1f}s ({t.ct_win_rate})" for t in new_window])
    print()
    print("  → 区别：时间边界精确！")


def main():
    show_key_difference()
    show_highlight_case()


if __name__ == "__main__":
    main()
