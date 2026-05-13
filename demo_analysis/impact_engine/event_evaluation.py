"""Event-level evaluation utilities for impact engine regression."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .align import extract_damage_events, extract_future_kill_events, extract_kill_events
from .models import EventType, GameEvent


@dataclass
class EventEvalSample:
    map_name: str
    predicted: list[GameEvent]
    truth: list[GameEvent]


def _normalize_weapon(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().lower().replace("weapon_", "")


def _match_event(pred: GameEvent, truth_candidates: list[GameEvent], time_tolerance: float = 0.6) -> tuple[int | None, str | None]:
    best_idx = None
    best_err = 10**9
    for idx, gt in enumerate(truth_candidates):
        if pred.event_type != gt.event_type:
            continue
        err = abs(pred.tick - gt.tick)
        if err <= time_tolerance and err < best_err:
            best_idx = idx
            best_err = err
    if best_idx is None:
        return None, "time_mismatch"

    gt = truth_candidates[best_idx]
    if pred.player != gt.player or pred.other_player != gt.other_player:
        return best_idx, "player_name_mismatch"
    if _normalize_weapon(pred.weapon) != _normalize_weapon(gt.weapon):
        return best_idx, "weapon_category_mismatch"
    return best_idx, None


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def evaluate_event_samples(samples: list[EventEvalSample]) -> dict[str, Any]:
    types = [EventType.KILL, EventType.DEATH, EventType.DAMAGE]
    summary: dict[str, dict[str, float]] = {}
    time_errors: list[float] = []
    attribution = Counter()
    map_buckets: dict[str, dict[str, dict[str, float]]] = {}

    for event_type in types:
        tp = fp = fn = 0
        for sample in samples:
            map_tp = map_fp = map_fn = 0
            pred = [e for e in sample.predicted if e.event_type == event_type]
            truth = [e for e in sample.truth if e.event_type == event_type]
            used_truth: set[int] = set()
            for p in pred:
                idx, reason = _match_event(p, truth)
                if idx is None:
                    fp += 1
                    map_fp += 1
                    if reason:
                        attribution[reason] += 1
                    continue
                gt = truth[idx]
                if idx in used_truth:
                    fp += 1
                    map_fp += 1
                    attribution["dedup_over_delete"] += 1
                    continue
                used_truth.add(idx)
                time_errors.append(abs(p.tick - gt.tick))
                if reason:
                    fp += 1
                    map_fp += 1
                    attribution[reason] += 1
                else:
                    tp += 1
                    map_tp += 1
            fn_delta = len(truth) - len(used_truth)
            fn += fn_delta
            map_fn += fn_delta

            by_map = map_buckets.setdefault(sample.map_name, {})
            counters = by_map.setdefault(event_type.value, {"tp": 0, "fp": 0, "fn": 0})
            counters["tp"] += map_tp
            counters["fp"] += map_fp
            counters["fn"] += map_fn

        summary[event_type.value.upper()] = _prf(tp, fp, fn)

    sorted_attr = sorted(attribution.items(), key=lambda x: x[1], reverse=True)
    time_distribution = {
        "count": len(time_errors),
        "mean_abs_error": round(sum(time_errors) / len(time_errors), 4) if time_errors else 0.0,
        "p95_abs_error": round(sorted(time_errors)[max(0, int(len(time_errors) * 0.95) - 1)], 4) if time_errors else 0.0,
    }

    map_bucket_performance: dict[str, dict[str, dict[str, float]]] = {}
    for map_name, event_stats in map_buckets.items():
        map_bucket_performance[map_name] = {}
        for event_name, counters in event_stats.items():
            map_bucket_performance[map_name][event_name] = _prf(
                int(counters["tp"]),
                int(counters["fp"]),
                int(counters["fn"]),
            )

    return {
        "metrics": summary,
        "time_error_distribution": time_distribution,
        "map_bucket_performance": map_bucket_performance,
        "error_attribution": [{"reason": k, "count": v} for k, v in sorted_attr],
    }


def build_predicted_events(rounds: list[dict[str, Any]], team1_players: list[str], team2_players: list[str]) -> list[EventEvalSample]:
    samples: list[EventEvalSample] = []
    for round_data in rounds:
        team1_on_ct = bool(round_data.get("team1_on_ct", True))
        pred = []
        pred.extend(extract_kill_events(round_data, team1_players, team2_players, team1_on_ct))
        pred.extend(extract_damage_events(round_data, team1_players, team2_players, team1_on_ct))
        pred.extend(extract_future_kill_events(round_data, team1_players, team2_players, team1_on_ct))
        truth = _build_truth_events(round_data)
        samples.append(EventEvalSample(map_name=str(round_data.get("map_name", "unknown")), predicted=pred, truth=truth))
    return samples


def _build_truth_events(round_data: dict[str, Any]) -> list[GameEvent]:
    gt = round_data.get("event_ground_truth")
    if not gt:
        return []
    out: list[GameEvent] = []
    for item in gt:
        out.append(GameEvent(
            event_type=EventType(str(item.get("event_type", "kill")).lower()),
            tick=float(item.get("tick", 0.0)),
            player=str(item.get("player", "")),
            other_player=item.get("other_player"),
            weapon=item.get("weapon"),
        ))
    return out
