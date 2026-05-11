"""Generate Chinese impact reports for CS2 matches."""

from typing import Any

from .align import safe_float
from .models import (
    EventImpact,
    ImpactReport,
    PlayerMatchImpact,
    PlayerRoundImpact,
    RiskType,
)


def format_percent(value: float) -> str:
    """Format a float as percentage."""
    return f"{value * 100:.1f}%"


def format_delta(value: float) -> str:
    """Format a delta value with sign."""
    if value >= 0:
        return f"+{value:.1%}"
    return f"{value:.1%}"


def get_player_summary(player: PlayerMatchImpact) -> str:
    """Generate a brief summary for a player."""
    rating = player.rating_0_100
    team = "CT" if player.team == "team1" else "T"

    if rating >= 80:
        verdict = "表现出色"
    elif rating >= 65:
        verdict = "发挥良好"
    elif rating >= 50:
        verdict = "中规中矩"
    elif rating >= 35:
        verdict = "表现欠佳"
    else:
        verdict = "严重失误"

    kills, deaths, _ = player.kda
    assists = sum(len(ri.deaths) for ri in player.round_impacts) - deaths

    summary = (
        f"{player.player_name}（{team}方）"
        f"评分: {rating:.0f}/100\n"
        f"KDA: {kills}/{deaths}/{assists}  "
        f"高影响回合: {player.high_impact_rounds}  "
        f"白给死亡: {player.bad_deaths}"
    )

    return summary


def generate_player_report(player: PlayerMatchImpact) -> str:
    """Generate detailed Chinese report for a player."""
    rating = player.rating_0_100
    team = "CT" if player.team == "team1" else "T"

    lines = []
    lines.append(f"# {player.player_name}（{team}方）")
    lines.append("")
    lines.append(f"## 综合评分: {rating:.0f} / 100")
    lines.append("")

    model_score = player.model_impact_score
    rule_score = player.rule_quality_score
    lines.append(f"**模型影响分**: {model_score:.1f}")
    lines.append(f"**规则质量分**: {rule_score:.1f}")
    lines.append("")

    kills, deaths, _ = player.kda
    lines.append(f"### KDA: {kills}/{deaths}")
    lines.append("")
    lines.append(f"- 高影响回合: **{player.high_impact_rounds}** 次")
    lines.append(f"- 正面回合: {player.positive_rounds} 次")
    lines.append(f"- 中性回合: {player.neutral_rounds} 次")
    lines.append(f"- 负面回合: {player.negative_rounds} 次")
    lines.append(f"- 失误回合: {player.throw_rounds} 次")
    lines.append("")

    lines.append("### 击杀贡献")
    lines.append("")
    lines.append(f"- 首杀: {player.opening_kills} 次")
    lines.append(f"- 补枪: {player.effective_trades} 次")
    lines.append(f"- 残局击杀: {player.clutch_kills} 次")
    lines.append(f"- Hard Duel Win: {player.hard_duel_wins} 次")
    lines.append(f"- 出口杀: {player.exit_frags} 次")
    lines.append(f"- 低价值击杀: {player.low_impact_kills} 次")
    lines.append("")

    lines.append("### 死亡分析")
    lines.append("")
    lines.append(f"- 首死: {player.opening_deaths} 次")
    lines.append(f"- 被补枪死亡: {player.trades_taken} 次")
    lines.append(f"- 白给死亡: {player.bad_deaths} 次")
    lines.append(f"- 自造风险死亡: {player.self_created_risk_deaths} 次")
    lines.append(f"- 合理高风险死亡: {player.forced_risk_deaths} 次")
    lines.append(f"- 意外死亡: {player.unexpected_deaths} 次")
    lines.append(f"- 下包后乱peek死亡: {player.post_plant_throw_deaths} 次")
    lines.append(f"- 独狼持包死亡: {player.bomb_carrier_died_alone} 次")
    lines.append(f"- Easy Duel Loss: {player.easy_duel_losses} 次")
    lines.append("")

    if player.positive_kill_events or player.negative_death_events:
        lines.append("### 关键正面行为")
        lines.append("")
        for i, event in enumerate(player.positive_kill_events[:3], 1):
            round_id = event.get("round", "?")
            opponent = event.get("opponent", "?")
            impact = event.get("impact", 0)
            wr_delta = event.get("win_rate_delta", 0)
            labels = event.get("labels", [])

            desc_parts = [f"{i}. 第 {round_id} 回合"]

            if "hard_duel_win" in labels:
                desc_parts.append("Hard Duel Win")
            if "trade_kill" in labels:
                desc_parts.append("补枪击杀")
            if "opening_kill" in labels:
                desc_parts.append("首杀")
            if "clutch_kill" in labels:
                desc_parts.append("残局击杀")

            wr_str = format_delta(wr_delta)
            desc_parts.append(f"胜率{wr_str}")

            lines.append(" ".join(desc_parts))
        lines.append("")

        lines.append("### 关键负面行为")
        lines.append("")
        for i, event in enumerate(player.negative_death_events[:3], 1):
            round_id = event.get("round", "?")
            opponent = event.get("opponent", "?")
            impact = event.get("impact", 0)
            labels = event.get("labels", [])

            desc_parts = [f"{i}. 第 {round_id} 回合 对阵 {opponent}"]

            if "self_created_risk_death" in labels:
                desc_parts.append("自造风险死亡")
            if "bad_death" in labels:
                desc_parts.append("白给")
            if "post_plant_throw_death" in labels:
                desc_parts.append("下包后乱peek")
            if "bomb_carrier_died_alone" in labels:
                desc_parts.append("持包单走")
            if "traded_death" in labels:
                desc_parts.append("未完成补枪")
            if "unexpected_death" in labels:
                desc_parts.append("意外死亡")

            lines.append(" ".join(desc_parts))
        lines.append("")

    conclusion = generate_conclusion(player)
    lines.append("### 综合结论")
    lines.append("")
    lines.append(conclusion)

    improvement = generate_improvement_suggestions(player)
    if improvement:
        lines.append("")
        lines.append("### 改进建议")
        lines.append("")
        lines.append(improvement)

    return "\n".join(lines)


