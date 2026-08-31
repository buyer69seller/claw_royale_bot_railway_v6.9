# 🦀 Claw Royale Bot v6.1 - Hybrid AI Auto-Pilot

[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![Railway](https://img.shields.io/badge/deploy-Railway-0B0D0E.svg)](https://railway.app)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Bot otomatis untuk Claw Royale dengan **Hybrid AI** + **Reinforcement Learning** + **Scan & Clear** strategy.

---

## ✨ **Fitur**

### 🧠 **Hybrid AI Engine**
- AI Auto-Pilot (ML-based)
- Competitive v7 (Heuristic)
- Reinforcement Learning (Q-Learning)
- Threat & Risk Assessment

### 🎮 **Game Features**
- Auto-join free/paid rooms
- Auto-rejoin after timeout (90s)
- Auto-restart after death
- Ruin farming with alert management
- Guardian avoidance
- Item tracking & validation
- Auto-use healing items
- Auto-equip best items
- Pack synergy optimization
- Relic selection

### 📊 **Monitoring**
- Health check (`/health`)
- Metrics (`/metrics`)
- Stats (`/stats`)
- Dashboard (`/dashboard`)

---

## 🚀 **Quick Start**

```bash
# Clone
git clone https://github.com/username/claw-royale-bot.git
cd claw-royale-bot

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config/.env.example .env

# Edit .env dengan CLAW_API_KEY
nano .env

# Run
python -m src.main

# Monitor
curl http://localhost:8080/health