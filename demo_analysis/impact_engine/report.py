"""Generate Chinese impact reports for CS2 matches."""

from typing import Any

from .align import safe_float
from .models import (
    EventImpact,
    HighlightMoment,
    ImpactReport,
    PlayerMatchImpact,
    PlayerRoundImpact,
    RiskType,
)
from .utility_flash import flash_blind_phrase


def format_percent(value: float) -> str:
    """Format a float as percentage."""
    return f"{value * 100:.1f}%"


def format_delta(value: float) -> str:
    """Format a delta value with sign."""
    if value >= 0:
        return f"+{value:.1%}"
    return f"{value:.1%}"


def summarize_flash_counts(player: PlayerMatchImpact) -> dict[str, int]:
    labels = [label for ri in player.round_impacts for flash in ri.flash_events for label in flash.labels]
    return {
        "strong_blinds": sum(1 for label in labels if label == "strong_blind"),
        "full_blinds": sum(1 for label in labels if label == "full_blind"),
        "partial_conversions": sum(
            1 for ri in player.round_impacts for flash in ri.flash_events
            if "partial_blind" in flash.labels and "converted_flash" in flash.labels
        ),
        "forced_turn_kills": sum(1 for label in labels if label == "forced_turn_kill"),
        "no_effect_weak_flashes": sum(
            1 for ri in player.round_impacts for flash in ri.flash_events
            if "weak_flash" in flash.labels and "no_flash_effect" in flash.labels
        ),
        "harmless_team_flashes": sum(1 for label in labels if label == "harmless_team_flash"),
        "effective_team_flashes": sum(1 for label in labels if label == "effective_team_flash"),
        "team_flash_with_conversions": sum(1 for label in labels if label == "team_flash_with_conversion"),
        "severe_team_flashes": sum(1 for label in labels if label == "severe_team_flash"),
    }


def describe_flash_event(event: dict[str, Any]) -> str:
    round_id = event.get("round", "?")
    labels = event.get("labels", [])
    enemies = event.get("affected_enemies") or []
    teammates = event.get("affected_teammates") or []
    converted = event.get("converted_kills") or []

    if "forced_turn_kill" in labels:
        target = enemies[0].get("player", "敌人") if enemies else "敌人"
        return f"第 {round_id} 回合：该闪光没有造成明显白屏，但迫使 {target} 转身躲闪，随后被击杀，判定为 forced_turn_kill。"

    if enemies:
        enemy = enemies[0]
        blind = safe_float(enemy.get("effective_blind"), 0.0)
        phrase = flash_blind_phrase(blind)
        target = enemy.get("player", "敌人")
        if converted:
            return f"第 {round_id} 回合：该闪光造成 {target} {blind:.1f} 秒{phrase}，随后完成击杀转化，判定为 converted_flash。"
        if "no_flash_effect" in labels:
            return f"第 {round_id} 回合：敌人仅受到 {blind:.1f} 秒轻微白屏，且无后续交火收益，判定为 weak_flash/no_flash_effect。"
        return f"第 {round_id} 回合：该闪光造成 {target} {blind:.1f} 秒{phrase}，标签为 {', '.join(labels)}。"

    if teammates:
        teammate = teammates[0]
        blind = safe_float(teammate.get("effective_blind"), 0.0)
        phrase = flash_blind_phrase(blind)
        target = teammate.get("player", "队友")
        if "team_flash_with_conversion" in labels:
            return f"第 {round_id} 回合：队友 {target} 受到 {blind:.1f} 秒{phrase}，但我方 3 秒内完成击杀，判定为 effective_team_flash，不扣分。"
        if "severe_team_flash" in labels:
            return f"第 {round_id} 回合：队友 {target} 被 {blind:.1f} 秒{phrase}且处于高风险状态，判定为 severe_team_flash。"
        if "harmless_team_flash" in labels:
            return f"第 {round_id} 回合：队友 {target} 受到 {blind:.1f} 秒{phrase}，没有影响进攻，判定为 harmless_team_flash。"
        return f"第 {round_id} 回合：队友 {target} 受到 {blind:.1f} 秒{phrase}，标签为 {', '.join(labels)}。"

    return f"第 {round_id} 回合：闪光标签为 {', '.join(labels)}。"