def generate_conclusion(player: PlayerMatchImpact) -> str:
    """Generate a conclusion for the player's performance."""
    rating = player.rating_0_100
    kills, deaths, _ = player.kda
    kd_ratio = kills / max(1, deaths)

    positives = []
    negatives = []

    if player.high_impact_rounds >= 3:
        positives.append(f"有 {player.high_impact_rounds} 个高影响回合")

    if player.hard_duel_wins >= 2:
        positives.append(f"完成 {player.hard_duel_wins} 次高难度击杀")

    if player.effective_trades >= 2:
        positives.append(f"补枪 {player.effective_trades} 次，帮助队友")

    if player.clutch_kills >= 1:
        positives.append(f"完成 {player.clutch_kills} 次残局击杀")

    if player.bad_deaths >= 2:
        negatives.append(f"有 {player.bad_deaths} 次白给死亡")

    if player.self_created_risk_deaths >= 2:
        negatives.append(f" {player.self_created_risk_deaths} 次自造风险死亡")

    if player.easy_duel_losses >= 1:
        negatives.append(f" {player.easy_duel_losses} 次Easy Duel Loss")

    if player.post_plant_throw_deaths >= 1:
        negatives.append(f" {player.post_plant_throw_deaths} 次下包后乱peek")

    if rating >= 75:
        base = "该玩家整体发挥出色。"
    elif rating >= 60:
        base = "该玩家整体发挥良好。"
    elif rating >= 45:
        base = "该玩家整体发挥中规中矩。"
    elif rating >= 30:
        base = "该玩家整体发挥有待提高。"
    else:
        base = "该玩家本场表现不佳，需要认真总结。"

    parts = [base]

    if positives:
        parts.append("亮点方面：" + "、".join(positives) + "。")

    if negatives:
        parts.append("不足方面：" + "、".join(negatives) + "。")

    return " ".join(parts)


