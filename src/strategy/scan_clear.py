# src/strategy/scan_clear.py
"""Scan & Clear Strategy - Mode ke-2 untuk bot"""

import logging
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field

from ..game.state import GameState
from ..game.actions import ActionBuilder
from ..core.constants import ACTION_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class RegionStatus:
    region_id: str
    turn_entered: int = 0
    items_collected: List[str] = field(default_factory=list)
    enemies_cleared: List[str] = field(default_factory=list)
    is_complete: bool = False
    items_count: int = 0
    enemies_count: int = 0


class ScanClearStrategy:
    """
    Strategy "SCAN & CLEAR"
    - Scan semua item di region
    - Clear semua musuh
    - Move ke region berikutnya
    - Max 10 turn per region
    """
    
    def __init__(self):
        self.action_builder = ActionBuilder()
        self.current_region: Optional[RegionStatus] = None
        self.visited_regions: Set[str] = set()
        self.max_turns_per_region = 10
        self.turn = 0
        self.region_counter = 0
        
        self.stats = {
            "regions_cleared": 0,
            "items_collected": 0,
            "enemies_killed": 0,
            "turns_spent": 0,
            "total_actions": 0
        }
    
    def reset(self):
        self.current_region = None
        self.visited_regions.clear()
        self.turn = 0
        self.region_counter = 0
        self.stats = {
            "regions_cleared": 0,
            "items_collected": 0,
            "enemies_killed": 0,
            "turns_spent": 0,
            "total_actions": 0
        }
        logger.info("🔄 Scan & Clear strategy reset")
    
    def decide(self, state: GameState) -> Dict[str, Any]:
        self.turn += 1
        self.stats["turns_spent"] += 1
        
        if not state.is_alive:
            return {"kind": "dead", "score": -1e9, "strategy": "scan_clear"}
        
        region = state.get_region()
        region_id = region.get("id", "unknown")
        
        if region_id != (self.current_region.region_id if self.current_region else None):
            self._enter_new_region(region_id, state)
        
        # STEP 1: SCAN INVENTORY
        item_action = self._scan_inventory(state)
        if item_action:
            self.stats["items_collected"] += 1
            self.stats["total_actions"] += 1
            logger.info(f"📦 SCAN & CLEAR: Collecting item")
            return {"kind": "pickup", "obj": item_action, "score": 100, "strategy": "scan_clear"}
        
        # STEP 2: CLEAR ENEMIES
        enemy_action = self._clear_enemies(state)
        if enemy_action:
            self.stats["enemies_killed"] += 1
            self.stats["total_actions"] += 1
            logger.info(f"⚔️ SCAN & CLEAR: Attacking enemy")
            return {"kind": "attack", "obj": enemy_action, "score": 90, "strategy": "scan_clear"}
        
        # STEP 3: MOVE TO NEXT REGION
        if self.current_region and self.current_region.turn_entered > self.max_turns_per_region:
            logger.info(f"🚪 SCAN & CLEAR: Max turns ({self.max_turns_per_region}) reached, moving to next region")
            move_action = self._move_to_next_region(state)
            if move_action:
                return {"kind": "move", "obj": move_action, "score": 50, "strategy": "scan_clear"}
        
        move_action = self._move_to_next_region(state)
        if move_action:
            return {"kind": "move", "obj": move_action, "score": 30, "strategy": "scan_clear"}
        
        return {"kind": "wait", "score": 0, "strategy": "scan_clear"}
    
    def _enter_new_region(self, region_id: str, state: GameState):
        self.visited_regions.add(region_id)
        self.region_counter += 1
        
        items = state.get_items()
        enemies = state.get_enemies()
        
        self.current_region = RegionStatus(
            region_id=region_id,
            turn_entered=self.turn,
            items_count=len(items),
            enemies_count=len(enemies)
        )
        
        logger.info(f"🗺️ SCAN & CLEAR: Entered region {region_id[:8]} ({len(items)} items, {len(enemies)} enemies)")
    
    def _scan_inventory(self, state: GameState) -> Optional[Dict]:
        items = state.get_items()
        
        if not items:
            return None
        
        me = state.get_self()
        
        healing_items = []
        weapon_items = []
        relic_items = []
        pack_items = []
        other_items = []
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            item_id = item.get("instanceId") or item.get("id")
            if not item_id:
                continue
            
            if not state.is_item_valid(item_id):
                continue
            
            try:
                distance = state._calculate_distance(me, item)
                if distance > 5:
                    continue
            except Exception:
                continue
            
            item_type = str(item.get("type", item.get("itemType", ""))).lower()
            heal = float(item.get("heal", item.get("healAmount", 0)))
            
            if heal > 0:
                healing_items.append((item, distance, heal))
            elif "weapon" in item_type:
                weapon_items.append((item, distance, item.get("value", 0)))
            elif "relic" in item_type:
                relic_items.append((item, distance, item.get("value", 0)))
            elif "pack" in item_type:
                pack_items.append((item, distance, item.get("value", 0)))
            else:
                other_items.append((item, distance, item.get("value", 0)))
        
        all_items = []
        all_items.extend(healing_items)
        all_items.extend(weapon_items)
        all_items.extend(relic_items)
        all_items.extend(pack_items)
        all_items.extend(other_items)
        
        for item, distance, value in all_items:
            item_id = item.get("instanceId") or item.get("id")
            if item_id:
                state.mark_item_attempted(item_id)
                logger.debug(f"📦 SCAN & CLEAR: Picked {item.get('type', 'item')} (distance: {distance:.1f})")
                return item
        
        return None
    
    def _clear_enemies(self, state: GameState) -> Optional[Dict]:
        enemies = state.get_enemies()
        
        if not enemies:
            return None
        
        me = state.get_self()
        my_hp = float(me.get("hp", 0))
        my_max_hp = float(me.get("maxHp", 1))
        hp_ratio = my_hp / max(my_max_hp, 1)
        
        if hp_ratio < 0.4:
            logger.debug("🛡️ SCAN & CLEAR: HP too low, skipping combat")
            return None
        
        targetable = []
        
        for enemy in enemies:
            if not isinstance(enemy, dict):
                continue
            
            is_guardian = enemy.get("isGuardian", False) or str(enemy.get("kind", "")).lower() == "guardian"
            
            if is_guardian and hp_ratio < 0.6:
                continue
            
            enemy_hp = float(enemy.get("hp", 0))
            enemy_max_hp = float(enemy.get("maxHp", 1))
            enemy_ratio = enemy_hp / max(enemy_max_hp, 1)
            
            try:
                distance = state._calculate_distance(me, enemy)
            except Exception:
                continue
            
            priority_score = (1 - enemy_ratio) * 100 - distance * 2
            
            if enemy_ratio < 0.2:
                priority_score += 50
            
            if is_guardian:
                priority_score -= 80
            
            targetable.append((enemy, priority_score, distance))
        
        if not targetable:
            return None
        
        targetable.sort(key=lambda x: x[1], reverse=True)
        best_enemy, score, distance = targetable[0]
        
        enemy_id = best_enemy.get("agentId") or best_enemy.get("monsterId") or best_enemy.get("id")
        if enemy_id:
            logger.debug(f"⚔️ SCAN & CLEAR: Attacking enemy (HP: {best_enemy.get('hp', 0):.0f}, distance: {distance:.1f})")
            return best_enemy
        
        return None
    
    def _move_to_next_region(self, state: GameState) -> Optional[Dict]:
        connections = state.get_connections()
        
        if not connections:
            return None
        
        safe_connections = []
        for conn in connections:
            if isinstance(conn, str):
                conn = {"regionId": conn, "insideDeathZone": False, "safetyScore": 0.5}
            elif not isinstance(conn, dict):
                continue
            
            if conn.get("insideDeathZone", False):
                continue
            
            region_id = conn.get("regionId")
            if region_id not in self.visited_regions:
                safe_connections.append(conn)
        
        if safe_connections:
            best = max(safe_connections, key=lambda c: c.get("safetyScore", 0))
            region_id = best.get("regionId", "unknown")
            logger.info(f"🚪 SCAN & CLEAR: Moving to new region {region_id[:8]}")
            return best
        
        safe_all = []
        for conn in connections:
            if isinstance(conn, str):
                conn = {"regionId": conn, "insideDeathZone": False, "safetyScore": 0.5}
            elif not isinstance(conn, dict):
                continue
            
            if not conn.get("insideDeathZone", False):
                safe_all.append(conn)
        
        if safe_all:
            best = max(safe_all, key=lambda c: c.get("safetyScore", 0))
            region_id = best.get("regionId", "unknown")
            logger.info(f"🚪 SCAN & CLEAR: Revisiting region {region_id[:8]} (all visited)")
            return best
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "current_region": self.current_region.region_id if self.current_region else None,
            "regions_visited": len(self.visited_regions),
            "total_regions": self.region_counter,
            "is_active": self.current_region is not None
        }