def generate_flash_quality_section(player: PlayerMatchImpact) -> list[str]:
    counts = summarize_flash_counts(player)
    if player.flash_score == 0 and not any(counts.values()):
        return []

    lines = []
    lines.append("### 闪光弹质量")
    lines.append("")
    lines.append(f"- 闪光弹分项: {player.flash_score:.1f}")
    lines.append(f"- 有效强白次数: {counts['strong_blinds']}")
    if counts["full_blinds"] > 0:
        lines.append(f"- 高质量全白次数: {counts['full_blinds']}")
    else:
        lines.append("- 高质量强闪次数: 0")
    lines.append(f"- 半白但有转化次数: {counts['partial_conversions']}")
    lines.append(f"- forced_turn_kill 次数: {counts['forced_turn_kills']}")
    lines.append(f"- 无意义弱闪次数: {counts['no_effect_weak_flashes']}")
    lines.append(f"- harmless_team_flash 次数: {counts['harmless_team_flashes']}")
    lines.append(f"- effective_team_flash 次数: {counts['effective_team_flashes']}")
    lines.append(f"- team_flash_with_conversion 次数: {counts['team_flash_with_conversions']}")
    lines.append(f"- severe_team_flash 次数: {counts['severe_team_flashes']}")
    lines.append("")

    if player.positive_flash_events:
        lines.append("代表性正面闪光：")
        for event in player.positive_flash_events[:2]:
            lines.append(f"- {describe_flash_event(event)}")
        lines.append("")

    if player.negative_flash_events:
        lines.append("代表性负面闪光：")
        for event in player.negative_flash_events[:2]:
            lines.append(f"- {describe_flash_event(event)}")
        lines.append("")

    return lines


def summarize_smoke_counts(player: PlayerMatchImpact) -> dict[str, int]:
    labels = [label for ri in player.round_impacts for smoke in ri.smoke_events for label in smoke.labels]
    return {
        "complete_blocks": sum(1 for label in labels if label == "complete_block_smoke"),
        "partial_blocks": sum(1 for label in labels if label == "partial_block_smoke"),
        "leaky_smokes": sum(1 for label in labels if label == "leaky_smoke"),
        "fatal_leaky_smokes": sum(1 for label in labels if label == "fatal_leaky_smoke"),
        "blocking_teammate_smokes": sum(1 for label in labels if label == "blocking_teammate_smoke"),
        "successful_fake_smokes": sum(1 for label in labels if label == "successful_fake_smoke"),
        "converted_execute_smokes": sum(1 for label in labels if label == "converted_execute_smoke"),
    }


def describe_smoke_event(event: dict[str, Any]) -> str:
    round_id = event.get("round", "?")
    labels = event.get("labels", [])
    reasons = event.get("reasons") or []
    intent = event.get("intent", "unknown_smoke")

    if "fatal_leaky_smoke" in labels:
        return (
            f"第 {round_id} 回合：该烟存在漏缝并制造错误安全感，队友依赖它过点时被缝隙击杀/抽死，"
            "判定为 fatal_leaky_smoke。"
        )
    if "blocking_teammate_smoke" in labels:
        return f"第 {round_id} 回合：该烟挡住己方关键路线或补枪视线，判定为 blocking_teammate_smoke。"
    if "successful_fake_smoke" in labels:
        return f"第 {round_id} 回合：该烟没有直接用于进点，但诱发防守转点并帮助另一侧进攻，判定为 successful_fake_smoke。"
    if "converted_execute_smoke" in labels:
        return f"第 {round_id} 回合：该烟封线质量达标，并通过 gating 后帮助进点/下包，判定为 converted_execute_smoke。"
    if "complete_block_smoke" in labels:
        return f"第 {round_id} 回合：该烟完整封住关键枪线，标签为 {', '.join(labels)}。"
    if "leaky_smoke" in labels:
        return f"第 {round_id} 回合：该烟接近目标但主枪线存在漏缝，标签为 {', '.join(labels)}。"
    if "missed_smoke" in labels:
        return f"第 {round_id} 回合：该烟未封住关键枪线，不能只因落点接近目标而视为好烟。"
    reason_text = reasons[0] if reasons else f"intent={intent}"
    return f"第 {round_id} 回合：{reason_text}，标签为 {', '.join(labels)}。"


