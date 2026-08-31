# src/ai/analyzer.py
"""Analysis Layer - Menganalisis situasi dan pattern"""

import logging
from typing import Dict, Any, List

from .perception import PerceivedState

logger = logging.getLogger(__name__)

class GameAnalyzer:
    def __init__(self):
        self.threat_history = []
        self.patterns = {}
        
    def analyze(self, state: PerceivedState) -> Dict[str, Any]:
        return {
            "threat_level": self._analyze_threat(state),
            "opportunities": self._analyze_opportunities(state),
            "risks": self._analyze_risks(state),
            "recommendations": self._analyze_recommendations(state),
            "battle_potential": self._analyze_battle_potential(state),
            "survival_strategy": self._analyze_survival_strategy(state),
            "pattern_match": self._match_patterns(state)
        }
    
    def _analyze_threat(self, state: PerceivedState) -> Dict[str, Any]:
        if not state.enemies:
            return {"level": "safe", "score": 0, "factors": []}
        
        threats = {"immediate": [], "nearby": [], "far": []}
        for enemy in state.enemies:
            if enemy.distance < 5:
                threats["immediate"].append(enemy)
            elif enemy.distance < 15:
                threats["nearby"].append(enemy)
            else:
                threats["far"].append(enemy)
        
        total_threat = sum(e.threat_score for e in state.enemies)
        
        if total_threat > 50 and state.hp_ratio < 0.5:
            level = "extreme"
        elif total_threat > 30 or state.hp_ratio < 0.3:
            level = "high"
        elif total_threat > 15:
            level = "medium"
        else:
            level = "low"
        
        return {
            "level": level,
            "score": total_threat,
            "factors": {
                "immediate_count": len(threats["immediate"]),
                "nearby_count": len(threats["nearby"]),
                "has_guardian": any(e.is_guardian for e in state.enemies),
                "hp_risk": 1 - state.hp_ratio
            }
        }
    
    def _analyze_opportunities(self, state: PerceivedState) -> Dict[str, Any]:
        opportunities = {"heal": [], "loot": [], "combat": [], "explore": []}
        
        for item in state.items:
            if item.metadata.get("heal", 0) > 0:
                opportunities["heal"].append({"id": item.id, "value": item.value_score, "distance": item.distance})
            if item.metadata.get("value", 0) > 10:
                opportunities["loot"].append({"id": item.id, "value": item.value_score, "distance": item.distance})
        
        for enemy in state.enemies:
            hp_ratio = enemy.hp / max(enemy.max_hp, 1)
            if hp_ratio < 0.4 and not enemy.is_guardian and state.hp_ratio > 0.5:
                opportunities["combat"].append({
                    "id": enemy.id,
                    "value": 50 - enemy.threat_score,
                    "distance": enemy.distance,
                    "hp_ratio": hp_ratio
                })
        
        for interactable in state.interactables:
            if interactable.value_score > 30:
                opportunities["explore"].append({
                    "id": interactable.id,
                    "value": interactable.value_score,
                    "distance": interactable.distance
                })
        
        total_opportunity = (
            sum(o["value"] / max(o["distance"], 1) for o in opportunities["heal"]) * 2 +
            sum(o["value"] / max(o["distance"], 1) for o in opportunities["loot"]) +
            sum(o["value"] / max(o["distance"], 1) for o in opportunities["combat"]) * 1.5 +
            sum(o["value"] / max(o["distance"], 1) for o in opportunities["explore"]) * 0.5
        )
        
        return {
            "best": max(
                [("heal", opportunities["heal"]), ("loot", opportunities["loot"]),
                 ("combat", opportunities["combat"]), ("explore", opportunities["explore"])],
                key=lambda x: len(x[1])
            )[0] if any(opportunities.values()) else "none",
            "score": total_opportunity,
            "details": opportunities
        }
    
    def _analyze_risks(self, state: PerceivedState) -> Dict[str, Any]:
        risks = []
        
        if state.hp_ratio < 0.25:
            risks.append({"type": "critical_hp", "severity": 10, "message": "HP critical!"})
        elif state.hp_ratio < 0.5:
            risks.append({"type": "low_hp", "severity": 7, "message": "HP is low"})
        
        for enemy in state.enemies:
            if enemy.is_guardian and enemy.distance < 10:
                risks.append({"type": "guardian_nearby", "severity": 8, "message": "Guardian nearby!"})
            elif enemy.threat_score > 20 and enemy.distance < 8:
                risks.append({"type": "threatening_enemy", "severity": 6, "message": "Threatening enemy nearby"})
        
        if state.in_cave:
            has_exit = any(i.metadata.get("is_exit", False) for i in state.interactables)
            if not has_exit:
                risks.append({"type": "trapped_in_cave", "severity": 5, "message": "Trapped in cave!"})
        
        for conn in state.connections:
            if conn.metadata.get("insideDeathZone", False):
                risks.append({"type": "death_zone_nearby", "severity": 7, "message": "Death zone nearby!"})
        
        alert = state.region.get("alertGauge", 0)
        if alert > 8:
            risks.append({"type": "high_alert", "severity": 6, "message": f"High alert level: {alert}"})
        
        total_risk = sum(r["severity"] for r in risks)
        
        return {
            "total": total_risk,
            "level": "critical" if total_risk > 30 else "high" if total_risk > 20 else "medium" if total_risk > 10 else "low",
            "risks": risks
        }
    
    def _analyze_recommendations(self, state: PerceivedState) -> Dict[str, Any]:
        recommendations = []
        
        if state.hp_ratio < 0.25:
            recommendations.append({"action": "heal_priority", "priority": 100, "reason": "Critical HP - focus on healing"})
        
        if state.in_cave:
            exit_obj = next((i for i in state.interactables if i.metadata.get("is_exit")), None)
            if exit_obj:
                recommendations.append({"action": "exit_cave", "target": exit_obj.id, "priority": 95, "reason": "Exit cave immediately"})
        
        if state.hp_ratio < 0.4:
            heal_items = [i for i in state.items if i.metadata.get("heal", 0) > 0]
            if heal_items:
                best_heal = min(heal_items, key=lambda x: x.distance)
                recommendations.append({"action": "pickup", "target": best_heal.id, "priority": 85, "reason": "Need healing"})
        
        if state.hp_ratio > 0.5:
            weak_enemies = [e for e in state.enemies if not e.is_guardian and e.hp / max(e.max_hp, 1) < 0.4 and e.distance < 10]
            if weak_enemies:
                best_target = min(weak_enemies, key=lambda x: x.distance)
                recommendations.append({"action": "attack", "target": best_target.id, "priority": 70, "reason": "Safe kill opportunity"})
        
        if state.hp_ratio > 0.6:
            valuable_items = [i for i in state.items if i.value_score > 30]
            if valuable_items:
                best_item = min(valuable_items, key=lambda x: x.distance)
                recommendations.append({"action": "pickup", "target": best_item.id, "priority": 50, "reason": "Valuable loot"})
        
        if state.hp_ratio > 0.7 and state.danger_level < 30:
            explore_targets = [i for i in state.interactables if i.value_score > 30]
            if explore_targets:
                best_target = min(explore_targets, key=lambda x: x.distance)
                recommendations.append({"action": "explore" if "ruin" in str(best_target.metadata.get("kind", "")) else "interact", "target": best_target.id, "priority": 30, "reason": "Explore opportunity"})
        
        if not recommendations:
            safe_connections = [c for c in state.connections if not c.metadata.get("insideDeathZone", False) and c.value_score > 20]
            if safe_connections:
                best_conn = max(safe_connections, key=lambda x: x.value_score)
                recommendations.append({"action": "move", "target": best_conn.id, "priority": 20, "reason": "Move to safer region"})
        
        recommendations.sort(key=lambda x: x["priority"], reverse=True)
        
        return {
            "best": recommendations[0] if recommendations else {"action": "wait", "priority": 0},
            "all": recommendations,
            "total_priority": sum(r["priority"] for r in recommendations) if recommendations else 0
        }
    
    def _analyze_battle_potential(self, state: PerceivedState) -> Dict[str, Any]:
        attack = state.self.metadata.get("attack", 0)
        enemy_count = len(state.enemies)
        weak_enemies = sum(1 for e in state.enemies if e.hp / max(e.max_hp, 1) < 0.3)
        strong_enemies = sum(1 for e in state.enemies if e.is_guardian)
        
        if enemy_count == 0:
            potential = "safe"
        elif weak_enemies > 0 and state.hp_ratio > 0.6:
            potential = "advantageous"
        elif strong_enemies > 0 and state.hp_ratio < 0.5:
            potential = "dangerous"
        elif state.hp_ratio > 0.4:
            potential = "neutral"
        else:
            potential = "disadvantageous"
        
        return {
            "potential": potential,
            "attack_power": attack,
            "enemy_count": enemy_count,
            "weak_enemies": weak_enemies,
            "strong_enemies": strong_enemies,
            "can_fight": state.hp_ratio > 0.4 and enemy_count > 0 and strong_enemies == 0
        }
    
    def _analyze_survival_strategy(self, state: PerceivedState) -> Dict[str, Any]:
        strategies = []
        
        if state.hp_ratio < 0.3:
            strategies.append("flee_and_heal")
        elif state.hp_ratio < 0.5:
            strategies.append("defensive")
        elif state.hp_ratio < 0.7:
            strategies.append("balanced")
        else:
            strategies.append("aggressive")
        
        if any(e.is_guardian for e in state.enemies):
            strategies.append("avoid_guardian")
        
        if len(state.enemies) > 3:
            strategies.append("avoid_being_swarmed")
        
        if state.in_cave:
            strategies.append("find_exit")
        
        if state.region.get("alertGauge", 0) > 7:
            strategies.append("reduce_alert")
        
        return {
            "primary": strategies[0] if strategies else "balanced",
            "all": strategies,
            "description": self._describe_strategy(strategies)
        }
    
    def _describe_strategy(self, strategies: List[str]) -> str:
        if "flee_and_heal" in strategies:
            return "Flee from danger and prioritize healing"
        elif "defensive" in strategies:
            return "Play defensively, avoid unnecessary fights"
        elif "avoid_guardian" in strategies:
            return "Avoid guardians at all cost"
        elif "aggressive" in strategies:
            return "Play aggressively, take advantage of HP advantage"
        elif "balanced" in strategies:
            return "Balanced approach: fight when advantageous, heal when needed"
        else:
            return "Proceed with caution"
    
    def _match_patterns(self, state: PerceivedState) -> Dict[str, Any]:
        patterns = {"danger_pattern": False, "opportunity_pattern": False, "ambush_pattern": False}
        if len(state.enemies) > 0 and state.hp_ratio < 0.3:
            patterns["danger_pattern"] = True
        if len(state.items) > 2 and state.hp_ratio > 0.7:
            patterns["opportunity_pattern"] = True
        return patterns