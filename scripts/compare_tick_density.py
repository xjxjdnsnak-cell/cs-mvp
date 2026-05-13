#!/usr/bin/env python3
"""
对比不同Tick密度对Impact Engine评分的影响。
使用已有的分析JSON，通过下采样模拟稀疏Tick，与原始全量Tick对比。

用法:
    # 如果有分析JSON文件
    python scripts/compare_tick_density.py --json analysis.json

    # 或者使用测试fixtures
    python scripts/compare_tick_density.py --use-fixture
"""

import argparse
import json
import sys
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo_analysis.high_level_analysis import build_dashboard_payload
from demo_analysis.impact_engine import ImpactEngine


def downsample_ticks(round_data: dict, interval: float) -> dict:
    """
    Downsample ticks in round_data to simulate different sampling intervals.

    Args:
        round_data: Round data with "ticks" list
        interval: Target sampling interval in seconds

    Returns:
        Modified round_data with downsampled ticks
    """
    result = copy.deepcopy(round_data)
    ticks = result.get("ticks", [])
    if not ticks:
        return result

    # Sort by round_seconds
    ticks_sorted = sorted(ticks, key=lambda t: t.get("round_seconds", 0))

    # Downsample: keep ticks at interval boundaries
    last_kept_time = -999
    downsampled = []
    for tick in ticks_sorted:
        t = tick.get("round_seconds", 0)
        if t - last_kept_time >= interval - 0.001:  # small tolerance
            downsampled.append(tick)
            last_kept_time = t

    result["ticks"] = downsampled
    return result


def analyze_with_tick_interval(raw_results: dict, interval: float | None) -> dict:
    """
    Run Impact Engine analysis with specified tick interval.

    Args:
        raw_results: Raw analysis results
        interval: If None, use original ticks. If float, downsample to that interval.

    Returns:
        Analysis result dict
    """
    modified_results = copy.deepcopy(raw_results)

    total_ticks = 0
    for key, val in modified_results.items():
        if not key.isdigit():
            continue
        if interval is not None:
            modified_results[key] = downsample_ticks(val, interval)
        total_ticks += len(modified_results[key].get("ticks", []))

    dashboard = build_dashboard_payload(modified_results)
    engine = ImpactEngine(dashboard)
    report = engine.analyze()

    return {
        "report": report,
        "total_ticks": total_ticks,
        "interval": interval,
    }


