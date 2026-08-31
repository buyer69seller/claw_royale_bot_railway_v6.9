# src/game/state.py
"""Manajemen state game - dengan Item Tracking & Detection yang Diperbaiki"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
import logging
import math

logger = logging.getLogger(__name__)


@dataclass
class GameState:
    """State dari game yang sedang berjalan"""
    
    # Game info
    game_id: Optional[str] = None
    entry_type: str = "free"
    
    # Agent info
    agent_id: Optional[str] = None
    self_token: Optional[str] = None
    is_alive: bool = True
    can_act: bool = True
    in_cave: bool = False
    
    # View data terakhir
    view: Dict[str, Any] = field(default_factory=dict)
    turn: int = 0
    last_view_hash: int = 0
    
    # Status
    is_finished: bool = False
    is_dead: bool = False
    
    # Metadata
    survival_time: int = 0
    kills: int = 0
    hp: float = 0
    max_hp: float = 1
    
    # Rejected action tracking
    rejected_count: int = 0
    last_rejected_action: Optional[str] = None
    
    # ===== ITEM TRACKING =====
    attempted_items: Set[str] = field(default_factory=set)
    collected_items: Set[str] = field(default_factory=set)
    item_cache: Dict[str, Dict] = field(default_factory=dict)
    last_item_scan_turn: int = 0
    
    # ===== RUIN & ALERT TRACKING =====
    alert_gauge: int = 0
    alert_active: bool = False
    ruin_cache: Dict[str, Dict] = field(default_factory=dict)
    explored_ruins: Set[str] = field(default_factory=set)
    
    # ===== INVENTORY TRACKING =====
    inventory_items: Dict[str, Dict] = field(default_factory=dict)
    equipped_items: Dict[str, str] = field(default_factory=dict)
    
    # ===== VISITED REGION TRACKING =====
    visited_regions: Set[str] = field(default_factory=set)
    region_visit_count: Dict[str, int] = field(default_factory=dict)
    current_region_id: Optional[str] = None
    
    def update_view(self, view_data: Dict, reason: str = "sync"):
        """Update view dari game - dengan item cache update"""
        import hashlib
        import json
        
        # Hash view untuk deteksi perubahan
        view_str = json.dumps(view_data, sort_keys=True)
        new_hash = hash(view_str)
        
        if new_hash == self.last_view_hash and reason == "action_rejected":
            self.rejected_count += 1
        else:
            self.rejected_count = 0
            self.last_view_hash = new_hash
        
        self.view = view_data
        self.turn += 1
        
        # Update self info
        self_data = view_data.get("self", {})
        self.is_alive = self_data.get("isAlive", True)
        self.self_token = self_data.get("id")
        self.in_cave = self_data.get("inCave", False)
        
        # Update HP
        self.hp = float(self_data.get("hp", self_data.get("currentHp", self_data.get("health", 0))))
        self.max_hp = float(self_data.get("maxHp", self_data.get("maxHealth", self_data.get("hp", 1))))
        
        # Track stats
        if "survivalTime" in self_data:
            self.survival_time = self_data.get("survivalTime", 0)
        if "kills" in self_data:
            self.kills = self_data.get("kills", 0)
        
        # ===== ITEM CACHE UPDATE =====
        self._update_item_cache(view_data)
        
        # ===== TRACK REGION =====
        region = view_data.get("currentRegion", {})
        region_id = region.get("id")
        if region_id:
            self.current_region_id = region_id
            self.visited_regions.add(region_id)
            self.region_visit_count[region_id] = self.region_visit_count.get(region_id, 0) + 1
            
            visit_count = self.region_visit_count[region_id]
            if visit_count > 3:
                logger.warning(f"⚠️ Region {region_id[:8]} visited {visit_count}x - possible loop!")
    
    def _update_item_cache(self, view_data: Dict):
        """Update item cache dari view - DIPERBAIKI"""
        region = view_data.get("currentRegion", {})
        items = region.get("items", [])
        
        if self.turn == 1:
            self.item_cache.clear()
            self.attempted_items.clear()
            self.collected_items.clear()
            logger.info("📦 Item cache reset for new game")
        
        current_item_ids = set()
        for item in items:
            if not isinstance(item, dict):
                continue
                
            item_id = item.get("instanceId") or item.get("id")
            if item_id:
                current_item_ids.add(item_id)
                self.item_cache[item_id] = item
                item_type = item.get("type", item.get("itemType", "unknown"))
                logger.debug(f"📦 Item cached: {item_id[:8]} - {item_type}")
        
        removed_items = []
        for cached_id in list(self.item_cache.keys()):
            if cached_id not in current_item_ids:
                if cached_id not in self.collected_items:
                    self.collected_items.add(cached_id)
                removed_items.append(cached_id)
                del self.item_cache[cached_id]
        
        if removed_items:
            logger.debug(f"🗑️ Items removed from cache: {len(removed_items)}")
        
        self.attempted_items = self.attempted_items - self.collected_items
        
        if self.turn % 10 == 0:
            logger.debug(f"📦 Item cache: {len(self.item_cache)} items, {len(self.collected_items)} collected, {len(self.attempted_items)} attempted")
    
    def get_items(self) -> List[Dict]:
        """Dapatkan semua item di region saat ini - DIPERBAIKI"""
        region = self.get_region()
        items = region.get("items", [])
        
        result = []
        for item in items:
            if isinstance(item, dict):
                result.append(item)
            else:
                logger.debug(f"⚠️ Skipping invalid item: {item}")
        
        return result
    
    def get_valid_items(self) -> List[Dict]:
        """Dapatkan item yang VALID dan BELUM DICOBA"""
        items = self.get_items()
        valid_items = []
        me = self.get_self()
        
        if not items:
            logger.debug("📭 No items in current view")
            return []
        
        logger.debug(f"📦 Total items in view: {len(items)}")
        
        for item in items:
            if not isinstance(item, dict):
                continue
                
            item_id = item.get("instanceId") or item.get("id")
            if not item_id:
                continue
            
            item_type = item.get("type", item.get("itemType", "unknown"))
            heal = float(item.get("heal", item.get("healAmount", 0)))
            value = float(item.get("value", item.get("rarityValue", 0)))
            logger.debug(f"🔍 Found item: {item_id[:8]} - {item_type} (heal: {heal}, value: {value})")
            
            if item_id in self.attempted_items:
                logger.debug(f"⏭️ Item {item_id[:8]} already attempted")
                continue
            
            if item_id in self.collected_items:
                logger.debug(f"⏭️ Item {item_id[:8]} already collected")
                continue
            
            try:
                distance = self._calculate_distance(me, item)
            except Exception as e:
                logger.debug(f"⚠️ Distance calc error for {item_id[:8]}: {e}")
                continue
            
            if distance < 5:
                valid_items.append(item)
                logger.debug(f"✅ Item {item_id[:8]} valid (distance: {distance:.1f})")
            else:
                logger.debug(f"📏 Item {item_id[:8]} too far (distance: {distance:.1f})")
        
        logger.debug(f"📦 Valid items: {len(valid_items)}")
        
        valid_items.sort(key=lambda x: (
            -float(x.get("heal", x.get("healAmount", 0))),
            -float(x.get("value", x.get("rarityValue", 0)))
        ))
        
        return valid_items
    
    def get_nearby_items(self, max_distance: float = 3.0) -> List[Dict]:
        """Dapatkan semua item dalam jarak tertentu"""
        items = self.get_items()
        nearby = []
        me = self.get_self()
        
        for item in items:
            if not isinstance(item, dict):
                continue
                
            item_id = item.get("instanceId") or item.get("id")
            if not item_id:
                continue
            
            try:
                distance = self._calculate_distance(me, item)
                if distance <= max_distance:
                    nearby.append(item)
                    logger.debug(f"📦 Nearby item: {item_id[:8]} - {distance:.1f}m")
            except Exception as e:
                logger.debug(f"⚠️ Distance error: {e}")
                continue
        
        return nearby
    
    def get_healing_items(self) -> List[Dict]:
        """Dapatkan item healing yang valid"""
        valid_items = self.get_valid_items()
        healing_items = []
        
        for item in valid_items:
            if not isinstance(item, dict):
                continue
            heal = float(item.get("heal", item.get("healAmount", 0)))
            if heal > 0:
                me = self.get_self()
                try:
                    distance = self._calculate_distance(me, item)
                    healing_items.append({
                        "item": item,
                        "heal": heal,
                        "distance": distance,
                        "score": heal / max(distance, 1)
                    })
                except Exception as e:
                    continue
        
        healing_items.sort(key=lambda x: x["score"], reverse=True)
        logger.debug(f"💚 Healing items available: {len(healing_items)}")
        return [h["item"] for h in healing_items]
    
    def get_loot_items(self) -> List[Dict]:
        """Dapatkan item loot yang valid (non-healing)"""
        valid_items = self.get_valid_items()
        loot_items = []
        
        for item in valid_items:
            if not isinstance(item, dict):
                continue
            heal = float(item.get("heal", item.get("healAmount", 0)))
            if heal == 0:
                value = float(item.get("value", item.get("rarityValue", 0)))
                item_type = str(item.get("type", item.get("itemType", ""))).lower()
                
                priority = 0
                if "relic" in item_type:
                    priority = 4
                elif "pack" in item_type:
                    priority = 3
                elif "weapon" in item_type or "armor" in item_type:
                    priority = 2
                else:
                    priority = 1
                
                loot_items.append({
                    "item": item,
                    "value": value,
                    "priority": priority,
                    "item_type": item_type
                })
        
        loot_items.sort(key=lambda x: (x["priority"], x["value"]), reverse=True)
        logger.debug(f"📦 Loot items available: {len(loot_items)}")
        return [l["item"] for l in loot_items]
    
    def get_item_by_id(self, item_id: str) -> Optional[Dict]:
        """Cari item berdasarkan ID"""
        if not item_id:
            return None
        
        if item_id in self.item_cache:
            return self.item_cache[item_id]
        
        for item in self.get_items():
            if item.get("instanceId") == item_id or item.get("id") == item_id:
                return item
        
        return None
    
    def get_items_by_type(self, item_type: str) -> List[Dict]:
        """Dapatkan item berdasarkan tipe"""
        items = []
        for item in self.get_items():
            if not isinstance(item, dict):
                continue
            item_type_str = str(item.get("type", item.get("itemType", ""))).lower()
            if item_type.lower() in item_type_str:
                items.append(item)
        return items
    
    def is_item_valid(self, item_id: str) -> bool:
        """Cek apakah item masih valid"""
        if not item_id:
            return False
        
        if item_id not in self.item_cache:
            logger.debug(f"⚠️ Item {item_id[:8]} not in cache")
            return False
        
        if item_id in self.attempted_items or item_id in self.collected_items:
            logger.debug(f"⏭️ Item {item_id[:8]} already attempted/collected")
            return False
        
        return True
    
    def mark_item_attempted(self, item_id: str):
        """Tandai item sudah dicoba"""
        if item_id:
            self.attempted_items.add(item_id)
            logger.debug(f"📝 Item {item_id[:8]} marked as attempted")
    
    def mark_item_collected(self, item_id: str):
        """Tandai item sudah dikoleksi"""
        if item_id:
            self.collected_items.add(item_id)
            self.attempted_items.add(item_id)
            if item_id in self.item_cache:
                del self.item_cache[item_id]
            logger.debug(f"✅ Item {item_id[:8]} marked as collected")
    
    def add_to_inventory(self, item: Dict):
        """Tambahkan item ke inventory"""
        if not isinstance(item, dict):
            return
        item_id = item.get("instanceId") or item.get("id")
        if item_id:
            self.inventory_items[item_id] = item
            logger.debug(f"📦 Added to inventory: {item_id[:8]}")
    
    def remove_from_inventory(self, item_id: str):
        """Hapus item dari inventory"""
        if item_id in self.inventory_items:
            del self.inventory_items[item_id]
            logger.debug(f"🗑️ Removed from inventory: {item_id[:8]}")
    
    def get_healing_items_inventory(self) -> List[Dict]:
        """Dapatkan item healing dari inventory"""
        healing_items = []
        for item in self.inventory_items.values():
            if not isinstance(item, dict):
                continue
            heal = float(item.get("heal", item.get("healAmount", 0)))
            if heal > 0:
                healing_items.append(item)
        return healing_items
    
    def get_best_healing_item(self) -> Optional[Dict]:
        """Dapatkan item healing terbaik dari inventory"""
        items = self.get_healing_items_inventory()
        if not items:
            return None
        items.sort(key=lambda x: float(x.get("heal", x.get("healAmount", 0))), reverse=True)
        return items[0]
    
    def has_healing_items(self) -> bool:
        """Cek apakah ada item healing di inventory"""
        return len(self.get_healing_items_inventory()) > 0
    
    def get_item_stats(self) -> Dict[str, Any]:
        """Dapatkan statistik item tracking"""
        return {
            "total_items_in_cache": len(self.item_cache),
            "attempted_items": len(self.attempted_items),
            "collected_items": len(self.collected_items),
            "valid_items_available": len(self.get_valid_items()),
            "inventory_items": len(self.inventory_items)
        }
    
    def is_region_visited(self, region_id: str) -> bool:
        """Cek apakah region sudah pernah dikunjungi"""
        return region_id in self.visited_regions
    
    def get_region_visit_count(self, region_id: str) -> int:
        """Dapatkan berapa kali region dikunjungi"""
        return self.region_visit_count.get(region_id, 0)
    
    def should_avoid_region(self, region_id: str) -> bool:
        """Cek apakah region harus dihindari (terlalu sering dikunjungi)"""
        return self.get_region_visit_count(region_id) > 3
    
    def _calculate_distance(self, obj1: Dict, obj2: Dict) -> float:
        """Hitung jarak antara dua objek - DIPERBAIKI dengan type checking"""
        try:
            if obj1 is None or obj2 is None:
                return 999.0
            
            if isinstance(obj1, str):
                obj1 = {"x": 0, "y": 0}
            if isinstance(obj2, str):
                obj2 = {"x": 0, "y": 0}
            
            if isinstance(obj1, list):
                obj1 = obj1[0] if obj1 else {"x": 0, "y": 0}
            if isinstance(obj2, list):
                obj2 = obj2[0] if obj2 else {"x": 0, "y": 0}
            
            if isinstance(obj1, (tuple, set)):
                obj1 = list(obj1)[0] if obj1 else {"x": 0, "y": 0}
            if isinstance(obj2, (tuple, set)):
                obj2 = list(obj2)[0] if obj2 else {"x": 0, "y": 0}
            
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
    
    def update_ruin_state(self, ruin_data: Dict):
        """Update ruin state dari event"""
        if not isinstance(ruin_data, dict):
            return
        ruin_id = ruin_data.get("ruinId")
        if not ruin_id:
            return
        
        self.ruin_cache[ruin_id] = ruin_data
        
        if ruin_data.get("isEmpty", False):
            self.explored_ruins.add(ruin_id)
            logger.debug(f"🗺️ Ruin {ruin_id[:8]} cleared")
    
    def update_alert_gauge(self, alert_data: Dict):
        """Update alert gauge dari event"""
        if not isinstance(alert_data, dict):
            return
        self.alert_gauge = alert_data.get("alertGauge", 0)
        self.alert_active = alert_data.get("alertActive", False)
        
        if self.alert_active:
            logger.warning(f"⚠️ Alert active! Gauge: {self.alert_gauge}")
        else:
            logger.debug(f"📊 Alert gauge: {self.alert_gauge}")
    
    def get_available_ruins(self) -> List[Dict]:
        """Dapatkan ruins yang tersedia"""
        available = []
        for ruin_id, ruin in self.ruin_cache.items():
            if not ruin.get("isEmpty", True) and not ruin.get("occupiedBy"):
                available.append(ruin)
        return available
    
    def get_best_ruin_to_explore(self) -> Optional[Dict]:
        """Dapatkan ruin terbaik untuk diexplore"""
        available = self.get_available_ruins()
        
        relic_ruins = [r for r in available if r.get("contentType") == "relic"]
        pack_ruins = [r for r in available if r.get("contentType") == "pack"]
        
        relic_ruins.sort(key=lambda r: r.get("gauge", 0), reverse=True)
        pack_ruins.sort(key=lambda r: r.get("gauge", 0), reverse=True)
        
        if relic_ruins:
            return relic_ruins[0]
        elif pack_ruins:
            return pack_ruins[0]
        
        return None
    
    def can_explore_ruin(self) -> bool:
        """Cek apakah aman untuk explore (alert < 8)"""
        return self.alert_gauge < 8
    
    def get_ruin_explore_count(self, ruin_id: str) -> int:
        """Dapatkan jumlah explore yang sudah dilakukan di ruin"""
        ruin = self.ruin_cache.get(ruin_id, {})
        return ruin.get("gauge", 0)
    
    def mark_dead(self):
        """Tandai agent sudah mati"""
        self.is_dead = True
        self.is_alive = False
        self.is_finished = True
        logger.info(f"💀 YOU DIED! Survival: {self.survival_time}, Kills: {self.kills}")
    
    def mark_finished(self):
        """Tandai game selesai"""
        self.is_finished = True
        logger.info(f"🏆 Game finished. Survival: {self.survival_time}, Kills: {self.kills}")
    
    def get_self(self) -> Dict:
        return self.view.get("self", {})
    
    def get_region(self) -> Dict:
        return self.view.get("currentRegion", {})
    
    def get_enemies(self) -> List[Dict]:
        enemies = []
        for enemy in self.view.get("visibleAgents", []):
            if self._is_alive(enemy):
                enemies.append(enemy)
        for monster in self.view.get("visibleMonsters", []):
            if self._is_alive(monster):
                enemies.append(monster)
        return enemies
    
    def get_interactables(self) -> List[Dict]:
        region = self.get_region()
        return region.get("interactables", [])
    
    def get_connections(self) -> List[Dict]:
        """Dapatkan koneksi (untuk move) - selalu return list of dicts"""
        region = self.get_region()
        connections = region.get("connections", [])
        
        result = []
        for conn in connections:
            if isinstance(conn, str):
                result.append({"regionId": conn, "insideDeathZone": False, "safetyScore": 0.5})
            elif isinstance(conn, dict):
                result.append(conn)
            else:
                continue
        
        return result
    
    def get_cave_exit(self) -> Optional[Dict]:
        if not self.in_cave:
            return None
        for obj in self.get_interactables():
            if not isinstance(obj, dict):
                continue
            obj_type = str(obj.get("type", obj.get("kind", ""))).lower()
            if "cave" in obj_type and obj.get("isExit", False):
                return obj
        return None
    
    def hp_ratio(self) -> float:
        return self.hp / max(self.max_hp, 1)
    
    def is_low_hp(self, threshold: float = 0.25) -> bool:
        return self.hp_ratio() < threshold
    
    def is_very_low_hp(self, threshold: float = 0.15) -> bool:
        return self.hp_ratio() < threshold
    
    @staticmethod
    def _is_alive(obj: Dict) -> bool:
        if not isinstance(obj, dict):
            return False
        return obj.get("isAlive", False) is True and obj.get("hp", 0) > 0