def generate_improvement_suggestions(player: PlayerMatchImpact) -> str:
    """Generate improvement suggestions based on player analysis."""
    suggestions = []

    if player.self_created_risk_deaths >= 2:
        suggestions.append("减少无意义的风险行为，避免在优势局面下单摸")

    if player.bad_deaths >= 3:
        suggestions.append("死亡选择需要更谨慎，注意评估风险收益比")

    if player.easy_duel_losses >= 1:
        suggestions.append("提升对枪质量，在不利位置避免强行对枪")

    if player.post_plant_throw_deaths >= 1:
        suggestions.append("下包后优先保持位置稳定，不要离开交叉火力位找人")

    if player.bomb_carrier_died_alone >= 1:
        suggestions.append("持包时保持与队友配合，避免独狼行动")

    if player.low_impact_kills >= 2:
        suggestions.append("提升进攻主动性，增加首杀和关键击杀的贡献")

    if player.opening_deaths >= 2 and player.opening_kills == 0:
        suggestions.append("增加首杀尝试或改善首死后的支援")

    if player.effective_trades < player.trades_taken:
        suggestions.append("注意补枪时机和位置，提高补枪成功率")

    if not suggestions:
        suggestions.append("继续保持当前表现，注意细节优化")

    return "；".join(suggestions) + "。"


def generate_match_report(report: ImpactReport) -> str:
    """Generate complete match report."""
    lines = []
    lines.append(f"# CS2 回合影响力评分报告")
    lines.append("")
    lines.append(f"**地图**: {report.map_name}")
    lines.append(f"**比赛回合数**: {report.total_rounds}")
    lines.append(f"**比分**: {report.match_info.get('team1_round_wins', '?')} - {report.match_info.get('team2_round_wins', '?')}")
    lines.append(f"**胜方**: {report.match_winner}")
    lines.append("")

    lines.append("## 评分说明")
    lines.append("")
    lines.append("- **综合评分 (0-100)**: 结合模型影响分(65%)和规则质量分(35%)")
    lines.append("- **模型影响分**: 基于RWI(回合胜率影响)、Hard Duel Win、Easy Duel Loss等")
    lines.append("- **规则质量分**: 基于补枪、白给死亡、自造风险、目标行为等")
    lines.append("")

    lines.append("## 选手评分")
    lines.append("")

    team1_players = [p for p in report.player_impacts if p.team == "team1"]
    team2_players = [p for p in report.player_impacts if p.team == "team2"]

    team1_names = report.match_info.get("team1_players", [])
    team2_names = report.match_info.get("team2_players", [])

    team1_players.sort(key=lambda p: p.rating_0_100, reverse=True)
    team2_players.sort(key=lambda p: p.rating_0_100, reverse=True)

    lines.append(f"### {report.team1_name}")
    lines.append("")
    for player in team1_players:
        rating = player.rating_0_100
        kills, deaths, _ = player.kda
        lines.append(f"- **{player.player_name}**: {rating:.0f}/100 (K/D: {kills}/{deaths})")
    lines.append("")

    lines.append(f"### {report.team2_name}")
    lines.append("")
    for player in team2_players:
        rating = player.rating_0_100
        kills, deaths, _ = player.kda
        lines.append(f"- **{player.player_name}**: {rating:.0f}/100 (K/D: {kills}/{deaths})")
    lines.append("")

    lines.append("---")
    lines.append("")

    lines.append("# 详细分析")
    lines.append("")

    for player in sorted(report.player_impacts, key=lambda p: p.rating_0_100, reverse=True):
        lines.append(generate_player_report(player))
        lines.append("")
        lines.append("---")
        lines.append("")

    if report.warnings:
        lines.append("## 注意事项")
        lines.append("")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines)


def generate_summary_table(report: ImpactReport) -> str:
    """Generate a summary table for all players."""
    lines = []
    lines.append("| 选手 | 阵营 | 评分 | 模型分 | 规则分 | K | D | 首杀 | 补枪 | 白给 | 自造风险 | Hard Duel | Easy Duel |")
    lines.append("|------|------|------|--------|--------|---|---|------|------|------|---------|-----------|-----------|")

    for player in sorted(report.player_impacts, key=lambda p: p.rating_0_100, reverse=True):
        team = "CT" if player.team == "team1" else "T"
        kills, deaths, _ = player.kda

        lines.append(
            f"| {player.player_name} | {team} | "
            f"{player.rating_0_100:.0f} | "
            f"{player.model_impact_score:.1f} | "
            f"{player.rule_quality_score:.1f} | "
            f"{kills} | {deaths} | "
            f"{player.opening_kills} | "
            f"{player.effective_trades} | "
            f"{player.bad_deaths} | "
            f"{player.self_created_risk_deaths} | "
            f"{player.hard_duel_wins} | "
            f"{player.easy_duel_losses} |"
        )

    return "\n".join(lines)


