# src/strategy/engine.py
"""Strategy engine (fallback untuk AI) - dengan perbaikan handling data"""

import logging
from typing import Dict, List, Any, Optional

from ..game.state import GameState
from ..game.actions import ActionBuilder
from .evaluators import (
    heal_score, combat_score, loot_score, 
    interact_score, explore_score, move_score,
    alive
)
from ..core.constants import SCORE_CAVE_EXIT
from ..core.exceptions import ClawRoyaleError

logger = logging.getLogger(__name__)

class StrategyEngine:
    """Engine untuk mengambil keputusan (fallback) dengan handling data robust"""
    
    def __init__(self):
        self.turn = 0
        self.action_builder = ActionBuilder()
        self._last_action = None
        self._consecutive_rejections = 0
        self._used_interactables = set()
        self._attack_cooldown = 0
        self._pack_modifiers = {}
    
    def set_pack_modifiers(self, main_pack: Dict, sub_pack: Dict):
        """Set pack modifiers dari loadout"""
        self._pack_modifiers = {}
        
        if main_pack:
            main_name = main_pack.get("name", "")
            from .evaluators import get_pack_strategy_modifier
            modifiers = get_pack_strategy_modifier(main_name, "main")
            self._pack_modifiers.update(modifiers)
        
        if sub_pack:
            sub_name = sub_pack.get("name", "")
            from .evaluators import get_pack_strategy_modifier
            modifiers = get_pack_strategy_modifier(sub_name, "sub")
            for key, value in modifiers.items():
                if isinstance(value, (int, float)):
                    self._pack_modifiers[key] = value * 0.5
                else:
                    self._pack_modifiers[key] = value
        
        if self._pack_modifiers:
            logger.debug(f"📦 Pack modifiers: {self._pack_modifiers}")
    
    def decide(self, state: GameState) -> Dict:
        """Ambil keputusan berdasarkan state game"""
        self.turn += 1
        
        if self._attack_cooldown > 0:
            self._attack_cooldown -= 1
        
        if not state.is_alive:
            return {"kind": "dead", "score": -1e9}
        
        if state.in_cave:
            cave_exit = state.get_cave_exit()
            if cave_exit:
                return {"kind": "interact", "obj": cave_exit, "score": SCORE_CAVE_EXIT}
            return {"kind": "wait", "score": 0}
        
        candidates = []
        hp_ratio = state.hp_ratio()
        
        # 1. HEALING
        if hp_ratio < 0.4:
            try:
                for item in state.get_items():
                    if not isinstance(item, dict):
                        continue
                    
                    item_id = item.get("instanceId") or item.get("id")
                    if not state.is_item_valid(item_id):
                        continue
                    
                    heal = float(item.get("heal", item.get("healAmount", 0)))
                    if heal > 0:
                        score = heal_score(item, hp_ratio)
                        me = state.get_self()
                        distance = state._calculate_distance(me, item)
                        if distance < 3:
                            score += 100
                        candidates.append({"kind": "pickup", "obj": item, "score": score})
            except Exception as e:
                logger.debug(f"Healing items error: {e}")
        
        # 2. RETREAT
        if hp_ratio < 0.2:
            try:
                for conn in state.get_connections():
                    if isinstance(conn, str):
                        conn = {"regionId": conn, "insideDeathZone": False, "safetyScore": 0.5}
                    elif not isinstance(conn, dict):
                        continue
                    
                    if not conn.get("insideDeathZone", False):
                        candidates.append({"kind": "move", "obj": conn, "score": 500})
            except Exception as e:
                logger.debug(f"Retreat error: {e}")
        
        # 3. COMBAT
        if hp_ratio > 0.4 and self._attack_cooldown == 0:
            try:
                for enemy in state.get_enemies():
                    if not isinstance(enemy, dict):
                        continue
                    
                    enemy_hp = float(enemy.get("hp", 0))
                    enemy_max_hp = float(enemy.get("maxHp", 1))
                    enemy_ratio = enemy_hp / max(enemy_max_hp, 1)
                    
                    is_guardian = enemy.get("isGuardian", False) or str(enemy.get("kind", "")).lower() == "guardian"
                    if is_guardian and hp_ratio < 0.6:
                        continue
                    
                    if enemy_ratio < 0.5 or (hp_ratio > 0.7 and enemy_ratio < 0.7):
                        score = combat_score(enemy, hp_ratio)
                        if score > 0:
                            candidates.append({"kind": "attack", "obj": enemy, "score": score})
            except Exception as e:
                logger.debug(f"Combat error: {e}")
        
        # 4. LOOT
        try:
            for item in state.get_items():
                if not isinstance(item, dict):
                    continue
                
                item_id = item.get("instanceId") or item.get("id")
                if not state.is_item_valid(item_id):
                    continue
                
                score = loot_score(item)
                if score > 0:
                    me = state.get_self()
                    distance = state._calculate_distance(me, item)
                    if distance < 3:
                        score += 50
                    candidates.append({"kind": "pickup", "obj": item, "score": score})
        except Exception as e:
            logger.debug(f"Loot error: {e}")
        
        # 5. INTERACT
        try:
            for obj in state.get_interactables():
                if not isinstance(obj, dict):
                    continue
                
                obj_id = obj.get("id") or obj.get("interactableId")
                if obj_id in self._used_interactables:
                    continue
                
                score = interact_score(obj)
                if score > 0:
                    candidates.append({"kind": "interact", "obj": obj, "score": score})
        except Exception as e:
            logger.debug(f"Interact error: {e}")
        
        # 6. EXPLORE
        if hp_ratio > 0.6:
            try:
                for obj in state.get_interactables():
                    if not isinstance(obj, dict):
                        continue
                    
                    obj_id = obj.get("id") or obj.get("interactableId")
                    if obj_id in self._used_interactables:
                        continue
                    
                    score = explore_score(obj, state.get_region())
                    if score > 0:
                        candidates.append({"kind": "explore", "obj": obj, "score": score})
            except Exception as e:
                logger.debug(f"Explore error: {e}")
        
        # 7. MOVE (FALLBACK)
        try:
            for conn in state.get_connections():
                if isinstance(conn, str):
                    conn = {"regionId": conn, "insideDeathZone": False, "safetyScore": 0.5}
                elif not isinstance(conn, dict):
                    continue
                
                score = move_score(conn, state.in_cave)
                if score > 0:
                    candidates.append({"kind": "move", "obj": conn, "score": score})
        except Exception as e:
            logger.debug(f"Move error: {e}")
        
        if not candidates:
            return {"kind": "wait", "score": 0}
        
        best = max(candidates, key=lambda x: x["score"])
        
        if best["kind"] == "attack":
            self._attack_cooldown = 2
        
        if best["kind"] in ("interact", "explore"):
            obj_id = best["obj"].get("id") or best["obj"].get("interactableId")
            if obj_id:
                self._used_interactables.add(obj_id)
        
        if best["kind"] == "pickup":
            item_id = best["obj"].get("instanceId") or best["obj"].get("id")
            if item_id:
                state.mark_item_attempted(item_id)
        
        if self._pack_modifiers:
            best = self._apply_pack_modifiers(best)
        
        return best
    
    def _apply_pack_modifiers(self, decision: Dict) -> Dict:
        """Terapkan pack modifiers pada keputusan"""
        modifiers = self._pack_modifiers
        if not modifiers:
            return decision
        
        modified = dict(decision)
        
        if modifiers.get("defensive"):
            if modified.get("kind") in ["attack", "explore"]:
                modified["score"] *= 0.7
        
        if modifiers.get("heal_priority", 1.0) > 1.0:
            if modified.get("kind") == "pickup":
                heal = modified.get("obj", {}).get("heal", 0)
                if heal > 0:
                    modified["score"] *= modifiers["heal_priority"]
        
        if modifiers.get("keep_distance"):
            if modified.get("kind") == "attack":
                modified["score"] *= 0.8
        
        return modified
    
    def execute(self, state: GameState, decision: Dict):
        """Eksekusi keputusan menjadi action"""
        kind = decision.get("kind")
        obj = decision.get("obj", {})
        
        if kind == "dead" or kind == "wait":
            return None
        
        if kind == "pickup":
            return self.action_builder.pickup(obj)
        elif kind == "attack":
            return self.action_builder.attack(obj)
        elif kind == "interact":
            return self.action_builder.interact(obj)
        elif kind == "explore":
            return self.action_builder.explore(obj)
        elif kind == "move":
            if isinstance(obj, str):
                return self.action_builder.move({"regionId": obj})
            return self.action_builder.move(obj)
        
        return None
    
    def reset_rejection_counter(self):
        self._consecutive_rejections = 0
    
    def reset(self):
        self._used_interactables.clear()
        self._attack_cooldown = 0
        self._consecutive_rejections = 0
        self._last_action = None
        self._pack_modifiers = {}
        self.turn = 0