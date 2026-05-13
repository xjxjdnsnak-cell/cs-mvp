"""Generate round-by-round timeline for player performance."""

from typing import Any

from .models import PlayerMatchImpact, PlayerRoundImpact


def _get_round_phase_label(round_impact: PlayerRoundImpact) -> str:
    """Get a human-readable round phase label."""
    if round_impact.carry_round:
        return "Carry"
    elif round_impact.throw_round:
        return "Throw"
    elif round_impact.round_total_impact > 0.5:
        return "High Impact"
    elif round_impact.round_total_impact < -0.5:
        return "Negative"
    return "Neutral"


def _extract_kill_events(round_impact: PlayerRoundImpact) -> list[dict[str, Any]]:
    """Extract kill events from round impact."""
    events = []
    for kill in round_impact.kills:
        ev = kill.event
        events.append({
            "type": "kill",
            "tick": ev.tick,
            "opponent": ev.other_player,
            "impact": kill.total_impact,
            "labels": kill.labels,
        })
    return events


def _extract_death_events(round_impact: PlayerRoundImpact) -> list[dict[str, Any]]:
    """Extract death events from round impact."""
    events = []
    for death in round_impact.deaths:
        ev = death.event
        events.append({
            "type": "death",
            "tick": ev.tick,
            "opponent": ev.other_player,
            "impact": death.total_impact,
            "labels": death.labels,
        })
    return events


def _extract_utility_events(round_impact: PlayerRoundImpact) -> list[dict[str, Any]]:
    """Extract utility events from round impact."""
    events = []
    for flash in round_impact.flash_events:
        events.append({
            "type": "utility",
            "subtype": "flash",
            "tick": flash.tick,
            "impact": flash.score,
            "labels": flash.labels,
        })
    for smoke in round_impact.smoke_events:
        events.append({
            "type": "utility",
            "subtype": "smoke",
            "tick": smoke.tick,
            "impact": smoke.score,
            "labels": smoke.labels,
        })
    for fire in round_impact.fire_events:
        events.append({
            "type": "utility",
            "subtype": "fire",
            "tick": fire.tick,
            "impact": fire.score,
            "labels": fire.labels,
        })
    for he in round_impact.he_events:
        events.append({
            "type": "utility",
            "subtype": "he",
            "tick": he.tick,
            "impact": he.score,
            "labels": he.labels,
        })
    return events


def _extract_tactical_events(round_impact: PlayerRoundImpact) -> list[dict[str, Any]]:
    """Extract tactical events from round impact."""
    events = []
    for te in round_impact.tactical_events:
        events.append({
            "type": "tactical",
            "tick": te.get("tick", 0),
            "label": te.get("label", ""),
            "impact": te.get("score", 0),
            "reason": te.get("reason", ""),
            "area": te.get("area"),
            "area_cn": te.get("area_cn"),
            "phase": te.get("phase", ""),
        })
    return events


def _format_event_description(event: dict[str, Any]) -> str:
    """Format a single event into human-readable description."""
    etype = event.get("type", "")

    if etype == "kill":
        opponent = event.get("opponent", "?")
        labels = event.get("labels", [])
        desc_parts = [f"击杀 {opponent}"]
        if "opening_kill" in labels:
            desc_parts.append("(首杀)")
        elif "trade_kill" in labels:
            desc_parts.append("(补枪)")
        elif "clutch_kill" in labels:
            desc_parts.append("(残局)")
        elif "hard_duel_win" in labels:
            desc_parts.append("(Hard Duel)")
        return " ".join(desc_parts)

    if etype == "death":
        opponent = event.get("opponent", "?")
        labels = event.get("labels", [])
        desc_parts = [f"被 {opponent} 击杀"]
        if "bad_death" in labels:
            desc_parts.append("(白给)")
        elif "self_created_risk_death" in labels:
            desc_parts.append("(自造风险)")
        elif "traded_death" in labels:
            desc_parts.append("(被补枪)")
        elif "opening_death" in labels:
            desc_parts.append("(首死)")
        return " ".join(desc_parts)

    if etype == "utility":
        subtype = event.get("subtype", "")
        labels = event.get("labels", [])
        desc_map = {
            "flash": "闪光弹",
            "smoke": "烟雾弹",
            "fire": "燃烧瓶",
            "he": "手雷",
        }
        desc = desc_map.get(subtype, subtype)
        if labels:
            desc += f" ({', '.join(labels[:2])})"
        return desc

    if etype == "tactical":
        label = event.get("label", "")
        reason = event.get("reason", "")
        area_cn = event.get("area_cn") or event.get("area") or ""
        desc = reason or label
        if area_cn:
            desc = f"[{area_cn}] {desc}"
        return desc

    return str(event)


