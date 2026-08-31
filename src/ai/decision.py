# src/ai/decision.py
"""Decision Engine - Inti pengambilan keputusan AI"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from .perception import PerceivedState, PerceptionEngine
from .analyzer import GameAnalyzer
from .risk import RiskAssessor
from .knowledge import KnowledgeBase

logger = logging.getLogger(__name__)

@dataclass
class AIDecision:
    action_type: str
    target_id: Optional[str] = None
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)
    risk_score: float = 0.0
    expected_value: float = 0.0

class DecisionEngine:
    def __init__(self):
        self.perception = PerceptionEngine()
        self.analyzer = GameAnalyzer()
        self.risk = RiskAssessor()
        self.knowledge = KnowledgeBase()
        self.decision_history = []
        self.current_strategy = "balanced"
        self.performance_score = 0.0
        
    async def _make_decision(self, perceived: PerceivedState, analysis: Dict, situation_risk: Dict) -> AIDecision:
        strategy = self._select_strategy(perceived, analysis, situation_risk)
        self.current_strategy = strategy
        
        recommendations = analysis["recommendations"]
        evaluated_actions = []
        
        for rec in recommendations["all"]:
            action = {"type": rec["action"], "target": {"id": rec["target"]} if rec.get("target") else None}
            risk = self.risk.assess_action_risk(action, perceived)
            expected_value = self._calculate_expected_value(action, perceived, analysis)
            
            if strategy == "defensive":
                expected_value *= (1 - risk["risk_score"])
            elif strategy == "aggressive":
                expected_value *= (1 + (1 - risk["risk_score"]) * 0.3)
            
            evaluated_actions.append({
                "action": action,
                "risk": risk,
                "expected_value": expected_value,
                "priority": rec["priority"],
                "reasoning": rec["reason"]
            })
        
        evaluated_actions.sort(key=lambda x: x["expected_value"], reverse=True)
        
        if evaluated_actions and evaluated_actions[0]["expected_value"] > 10:
            best = evaluated_actions[0]
            return AIDecision(
                action_type=best["action"]["type"],
                target_id=best["action"]["target"]["id"] if best["action"]["target"] else None,
                confidence=self._calculate_confidence(best, perceived),
                reasoning=[best["reasoning"], f"Strategy: {strategy}"],
                risk_score=best["risk"]["risk_score"],
                expected_value=best["expected_value"]
            )
        
        return AIDecision(action_type="wait", confidence=0.5, reasoning=["No good action found"], risk_score=0, expected_value=0)
    
    def _select_strategy(self, perceived: PerceivedState, analysis: Dict, situation_risk: Dict) -> str:
        hp = perceived.hp_ratio
        danger = perceived.danger_level
        
        if hp < 0.25 or situation_risk["risk_score"] > 0.8:
            return "defensive"
        if hp > 0.7 and danger < 20 and analysis["battle_potential"]["can_fight"]:
            return "aggressive"
        if perceived.in_cave:
            return "explore"
        return "balanced"
    
    def _calculate_expected_value(self, action: Dict, perceived: PerceivedState, analysis: Dict) -> float:
        action_type = action["type"]
        
        if action_type == "attack":
            target = next((e for e in perceived.enemies if e.id == action["target"]["id"]), None)
            if target:
                damage_value = (1 - target.hp / max(target.max_hp, 1)) * 50
                kill_bonus = 30 if target.hp < target.max_hp * 0.3 else 0
                risk_penalty = target.threat_score * 0.5
                return damage_value + kill_bonus - risk_penalty
            return 0
            
        elif action_type == "pickup":
            item = next((i for i in perceived.items if i.id == action["target"]["id"]), None)
            if item:
                return item.value_score - item.distance * 0.5
            return 0
            
        elif action_type in ("interact", "explore"):
            interactable = next((i for i in perceived.interactables if i.id == action["target"]["id"]), None)
            if interactable:
                return interactable.value_score - interactable.distance * 0.3
            return 0
            
        elif action_type == "move":
            conn = next((c for c in perceived.connections if c.id == action["target"]["id"]), None)
            if conn:
                safety = conn.metadata.get("safetyScore", 0)
                return safety * 30 - (10 if conn.metadata.get("insideDeathZone", False) else 0)
            return 0
            
        return 0
    
    def _calculate_confidence(self, best_action: Dict, perceived: PerceivedState) -> float:
        risk_score = best_action["risk"]["risk_score"]
        expected_value = best_action["expected_value"]
        confidence = (1 - risk_score) * 0.6 + min(expected_value / 100, 0.4)
        if perceived.hp_ratio < 0.3:
            confidence *= 0.8
        return min(max(confidence, 0), 1)
    
    def _update_performance(self, decision: AIDecision, perceived: PerceivedState):
        if decision.action_type != "wait":
            self.performance_score += 1
        else:
            self.performance_score -= 0.5
        self.performance_score = max(min(self.performance_score, 100), 0)
    
    def get_strategy_name(self) -> str:
        names = {"defensive": "🛡️ Defensive", "aggressive": "⚔️ Aggressive", "balanced": "⚖️ Balanced", "explore": "🔍 Exploring"}
        return names.get(self.current_strategy, "❓ Unknown")