# src/ai/knowledge.py
"""Knowledge Base - Belajar dari pengalaman dengan memory limit"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import datetime
from collections import deque

logger = logging.getLogger(__name__)

class KnowledgeBase:
    MAX_HISTORY = 500
    MAX_PATTERNS = 100
    MAX_SESSION_HISTORY = 50
    
    def __init__(self, storage_path: str = "knowledge.json"):
        self.storage_path = Path(storage_path)
        self.data = self._load()
        self.session_id = datetime.datetime.now().isoformat()
        self._session_count = 0
        self._memory_usage = {
            "history": len(self.data.get("history", [])),
            "patterns": sum(len(v) for v in self.data.get("patterns", {}).values()),
            "session_history": 0
        }
        logger.debug(f"📊 Memory usage: {self._memory_usage}")
    
    def _load(self) -> Dict[str, Any]:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    if len(data.get("history", [])) > self.MAX_HISTORY:
                        data["history"] = data["history"][-self.MAX_HISTORY:]
                    return data
            except Exception as e:
                logger.warning(f"Failed to load knowledge: {e}")
        return self._default_knowledge()
    
    def _default_knowledge(self) -> Dict[str, Any]:
        return {
            "patterns": {
                "dangerous_situations": [],
                "good_opportunities": [],
                "failed_actions": [],
                "successful_actions": []
            },
            "stats": {
                "total_games": 0,
                "games_won": 0,
                "total_actions": 0,
                "successful_actions": 0,
                "kills": 0,
                "deaths": 0,
                "avg_survival": 0
            },
            "learned_weights": {
                "heal_value": 1.0,
                "attack_value": 1.0,
                "loot_value": 1.0,
                "explore_value": 1.0,
                "move_value": 1.0
            },
            "history": []
        }
    
    def save(self):
        self._cleanup()
        try:
            compact_data = self._compact_data()
            with open(self.storage_path, 'w') as f:
                json.dump(compact_data, f, indent=2)
            logger.debug(f"💾 Knowledge saved ({len(compact_data['history'])} entries)")
        except Exception as e:
            logger.error(f"Failed to save knowledge: {e}")
    
    def _cleanup(self):
        if len(self.data.get("history", [])) > self.MAX_HISTORY:
            removed = len(self.data["history"]) - self.MAX_HISTORY
            self.data["history"] = self.data["history"][-self.MAX_HISTORY:]
            logger.debug(f"🧹 Removed {removed} old history entries")
        
        for key in self.data.get("patterns", {}):
            if len(self.data["patterns"][key]) > self.MAX_PATTERNS:
                removed = len(self.data["patterns"][key]) - self.MAX_PATTERNS
                self.data["patterns"][key] = self.data["patterns"][key][-self.MAX_PATTERNS:]
                logger.debug(f"🧹 Removed {removed} old {key} patterns")
        
        self._memory_usage = {
            "history": len(self.data.get("history", [])),
            "patterns": sum(len(v) for v in self.data.get("patterns", {}).values()),
            "session_history": self._session_count
        }
    
    def _compact_data(self) -> Dict[str, Any]:
        return {
            "patterns": self.data.get("patterns", {}),
            "stats": self.data.get("stats", {}),
            "learned_weights": self.data.get("learned_weights", {}),
            "history": self.data.get("history", [])[-self.MAX_HISTORY:],
            "last_updated": datetime.datetime.now().isoformat(),
            "total_entries": len(self.data.get("history", []))
        }
    
    async def record_decision(self, decision, perceived, analysis):
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "session": self.session_id,
            "decision": {
                "action_type": decision.action_type,
                "target_id": decision.target_id,
                "confidence": decision.confidence,
                "expected_value": decision.expected_value
            },
            "context": {
                "hp_ratio": perceived.hp_ratio,
                "in_cave": perceived.in_cave,
                "enemy_count": len(perceived.enemies),
                "danger_level": perceived.danger_level,
                "opportunity_score": perceived.opportunity_score,
                "turn": perceived.turn
            },
            "analysis": {
                "threat_level": analysis["threat_level"]["level"],
                "battle_potential": analysis["battle_potential"]["potential"],
                "strategy": analysis["survival_strategy"]["primary"]
            }
        }
        self.data["history"].append(entry)
        self.data["stats"]["total_actions"] += 1
        self._session_count += 1
        
        if len(self.data["history"]) % 50 == 0:
            self._cleanup()
            self.save()
    
    def record_outcome(self, outcome: str, details: Dict = None):
        self.data["stats"]["total_games"] += 1
        
        if outcome == "win":
            self.data["stats"]["games_won"] += 1
        elif outcome == "death":
            self.data["stats"]["deaths"] += 1
        
        if details:
            self.data["stats"]["kills"] += details.get("kills", 0)
            total_games = self.data["stats"]["total_games"]
            avg = self.data["stats"]["avg_survival"]
            survival = details.get("survival_time", 0)
            self.data["stats"]["avg_survival"] = (avg * (total_games - 1) + survival) / total_games
        
        self._cleanup()
        self.save()
    
    def record_pattern(self, pattern_type: str, pattern_data: Dict):
        if pattern_type in self.data["patterns"]:
            self.data["patterns"][pattern_type].append({
                "timestamp": datetime.datetime.now().isoformat(),
                "data": pattern_data
            })
            if len(self.data["patterns"][pattern_type]) > self.MAX_PATTERNS:
                self.data["patterns"][pattern_type] = self.data["patterns"][pattern_type][-self.MAX_PATTERNS:]
            self.save()
    
    def get_learned_weight(self, action_type: str) -> float:
        return self.data["learned_weights"].get(action_type + "_value", 1.0)
    
    def update_learned_weight(self, action_type: str, adjustment: float):
        key = action_type + "_value"
        if key in self.data["learned_weights"]:
            current = self.data["learned_weights"][key]
            new_value = current + adjustment
            self.data["learned_weights"][key] = max(min(new_value, 2.0), 0.5)
            self.save()
    
    def get_insights(self) -> Dict[str, Any]:
        stats = self.data["stats"]
        
        return {
            "performance": {
                "win_rate": stats["games_won"] / max(stats["total_games"], 1),
                "avg_survival": stats["avg_survival"],
                "kills_per_game": stats["kills"] / max(stats["total_games"], 1),
                "success_rate": stats["successful_actions"] / max(stats["total_actions"], 1)
            },
            "weights": self.data["learned_weights"],
            "pattern_count": {
                k: len(v) for k, v in self.data["patterns"].items()
            },
            "total_games": stats["total_games"],
            "memory": {
                "history_entries": len(self.data.get("history", [])),
                "max_history": self.MAX_HISTORY,
                "usage_percent": (len(self.data.get("history", [])) / self.MAX_HISTORY) * 100
            }
        }
    
    def clear_old_data(self, days: int = 30):
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        original_count = len(self.data.get("history", []))
        self.data["history"] = [
            h for h in self.data.get("history", [])
            if h.get("timestamp", "") > cutoff_str
        ]
        removed = original_count - len(self.data["history"])
        
        logger.info(f"🧹 Cleared {removed} entries older than {days} days")
        self.save()
        return removed
    
    def get_memory_stats(self) -> Dict[str, Any]:
        return {
            "history_count": len(self.data.get("history", [])),
            "history_limit": self.MAX_HISTORY,
            "history_usage": f"{len(self.data.get('history', [])) / self.MAX_HISTORY * 100:.1f}%",
            "patterns_count": sum(len(v) for v in self.data.get("patterns", {}).values()),
            "patterns_limit": self.MAX_PATTERNS,
            "session_entries": self._session_count,
            "file_size": self.storage_path.stat().st_size if self.storage_path.exists() else 0
        }