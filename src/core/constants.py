# src/core/constants.py
"""Konstanta global untuk bot Claw Royale"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any

# Base directory
BASE_DIR = Path(__file__).parent.parent.parent

# Runtime directories
CACHE_DIR = os.getenv("CACHE_DIR", str(BASE_DIR / "runtime_cache"))
LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))
KNOWLEDGE_PATH = os.getenv("KNOWLEDGE_PATH", str(BASE_DIR / "knowledge.json"))

def ensure_directories():
    """Buat semua direktori yang dibutuhkan"""
    for d in [CACHE_DIR, LOG_DIR]:
        Path(d).mkdir(parents=True, exist_ok=True)

# API Endpoints
BASE_API = "https://cdn.clawroyale.ai/api"
JOIN_WS = "wss://cdn.clawroyale.ai/ws/join"
AGENT_WS = "wss://cdn.clawroyale.ai/ws/agent"
API_VERSION_URL = f"{BASE_API}/version"

# Default values
DEFAULT_ENTRY_TYPE = "free"
DEFAULT_PREFERRED_MODE = "offchain"
DEFAULT_ACTION_INTERVAL = 0.25

# ACTION_INTERVAL_SECONDS
ACTION_INTERVAL_SECONDS = float(os.getenv("ACTION_INTERVAL_SECONDS", str(DEFAULT_ACTION_INTERVAL)))

# Retry configuration
MIN_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0
RETRY_BACKOFF_MULTIPLIER = 2.0
RECONNECT_RESET_THRESHOLD = 10.0

# Strategy scoring - Survival-first
SCORE_HEAL_BASE = 900
SCORE_HEAL_HP_BONUS = 700
SCORE_ATTACK_BASE = 550
SCORE_ATTACK_HP_BONUS = 600
SCORE_GUARDIAN_PENALTY = 300
SCORE_ATTACK_KILL_BONUS = 150
SCORE_SURVIVAL_BONUS = 200

# Loot scoring
SCORE_LOOT_BASE = 300
SCORE_LOOT_BONUS = 250
SCORE_INTERACT_BASE = 520
SCORE_EXPLORE_BASE = 380
SCORE_MOVE_BASE = 250

# Cave escape priority
SCORE_CAVE_EXIT = 1000

# Document cache paths
DOCS_TO_CACHE = [
    "/skill.md",
    "/openapi.yaml", 
    "/references/actions.md",
    "/references/game-loop.md",
    "/references/combat-items.md",
    "/references/game-systems.md",
    "/references/api-summary.md",
    "/references/errors.md",
    "/references/changelog.md",
    "/references/economy.md",
    "/references/free-games.md",
    "/references/paid-games.md",
]

# AI Constants
AI_LEARNING_RATE = 0.1
AI_CONFIDENCE_THRESHOLD = 0.6
AI_RISK_THRESHOLD = 0.7
AI_STRATEGY_SWITCH_INTERVAL = 10

# Auto-equip Constants
AUTO_EQUIP_ENABLED = True
AUTO_EQUIP_INTERVAL_GAMES = 3
AUTO_EQUIP_ON_STARTUP = True

# ===== PRE-SEASON 1 PACK DATA =====

MAIN_ONLY_PACKS = ["Scout", "Assassin"]

SUB_CAPABLE_PACKS = [
    "Moltz Expert", "Item Expert", "Goliath", "Thorns",
    "Ruin Expert", "Berserker", "Double Attack",
    "Heart of the Giant", "Bomber", "Trail Ward",
    "Ranged", "Sword Master", "Duelist", "Raider",
    "Last Stand", "Iron Heart", "Sunflame Cloak", "Pickpocket"
]

PACK_EFFECTS: Dict[str, Dict] = {
    "Moltz Expert": {
        "description": "Convert weapons/armor to Moltz",
        "main": {"moltz_convert": 1.0},
        "sub": {"moltz_convert": 0.5}
    },
    "Item Expert": {
        "description": "Moltz → Item ATK",
        "main": {"item_atk_coef": 1.0},
        "sub": {"item_atk_coef": 0.5}
    },
    "Goliath": {
        "description": "AoE attack",
        "main": {"aoe_multiplier": 0.85},
        "sub": {"aoe_multiplier": 0.425}
    },
    "Thorns": {
        "description": "Damage reduction + reflect",
        "main": {"dmg_reduction": 0.50, "reflect": 1.0},
        "sub": {"dmg_reduction": 0.25, "reflect": 0.5}
    },
    "Scout": {
        "description": "Vision +2, move -2 EP",
        "main": {"vision": 2, "move_ep_discount": 2},
        "sub": None
    },
    "Ruin Expert": {
        "description": "Instant relics, max alert",
        "main": {"instant_relics": True, "alert_max": True},
        "sub": {"instant_relics": True, "alert_max": True}
    },
    "Berserker": {
        "description": "DMG boost when HP < 50%",
        "main": {"berserker_dmg": 1.7},
        "sub": {"berserker_dmg": 1.3}
    },
    "Double Attack": {
        "description": "Attack twice",
        "main": {"hit_count": 2, "hit_multiplier": 0.65},
        "sub": {"hit_count": 2, "hit_multiplier": 0.55}
    },
    "Heart of the Giant": {
        "description": "Healing bonus + self-heal",
        "main": {"heal_bonus": 0.75, "self_heal": 0.03},
        "sub": {"heal_bonus": 0.375, "self_heal": 0.015}
    },
    "Bomber": {
        "description": "Convert items to bombs",
        "main": {"bomb_count": 3, "bomb_dmg": 0.2},
        "sub": {"bomb_count": 3, "bomb_dmg": 0.1}
    },
    "Trail Ward": {
        "description": "Start with vision wards",
        "main": {"wards": 3},
        "sub": {"wards": 2}
    },
    "Ranged": {
        "description": "Range +1, ranged damage +15%",
        "main": {"range_bonus": 1, "ranged_dmg": 0.15},
        "sub": {"range_bonus": 1, "ranged_dmg": 0.15, "ep_cost": 1}
    },
    "Sword Master": {
        "description": "No ranged, ignore ranged damage",
        "main": {"item_atk_multiplier": 1.0},
        "sub": {"item_atk_multiplier": 0.5}
    },
    "Duelist": {
        "description": "Alone → ATK/DEF boost",
        "main": {"solo_atk": 0.9, "solo_def": 0.9},
        "sub": {"solo_atk": 0.45, "solo_def": 0.45}
    },
    "Raider": {
        "description": "Steal inventory slot",
        "main": {"steal_slot": True},
        "sub": {"steal_slot": True, "ep_cost": 1}
    },
    "Last Stand": {
        "description": "Survive lethal, berserk",
        "main": {"survive_lethal": True, "berserk_turns": 3},
        "sub": {"survive_lethal": True, "berserk_turns": 1}
    },
    "Iron Heart": {
        "description": "On attack gain max-HP, DEF",
        "main": {"hp_gain": 5, "def_gain": 1},
        "sub": {"hp_gain": 2.5, "def_gain": 0.5}
    },
    "Sunflame Cloak": {
        "description": "Aura damage",
        "main": {"aura_dmg": 1.0},
        "sub": {"aura_dmg": 0.5}
    },
    "Assassin": {
        "description": "Stealth, bonus damage",
        "main": {"stealth": 3, "bonus_dmg": 0.6},
        "sub": None
    },
    "Pickpocket": {
        "description": "Steal sMoltz",
        "main": {"steal_amount": 3},
        "sub": {"steal_amount": 3, "ep_cost": 1}
    }
}

# ===== SUB ATTENUATION =====

PACK_ATTENUATION = {
    "Moltz Expert": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Item Expert": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Goliath": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Thorns": {"mode": "PARTIAL", "sub_factors": {"dmg_reduction": 0.25, "reflect": 0.5}},
    "Scout": {"mode": "MAIN_ONLY"},
    "Ruin Expert": {"mode": "SUB_VALUE", "sub_effect": "same as main"},
    "Berserker": {"mode": "PARTIAL", "sub_factors": {"berserker_dmg": 1.3}},
    "Double Attack": {"mode": "PARTIAL", "sub_factors": {"hit_multiplier": 0.55}},
    "Heart of the Giant": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Bomber": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Trail Ward": {"mode": "SUB_VALUE", "sub_effect": {"wards": 2}},
    "Ranged": {"mode": "PARTIAL", "sub_factors": {"ranged_dmg": 0.15, "ep_cost": 1}},
    "Sword Master": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Duelist": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Raider": {"mode": "SUB_VALUE", "sub_effect": {"steal_slot": True, "ep_cost": 1}},
    "Last Stand": {"mode": "SUB_VALUE", "sub_effect": {"survive_lethal": True, "berserk_turns": 1}},
    "Iron Heart": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Sunflame Cloak": {"mode": "MULTIPLY_0_5", "sub_factor": 0.5},
    "Assassin": {"mode": "MAIN_ONLY"},
    "Pickpocket": {"mode": "SUB_VALUE", "sub_effect": {"steal_amount": 3, "ep_cost": 1}}
}

# ===== RELICS PRE-SEASON 1 =====

RELIC_SLOTS = {
    "Ruby": 0,
    "Emerald": 1,
    "Sapphire": 2
}

RELIC_AFFIXES = {
    "atk": {
        "positive": {"name": "Ferocious", "min": 1, "max": 10},
        "negative": {"name": "Feeble", "min": -10, "max": -1}
    },
    "def": {
        "positive": {"name": "Unyielding", "min": 1, "max": 5},
        "negative": {"name": "Fragile", "min": -5, "max": -1}
    },
    "explore": {
        "positive": {"name": "Insightful", "min": 1, "max": 1},
        "negative": {"name": "Deluded", "min": -1, "max": -1}
    },
    "item_atk": {
        "positive": {"name": "Sharp", "min": 5, "max": 15},
        "negative": {"name": "Blunt", "min": -15, "max": -5}
    },
    "max_hp": {
        "positive": {"name": "Sturdy", "min": 1, "max": 10},
        "negative": {"name": "Sickly", "min": -10, "max": -1}
    },
    "max_ep": {
        "positive": {"name": "Bountiful", "min": 1, "max": 2},
        "negative": {"name": "Withered", "min": -2, "max": -1}
    },
    "ep_regen": {
        "positive": {"name": "Energized", "min": 1, "max": 1},
        "negative": {"name": "Sluggish", "min": -1, "max": -1}
    },
    "hp_regen": {
        "positive": {"name": "Regenerating", "min": 1, "max": 3},
        "negative": {"name": "Festering", "min": -3, "max": -1}
    }
}

RELIC_AFFIX_PRIORITY = {
    "atk": 5,
    "item_atk": 4,
    "max_hp": 4,
    "def": 3,
    "hp_regen": 3,
    "explore": 2,
    "max_ep": 2,
    "ep_regen": 1
}

# Inventory caps
INVENTORY_CAPS = {
    "in_game_relics": 5,
    "in_game_packs": 1,
    "lobby_relics": 15,
    "lobby_packs": 5,
    "items": 10
}

# ===== PACK HELPER FUNCTIONS =====

def get_pack_by_name(name: str) -> Optional[Dict]:
    """Dapatkan data pack berdasarkan nama"""
    return PACK_EFFECTS.get(name)

def get_pack_effect(name: str, slot: str = "main") -> Optional[Dict]:
    """Dapatkan efek pack berdasarkan slot"""
    pack = get_pack_by_name(name)
    if not pack:
        return None
    return pack.get(slot)

def is_main_only_pack(name: str) -> bool:
    """Cek apakah pack hanya bisa di Main slot"""
    return name in MAIN_ONLY_PACKS

def is_sub_capable_pack(name: str) -> bool:
    """Cek apakah pack bisa di Sub slot"""
    return name in SUB_CAPABLE_PACKS