def generate_smoke_quality_section(player: PlayerMatchImpact) -> list[str]:
    counts = summarize_smoke_counts(player)
    if player.smoke_score == 0 and not any(counts.values()):
        return []

    lines = []
    lines.append("### 烟雾弹质量")
    lines.append("")
    lines.append(f"- 烟雾弹分项: {player.smoke_score:.1f}")
    lines.append(f"- 高质量封线烟次数: {counts['complete_blocks']}")
    lines.append(f"- partial_block_smoke 次数: {counts['partial_blocks']}")
    lines.append(f"- leaky_smoke 次数: {counts['leaky_smokes']}")
    lines.append(f"- fatal_leaky_smoke 次数: {counts['fatal_leaky_smokes']}")
    lines.append(f"- blocking_teammate_smoke 次数: {counts['blocking_teammate_smokes']}")
    lines.append(f"- successful_fake_smoke 次数: {counts['successful_fake_smokes']}")
    lines.append(f"- converted_execute_smoke 次数: {counts['converted_execute_smokes']}")
    lines.append("")

    if player.positive_smoke_events:
        lines.append("代表性正面烟：")
        for event in player.positive_smoke_events[:2]:
            lines.append(f"- {describe_smoke_event(event)}")
        lines.append("")

    if player.negative_smoke_events:
        lines.append("代表性负面烟：")
        for event in player.negative_smoke_events[:2]:
            lines.append(f"- {describe_smoke_event(event)}")
        lines.append("")

    return lines


def summarize_fire_counts(player: PlayerMatchImpact) -> dict[str, int]:
    labels = [label for ri in player.round_impacts for fire in ri.fire_events for label in fire.labels]
    return {
        "successful_delays": sum(1 for label in labels if label == "successful_delay_fire"),
        "anti_rush_fires": sum(1 for label in labels if label == "anti_rush_fire"),
        "post_plant_fires": sum(1 for label in labels if label == "post_plant_fire"),
        "anti_defuse_fires": sum(1 for label in labels if label == "anti_defuse_fire"),
        "forced_position_fires": sum(1 for label in labels if label == "forced_position_fire"),
        "kill_fires": sum(1 for label in labels if label == "kill_fire"),
        "forced_smoke_extinguishes": sum(1 for label in labels if label == "forced_smoke_extinguish"),
        "harmful_fires": sum(1 for label in labels if label == "harmful_fire"),
    }


def describe_fire_event(event: dict[str, Any]) -> str:
    round_id = event.get("round", "?")
    labels = event.get("labels", [])

    if "harmful_fire" in labels:
        return f"第 {round_id} 回合：该火烧到队友或破坏补枪/进点节奏，判定为 harmful_fire。"
    if "teammate_blocking_fire" in labels:
        return f"第 {round_id} 回合：该火挡住队友进点路线或补枪路径，判定为 teammate_blocking_fire。"
    if "anti_defuse_fire" in labels:
        return f"第 {round_id} 回合：炸弹已下，该火覆盖拆包区域或拆包路径，判定为 anti_defuse_fire。"
    if "post_plant_fire" in labels and "forced_smoke_extinguish" in labels:
        return f"第 {round_id} 回合：炸弹已下，该火迫使 CT 交烟灭火，判定为 post_plant_fire + forced_smoke_extinguish。"
    if "forced_position_fire" in labels:
        return f"第 {round_id} 回合：该火没有只按伤害计分，而是逼敌人离开强位并创造后续机会，判定为 forced_position_fire。"
    if "anti_rush_fire" in labels or "successful_delay_fire" in labels:
        return f"第 {round_id} 回合：该火覆盖关键入口，阻止 rush / 拖延进攻，判定为 anti_rush_fire。"
    if "fake_pressure_fire" in labels:
        return f"第 {round_id} 回合：该火用于制造一侧压力并诱导防守反应，判定为 fake_pressure_fire。"
    if "kill_fire" in labels:
        return f"第 {round_id} 回合：该火直接造成击杀，判定为 kill_fire。"
    if "extinguished_no_value" in labels:
        return f"第 {round_id} 回合：该火很快被烟灭且没有伤害、拖延或资源消耗价值，判定为 extinguished_no_value。"
    return f"第 {round_id} 回合：火瓶/燃烧弹标签为 {', '.join(labels)}。"


