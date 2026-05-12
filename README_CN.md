<p align="center">
  <img src="assets/logo.svg" width="120" height="120" alt="cs-net-logo">
</p>

<h1 align="center">CS-NET</h1>

<p align="center">
  <strong>Counter-Strike 2 比赛分析框架</strong>
</p>

<p align="center">
  <a href="README.md">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Framework-PyTorch-ee4c2c.svg" alt="PyTorch">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
</p>

## 快速导航

- [项目概览](#-项目概览)
- [核心组件](#-核心组件)
- [预测任务](#-预测任务)
- [Impact Engine](#-impact-engine)
- [快速开始](#-快速开始)
- [Web 应用](#-web-应用)
- [项目结构](#-项目结构)
- [贡献指南](#-贡献指南)
- [致谢](#-致谢)

---

## 📌 项目概览

CS-NET 是一个综合性的 **Counter-Strike 2 比赛分析框架**，结合了深度学习预测和规则式战术分析。它解析 demo 文件，提取游戏状态，并通过多个组件提供可操作的洞察。

### 核心能力

1. **深度学习预测**：基于 Transformer 的模型进行胜率、存活率和击杀预测
2. **影响力分析**：评估玩家对回合结果的贡献
3. **战术分析**：地图特定的战术评分和事件检测
4. **交互式可视化**：基于 Web 的 demo 查看器和实时预测展示

---

## 🧩 核心组件

### 1. CS-NET 模型

基于 Transformer 的深度学习模型，同时处理游戏状态序列来预测多个结果。

### 2. Impact Engine

高级玩家影响力分析系统，结合模型预测和规则评分来评估每个玩家在回合中的真实贡献。

### 3. 地图知识库

战术分析的地图特定配置，包括区域、路线、枪线和道具目标。

### 4. Web 应用

交互式 demo 分析工具，包含 2D 雷达可视化、时间线分析和 LLM 驱动的比赛总结。

---

## 🎯 预测任务

| 任务 | 说明 | 输出 |
|------|------|------|
| **胜率预测** | 当前队伍赢下回合的概率 | 标量 [0, 1] |
| **存活预测** | 每个玩家未来 5 秒内存活概率 | 10 个概率值 |
| **下一击杀预测** | 谁最可能获得下一次击杀 | 11 类概率分布 |
| **下一阵亡预测** | 谁最可能成为下一个阵亡者 | 11 类概率分布 |
| **决斗预测** | 任意 CT-T 玩家对的 1v1 胜率 | 5×5 概率矩阵 |

---

## ⚡ Impact Engine

Impact Engine 通过结合模型预测和战术洞察提供全面的玩家表现分析。

### 核心功能

- **RWI（回合胜率影响）**：衡量每个行为对队伍胜率的影响
- **战术评分**：地图特定的战术事件检测（中路控制、进点执行、回防等）
- **道具分析**：烟雾/闪光/燃烧弹/手雷的有效性评估
- **纪律追踪**：下包后站位和回防纪律

### 检测的战术事件

| 类别 | 事件 |
|------|------|
| **地图控制** | `mid_control_success`, `mid_control_hold`, `key_area_isolated_death` |
| **进点执行** | `valid_entry_sacrifice`, `failed_entry_no_trade` |
| **下包后** | `post_plant_crossfire_hold`, `post_plant_discipline_error` |
| **回防** | `retake_grouped`, `retake_solo_feed` |
| **残局** | `save_correct`, `save_throw`, `exit_frag_low_impact` |

### 支持的地图

- de_mirage（完整战术支持）
- de_ancient, de_anubis, de_dust2, de_inferno, de_nuke, de_overpass, de_train, de_vertigo

---

## 🚀 快速开始

### 1. 配置环境

```bash
conda create -n cs-net python=3.10
conda activate cs-net
pip install -r requirements.txt
```

### 2. 下载预训练模型

```bash
python -m scripts.download_model
```

模型将下载到 `./cs-net-models/`。

### 3. 分析 Demo

#### 选项 A：完整流程（Demo → 分析 → 报告）

```bash
# 步骤 1：处理 demo 提取游戏状态
python -m demo_analysis.get_round_win_rate \
  --demo path/to/your/demo.dem \
  --model-root cs-net-models/ \
  --output output/analysis.json

# 步骤 2：生成影响力报告
python -m demo_analysis.impact_engine.cli \
  --analysis-json output/analysis.json \
  --out output/impact_report.md \
  --json-out output/impact_report.json
```

#### 选项 B：使用现有分析结果快速测试

```bash
python -m demo_analysis.impact_engine.cli \
  --analysis-json output/analysis.json \
  --out output/report.md \
  --json-out output/report.json
```

### 4. 运行测试

```bash
python -m pytest demo_analysis/impact_engine/tests -q
```

---

## 🌐 Web 应用

### 启动 Web 应用

```bash
python -m demo_analysis.web_app
```

在浏览器中打开 `http://127.0.0.1:7860`。

### 功能特性

- **交互式 Demo 分析**：上传和分析 .dem 文件
- **实时 2D 雷达**：实时玩家位置和游戏状态
- **时间线分析**：回合胜率曲线和击杀标记
- **玩家指标**：存活概率、决斗胜率、影响力评分
- **LLM 总结**：AI 生成的比赛分析报告
- **双语支持**：中英文界面和报告

---

## 📁 项目结构

```
cs-mvp/
├── assets/                    # 静态资源（Logo、图片）
├── config/                    # 配置文件
│   └── callouts/              # 地图特定配置
├── data/                      # 数据处理脚本
├── demo_analysis/             # Demo 分析管道
│   ├── impact_engine/         # 影响力分析引擎
│   │   ├── tests/             # 单元测试
│   │   ├── cli.py             # 命令行接口
│   │   ├── engine.py          # 核心引擎
│   │   ├── scoring.py         # 评分计算
│   │   ├── tactical_scoring.py # 战术事件评分
│   │   ├── map_tactics.py     # 地图区域查询
│   │   └── report.py          # 报告生成
│   ├── static/                # Web 应用静态文件
│   ├── templates/             # HTML 模板
│   └── web_app.py            # Flask Web 服务器
├── demoparser_utils/          # Demo 解析工具
├── models/                    # 模型实现
├── output/                    # 生成的报告
├── scripts/                   # 实用脚本
└── tests/                     # 额外测试
```

### 关键文件

| 文件 | 说明 |
|------|------|
| [`demo_analysis/impact_engine/engine.py`](demo_analysis/impact_engine/engine.py) | 核心影响力计算引擎 |
| [`demo_analysis/impact_engine/scoring.py`](demo_analysis/impact_engine/scoring.py) | 玩家评分逻辑 |
| [`demo_analysis/impact_engine/tactical_scoring.py`](demo_analysis/impact_engine/tactical_scoring.py) | 战术事件检测和评分 |
| [`demo_analysis/impact_engine/map_tactics.py`](demo_analysis/impact_engine/map_tactics.py) | 地图区域查询和工具 |
| [`demo_analysis/impact_engine/report.py`](demo_analysis/impact_engine/report.py) | Markdown 报告生成 |
| [`config/callouts/de_mirage.yaml`](config/callouts/de_mirage.yaml) | Mirage 地图配置 |

---

## 📊 输出格式

### Markdown 报告

包含详细分析，包括：
- 玩家评分（0-100 分）
- RWI（回合胜率影响）细分
- 地图控制表现
- 战术事件时间线
- 死亡分析和纪律指标
- 道具使用有效性
- 改进建议

### JSON 输出

结构化数据，便于程序化访问：
- 每回合玩家影响力
- 带时间戳的战术事件
- 模型预测
- 道具使用统计

---

## 🤝 贡献指南

### 开发流程

1. Fork 仓库
2. 创建功能分支（`git checkout -b feature/your-feature`）
3. 进行修改
4. 运行测试（`python -m pytest demo_analysis/impact_engine/tests`）
5. 提交并推送
6. 创建 Pull Request

### 代码规范

- 遵循 PEP 8 代码规范
- 使用类型提示
- 为公共函数添加文档字符串
- 为新功能添加单元测试

---

## 🙏 致谢

### 第三方组件

- **2D Demo 查看器**：基于 [sparkoo/csgo-2d-demo-viewer](https://github.com/sparkoo/csgo-2d-demo-viewer) 的修改集成，MIT 许可证
- **Demo 解析**：使用 Valve 的 demo 解析工具
- **预训练模型**：托管在 Hugging Face

### 参考资料

- CS-NET 模型：[Hugging Face 仓库](https://huggingface.co/gary2oos/CS-Net-V3)
- 原始 CS-NET 论文：即将发布

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## ⭐ 星标历史

<a href="https://www.star-history.com/?repos=Gary2005%2Fcs-net&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Gary2005/cs-net&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Gary2005/cs-net&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=Gary2005/cs-net&type=date&legend=top-left" />
 </picture>
</a>

---

## 📞 联系方式

如有问题或需要支持，请在 GitHub 仓库中提交 issue。