def generate_player_timeline(player: PlayerMatchImpact) -> list[dict[str, Any]]:
    """Generate round-by-round timeline for a player.

    Returns a list of round entries, each containing:
    - round_id: int
    - side: "CT" | "T"
    - phase: str (Carry/Throw/High Impact/Negative/Neutral)
    - round_total_impact: float
    - kda: str (e.g. "2/1")
    - events: list of formatted event descriptions
    - key_positives: list[str]
    - key_negatives: list[str]
    """
    timeline = []
    for ri in player.round_impacts:
        kills = len(ri.kills)
        deaths = len(ri.deaths)

        kill_events = _extract_kill_events(ri)
        death_events = _extract_death_events(ri)
        utility_events = _extract_utility_events(ri)
        tactical_events = _extract_tactical_events(ri)

        if len(tactical_events) > 3:
            tactical_events.sort(key=lambda e: abs(e.get("impact", 0)), reverse=True)
            tactical_events = tactical_events[:3]

        all_events = kill_events + death_events + utility_events + tactical_events
        all_events.sort(key=lambda e: e.get("tick", 0))

        event_descs = [_format_event_description(e) for e in all_events]

        entry = {
            "round_id": ri.round_id,
            "side": ri.player_side,
            "phase": _get_round_phase_label(ri),
            "round_total_impact": round(ri.round_total_impact, 2),
            "kda": f"{kills}/{deaths}",
            "events": event_descs,
            "key_positives": ri.key_positives,
            "key_negatives": ri.key_negatives,
        }
        timeline.append(entry)
    return timeline


def generate_timeline_markdown(player: PlayerMatchImpact) -> list[str]:
    """Generate Markdown timeline section for a player."""
    timeline = generate_player_timeline(player)
    if not timeline:
        return []

    lines = []
    lines.append("### 时间线梳理")
    lines.append("")
    lines.append("| 回合 | 阵营 | 阶段 | 影响 | K/D | 关键事件 |")
    lines.append("|------|------|------|------|-----|----------|")

    for entry in timeline:
        round_id = entry["round_id"]
        side = entry["side"]
        phase = entry["phase"]
        impact = entry["round_total_impact"]
        kda = entry["kda"]
        events = entry["events"]

        impact_str = f"{impact:+.2f}"
        if phase == "Carry":
            phase_str = f"**{phase}**"
        elif phase == "Throw":
            phase_str = f"**{phase}**"
        else:
            phase_str = phase

        events_str = "; ".join(events[:3]) if events else "-"
        if len(events) > 3:
            events_str += f" (+{len(events) - 3} more)"

        lines.append(
            f"| {round_id} | {side} | {phase_str} | {impact_str} | {kda} | {events_str} |"
        )

    lines.append("")
    return lines


def generate_match_timeline_markdown(report) -> list[str]:
    """Generate match-level timeline showing key moments per round."""
    lines = []
    lines.append("## 比赛时间线")
    lines.append("")
    lines.append("| 回合 | 关键事件 | 影响选手 |")
    lines.append("|------|----------|----------|")

    all_rounds = {}
    for player in report.player_impacts:
        for ri in player.round_impacts:
            rid = ri.round_id
            if rid not in all_rounds:
                all_rounds[rid] = []

            events = []
            for k in ri.kills:
                events.append(f"{player.player_name} 击杀 {k.event.other_player}")
            for d in ri.deaths:
                events.append(f"{player.player_name} 被 {d.event.other_player} 击杀")
            for te in ri.tactical_events:
                label = te.get("label", "")
                if label in ["valid_entry_sacrifice", "post_plant_discipline_error",
                             "post_plant_overpeek", "retake_solo_feed",
                             "key_area_isolated_death"]:
                    events.append(te.get("reason", label))

            if events:
                all_rounds[rid].extend(events)

    for rid in sorted(all_rounds.keys()):
        events = all_rounds[rid]
        if events:
            key_events = events[:3]
            events_str = "; ".join(key_events)
            if len(events) > 3:
                events_str += f" (+{len(events) - 3})"
            players_involved = []
            for e in events:
                if e.startswith("击杀 ") or e.startswith("被 "):
                    continue
                name = e.split(" 击杀 ")[0].split(" 被 ")[0].split(": ")[0]
                if name and name not in players_involved:
                    players_involved.append(name)
            players_involved = players_involved[:5]
            players_str = ", ".join(players_involved)
            lines.append(f"| {rid} | {events_str} | {players_str} |")

    lines.append("")
    return lines