def generate_fire_quality_section(player: PlayerMatchImpact) -> list[str]:
    counts = summarize_fire_counts(player)
    if player.fire_score == 0 and not any(counts.values()):
        return []

    lines = []
    lines.append("### 火瓶/燃烧弹质量")
    lines.append("")
    lines.append(f"- 火瓶/燃烧弹分项: {player.fire_score:.1f}")
    lines.append(f"- 高价值拖延火次数: {counts['successful_delays']}")
    lines.append(f"- anti_rush_fire 次数: {counts['anti_rush_fires']}")
    lines.append(f"- post_plant_fire 次数: {counts['post_plant_fires']}")
    lines.append(f"- anti_defuse_fire 次数: {counts['anti_defuse_fires']}")
    lines.append(f"- forced_position_fire 次数: {counts['forced_position_fires']}")
    lines.append(f"- kill_fire 次数: {counts['kill_fires']}")
    lines.append(f"- forced_smoke_extinguish 次数: {counts['forced_smoke_extinguishes']}")
    lines.append(f"- harmful_fire 次数: {counts['harmful_fires']}")
    lines.append("")

    if player.positive_fire_events:
        lines.append("代表性正面火：")
        for event in player.positive_fire_events[:2]:
            lines.append(f"- {describe_fire_event(event)}")
        lines.append("")

    if player.negative_fire_events:
        lines.append("代表性负面火：")
        for event in player.negative_fire_events[:2]:
            lines.append(f"- {describe_fire_event(event)}")
        lines.append("")

    return lines


def summarize_he_counts(player: PlayerMatchImpact) -> dict[str, int]:
    labels = [label for ri in player.round_impacts for he in ri.he_events for label in he.labels]
    return {
        "he_kills": sum(1 for label in labels if label == "kill_he"),
        "anti_smoke_kills": sum(1 for label in labels if label in ("anti_smoke_he_direct_kill", "anti_smoke_route_he_kill")),
        "anti_smoke_routes": sum(1 for label in labels if label == "anti_smoke_route_he"),
        "objective_hes": sum(1 for label in labels if label in ("anti_defuse_he", "anti_plant_he")),
        "anti_rush_hes": sum(1 for label in labels if label == "anti_rush_he"),
        "nade_stack_hits": sum(1 for label in labels if label == "nade_stack_damage"),
        "low_value_hes": sum(1 for label in labels if label == "low_value_he"),
        "harmful_hes": sum(1 for label in labels if label == "harmful_he"),
    }


