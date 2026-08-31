# src/ai/hybrid_engine.py
"""Hybrid AI Engine - Gabungan AI Auto-Pilot + Competitive v7 dengan Item Tracking"""

import logging
import math
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from .perception import PerceivedState, PerceptionEngine
from .analyzer import GameAnalyzer
from .decision import DecisionEngine, AIDecision
from .risk import RiskAssessor
from .knowledge import KnowledgeBase
from ..game.state import GameState
from ..core.constants import ACTION_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class ThreatAssessment:
    kill_probability: float
    damage_received: float
    survival_chance: float
    escape_chance: float
    zone_threat: float
    risk_score: float
    is_safe: bool
    should_fight: bool
    should_flee: bool


@dataclass
class PriorityDecision:
    priority: int
    action_type: str
    target_id: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.0


class HybridAIEngine:
    def __init__(self):
        self.ai = DecisionEngine()
        self.perception = PerceptionEngine()
        self.analyzer = GameAnalyzer()
        self.risk = RiskAssessor()
        self.knowledge = KnowledgeBase()
        self.turn = 0
        self.kills = 0
        self.survival_time = 0
        
        self.stats = {
            "decisions_made": 0,
            "ai_decisions": 0,
            "heuristic_decisions": 0,
            "survival_priority": 0,
            "kill_priority": 0,
            "loot_priority": 0,
            "explore_priority": 0
        }
        
        self._decision_cache: Dict[int, AIDecision] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._max_cache_size = 50
        self._last_hp = 0
        self._last_turn = 0
        
        # RL
        self.rl_agent = None
        self.rl_enabled = True
        self.last_rl_state = None
        self.last_rl_action = None
        self.rl_learning_mode = True
        self.rl_stats = {
            "rl_decisions": 0,
            "exploration_decisions": 0,
            "exploitation_decisions": 0,
            "avg_rl_reward": 0
        }
        
        try:
            from .rl_agent import QLearningAgent
            self.rl_agent = QLearningAgent()
        except ImportError:
            logger.warning("⚠️ RL agent not available")
            self.rl_enabled = False
    
    async def decide(self, state: GameState) -> AIDecision:
        self.turn += 1
        
        hp_ratio = state.hp_ratio()
        if hp_ratio < 0.15:
            healing_items = state.get_healing_items()
            for item in healing_items[:3]:
                heal = float(item.get("heal", item.get("healAmount", 0)))
                if heal > 0:
                    distance = state._calculate_distance(state.get_self(), item)
                    if distance < 3:
                        item_id = item.get("instanceId") or item.get("id")
                        if item_id:
                            state.mark_item_attempted(item_id)
                            logger.info(f"⚡ CRITICAL HP ({hp_ratio:.0%}) - emergency heal!")
                            return AIDecision(
                                action_type="pickup",
                                target_id=item_id,
                                confidence=0.98,
                                reasoning=[f"Critical HP ({hp_ratio:.0%}) - emergency healing"],
                                risk_score=0.05,
                                expected_value=1.0
                            )
        
        if self.turn > 1 and self.turn == self._last_turn + 1:
            hp_changed = abs(hp_ratio - self._last_hp) < 0.05
            cached = self._decision_cache.get(self.turn - 1)
            if cached and hp_changed:
                self._cache_hits += 1
                return cached
        
        self._cache_misses += 1
        self._last_hp = hp_ratio
        self._last_turn = self.turn
        
        perceived = self.perception.perceive(state)
        threat = await self._assess_threat(perceived, state)
        priority_decision = await self._priority_decision(perceived, state, threat)
        
        ai_decision = await self.ai._make_decision(
            perceived, 
            self.ai.analyzer.analyze(perceived),
            self.risk.assess_current_situation(perceived)
        )
        
        rl_decision = None
        if self.rl_enabled and self.rl_agent and self.turn > 10:
            available_actions = self._get_available_actions(state)
            rl_decision = await self._rl_decision(state, available_actions)
        
        if rl_decision and rl_decision.confidence > 0.6:
            final_decision = await self._rl_hybrid_selection(
                rl_decision, priority_decision, ai_decision, threat
            )
        else:
            final_decision = await self._hybrid_selection(
                priority_decision, ai_decision, perceived, threat
            )
        
        self.stats["decisions_made"] += 1
        if final_decision.confidence > 0.6:
            self.stats["ai_decisions"] += 1
        else:
            self.stats["heuristic_decisions"] += 1
        
        if self.turn % 10 == 0:
            try:
                item_stats = state.get_item_stats()
                logger.debug(f"📊 Item Stats: {item_stats}")
            except Exception:
                pass
        
        logger.info(
            f"🧠 Hybrid AI: {final_decision.action_type} "
            f"(Priority: {priority_decision.priority}, "
            f"Conf: {final_decision.confidence:.2f}, "
            f"Risk: {threat['risk_score']:.2f})"
        )
        
        if len(self._decision_cache) > self._max_cache_size:
            oldest_keys = sorted(self._decision_cache.keys())[:10]
            for key in oldest_keys:
                del self._decision_cache[key]
        
        self._decision_cache[self.turn] = final_decision
        
        return final_decision
    
    async def _assess_threat(self, perceived: PerceivedState, state: GameState) -> Dict[str, Any]:
        threat = {
            "kill_probability": 0.0,
            "damage_received": 0.0,
            "survival_chance": 1.0,
            "escape_chance": 1.0,
            "zone_threat": 0.0,
            "risk_score": 0.0,
            "is_safe": True,
            "should_fight": False,
            "should_flee": False,
            "guardian_nearby": False,
            "guardian_distance": 999.0
        }
        
        try:
            me = state.get_self()
            if not isinstance(me, dict):
                return threat
            
            my_hp = float(me.get("hp", 0))
            my_max_hp = float(me.get("maxHp", 1))
            my_atk = float(me.get("attack", me.get("atk", 0)))
            my_def = float(me.get("defense", me.get("def", 0)))
            hp_ratio = my_hp / max(my_max_hp, 1)
            
            enemies = state.get_enemies()
            valid_enemies = [e for e in enemies if isinstance(e, dict)]
            
            if len(valid_enemies) > 8:
                valid_enemies.sort(key=lambda e: state._calculate_distance(me, e))
                valid_enemies = valid_enemies[:8]
            
            guardian_nearby = False
            guardian_distance = 999.0
            
            for enemy in valid_enemies:
                if enemy.get("isGuardian", False) or str(enemy.get("kind", "")).lower() == "guardian":
                    guardian_nearby = True
                    dist = self._distance(me, enemy)
                    if dist < guardian_distance:
                        guardian_distance = dist
            
            threat["guardian_nearby"] = guardian_nearby
            threat["guardian_distance"] = guardian_distance
            
            if guardian_nearby and guardian_distance < 15:
                threat["risk_score"] += 0.3 * (1 - guardian_distance / 15)
                threat["should_flee"] = True
                threat["should_fight"] = False
            
            if valid_enemies:
                closest = min(valid_enemies, key=lambda e: self._distance(me, e))
                target_hp = float(closest.get("hp", 0))
                target_max_hp = float(closest.get("maxHp", 1))
                target_atk = float(closest.get("attack", closest.get("atk", 0)))
                target_def = float(closest.get("defense", closest.get("def", 0)))
                
                threat["kill_probability"] = max(0, min(1, (my_atk - target_def) / max(target_hp, 1)))
                turns_to_kill = target_hp / max(my_atk - target_def, 1)
                threat["damage_received"] = (target_atk - my_def) * turns_to_kill
                threat["survival_chance"] = max(0, min(1, 1 - (threat["damage_received"] / max(my_hp, 1))))
                enemy_density = len(valid_enemies)
                threat["escape_chance"] = max(0, min(1, 1 - (enemy_density / 10)))
                
                threat["should_fight"] = (
                    hp_ratio > 0.5 and 
                    threat["kill_probability"] > 0.6 and
                    threat["survival_chance"] > 0.7 and
                    not guardian_nearby
                )
                
                threat["should_flee"] = (
                    hp_ratio < 0.3 or
                    threat["survival_chance"] < 0.5 or
                    threat["kill_probability"] < 0.3 or
                    guardian_nearby
                )
            
            region = state.get_region()
            if isinstance(region, dict) and region.get("insideDeathZone", False):
                threat["zone_threat"] = 0.8
            else:
                threat["zone_threat"] = 0.0
            
            threat["risk_score"] = min(1.0, (
                (1 - hp_ratio) * 0.4 +
                (1 - threat["survival_chance"]) * 0.3 +
                threat["zone_threat"] * 0.2 +
                (1 - threat["escape_chance"]) * 0.1
            ))
            
            threat["is_safe"] = threat["risk_score"] < 0.4
            
        except Exception as e:
            logger.debug(f"Threat assessment error: {e}")
        
        return threat
    
    async def _priority_decision(self, perceived: PerceivedState, state: GameState, threat: Dict) -> PriorityDecision:
        try:
            me = state.get_self()
            if not isinstance(me, dict):
                return PriorityDecision(priority=5, action_type="wait", reasoning="No self data", confidence=0.1)
            
            my_hp = float(me.get("hp", 0))
            my_max_hp = float(me.get("maxHp", 1))
            hp_ratio = my_hp / max(my_max_hp, 1)
            alert = state.get_region().get("alertGauge", 0)
            my_atk = float(me.get("attack", me.get("atk", 0)))
            
            # Use item dari inventory
            if hp_ratio < 0.5 and state.has_healing_items():
                best_heal = state.get_best_healing_item()
                if best_heal:
                    heal_amount = float(best_heal.get("heal", best_heal.get("healAmount", 0)))
                    if heal_amount > 0:
                        self.stats["survival_priority"] += 1
                        item_id = best_heal.get("instanceId") or best_heal.get("id")
                        if item_id:
                            logger.info(f"💚 Using healing item: {heal_amount} HP (HP: {hp_ratio:.0%})")
                            state.remove_from_inventory(item_id)
                            return PriorityDecision(
                                priority=1,
                                action_type="use",
                                target_id=item_id,
                                reasoning=f"Using healing item ({heal_amount} HP)",
                                confidence=0.98
                            )
            
            # HP < 40% → cari healing di ground
            if hp_ratio < 0.4:
                healing_items = state.get_healing_items()
                for item in healing_items[:5]:
                    if not isinstance(item, dict):
                        continue
                    heal = float(item.get("heal", item.get("healAmount", 0)))
                    if heal > 0:
                        distance = state._calculate_distance(state.get_self(), item)
                        if distance < 3:
                            self.stats["survival_priority"] += 1
                            item_id = item.get("instanceId") or item.get("id")
                            if item_id:
                                state.mark_item_attempted(item_id)
                                return PriorityDecision(
                                    priority=1,
                                    action_type="pickup",
                                    target_id=item_id,
                                    reasoning=f"Pickup healing ({heal} HP) - HP: {hp_ratio:.0%}",
                                    confidence=0.95
                                )
            
            # HP < 20% → retreat
            if hp_ratio < 0.2:
                self.stats["survival_priority"] += 1
                connections = state.get_connections()
                for conn in connections[:5]:
                    if isinstance(conn, dict) and not conn.get("insideDeathZone", False):
                        return PriorityDecision(
                            priority=1,
                            action_type="move",
                            target_id=conn.get("regionId"),
                            reasoning=f"Critical HP ({hp_ratio:.0%}) - retreating",
                            confidence=0.9
                        )
            
            # In cave → exit
            if state.in_cave:
                interactables = state.get_interactables()
                for obj in interactables[:5]:
                    if isinstance(obj, dict) and obj.get("isExit", False) and "cave" in str(obj.get("type", "")):
                        self.stats["survival_priority"] += 1
                        return PriorityDecision(
                            priority=1,
                            action_type="interact",
                            target_id=obj.get("interactableId") or obj.get("id"),
                            reasoning="Exiting cave",
                            confidence=0.95
                        )
            
            # In death zone → move to center
            try:
                region = state.get_region()
                if isinstance(region, dict) and region.get("insideDeathZone", False):
                    self.stats["survival_priority"] += 1
                    connections = state.get_connections()
                    for conn in connections[:5]:
                        if isinstance(conn, dict) and not conn.get("insideDeathZone", False):
                            return PriorityDecision(
                                priority=1,
                                action_type="move",
                                target_id=conn.get("regionId"),
                                reasoning="Escaping death zone",
                                confidence=0.9
                            )
            except Exception:
                pass
            
            # Alert > 7 → hide/retreat
            if alert > 7:
                self.stats["survival_priority"] += 1
                connections = state.get_connections()
                for conn in connections[:5]:
                    if isinstance(conn, dict) and conn.get("safetyScore", 0) > 0.5:
                        return PriorityDecision(
                            priority=1,
                            action_type="move",
                            target_id=conn.get("regionId"),
                            reasoning=f"High alert ({alert}) - moving to safety",
                            confidence=0.85
                        )
            
            # Loot items
            valid_items = state.get_valid_items()
            if valid_items:
                item = valid_items[0]
                item_id = item.get("instanceId") or item.get("id")
                distance = state._calculate_distance(state.get_self(), item)
                if item_id:
                    state.mark_item_attempted(item_id)
                    self.stats["loot_priority"] += 1
                    return PriorityDecision(
                        priority=2,
                        action_type="pickup",
                        target_id=item_id,
                        reasoning="Collecting loot",
                        confidence=0.8
                    )
            
            # Kill
            if hp_ratio > 0.5 and threat.get("should_fight", False):
                enemies = state.get_enemies()
                if enemies:
                    targetable = []
                    self_pos = state.get_self()
                    for e in enemies[:10]:
                        if not isinstance(e, dict):
                            continue
                        dist = self._distance(self_pos, e)
                        if dist < 10:
                            targetable.append((e, dist))
                    
                    if targetable:
                        targetable.sort(key=lambda x: float(x[0].get("hp", 0)))
                        target, dist = targetable[0]
                        
                        target_hp = float(target.get("hp", 0))
                        target_def = float(target.get("defense", target.get("def", 0)))
                        kill_prob = (my_atk - target_def) / max(target_hp, 1)
                        
                        if kill_prob > 0.6:
                            self.stats["kill_priority"] += 1
                            return PriorityDecision(
                                priority=3,
                                action_type="attack",
                                target_id=target.get("agentId") or target.get("monsterId") or target.get("id"),
                                reasoning=f"Kill opportunity (HP: {target_hp:.0f})",
                                confidence=min(kill_prob, 0.9)
                            )
            
            # Explore ruins
            if hp_ratio > 0.6 and alert < 6:
                interactables = state.get_interactables()
                for obj in interactables[:8]:
                    if not isinstance(obj, dict):
                        continue
                    obj_type = str(obj.get("type", obj.get("kind", ""))).lower()
                    if "ruin" in obj_type:
                        distance = self._distance(state.get_self(), obj)
                        if distance < 3:
                            self.stats["explore_priority"] += 1
                            return PriorityDecision(
                                priority=4,
                                action_type="explore",
                                target_id=obj.get("interactableId") or obj.get("id"),
                                reasoning=f"Farming ruin (distance: {distance:.1f})",
                                confidence=0.8
                            )
                        elif distance < 8:
                            self.stats["explore_priority"] += 1
                            return PriorityDecision(
                                priority=4,
                                action_type="move",
                                target_id=obj.get("regionId"),
                                reasoning="Moving to ruin",
                                confidence=0.65
                            )
            
            # Move fallback - prioritize unvisited regions
            unvisited_connections = []
            for conn in state.get_connections():
                if not isinstance(conn, dict):
                    continue
                region_id = conn.get("regionId")
                if region_id and not state.is_region_visited(region_id) and not conn.get("insideDeathZone", False):
                    unvisited_connections.append(conn)
            
            if unvisited_connections:
                best = max(unvisited_connections, key=lambda c: c.get("safetyScore", 0))
                self.stats["explore_priority"] += 1
                return PriorityDecision(
                    priority=4,
                    action_type="move",
                    target_id=best.get("regionId"),
                    reasoning=f"Exploring new region (safety: {best.get('safetyScore', 0):.2f})",
                    confidence=0.7
                )
            
            for conn in state.get_connections():
                if isinstance(conn, dict) and conn.get("safetyScore", 0) > 0.5 and not conn.get("insideDeathZone", False):
                    return PriorityDecision(
                        priority=4,
                        action_type="move",
                        target_id=conn.get("regionId"),
                        reasoning="Moving to safer area",
                        confidence=0.5
                    )
            
            for conn in state.get_connections():
                if isinstance(conn, dict) and not conn.get("insideDeathZone", False):
                    return PriorityDecision(
                        priority=4,
                        action_type="move",
                        target_id=conn.get("regionId"),
                        reasoning="Moving randomly",
                        confidence=0.3
                    )
            
        except Exception as e:
            logger.debug(f"Priority decision error: {e}")
        
        return PriorityDecision(
            priority=5,
            action_type="wait",
            reasoning="No action available",
            confidence=0.1
        )
    
    async def _hybrid_selection(self, priority: PriorityDecision, ai: AIDecision, perceived: PerceivedState, threat: Dict) -> AIDecision:
        if priority.confidence > 0.8:
            return AIDecision(
                action_type=priority.action_type,
                target_id=priority.target_id,
                confidence=priority.confidence,
                reasoning=[priority.reasoning, "Priority-based"],
                risk_score=threat.get("risk_score", 0.5),
                expected_value=1 - threat.get("risk_score", 0.5)
            )
        
        if ai.confidence > 0.7 and priority.priority > 2:
            return ai
        
        if priority.priority <= 2:
            return AIDecision(
                action_type=priority.action_type,
                target_id=priority.target_id,
                confidence=priority.confidence,
                reasoning=[priority.reasoning, "Emergency priority"],
                risk_score=threat.get("risk_score", 0.5),
                expected_value=1 - threat.get("risk_score", 0.5)
            )
        
        return ai
    
    async def _rl_decision(self, state: GameState, available_actions: List[str]) -> Optional[PriorityDecision]:
        if not self.rl_enabled or not self.rl_agent:
            return None
        
        rl_state = self.rl_agent.get_state_features(state)
        action, is_exploration = self.rl_agent.choose_action(rl_state, available_actions)
        
        if is_exploration:
            self.rl_stats["exploration_decisions"] += 1
            logger.debug(f"🧠 RL Exploration: {action}")
        else:
            self.rl_stats["exploitation_decisions"] += 1
            q_value = self.rl_agent.get_q_value(rl_state, action)
            logger.debug(f"🧠 RL Exploitation: {action} (Q: {q_value:.2f})")
        
        self.rl_stats["rl_decisions"] += 1
        
        self.last_rl_state = rl_state
        self.last_rl_action = action
        
        return self._action_to_priority(action, state)
    
    def _action_to_priority(self, action: str, state: GameState) -> Optional[PriorityDecision]:
        if action == "attack":
            enemies = state.get_enemies()
            if enemies:
                target = min(enemies, key=lambda e: e.get("hp", 0))
                return PriorityDecision(
                    priority=3,
                    action_type="attack",
                    target_id=target.get("agentId") or target.get("monsterId") or target.get("id"),
                    reasoning="RL: Attack",
                    confidence=0.7
                )
        elif action == "pickup":
            items = state.get_valid_items()
            if items:
                best_item = max(items, key=lambda i: i.get("value", 0))
                return PriorityDecision(
                    priority=2,
                    action_type="pickup",
                    target_id=best_item.get("instanceId") or best_item.get("id"),
                    reasoning="RL: Pickup",
                    confidence=0.7
                )
        elif action == "move":
            connections = state.get_connections()
            if connections:
                best_conn = max(connections, key=lambda c: c.get("safetyScore", 0))
                return PriorityDecision(
                    priority=4,
                    action_type="move",
                    target_id=best_conn.get("regionId"),
                    reasoning="RL: Move",
                    confidence=0.6
                )
        elif action == "explore":
            interactables = state.get_interactables()
            for obj in interactables:
                if "ruin" in str(obj.get("type", obj.get("kind", ""))):
                    return PriorityDecision(
                        priority=4,
                        action_type="explore",
                        target_id=obj.get("interactableId") or obj.get("id"),
                        reasoning="RL: Explore",
                        confidence=0.7
                    )
        elif action == "interact":
            interactables = state.get_interactables()
            if interactables:
                best_obj = max(interactables, key=lambda o: o.get("value", 0))
                return PriorityDecision(
                    priority=4,
                    action_type="interact",
                    target_id=best_obj.get("interactableId") or best_obj.get("id"),
                    reasoning="RL: Interact",
                    confidence=0.6
                )
        elif action == "use":
            if state.has_healing_items():
                heal_item = state.get_best_healing_item()
                if heal_item:
                    return PriorityDecision(
                        priority=1,
                        action_type="use",
                        target_id=heal_item.get("instanceId") or heal_item.get("id"),
                        reasoning="RL: Use item",
                        confidence=0.8
                    )
        elif action == "wait":
            return PriorityDecision(
                priority=5,
                action_type="wait",
                reasoning="RL: Wait",
                confidence=0.3
            )
        
        return None
    
    async def _rl_hybrid_selection(self, rl: PriorityDecision, priority: PriorityDecision, ai: AIDecision, threat: Dict) -> AIDecision:
        if rl.confidence > 0.7:
            return AIDecision(
                action_type=rl.action_type,
                target_id=rl.target_id,
                confidence=rl.confidence,
                reasoning=[rl.reasoning, "RL-based"],
                risk_score=threat.get("risk_score", 0.5),
                expected_value=1 - threat.get("risk_score", 0.5)
            )
        
        return await self._hybrid_selection(priority, ai, None, threat)
    
    def _get_available_actions(self, state: GameState) -> List[str]:
        actions = []
        if state.get_enemies():
            actions.append("attack")
        if state.get_valid_items():
            actions.append("pickup")
        if state.get_connections():
            actions.append("move")
        if state.get_interactables():
            actions.append("explore")
            actions.append("interact")
        if state.has_healing_items():
            actions.append("use")
        actions.append("wait")
        return actions
    
    def _update_rl_reward(self, state: GameState, action: str, success: bool):
        if not self.rl_enabled or not self.rl_agent or not self.last_rl_state:
            return
        
        reward = self.rl_agent.get_reward(state, action, success)
        next_state = self.rl_agent.get_state_features(state)
        
        done = not state.is_alive or state.is_finished
        self.rl_agent.learn(
            state=self.last_rl_state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done
        )
        
        self.rl_stats["avg_rl_reward"] = (
            self.rl_stats["avg_rl_reward"] * (self.rl_stats["rl_decisions"] - 1) + reward
        ) / self.rl_stats["rl_decisions"]
        
        if abs(reward) > 0.5:
            logger.debug(f"📊 RL Reward: {reward:.2f} for {action}")
        
        self.last_rl_state = None
        self.last_rl_action = None
    
    def _distance(self, obj1, obj2) -> float:
        try:
            if obj1 is None or obj2 is None:
                return 999.0
            if isinstance(obj1, str) or isinstance(obj2, str):
                return 999.0
            if isinstance(obj1, list):
                obj1 = obj1[0] if obj1 else {}
            if isinstance(obj2, list):
                obj2 = obj2[0] if obj2 else {}
            if isinstance(obj1, (tuple, set)):
                obj1 = list(obj1)[0] if obj1 else {}
            if isinstance(obj2, (tuple, set)):
                obj2 = list(obj2)[0] if obj2 else {}
            if not isinstance(obj1, dict) or not isinstance(obj2, dict):
                return 999.0
            
            x1 = float(obj1.get("x", obj1.get("position", {}).get("x", 0)))
            y1 = float(obj1.get("y", obj1.get("position", {}).get("y", 0)))
            x2 = float(obj2.get("x", obj2.get("position", {}).get("x", 0)))
            y2 = float(obj2.get("y", obj2.get("position", {}).get("y", 0)))
            return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
        except Exception as e:
            logger.debug(f"Distance calculation error: {e}")
            return 999.0
    
    def get_stats(self) -> Dict:
        base_stats = {
            **self.stats,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": self._cache_hits / max(self._cache_hits + self._cache_misses, 1) * 100
        }
        
        if self.rl_agent:
            base_stats["rl"] = self.rl_agent.get_stats()
        
        return base_stats