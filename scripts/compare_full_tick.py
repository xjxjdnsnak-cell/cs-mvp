#!/usr/bin/env python3
"""
对比稀疏Tick和全量Tick对Impact Engine评分的影响。

用法:
    python scripts/compare_full_tick.py --demo demo/falcons-vs-9z-m2-mirage.dem --model_root cs-net-models
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demoparser2 import DemoParser
from data.process_demo import get_important_ticks_by_round, get_all_ticks_by_round
from demoparser_utils.state_extract import extract_states_by_group
from demo_analysis.get_round_win_rate import (
    load_model_and_cfg, load_tokenizer_cfg, build_weapon_index, build_projectile_index,
    run_round_inference, process_round_json, build_round_ticks, resolve_head_dirs,
    to_jsonable,
)
from demo_analysis.high_level_analysis import build_dashboard_payload
from demo_analysis.impact_engine import ImpactEngine
import torch


def run_analysis_with_tick_mode(demo_path: Path, model_root: Path, device: torch.device,
                                 tick_mode: str, batch_size: int = 32) -> dict:
    """
    Run complete analysis pipeline with specified tick mode.

    Args:
        tick_mode: "sparse" or "full"
    """
    print(f"\n{'='*60}")
    print(f"Running with {tick_mode.upper()} tick mode")
    print(f"{'='*60}")

    head_dirs = resolve_head_dirs(model_root)

    models = {}
    cfgs = {}
    for head, head_dir in head_dirs.items():
        if head_dir is None:
            models[head] = None
            cfgs[head] = None
            continue
        model, cfg, ckpt = load_model_and_cfg(head_dir, device)
        models[head] = model
        cfgs[head] = cfg
        print(f"  Loaded {head} model")

    tokenizer_cfg = load_tokenizer_cfg()
    weapon2idx = build_weapon_index(tokenizer_cfg)
    projectile2idx = build_projectile_index(tokenizer_cfg)

    demo_parser = DemoParser(str(demo_path))

    # Step 1: Extract ticks based on mode
    tick_start = time.perf_counter()
    if tick_mode == "sparse":
        ticks_by_round = get_important_ticks_by_round(demo_parser, interval=0.5)
        full_ticks_by_round = None
    else:  # full
        ticks_by_round = get_all_ticks_by_round(demo_parser)
        # For full mode, also get sparse ticks for model inference
        demo_parser_sparse = DemoParser(str(demo_path))
        full_ticks_by_round = ticks_by_round
        ticks_by_round = get_important_ticks_by_round(demo_parser_sparse, interval=0.5)

    total_ticks = sum(len(v) for v in ticks_by_round.values())
    print(f"  Total ticks extracted: {total_ticks}")
    tick_end = time.perf_counter()

    # Step 2: Extract states (always use sparse ticks for model inference)
    ticks_group = [ticks_by_round[r] for r in sorted(ticks_by_round.keys())]
    states_start = time.perf_counter()
    results_group = extract_states_by_group(str(demo_path), ticks_group)
    states_end = time.perf_counter()

    # Step 3: Run model inference
    inference_start = time.perf_counter()
    results = {}
    duel_fallback = [[0.5] * 10 for _ in range(10)]

    for idx, round_id in enumerate(sorted(ticks_by_round.keys())):
        round_states = results_group[idx]
        if not round_states:
            results[f"error_round_{round_id}"] = "No states extracted"
            continue

        try:
            run_round_inference(
                round_states, models, cfgs,
                weapon2idx, projectile2idx, device, batch_size,
            )
        except Exception as e:
            results[f"error_round_{round_id}"] = f"{type(e).__name__}: {str(e)}"
            continue

        round_result = process_round_json(round_states)
        if isinstance(round_result, dict) and "error" in round_result:
            results[f"error_round_{round_id}"] = round_result["error"]
            continue

        round_result["map_name"] = round_states[0].get("map_name")
        round_result["ticks"] = build_round_ticks(round_states, duel_fallback)
        # Inject full_ticks for full mode
        if full_ticks_by_round is not None and round_id in full_ticks_by_round:
            round_result["full_ticks"] = full_ticks_by_round[round_id]
        results[str(round_id)] = round_result

    inference_end = time.perf_counter()

    # Step 4: Build dashboard and run Impact Engine
    impact_start = time.perf_counter()
    dashboard = build_dashboard_payload(results)
    engine = ImpactEngine(dashboard)
    report = engine.analyze()
    impact_end = time.perf_counter()

    # Collect timing
    timing = {
        "tick_extraction": tick_end - tick_start,
        "state_extraction": states_end - states_start,
        "model_inference": inference_end - inference_start,
        "impact_engine": impact_end - impact_start,
        "total": impact_end - tick_start,
    }

    return {
        "report": report,
        "timing": timing,
        "total_ticks": total_ticks,
        "dashboard": dashboard,
    }


def compare_reports(sparse_report, full_report):
    """Compare two impact reports and print differences."""
    print(f"\n{'='*60}")
    print("COMPARISON: Sparse vs Full Tick Mode")
    print(f"{'='*60}")

    # Timing comparison
    print("\n--- Timing Comparison ---")
    sparse_time = sparse_report["timing"]
    full_time = full_report["timing"]

    print(f"{'Stage':<25} {'Sparse':>12} {'Full':>12} {'Ratio':>8}")
    print("-" * 60)
    for stage in ["tick_extraction", "state_extraction", "model_inference", "impact_engine", "total"]:
        s = sparse_time[stage]
        f = full_time[stage]
        ratio = f / s if s > 0 else 0
        print(f"{stage:<25} {s:>10.2f}s {f:>10.2f}s {ratio:>7.1f}x")

    # Tick count
    print(f"\n--- Tick Count ---")
    print(f"Sparse mode: {sparse_report['total_ticks']:,} ticks")
    print(f"Full mode:   {full_report['total_ticks']:,} ticks")
    print(f"Ratio:       {full_report['total_ticks'] / sparse_report['total_ticks']:.1f}x")

    # Player ratings comparison
    print(f"\n--- Player Rating Comparison ---")
    sparse_players = {p.player_name: p for p in sparse_report["report"].player_impacts}
    full_players = {p.player_name: p for p in full_report["report"].player_impacts}

    all_players = sorted(set(sparse_players.keys()) | set(full_players.keys()))

    print(f"{'Player':<20} {'Sparse':>10} {'Full':>10} {'Diff':>10} {'%Diff':>8}")
    print("-" * 60)

    for player_name in all_players:
        sparse_p = sparse_players.get(player_name)
        full_p = full_players.get(player_name)

        sparse_rating = sparse_p.rating_0_100 if sparse_p else 0
        full_rating = full_p.rating_0_100 if full_p else 0
        diff = full_rating - sparse_rating
        pct_diff = (diff / sparse_rating * 100) if sparse_rating > 0 else 0

        print(f"{player_name:<20} {sparse_rating:>10.1f} {full_rating:>10.1f} {diff:>+10.1f} {pct_diff:>+7.1f}%")

    # Round impact comparison (top 5 most different rounds)
    print(f"\n--- Round Impact Comparison (Top 5 differences) ---")

    sparse_rounds = {}
    full_rounds = {}

    for p in sparse_report["report"].player_impacts:
        for ri in p.round_impacts:
            key = (p.player_name, ri.round_id)
            sparse_rounds[key] = ri.round_total_impact

    for p in full_report["report"].player_impacts:
        for ri in p.round_impacts:
            key = (p.player_name, ri.round_id)
            full_rounds[key] = ri.round_total_impact

    diffs = []
    for key in set(sparse_rounds.keys()) | set(full_rounds.keys()):
        s = sparse_rounds.get(key, 0)
        f = full_rounds.get(key, 0)
        diffs.append((key, s, f, abs(f - s)))

    diffs.sort(key=lambda x: x[3], reverse=True)

    print(f"{'Player':<20} {'Round':>6} {'Sparse':>10} {'Full':>10} {'Diff':>10}")
    print("-" * 60)
    for (player, round_id), s, f, diff in diffs[:10]:
        print(f"{player:<20} {round_id:>6} {s:>+10.2f} {f:>+10.2f} {f-s:>+10.2f}")

    # Event-level comparison (kills)
    print(f"\n--- Kill Impact Comparison (Top 5 differences) ---")

    sparse_kills = []
    full_kills = []

    for p in sparse_report["report"].player_impacts:
        for ri in p.round_impacts:
            for ki in ri.kills:
                sparse_kills.append({
                    "player": p.player_name,
                    "round": ri.round_id,
                    "victim": ki.event.other_player,
                    "tick": ki.event.tick,
                    "impact": ki.total_impact,
                    "win_rate_delta": ki.win_rate_delta,
                    "labels": ki.labels,
                })

    for p in full_report["report"].player_impacts:
        for ri in p.round_impacts:
            for ki in ri.kills:
                full_kills.append({
                    "player": p.player_name,
                    "round": ri.round_id,
                    "victim": ki.event.other_player,
                    "tick": ki.event.tick,
                    "impact": ki.total_impact,
                    "win_rate_delta": ki.win_rate_delta,
                    "labels": ki.labels,
                })

    # Match kills by player+victim+round
    sparse_kill_map = {}
    for k in sparse_kills:
        key = (k["player"], k["victim"], k["round"])
        sparse_kill_map[key] = k

    full_kill_map = {}
    for k in full_kills:
        key = (k["player"], k["victim"], k["round"])
        full_kill_map[key] = k

    kill_diffs = []
    for key in set(sparse_kill_map.keys()) | set(full_kill_map.keys()):
        s = sparse_kill_map.get(key, {"impact": 0, "win_rate_delta": 0})
        f = full_kill_map.get(key, {"impact": 0, "win_rate_delta": 0})
        kill_diffs.append((key, s, f, abs(f["impact"] - s["impact"])))

    kill_diffs.sort(key=lambda x: x[3], reverse=True)

    print(f"{'Player':<15} {'Victim':<15} {'Round':>6} {'Sparse':>10} {'Full':>10} {'Diff':>10}")
    print("-" * 70)
    for (player, victim, round_id), s, f, diff in kill_diffs[:10]:
        print(f"{player:<15} {victim:<15} {round_id:>6} {s['impact']:>+10.2f} {f['impact']:>+10.2f} {f['impact']-s['impact']:>+10.2f}")

    # Summary statistics
    print(f"\n--- Summary Statistics ---")
    sparse_total_impact = sum(p.total_score for p in sparse_report["report"].player_impacts)
    full_total_impact = sum(p.total_score for p in full_report["report"].player_impacts)
    print(f"Total match impact (sparse): {sparse_total_impact:.2f}")
    print(f"Total match impact (full):   {full_total_impact:.2f}")
    print(f"Difference:                  {full_total_impact - sparse_total_impact:+.2f}")

    # Save detailed comparison to file
    output = {
        "timing": {
            "sparse": sparse_report["timing"],
            "full": full_report["timing"],
        },
        "tick_counts": {
            "sparse": sparse_report["total_ticks"],
            "full": full_report["total_ticks"],
        },
        "player_ratings": {
            player_name: {
                "sparse": sparse_players.get(player_name, {}).rating_0_100 if sparse_players.get(player_name) else 0,
                "full": full_players.get(player_name, {}).rating_0_100 if full_players.get(player_name) else 0,
            }
            for player_name in all_players
        },
    }

    return output


def main():
    parser = argparse.ArgumentParser(description="Compare sparse vs full tick Impact Engine analysis")
    parser.add_argument("--demo", required=True, help="Path to .dem file")
    parser.add_argument("--model_root", default="cs-net-models", help="Model root directory")
    parser.add_argument("--device", default="cpu", help="Device (cpu/cuda)")
    parser.add_argument("--batch_size", type=int, default=32, help="Inference batch size")
    parser.add_argument("--output", default="full_tick_comparison.json", help="Output comparison JSON")
    parser.add_argument("--sparse-only", action="store_true", help="Only run sparse mode (for testing)")
    args = parser.parse_args()

    demo_path = Path(args.demo)
    model_root = Path(args.model_root)

    if not demo_path.exists():
        print(f"Error: Demo file not found: {demo_path}")
        sys.exit(1)

    if not model_root.exists():
        print(f"Error: Model root not found: {model_root}")
        sys.exit(1)

    device = torch.device(args.device)

    # Run sparse mode
    sparse_result = run_analysis_with_tick_mode(demo_path, model_root, device, "sparse", args.batch_size)

    if args.sparse_only:
        print("\nSparse-only mode, skipping full tick analysis")
        return

    # Run full mode
    full_result = run_analysis_with_tick_mode(demo_path, model_root, device, "full", args.batch_size)

    # Compare
    comparison = compare_reports(sparse_result, full_result)

    # Save comparison
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"\nComparison saved to: {output_path}")


if __name__ == "__main__":
    main()