def describe_he_event(event: dict[str, Any]) -> str:
    round_id = event.get("round", "?")
    labels = event.get("labels", [])
    damage_events = event.get("damage_events") or []
    damage = sum(int(item.get("damage", 0)) for item in damage_events if not item.get("team_damage"))

    if "anti_smoke_he_direct_kill" in labels:
        return f"第 {round_id} 回合：该 HE 炸烟内/烟边目标并造成击杀，判定为 anti_smoke_he_direct_kill。"
    if "anti_smoke_route_he_kill" in labels:
        return f"第 {round_id} 回合：该 HE 针对烟后默认路线的预判雷造成击杀，判定为 anti_smoke_route_he_kill。"
    if "anti_smoke_route_he" in labels:
        return f"第 {round_id} 回合：该 HE 命中烟后默认路线的预判区域，判定为 anti_smoke_route_he。"
    if "anti_smoke_he_direct" in labels:
        return f"第 {round_id} 回合：该 HE 炸烟内/烟边目标并造成伤害，判定为 anti_smoke_he_direct。"
    if "anti_defuse_he" in labels:
        return f"第 {round_id} 回合：该 HE 落在炸弹附近，打断或阻止 CT 拆包，判定为 anti_defuse_he。"
    if "anti_plant_he" in labels:
        return f"第 {round_id} 回合：该 HE 覆盖下包点或下包路线，阻止/延迟下包，判定为 anti_plant_he。"
    if "anti_rush_he" in labels:
        return f"第 {round_id} 回合：该 HE 对 rush/聚集敌人造成群体压力并打乱推进，判定为 anti_rush_he。"
    if "nade_stack_damage" in labels:
        return f"第 {round_id} 回合：该 HE 与队友多雷配合同区命中，判定为 nade_stack_damage。"
    if "harmful_he" in labels:
        return f"第 {round_id} 回合：该 HE 伤害队友并造成严重后果，判定为 harmful_he。"
    if "team_damage_he" in labels:
        return f"第 {round_id} 回合：该 HE 造成队友伤害，判定为 team_damage_he。"
    if "low_value_he" in labels:
        return f"第 {round_id} 回合：该 HE 只造成 {damage} 点伤害，没有阻止行动或形成补杀，判定为 low_value_he。"
    if "kill_he" in labels:
        return f"第 {round_id} 回合：该 HE 直接造成击杀，判定为 kill_he。"
    return f"第 {round_id} 回合：HE 标签为 {', '.join(labels)}。"


def generate_he_quality_section(player: PlayerMatchImpact) -> list[str]:
    counts = summarize_he_counts(player)
    if player.he_score == 0 and not any(counts.values()) and player.he_damage_total == 0:
        return []

    lines = []
    lines.append("### HE 手雷质量")
    lines.append("")
    lines.append(f"- HE 分项: {player.he_score:.1f}")
    lines.append(f"- 总 HE 伤害: {player.he_damage_total}")
    lines.append(f"- HE 击杀数: {counts['he_kills']}")
    lines.append(f"- 高价值炸烟雷: {counts['anti_smoke_kills']}")
    lines.append(f"- 烟后路线预判雷: {counts['anti_smoke_routes']}")
    lines.append(f"- 阻止拆包/下包雷: {counts['objective_hes']}")
    lines.append(f"- 反 rush 雷: {counts['anti_rush_hes']}")
    lines.append(f"- 多雷配合: {counts['nade_stack_hits']}")
    lines.append(f"- 低价值雷: {counts['low_value_hes']}")
    lines.append(f"- 反效果雷: {counts['harmful_hes']}")
    lines.append("")

    if player.positive_he_events:
        lines.append("代表性正面 HE：")
        for event in player.positive_he_events[:2]:
            lines.append(f"- {describe_he_event(event)}")
        lines.append("")

    if player.negative_he_events:
        lines.append("代表性负面 HE：")
        for event in player.negative_he_events[:2]:
            lines.append(f"- {describe_he_event(event)}")
        lines.append("")

    return lines


def describe_highlight_moment(hm: HighlightMoment) -> str:
    """Generate Chinese description for a highlight moment."""
    return f"{hm.description} (影响力: {hm.score:.1f})"


