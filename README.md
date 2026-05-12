<p align="center">
  <img src="assets/logo.svg" width="120" height="120" alt="cs-net-logo">
</p>

<h1 align="center">CS-NET</h1>

<p align="center">
  <strong>Counter-Strike 2 Match Analysis Framework</strong>
</p>

<p align="center">
  <a href="README_CN.md">中文文档</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Framework-PyTorch-ee4c2c.svg" alt="PyTorch">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
</p>

## Quick Links

- [Project Overview](#-project-overview)
- [Core Components](#-core-components)
- [Prediction Tasks](#-prediction-tasks)
- [Impact Engine](#-impact-engine)
- [Quick Start](#-quick-start)
- [Web App](#-web-app)
- [Project Structure](#-project-structure)
- [Contributing](#-contributing)
- [Acknowledgements](#-acknowledgements)

---

## 📌 Project Overview

CS-NET is a comprehensive **Counter-Strike 2 match analysis framework** that combines deep learning-based predictions with rule-based tactical analysis. It parses demo files, extracts game states, and provides actionable insights through multiple components.

### Key Capabilities

1. **Deep Learning Predictions**: Transformer-based models for win rate, survival, and kill predictions
2. **Impact Analysis**: Evaluate player contributions and impact on round outcomes
3. **Tactical Analysis**: Map-specific tactical scoring and event detection
4. **Interactive Visualization**: Web-based demo viewer with real-time predictions

---

## 🧩 Core Components

### 1. CS-NET Model

A Transformer-based deep learning model that processes game state sequences to predict multiple outcomes simultaneously.

### 2. Impact Engine

Advanced player impact analysis system that evaluates each player's real influence in rounds, combining model-based and rule-based scoring.

### 3. Map Knowledge Base

Map-specific configurations for tactical analysis, including areas, routes, sightlines, and utility targets.

### 4. Web Application

Interactive demo analysis tool with 2D radar visualization, timeline analysis, and LLM-powered match summaries.

---

## 🎯 Prediction Tasks

| Task | Description | Output |
|------|-------------|--------|
| **Win Rate** | Probability of the current team winning the round | Scalar [0, 1] |
| **Alive** | Per-player survival probability for the next 5 seconds | 10 probabilities |
| **Next Kill** | Probability distribution for who gets the next kill | 11-class distribution |
| **Next Death** | Probability distribution for who dies next | 11-class distribution |
| **Duel** | 1v1 win probability for any CT-T player pair | 5×5 probability matrix |

---

## ⚡ Impact Engine

The Impact Engine provides comprehensive player performance analysis by combining model predictions with tactical insights.

### Key Features

- **Round Win Impact (RWI)**: Measures action impact on team win probability
- **Tactical Scoring**: Map-specific tactical event detection (mid control, site execution, retake, etc.)
- **Utility Analysis**: Smoke/flash/fire/HE effectiveness evaluation
- **Discipline Tracking**: Post-plant positioning and retake discipline

### Tactical Events Detected

| Category | Events |
|----------|--------|
| **Map Control** | `mid_control_success`, `mid_control_hold`, `key_area_isolated_death` |
| **Site Execution** | `valid_entry_sacrifice`, `failed_entry_no_trade` |
| **Post-Plant** | `post_plant_crossfire_hold`, `post_plant_discipline_error` |
| **Retake** | `retake_grouped`, `retake_solo_feed` |
| **Endgame** | `save_correct`, `save_throw`, `exit_frag_low_impact` |

### Supported Maps

- de_mirage (full tactical support)
- de_ancient, de_anubis, de_dust2, de_inferno, de_nuke, de_overpass, de_train, de_vertigo

---

## 🚀 Quick Start

### 1. Setup Environment

```bash
conda create -n cs-net python=3.10
conda activate cs-net
pip install -r requirements.txt
```

### 2. Download Pre-trained Models

```bash
python -m scripts.download_model
```

Models are downloaded to `./cs-net-models/`.

### 3. Analyze a Demo

#### Option A: Full Pipeline (Demo → Analysis → Report)

```bash
# Step 1: Process demo to extract game states
python -m demo_analysis.get_round_win_rate \
  --demo path/to/your/demo.dem \
  --model-root cs-net-models/ \
  --output output/analysis.json

# Step 2: Generate impact report
python -m demo_analysis.impact_engine.cli \
  --analysis-json output/analysis.json \
  --out output/impact_report.md \
  --json-out output/impact_report.json
```

#### Option B: Quick Test with Existing Analysis

```bash
python -m demo_analysis.impact_engine.cli \
  --analysis-json output/analysis.json \
  --out output/report.md \
  --json-out output/report.json
```

### 4. Run Tests

```bash
python -m pytest demo_analysis/impact_engine/tests -q
```

---

## 🌐 Web App

### Start the Web Application

```bash
python -m demo_analysis.web_app
```

Open `http://127.0.0.1:7860` in your browser.

### Features

- **Interactive Demo Analysis**: Upload and analyze .dem files
- **Live 2D Radar**: Real-time player positions and game state
- **Timeline Analysis**: Round-by-round win rate curve with kill markers
- **Player Metrics**: Survival probability, duel win rates, impact scores
- **LLM Summary**: AI-generated match analysis reports
- **Bilingual Support**: Chinese/English UI and reports

---

## 📁 Project Structure

```
cs-mvp/
├── assets/                    # Static assets (logo, images)
├── config/                    # Configuration files
│   └── callouts/              # Map-specific configurations
├── data/                      # Data processing scripts
├── demo_analysis/             # Demo analysis pipeline
│   ├── impact_engine/         # Impact analysis engine
│   │   ├── tests/             # Unit tests
│   │   ├── cli.py             # Command-line interface
│   │   ├── engine.py          # Core engine
│   │   ├── scoring.py         # Scoring calculations
│   │   ├── tactical_scoring.py # Tactical event scoring
│   │   ├── map_tactics.py     # Map area lookup
│   │   └── report.py          # Report generation
│   ├── static/                # Web app static files
│   ├── templates/             # HTML templates
│   └── web_app.py            # Flask web server
├── demoparser_utils/          # Demo parsing utilities
├── models/                    # Model implementations
├── output/                    # Generated reports
├── scripts/                   # Utility scripts
└── tests/                     # Additional tests
```

### Key Files

| File | Description |
|------|-------------|
| [`demo_analysis/impact_engine/engine.py`](demo_analysis/impact_engine/engine.py) | Core impact calculation engine |
| [`demo_analysis/impact_engine/scoring.py`](demo_analysis/impact_engine/scoring.py) | Player scoring logic |
| [`demo_analysis/impact_engine/tactical_scoring.py`](demo_analysis/impact_engine/tactical_scoring.py) | Tactical event detection and scoring |
| [`demo_analysis/impact_engine/map_tactics.py`](demo_analysis/impact_engine/map_tactics.py) | Map area lookup and utilities |
| [`demo_analysis/impact_engine/report.py`](demo_analysis/impact_engine/report.py) | Markdown report generation |
| [`config/callouts/de_mirage.yaml`](config/callouts/de_mirage.yaml) | Mirage map configuration |

---

## 📊 Output Formats

### Markdown Report

Contains detailed analysis including:
- Player ratings (0-100 scale)
- Round Win Impact (RWI) breakdown
- Map control performance
- Tactical event timeline
- Death analysis and discipline metrics
- Utility usage effectiveness
- Improvement suggestions

### JSON Output

Structured data for programmatic access:
- Player impacts per round
- Tactical events with timestamps
- Model predictions
- Utility usage statistics

---

## 🤝 Contributing

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests (`python -m pytest demo_analysis/impact_engine/tests`)
5. Commit and push
6. Create a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use type hints for function signatures
- Add docstrings for public functions
- Include unit tests for new features

---

## 🙏 Acknowledgements

### Original CS-NET Project

This project is built upon and extends the original **CS-NET** framework developed by Gary2005 and contributors:

- **Original Repository**: [Gary2005/cs-net](https://github.com/Gary2005/cs-net)
- **Pre-trained Models**: [Hugging Face Repository](https://huggingface.co/gary2oos/CS-Net-V3)
- **Original Paper**: CS-NET: A Transformer-based Framework for Counter-Strike Match Analysis (Under Review)

### Third-Party Components

- **2D Demo Viewer**: Modified integration of [sparkoo/csgo-2d-demo-viewer](https://github.com/sparkoo/csgo-2d-demo-viewer) under MIT License
- **Demo Parsing**: Uses Valve's demo parsing utilities
- **Pre-trained Models**: Hosted on Hugging Face

### References

If you use this project in your research or work, please cite the original CS-NET work:

```bibtex
@misc{csnet2024,
  author = {Gary2005 and contributors},
  title = {CS-NET: A Transformer-based Framework for Counter-Strike Match Analysis},
  year = {2024},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/Gary2005/cs-net}},
}
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⭐ Star History

<a href="https://www.star-history.com/?repos=Gary2005%2Fcs-net&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Gary2005/cs-net&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Gary2005/cs-net&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=Gary2005/cs-net&type=date&legend=top-left" />
 </picture>
</a>

---

## 📞 Contact

For questions or support, please open an issue in the GitHub repository.