def report_to_json(report: ImpactReport) -> dict[str, Any]:
    """Convert ImpactReport to JSON-serializable dict."""
    result = {
        "match_info": report.match_info,
        "map_name": report.map_name,
        "total_rounds": report.total_rounds,
        "match_winner": report.match_winner,
        "confidence": report.confidence,
        "warnings": report.warnings,
        "players": [],
    }

    # Report-level diagnostics for score calibration
    model_impact_clip_count_min = 0
    model_impact_clip_count_max = 0
    rating_zero_count = 0
    rating_hundred_count = 0

    for player in report.player_impacts:
        if player.model_impact_score_raw < -50:
            model_impact_clip_count_min += 1
        if player.model_impact_score_raw > 50:
            model_impact_clip_count_max += 1
        if player.rating_0_100 <= 0.0:
            rating_zero_count += 1
        if player.rating_0_100 >= 100.0:
            rating_hundred_count += 1

        player_data = {
            "player_name": player.player_name,
            "team": player.team,
            "rating_0_100": round(player.rating_0_100, 1),
            "model_impact_score": round(player.model_impact_score, 2),
            "rule_quality_score": round(player.rule_quality_score, 2),
            "kda": {
                "kills": player.kda[0],
                "deaths": player.kda[1],
            },
            "round_stats": {
                "high_impact": player.high_impact_rounds,
                "positive": player.positive_rounds,
                "neutral": player.neutral_rounds,
                "negative": player.negative_rounds,
                "throw": player.throw_rounds,
            },
            "kill_stats": {
                "opening_kills": player.opening_kills,
                "effective_trades": player.effective_trades,
                "clutch_kills": player.clutch_kills,
                "hard_duel_wins": player.hard_duel_wins,
                "exit_frags": player.exit_frags,
                "low_impact_kills": player.low_impact_kills,
            },
            "death_stats": {
                "opening_deaths": player.opening_deaths,
                "trades_taken": player.trades_taken,
                "bad_deaths": player.bad_deaths,
                "self_created_risk_deaths": player.self_created_risk_deaths,
                "forced_risk_deaths": player.forced_risk_deaths,
                "unexpected_deaths": player.unexpected_deaths,
                "post_plant_throw_deaths": player.post_plant_throw_deaths,
                "bomb_carrier_died_alone": player.bomb_carrier_died_alone,
                "easy_duel_losses": player.easy_duel_losses,
            },
            "positive_events": player.positive_kill_events[:5],
            "negative_events": player.negative_death_events[:5],
            # Diagnostic fields
            "diagnostics": {
                "avg_round_impact": round(player.avg_round_impact, 3),
                "total_round_impact": round(player.total_round_impact, 2),
                "model_impact_score_raw": round(player.model_impact_score_raw, 2),
                "model_impact_score_clipped": round(player.model_impact_score_clipped, 2),
                "rule_quality_score_raw": round(player.rule_quality_score_raw, 2),
                "rule_quality_score_clipped": round(player.rule_quality_score_clipped, 2),
                "kill_impact_total": round(player.kill_impact_total, 2),
                "death_impact_total": round(player.death_impact_total, 2),
            },
        }
        result["players"].append(player_data)

    # Add report-level diagnostics
    result["diagnostics"] = {
        "model_impact_clip_count_min": model_impact_clip_count_min,
        "model_impact_clip_count_max": model_impact_clip_count_max,
        "rating_zero_count": rating_zero_count,
        "rating_hundred_count": rating_hundred_count,
    }

    # Add warning if model impact is heavily clipped
    total_players = len(report.player_impacts)
    if total_players > 0:
        clip_ratio = (model_impact_clip_count_min + model_impact_clip_count_max) / total_players
        if clip_ratio >= 0.3:
            warning = "model_impact_score appears heavily clipped; rating calibration may need adjustment."
            if warning not in result["warnings"]:
                result["warnings"].append(warning)

    return result
