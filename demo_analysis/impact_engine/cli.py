"""Command-line interface for the CS2 Impact Engine."""

import argparse
import json
import sys
from pathlib import Path

from demo_analysis.high_level_analysis import build_dashboard_payload

from .engine import ImpactEngine
from .report import generate_match_report, report_to_json


def main():
    parser = argparse.ArgumentParser(
        description="CS2 个人回合影响力评分引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python -m demo_analysis.impact_engine.cli --analysis-json output/analysis.json --out report.md
  python -m demo_analysis.impact_engine.cli --analysis-json output/analysis.json --json-out report.json
  python -m demo_analysis.impact_engine.cli -i output/analysis.json -o report.md -j report.json
        """
    )

    parser.add_argument(
        "--analysis-json", "-i",
        required=True,
        help="CS-NET 分析结果 JSON 文件路径"
    )
    parser.add_argument(
        "--out", "-o",
        help="Markdown 报告输出路径"
    )
    parser.add_argument(
        "--json-out", "-j",
        help="JSON 结构化评分文件输出路径"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="静默模式，不输出详细信息"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出模式"
    )

    args = parser.parse_args()

    input_path = Path(args.analysis_json)
    if not input_path.exists():
        print(f"错误: 文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"正在加载分析数据: {input_path}")

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_results = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print("正在构建 Dashboard 数据...")

    try:
        dashboard_payload = build_dashboard_payload(raw_results)
    except Exception as e:
        print(f"错误: 数据构建失败: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    if not args.quiet:
        print("正在分析回合影响力...")

    engine = ImpactEngine(dashboard_payload)
    report = engine.analyze()

    if args.json_out:
        json_output = report_to_json(report)
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(f"JSON 输出已保存: {json_path}")

    if args.out:
        md_output = generate_match_report(report)
        md_path = Path(args.out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_output)
        if not args.quiet:
            print(f"Markdown 报告已保存: {md_path}")

    if not args.quiet:
        print("\n" + "=" * 50)
        print("分析完成!")
        print("=" * 50)
        print(f"地图: {report.map_name}")
        print(f"回合数: {report.total_rounds}")
        print(f"比分: {report.match_info.get('team1_round_wins', '?')} - {report.match_info.get('team2_round_wins', '?')}")
        print(f"胜方: {report.match_winner}")
        print()

        print("选手评分 (CT方):")
        ct_players = [p for p in report.player_impacts if p.team == "team1"]
        ct_players.sort(key=lambda p: p.rating_0_100, reverse=True)
        for player in ct_players:
            kills, deaths, _ = player.kda
            print(f"  {player.player_name}: {player.rating_0_100:.0f}/100 (K/D: {kills}/{deaths})")

        print("\n选手评分 (T方):")
        t_players = [p for p in report.player_impacts if p.team == "team2"]
        t_players.sort(key=lambda p: p.rating_0_100, reverse=True)
        for player in t_players:
            kills, deaths, _ = player.kda
            print(f"  {player.player_name}: {player.rating_0_100:.0f}/100 (K/D: {kills}/{deaths})")

        if report.warnings:
            print("\n注意事项:")
            for warning in report.warnings:
                print(f"  - {warning}")

    if args.verbose and report.warnings:
        for warning in report.warnings:
            print(f"[警告] {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()