def generate_highlight_section(player: PlayerMatchImpact) -> list[str]:
    """Generate highlight moments section for a player."""
    if not player.highlight_moments:
        return []

    lines = []
    lines.append("### 高光时刻")
    lines.append("")

    # Group by type
    by_type: dict[str, list[HighlightMoment]] = {}
    for hm in player.highlight_moments:
        by_type.setdefault(hm.type, []).append(hm)

    for type_key, moments in by_type.items():
        type_names = {
            "multi_kill": "多杀",
            "quick_multi_kill": "快速连杀",
            "clutch": "残局胜利",
            "hard_duel": "高难度对枪",
            "he_multi_hit": "手雷多杀",
            "impactful_opening_kill": "关键首杀",
        }
        type_name = type_names.get(type_key, type_key)
        lines.append(f"**{type_name}** ({len(moments)}次)")
        for hm in moments[:3]:  # Show top 3 per type
            lines.append(f"- {describe_highlight_moment(hm)}")
        lines.append("")

    return lines


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

    lines.extend(generate_highlight_section(player))

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

    lines.extend(generate_flash_quality_section(player))
    lines.extend(generate_smoke_quality_section(player))
    lines.extend(generate_fire_quality_section(player))
    lines.extend(generate_he_quality_section(player))
    lines.extend(generate_tactical_section(player))

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


def generate_tactical_section(player: PlayerMatchImpact) -> list[str]:
    """Generate the per-player tactical summary section."""
    has_tactical_score = bool(player.map_control_score or player.tactical_discipline_score)
    has_tactical_events = bool(player.positive_tactical_events or player.negative_tactical_events)
    if not has_tactical_score and not has_tactical_events:
        return []

    lines = [
        "### 地图战术表现 / 鍦板浘鎴樻湳琛ㄧ幇",
        "",
        f"- 地图控制分: {player.map_control_score:.1f}",
        f"- 战术纪律分: {player.tactical_discipline_score:.1f}",
        f"- 关键区域孤立死亡: {player.key_area_deaths}",
        f"- 有效进点牺牲: {player.valid_entry_sacrifices}",
        f"- 下包后纪律错误: {player.post_plant_errors}",
        f"- 回防错误: {player.retake_errors}",
    ]

    positive = player.positive_tactical_events[:3]
    negative = player.negative_tactical_events[:3]
    if positive:
        lines.extend(["", "代表性正面战术事件:"])
        for event in positive:
            lines.append(_format_tactical_event_line(event))
    if negative:
        lines.extend(["", "代表性负面战术事件:"])
        for event in negative:
            lines.append(_format_tactical_event_line(event))
    return lines


def _format_tactical_event_line(event: dict[str, Any]) -> str:
    round_id = event.get("round") or event.get("round_id")
    tick = event.get("tick") or event.get("start_tick")
    label = event.get("label", "tactical_event")
    reason = event.get("reason", "")
    area = event.get("area_cn") or event.get("area")
    prefix = f"- 第 {round_id} 回合"
    if tick is not None:
        prefix += f" {safe_float(tick):.1f}s"
    if area:
        prefix += f" {area}"
    return f"{prefix}: {label}，{reason}".rstrip("，")