def compare_results(results_list: list[dict]):
    """Compare multiple analysis results with different tick intervals."""
    print(f"\n{'='*80}")
    print("Tick Density Impact Comparison")
    print(f"{'='*80}")

    # Tick counts
    print("\n--- Tick Counts ---")
    for r in results_list:
        interval = r["interval"]
        label = "Original" if interval is None else f"{interval}s interval"
        print(f"  {label:<20}: {r['total_ticks']:,} ticks")

    # Player ratings comparison
    print(f"\n--- Player Rating Comparison ---")

    # Collect all players
    all_players = set()
    for r in results_list:
        for p in r["report"].player_impacts:
            all_players.add(p.player_name)

    # Header
    headers = ["Player"]
    for r in results_list:
        interval = r["interval"]
        label = "Original" if interval is None else f"{interval}s"
        headers.extend([f"{label}", "Diff"])

    print(f"{'Player':<18}", end="")
    for r in results_list:
        interval = r["interval"]
        label = "Orig" if interval is None else f"{interval}s"
        print(f" {label:>10} {'Diff':>10}", end="")
    print()
    print("-" * (18 + 20 * len(results_list)))

    # Data rows
    baseline = results_list[0]
    baseline_players = {p.player_name: p for p in baseline["report"].player_impacts}

    for player_name in sorted(all_players):
        print(f"{player_name:<18}", end="")

        baseline_rating = baseline_players.get(player_name, None)
        baseline_val = baseline_rating.rating_0_100 if baseline_rating else 0

        for r in results_list:
            players = {p.player_name: p for p in r["report"].player_impacts}
            p = players.get(player_name)
            rating = p.rating_0_100 if p else 0
            diff = rating - baseline_val
            print(f" {rating:>10.1f} {diff:>+10.1f}", end="")
        print()

    # Round impact comparison
    print(f"\n--- Round Impact StdDev (variability measure) ---")

    for r in results_list:
        interval = r["interval"]
        label = "Original" if interval is None else f"{interval}s"

        round_impacts = []
        for p in r["report"].player_impacts:
            for ri in p.round_impacts:
                round_impacts.append(ri.round_total_impact)

        if round_impacts:
            mean_impact = sum(round_impacts) / len(round_impacts)
            variance = sum((x - mean_impact) ** 2 for x in round_impacts) / len(round_impacts)
            stddev = variance ** 0.5
            print(f"  {label:<20}: mean={mean_impact:+.3f}, stddev={stddev:.3f}")

    # Kill impact comparison
    print(f"\n--- Kill Impact Statistics ---")

    for r in results_list:
        interval = r["interval"]
        label = "Original" if interval is None else f"{interval}s"

        kills = []
        for p in r["report"].player_impacts:
            for ri in p.round_impacts:
                for ki in ri.kills:
                    kills.append(ki.total_impact)

        if kills:
            mean_kill = sum(kills) / len(kills)
            max_kill = max(kills)
            min_kill = min(kills)
            print(f"  {label:<20}: count={len(kills)}, mean={mean_kill:+.3f}, max={max_kill:+.3f}, min={min_kill:+.3f}")

    # Death impact comparison
    print(f"\n--- Death Impact Statistics ---")

    for r in results_list:
        interval = r["interval"]
        label = "Original" if interval is None else f"{interval}s"

        deaths = []
        for p in r["report"].player_impacts:
            for ri in p.round_impacts:
                for di in ri.deaths:
                    deaths.append(di.total_impact)

        if deaths:
            mean_death = sum(deaths) / len(deaths)
            max_death = max(deaths)
            min_death = min(deaths)
            print(f"  {label:<20}: count={len(deaths)}, mean={mean_death:+.3f}, max={max_death:+.3f}, min={min_death:+.3f}")

    # Win rate delta accuracy (how often we find exact tick vs nearest)
    print(f"\n--- Event Alignment Quality ---")

    for r in results_list:
        interval = r["interval"]
        label = "Original" if interval is None else f"{interval}s"

        exact_alignments = 0
        total_events = 0

        for p in r["report"].player_impacts:
            for ri in p.round_impacts:
                for ki in ri.kills:
                    total_events += 1
                    if ki.before_tick and ki.after_tick:
                        # Check if alignment is within 0.02s of event time
                        before_gap = abs(ki.before_tick.round_seconds - (ki.event.tick - 0.1))
                        after_gap = abs(ki.after_tick.round_seconds - (ki.event.tick + 0.1))
                        if before_gap <= 0.02 and after_gap <= 0.02:
                            exact_alignments += 1

        if total_events > 0:
            accuracy = exact_alignments / total_events * 100
            print(f"  {label:<20}: {exact_alignments}/{total_events} exact alignments ({accuracy:.1f}%)")

    # Save comparison
    output = {
        "tick_intervals": [
            {
                "interval": r["interval"],
                "total_ticks": r["total_ticks"],
                "players": [
                    {
                        "name": p.player_name,
                        "rating": p.rating_0_100,
                        "total_score": p.total_score,
                    }
                    for p in r["report"].player_impacts
                ],
            }
            for r in results_list
        ],
    }

    return output


def main():
    parser = argparse.ArgumentParser(description="Compare tick density impact on Impact Engine")
    parser.add_argument("--json", help="Path to analysis JSON file")
    parser.add_argument("--use-fixture", action="store_true", help="Use test fixture data")
    parser.add_argument("--intervals", nargs="+", type=float, default=[0.5, 1.0, 2.0],
                        help="Tick intervals to test (default: 0.5 1.0 2.0)")
    parser.add_argument("--output", default="tick_density_comparison.json", help="Output JSON path")
    args = parser.parse_args()

    # Load data
    if args.use_fixture:
        fixture_path = Path(__file__).resolve().parent.parent / "demo_analysis" / "impact_engine" / "tests" / "fixtures" / "synthetic_analysis.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_results = json.load(f)
        print(f"Loaded fixture data: {fixture_path}")
    elif args.json:
        with open(args.json, "r", encoding="utf-8") as f:
            raw_results = json.load(f)
        print(f"Loaded analysis data: {args.json}")
    else:
        print("Error: Provide --json or --use-fixture")
        sys.exit(1)

    # Run analyses with different intervals
    results_list = []

    # Original (no downsampling)
    print("\nAnalyzing with original tick density...")
    results_list.append(analyze_with_tick_interval(raw_results, None))

    # Downsampled intervals
    for interval in args.intervals:
        print(f"Analyzing with {interval}s tick interval...")
        results_list.append(analyze_with_tick_interval(raw_results, interval))

    # Compare
    comparison = compare_results(results_list)

    # Save
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"\nComparison saved to: {output_path}")


if __name__ == "__main__":
    main()
