#!/usr/bin/env python3
"""Calibrate impact-engine thresholds by map and round phase.

This script reuses the event statistics pattern in compare_* scripts and performs
simple grid-search/quantile calibration for:
- kill_impact.trade_window_seconds
- duel_thresholds.hard_duel_win_max_prob
- align_tolerance_seconds (for event/tick matching quality)

Output format is a layered config with map -> phase -> thresholds, plus a global
fallback section.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import quantiles
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo_analysis.high_level_analysis import build_dashboard_payload
from demo_analysis.impact_engine import ImpactEngine


PHASE_BINS = {
    "opening": (0.0, 35.0),
    "mid": (35.0, 75.0),
    "late": (75.0, float("inf")),
}


@dataclass
class CalibrationPoint:
    map_name: str
    phase: str
    round_id: int
    event_tick: float


def _phase_from_tick(tick: float) -> str:
    for phase, (start, end) in PHASE_BINS.items():
        if start <= tick < end:
            return phase
    return "mid"


def _extract_points(raw_results: dict[str, Any]) -> list[CalibrationPoint]:
    points: list[CalibrationPoint] = []
    for key, value in raw_results.items():
        if not key.isdigit() or not isinstance(value, dict):
            continue
        map_name = value.get("map_name") or "unknown"
        round_id = int(key)
        for event in value.get("kills", []):
            tick = float(event.get("tick", 0.0))
            points.append(CalibrationPoint(map_name, _phase_from_tick(tick), round_id, tick))
    return points


def _nearest_gap(ticks: list[dict[str, Any]], event_tick: float) -> float | None:
    if not ticks:
        return None
    vals = [abs(float(t.get("round_seconds", 0.0)) - event_tick) for t in ticks]
    return min(vals) if vals else None


def _score_alignment(raw_results: dict[str, Any], tolerance: float, map_name: str, phase: str) -> tuple[float, float, float]:
    tp = fp = fn = 0
    for key, value in raw_results.items():
        if not key.isdigit() or not isinstance(value, dict):
            continue
        if (value.get("map_name") or "unknown") != map_name:
            continue
        ticks = value.get("ticks", [])
        for event in value.get("kills", []):
            tick = float(event.get("tick", 0.0))
            if _phase_from_tick(tick) != phase:
                continue
            gap = _nearest_gap(ticks, tick)
            if gap is None:
                fn += 1
            elif gap <= tolerance:
                tp += 1
            else:
                fp += 1
                fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return f1, precision, recall


def _evaluate_with_thresholds(raw_results: dict[str, Any], trade_window: float, hard_duel: float) -> dict[str, Any]:
    modified = copy.deepcopy(raw_results)
    dashboard = build_dashboard_payload(modified)
    engine = ImpactEngine(dashboard)
    # override runtime weights (global for this run)
    from demo_analysis.impact_engine.config import IMPACT_WEIGHTS

    IMPACT_WEIGHTS["kill_impact"]["trade_window_seconds"] = trade_window
    IMPACT_WEIGHTS["duel_thresholds"]["hard_duel_win_max_prob"] = hard_duel
    report = engine.analyze()

    return {
        "report": report,
    }


def calibrate(raw_results: dict[str, Any], trade_windows: list[float], hard_duels: list[float], tolerances: list[float]) -> dict[str, Any]:
    points = _extract_points(raw_results)
    maps = sorted({p.map_name for p in points})
    phases = ["opening", "mid", "late"]

    output: dict[str, Any] = {"global": {}, "maps": {}}

    for map_name in maps:
        output["maps"][map_name] = {}
        for phase in phases:
            best = None
            best_metrics = (-1.0, 0.0, 0.0)
            for trade_window in trade_windows:
                for hard_duel in hard_duels:
                    _evaluate_with_thresholds(raw_results, trade_window, hard_duel)
                    for tol in tolerances:
                        f1, p, r = _score_alignment(raw_results, tol, map_name, phase)
                        if f1 > best_metrics[0]:
                            best_metrics = (f1, p, r)
                            best = {
                                "trade_window_seconds": trade_window,
                                "hard_duel_win_max_prob": hard_duel,
                                "align_tolerance_seconds": tol,
                                "metrics": {"f1": round(f1, 4), "precision": round(p, 4), "recall": round(r, 4)},
                            }
            if best is not None:
                output["maps"][map_name][phase] = best

    # Global fallback by quantiles from selected map/phase values.
    tw = [v["trade_window_seconds"] for m in output["maps"].values() for v in m.values()]
    hd = [v["hard_duel_win_max_prob"] for m in output["maps"].values() for v in m.values()]
    at = [v["align_tolerance_seconds"] for m in output["maps"].values() for v in m.values()]

    if tw and hd and at:
        output["global"] = {
            "trade_window_seconds": round(quantiles(tw, n=2)[0], 3) if len(tw) > 1 else tw[0],
            "hard_duel_win_max_prob": round(quantiles(hd, n=2)[0], 3) if len(hd) > 1 else hd[0],
            "align_tolerance_seconds": round(quantiles(at, n=2)[0], 3) if len(at) > 1 else at[0],
        }

    return output


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Calibrate impact thresholds by map and phase")
    ap.add_argument("--json", required=True, help="Path to analysis json")
    ap.add_argument("--output", default="config/impact_thresholds.yaml")
    ap.add_argument("--trade-windows", default="3,4,5,6")
    ap.add_argument("--hard-duels", default="0.40,0.45,0.50")
    ap.add_argument("--tolerances", default="0.02,0.05,0.10")
    return ap.parse_args()


def _parse_csv_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def main() -> int:
    args = parse_args()
    path = Path(args.json)
    raw_results = json.loads(path.read_text(encoding="utf-8"))
    output = calibrate(
        raw_results,
        trade_windows=_parse_csv_floats(args.trade_windows),
        hard_duels=_parse_csv_floats(args.hard_duels),
        tolerances=_parse_csv_floats(args.tolerances),
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(output, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote calibration config to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