def report_to_json(report: ImpactReport) -> dict[str, Any]:
    """Convert ImpactReport to JSON-serializable dict."""
    result = {
        "match_info": report.match_info,
        "map_name": report.map_name,
        "total_rounds": report.total_rounds,
        "match_winner": report.match_winner,
        "confidence": report.confidence,
        "warnings": report.warnings,
        "utility_diagnostics": report.utility_diagnostics,
        "players": [],
    }

    # Compute report-level diagnostics
    model_impact_clip_count_min = sum(
        1 for p in report.player_impacts if p.model_impact_score_raw < -50
    )
    model_impact_clip_count_max = sum(
        1 for p in report.player_impacts if p.model_impact_score_raw > 50
    )
    rating_zero_count = sum(1 for p in report.player_impacts if p.rating_0_100 <= 0.0)
    rating_hundred_count = sum(1 for p in report.player_impacts if p.rating_0_100 >= 100.0)

    alignment_stats = [
        ri.alignment_diagnostics
        for p in report.player_impacts
        for ri in p.round_impacts
        if ri.alignment_diagnostics
    ]
    exact_match_rate = (
        sum(safe_float(stat.get("exact_match_rate"), 0.0) for stat in alignment_stats) / len(alignment_stats)
        if alignment_stats else 0.0
    )
    fallback_rate = (
        sum(safe_float(stat.get("fallback_rate"), 0.0) for stat in alignment_stats) / len(alignment_stats)
        if alignment_stats else 0.0
    )
    avg_time_error = (
        sum(safe_float(stat.get("avg_time_error"), 0.0) for stat in alignment_stats) / len(alignment_stats)
        if alignment_stats else 0.0
    )

    result["diagnostics"] = {
        "model_impact_clip_count_min": model_impact_clip_count_min,
        "model_impact_clip_count_max": model_impact_clip_count_max,
        "rating_zero_count": rating_zero_count,
        "rating_hundred_count": rating_hundred_count,
        "exact_match_rate": exact_match_rate,
        "fallback_rate": fallback_rate,
        "avg_time_error": avg_time_error,
    }

    total_players = len(report.player_impacts)
    if total_players > 0 and (model_impact_clip_count_min + model_impact_clip_count_max) / total_players > 0.3:
        if "model_impact_score appears heavily clipped; rating calibration may need adjustment." not in report.warnings:
            result["warnings"].append("model_impact_score appears heavily clipped; rating calibration may need adjustment.")

    for player in report.player_impacts:
        player_data = {
            "player_name": player.player_name,
            "team": player.team,
            "rating_0_100": round(player.rating_0_100, 1),
            "rating_components": player.rating_components,
            "model_impact_score": round(player.model_impact_score, 2),
            "rule_quality_score": round(player.rule_quality_score, 2),
            "flash_score": round(player.flash_score, 2),
            "smoke_score": round(player.smoke_score, 2),
            "fire_score": round(player.fire_score, 2),
            "he_score": round(player.he_score, 2),
            "utility_impact": round(sum(ri.utility_impact for ri in player.round_impacts), 2),
            "utility_event_count": sum(
                len(ri.flash_events) + len(ri.smoke_events) + len(ri.fire_events) + len(ri.he_events)
                for ri in player.round_impacts
            ),
            "map_control_score": round(player.map_control_score, 2),
            "tactical_discipline_score": round(player.tactical_discipline_score, 2),
            "key_area_deaths": player.key_area_deaths,
            "post_plant_errors": player.post_plant_errors,
            "valid_entry_sacrifices": player.valid_entry_sacrifices,
            "retake_errors": player.retake_errors,
            "model_impact_score_raw": round(player.model_impact_score_raw, 2),
            "model_impact_score_clipped": round(player.model_impact_score_clipped, 2),
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
            "utility_stats": {
                "flash": {
                    "score": round(player.flash_score, 2),
                    "effective_flashes": player.effective_flashes,
                    "converted_flashes": player.converted_flashes,
                    "forced_turn_kills": player.forced_turn_kills,
                    "severe_team_flashes": player.severe_team_flashes,
                    "harmless_team_flashes": player.harmless_team_flashes,
                    "team_flash_with_conversions": player.team_flash_with_conversions,
                },
                "smoke": {
                    "score": round(player.smoke_score, 2),
                    "successful_fake_smokes": player.successful_fake_smokes,
                    "fatal_leaky_smokes": player.fatal_leaky_smokes,
                    "blocking_teammate_smokes": player.blocking_teammate_smokes,
                    "converted_execute_smokes": player.converted_execute_smokes,
                },
                "fire": {
                    "score": round(player.fire_score, 2),
                    "anti_rush_fires": player.anti_rush_fires,
                    "post_plant_fires": player.post_plant_fires,
                    "anti_defuse_fires": player.anti_defuse_fires,
                    "forced_position_fires": player.forced_position_fires,
                    "kill_fires": player.kill_fires,
                    "harmful_fires": player.harmful_fires,
                    "forced_smoke_extinguishes": player.forced_smoke_extinguishes,
                },
                "he": {
                    "score": round(player.he_score, 2),
                    "damage_total": player.he_damage_total,
                    "kills": player.he_kills,
                    "anti_smoke_he_kills": player.anti_smoke_he_kills,
                    "anti_smoke_route_hes": player.anti_smoke_route_hes,
                    "anti_defuse_hes": player.anti_defuse_hes,
                    "anti_plant_hes": player.anti_plant_hes,
                    "anti_rush_hes": player.anti_rush_hes,
                    "nade_stack_hits": player.nade_stack_hits,
                    "low_value_hes": player.low_value_hes,
                    "harmful_hes": player.harmful_hes,
                },
            },
            "flash_events": [
                {
                    "round": event.get("round"),
                    "tick": round(safe_float(event.get("tick")), 2),
                    "impact": round(safe_float(event.get("impact")), 2),
                    "labels": event.get("labels", []),
                    "affected_enemies": event.get("affected_enemies", []),
                    "affected_teammates": event.get("affected_teammates", []),
                    "converted_kills": event.get("converted_kills", []),
                    "reasons": event.get("reasons", []),
                }
                for event in (player.positive_flash_events + player.negative_flash_events)[:10]
            ],
            "smoke_events": [
                {
                    "round": event.get("round"),
                    "tick": round(safe_float(event.get("tick")), 2),
                    "impact": round(safe_float(event.get("impact")), 2),
                    "intent": event.get("intent"),
                    "labels": event.get("labels", []),
                    "reasons": event.get("reasons", []),
                    "target_matched": bool(event.get("target_matched", False)),
                    "block_score": round(safe_float(event.get("block_score")), 2),
                    "leak_risk": event.get("leak_risk"),
                    "conversion_score": round(safe_float(event.get("conversion_score")), 2),
                    "teammate_dependency": round(safe_float(event.get("teammate_dependency")), 2),
                    "enemy_exploitation": round(safe_float(event.get("enemy_exploitation")), 2),
                }
                for event in (player.positive_smoke_events + player.negative_smoke_events)[:10]
            ],
            "fire_events": [
                {
                    "round": event.get("round"),
                    "tick": round(safe_float(event.get("tick")), 2),
                    "impact": round(safe_float(event.get("impact")), 2),
                    "intent": event.get("intent"),
                    "fire_type": event.get("fire_type"),
                    "labels": event.get("labels", []),
                    "reasons": event.get("reasons", []),
                    "damage_events": event.get("damage_events", []),
                    "forced_movements": event.get("forced_movements", []),
                    "conversions": event.get("conversions", []),
                }
                for event in (player.positive_fire_events + player.negative_fire_events)[:10]
            ],
            "he_events": [
                {
                    "round": event.get("round"),
                    "tick": round(safe_float(event.get("tick")), 2),
                    "impact": round(safe_float(event.get("impact")), 2),
                    "labels": event.get("labels", []),
                    "damage_events": event.get("damage_events", []),
                    "kill_events": event.get("kill_events", []),
                    "smoke_context": event.get("smoke_context"),
                    "objective_context": event.get("objective_context"),
                    "reasons": event.get("reasons", []),
                }
                for event in (player.positive_he_events + player.negative_he_events)[:10]
            ],
            "tactical_events": [
                {
                    "round": event.get("round"),
                    "tick": round(safe_float(event.get("tick")), 2),
                    "phase": event.get("phase"),
                    "area": event.get("area"),
                    "area_cn": event.get("area_cn"),
                    "impact": round(safe_float(event.get("impact")), 2),
                    "label": event.get("label"),
                    "reason": event.get("reason", ""),
                }
                for event in (player.positive_tactical_events + player.negative_tactical_events)[:10]
            ],
            "highlight_moments": [
                {
                    "round": hm.round_id,
                    "tick": round(hm.tick, 2),
                    "type": hm.type,
                    "subtype": hm.subtype,
                    "description": hm.description,
                    "score": round(hm.score, 2),
                    "details": hm.details,
                }
                for hm in player.highlight_moments
            ],
            "positive_events": player.positive_kill_events[:5],
            "negative_events": player.negative_death_events[:5],
            "diagnostics": {
                "avg_round_impact": round(player.avg_round_impact, 2),
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

    return result
