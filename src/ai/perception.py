# src/ai/perception.py
"""Perception Layer - Memahami lingkungan game dengan optimasi performa"""

import logging
import math
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class PerceivedEntity:
    id: str
    type: str
    position: Dict[str, float]
    hp: float
    max_hp: float
    is_alive: bool
    is_enemy: bool
    is_guardian: bool = False
    threat_score: float = 0.0
    value_score: float = 0.0
    distance: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerceivedState:
    turn: int
    self: PerceivedEntity
    hp_ratio: float
    in_cave: bool
    region: Dict[str, Any]
    enemies: List[PerceivedEntity] = field(default_factory=list)
    allies: List[PerceivedEntity] = field(default_factory=list)
    items: List[PerceivedEntity] = field(default_factory=list)
    interactables: List[PerceivedEntity] = field(default_factory=list)
    connections: List[PerceivedEntity] = field(default_factory=list)
    danger_level: float = 0.0
    opportunity_score: float = 0.0
    survival_potential: float = 1.0


class PerceptionEngine:
    MAX_ENEMY_DISTANCE = 20.0
    MAX_ITEM_DISTANCE = 10.0
    MAX_INTERACTABLE_DISTANCE = 10.0
    MAX_ENEMIES = 10
    MAX_ITEMS = 15
    MAX_INTERACTABLES = 10
    MAX_CONNECTIONS = 8
    
    def __init__(self):
        self.history = deque(maxlen=50)
        self.last_perception = None
        self._distance_cache: Dict[str, float] = {}
        self._last_self_pos: Tuple[float, float] = (0, 0)
        self._cache_clear_counter = 0
        self._stats = {
            "items_scanned": 0,
            "items_filtered": 0,
            "enemies_scanned": 0,
            "enemies_filtered": 0,
            "distance_cache_hits": 0,
            "distance_cache_misses": 0
        }
    
    def perceive(self, game_state) -> PerceivedState:
        view = game_state.view
        self_data = view.get("self", {})
        region = view.get("currentRegion", {})
        
        if not self_data:
            return self._empty_state()
        
        self_entity = self._perceive_self(self_data)
        
        self_x = self_entity.position.get("x", 0)
        self_y = self_entity.position.get("y", 0)
        self._last_self_pos = (self_x, self_y)
        
        self._cache_clear_counter += 1
        if self._cache_clear_counter > 50:
            self._distance_cache.clear()
            self._cache_clear_counter = 0
        
        enemies = self._perceive_enemies(view, self_entity)
        items = self._perceive_items(region, self_entity)
        interactables = self._perceive_interactables(region, self_entity)
        connections = self._perceive_connections(region, self_entity)
        
        danger_level = self._calculate_danger_level(enemies, self_entity, view)
        opportunity_score = self._calculate_opportunity(items, interactables, view)
        survival_potential = self._calculate_survival_potential(self_entity, enemies, region)
        
        state = PerceivedState(
            turn=game_state.turn,
            self=self_entity,
            hp_ratio=self_entity.hp / max(self_entity.max_hp, 1),
            in_cave=game_state.in_cave,
            region=region,
            enemies=enemies,
            items=items,
            interactables=interactables,
            connections=connections,
            danger_level=danger_level,
            opportunity_score=opportunity_score,
            survival_potential=survival_potential
        )
        
        self.history.append(state)
        self.last_perception = state
        
        if game_state.turn % 20 == 0:
            logger.debug(f"📊 Perception Stats: {self._stats}")
        
        return state
    
    def _empty_state(self) -> PerceivedState:
        empty_entity = PerceivedEntity(
            id="", type="self", position={"x": 0, "y": 0},
            hp=0, max_hp=1, is_alive=True, is_enemy=False
        )
        return PerceivedState(
            turn=0, self=empty_entity, hp_ratio=0,
            in_cave=False, region={},
            enemies=[], items=[], interactables=[], connections=[]
        )
    
    def _perceive_self(self, data: Dict) -> PerceivedEntity:
        return PerceivedEntity(
            id=data.get("id", ""),
            type="self",
            position={"x": float(data.get("x", 0)), "y": float(data.get("y", 0))},
            hp=float(data.get("hp", data.get("currentHp", 0))),
            max_hp=float(data.get("maxHp", data.get("maxHealth", 1))),
            is_alive=data.get("isAlive", True),
            is_enemy=False,
            metadata={
                "attack": float(data.get("attack", data.get("atk", 0))),
                "defense": float(data.get("defense", data.get("def", 0))),
                "speed": float(data.get("speed", 1)),
                "in_cave": data.get("inCave", False),
                "kills": data.get("kills", 0),
                "survival_time": data.get("survivalTime", 0)
            }
        )
    
    def _perceive_enemies(self, view: Dict, self_entity: PerceivedEntity) -> List[PerceivedEntity]:
        enemies = []
        self_x, self_y = self._last_self_pos
        
        agents = view.get("visibleAgents", [])
        self._stats["enemies_scanned"] += len(agents)
        
        for agent in agents:
            if not agent.get("isAlive", False):
                continue
            
            ax = float(agent.get("x", agent.get("position", {}).get("x", 0)))
            ay = float(agent.get("y", agent.get("position", {}).get("y", 0)))
            dx = ax - self_x
            dy = ay - self_y
            dist_sq = dx*dx + dy*dy
            
            if dist_sq > self.MAX_ENEMY_DISTANCE * self.MAX_ENEMY_DISTANCE:
                self._stats["enemies_filtered"] += 1
                continue
            
            distance = math.sqrt(dist_sq)
            enemy = self._create_enemy_entity(agent, "agent", self_entity, distance)
            if enemy:
                enemies.append(enemy)
        
        monsters = view.get("visibleMonsters", [])
        for monster in monsters:
            if not monster.get("isAlive", False):
                continue
            
            mx = float(monster.get("x", monster.get("position", {}).get("x", 0)))
            my = float(monster.get("y", monster.get("position", {}).get("y", 0)))
            dx = mx - self_x
            dy = my - self_y
            dist_sq = dx*dx + dy*dy
            
            if dist_sq > self.MAX_ENEMY_DISTANCE * self.MAX_ENEMY_DISTANCE:
                self._stats["enemies_filtered"] += 1
                continue
            
            distance = math.sqrt(dist_sq)
            enemy = self._create_enemy_entity(monster, "monster", self_entity, distance)
            if enemy:
                enemies.append(enemy)
        
        if len(enemies) > self.MAX_ENEMIES:
            enemies.sort(key=lambda e: (e.threat_score, -1/e.distance), reverse=True)
            enemies = enemies[:self.MAX_ENEMIES]
        
        return enemies
    
    def _create_enemy_entity(self, data: Dict, entity_type: str, self_entity: PerceivedEntity, distance: float) -> Optional[PerceivedEntity]:
        try:
            is_guardian = data.get("isGuardian", False) or str(data.get("kind", "")).lower() == "guardian"
            threat_score = self._calculate_threat_score(data, distance, is_guardian)
            
            return PerceivedEntity(
                id=data.get("agentId") or data.get("monsterId") or data.get("id", ""),
                type=entity_type,
                position={"x": float(data.get("x", data.get("position", {}).get("x", 0))),
                         "y": float(data.get("y", data.get("position", {}).get("y", 0)))},
                hp=float(data.get("hp", data.get("currentHp", 0))),
                max_hp=float(data.get("maxHp", data.get("maxHealth", 1))),
                is_alive=data.get("isAlive", True),
                is_enemy=True,
                is_guardian=is_guardian,
                threat_score=threat_score,
                distance=distance,
                metadata={
                    "attack": float(data.get("attack", data.get("atk", 0))),
                    "defense": float(data.get("defense", data.get("def", 0))),
                    "kind": data.get("kind", ""),
                    "name": data.get("name", "")
                }
            )
        except Exception as e:
            logger.debug(f"Failed to create enemy entity: {e}")
            return None
    
    def _calculate_threat_score(self, data: Dict, distance: float, is_guardian: bool) -> float:
        hp_ratio = float(data.get("hp", 0)) / max(float(data.get("maxHp", 1)), 1)
        attack = float(data.get("attack", data.get("atk", 0)))
        threat = (attack + 10) * (1 - hp_ratio + 0.3) / max(distance, 1)
        if is_guardian:
            threat *= 1.5
        return min(max(threat, 0), 100)
    
    def _perceive_items(self, region: Dict, self_entity: PerceivedEntity) -> List[PerceivedEntity]:
        items = []
        self_x, self_y = self._last_self_pos
        
        raw_items = region.get("items", [])
        self._stats["items_scanned"] += len(raw_items)
        
        for item in raw_items:
            try:
                pos_x = float(item.get("x", 0))
                pos_y = float(item.get("y", 0))
                dx = pos_x - self_x
                dy = pos_y - self_y
                dist_sq = dx*dx + dy*dy
                
                if dist_sq > self.MAX_ITEM_DISTANCE * self.MAX_ITEM_DISTANCE:
                    self._stats["items_filtered"] += 1
                    continue
                
                distance = math.sqrt(dist_sq)
                value_score = self._calculate_item_value(item)
                
                if value_score < 5 and distance > 5:
                    continue
                
                items.append(PerceivedEntity(
                    id=item.get("instanceId") or item.get("itemInstanceId") or item.get("id", ""),
                    type="item",
                    position={"x": pos_x, "y": pos_y},
                    hp=0,
                    max_hp=1,
                    is_alive=True,
                    is_enemy=False,
                    value_score=value_score,
                    distance=distance,
                    metadata={
                        "item_type": item.get("type", item.get("itemType", "")),
                        "heal": float(item.get("heal", item.get("healAmount", 0))),
                        "value": float(item.get("value", item.get("rarityValue", 0)))
                    }
                ))
            except Exception as e:
                pass
        
        if len(items) > self.MAX_ITEMS:
            items.sort(key=lambda x: x.value_score / max(x.distance, 0.1), reverse=True)
            items = items[:self.MAX_ITEMS]
        else:
            items.sort(key=lambda x: x.distance)
        
        return items
    
    def _calculate_item_value(self, item: Dict) -> float:
        item_type = str(item.get("type", item.get("itemType", ""))).lower()
        value = float(item.get("value", item.get("rarityValue", 0)))
        heal = float(item.get("heal", item.get("healAmount", 0)))
        
        score = value
        if heal > 0:
            score += heal * 5
        if any(k in item_type for k in ("weapon", "armor", "relic")):
            score += 50
        if "ep" in item_type:
            score += 20
        return score
    
    def _perceive_interactables(self, region: Dict, self_entity: PerceivedEntity) -> List[PerceivedEntity]:
        interactables = []
        self_x, self_y = self._last_self_pos
        
        for obj in region.get("interactables", []):
            try:
                pos_x = float(obj.get("x", 0))
                pos_y = float(obj.get("y", 0))
                dx = pos_x - self_x
                dy = pos_y - self_y
                dist_sq = dx*dx + dy*dy
                
                if dist_sq > self.MAX_INTERACTABLE_DISTANCE * self.MAX_INTERACTABLE_DISTANCE:
                    continue
                
                distance = math.sqrt(dist_sq)
                obj_type = str(obj.get("type", obj.get("kind", ""))).lower()
                
                value_score = 0
                if any(k in obj_type for k in ("medical", "supply", "cache", "watchtower")):
                    value_score = 80
                elif "ruin" in obj_type:
                    alert = region.get("alertGauge", 0)
                    value_score = 60 - max(0, alert - 6) * 10
                elif obj.get("isExit", False) and "cave" in obj_type:
                    value_score = 100
                
                if value_score < 30 and distance > 5:
                    continue
                
                interactables.append(PerceivedEntity(
                    id=obj.get("interactableId") or obj.get("id", ""),
                    type="interactable",
                    position={"x": pos_x, "y": pos_y},
                    hp=0,
                    max_hp=1,
                    is_alive=True,
                    is_enemy=False,
                    value_score=value_score,
                    distance=distance,
                    metadata={
                        "kind": obj_type,
                        "is_exit": obj.get("isExit", False),
                        "alert_gauge": region.get("alertGauge", 0)
                    }
                ))
            except Exception as e:
                pass
        
        if len(interactables) > self.MAX_INTERACTABLES:
            interactables.sort(key=lambda x: x.value_score / max(x.distance, 0.1), reverse=True)
            interactables = interactables[:self.MAX_INTERACTABLES]
        
        return interactables
    
    def _perceive_connections(self, region: Dict, self_entity: PerceivedEntity) -> List[PerceivedEntity]:
        connections = []
        
        for conn in region.get("connections", []):
            try:
                score = 30
                if isinstance(conn, dict):
                    score += float(conn.get("safetyScore", conn.get("zoneSafety", 0))) * 10
                    if conn.get("insideDeathZone") is True:
                        score -= 100
                
                connections.append(PerceivedEntity(
                    id=conn.get("regionId", ""),
                    type="connection",
                    position={"x": 0, "y": 0},
                    hp=0,
                    max_hp=1,
                    is_alive=True,
                    is_enemy=False,
                    value_score=score,
                    distance=0,
                    metadata=conn if isinstance(conn, dict) else {}
                ))
            except Exception as e:
                pass
        
        if len(connections) > self.MAX_CONNECTIONS:
            connections.sort(key=lambda x: x.value_score, reverse=True)
            connections = connections[:self.MAX_CONNECTIONS]
        
        return connections
    
    def _calculate_danger_level(self, enemies: List[PerceivedEntity], self_entity: PerceivedEntity, view: Dict) -> float:
        if not enemies:
            return 0.0
        
        nearby = [e for e in enemies if e.distance < 15]
        if not nearby:
            return 0.0
        
        if len(nearby) > 5:
            nearby.sort(key=lambda x: x.threat_score, reverse=True)
            nearby = nearby[:5]
        
        total_threat = sum(e.threat_score for e in nearby)
        hp_penalty = 1 + (1 - self_entity.hp / max(self_entity.max_hp, 1)) * 0.5
        nearby_factor = 1 + len(nearby) * 0.3
        guardian_factor = 1 + sum(1 for e in nearby if e.is_guardian) * 0.5
        
        danger = total_threat * hp_penalty * nearby_factor * guardian_factor
        
        return min(danger, 100)
    
    def _calculate_opportunity(self, items: List[PerceivedEntity], interactables: List[PerceivedEntity], view: Dict) -> float:
        close_items = [i for i in items if i.distance < 5]
        close_interact = [i for i in interactables if i.distance < 5]
        
        if not close_items and not close_interact:
            return 0.0
        
        item_value = sum(i.value_score / max(i.distance, 0.1) for i in close_items[:5])
        interactable_value = sum(i.value_score / max(i.distance, 0.1) for i in close_interact[:3])
        
        return min(item_value + interactable_value, 100)
    
    def _calculate_survival_potential(self, self_entity: PerceivedEntity, enemies: List[PerceivedEntity], region: Dict) -> float:
        hp_ratio = self_entity.hp / max(self_entity.max_hp, 1)
        hp_factor = hp_ratio
        
        nearby_enemies = [e for e in enemies if e.distance < 15]
        enemy_threat = sum(e.threat_score for e in nearby_enemies[:5])
        enemy_factor = max(0, 1 - enemy_threat / 100)
        
        items = region.get("items", [])
        healing_items = sum(1 for i in items[:10] if float(i.get("heal", i.get("healAmount", 0))) > 0)
        item_factor = min(1 + healing_items * 0.1, 2)
        
        guardian_nearby = any(e.is_guardian and e.distance < 15 for e in nearby_enemies)
        guardian_factor = 0.5 if guardian_nearby else 1
        
        potential = hp_factor * enemy_factor * item_factor * guardian_factor
        
        return min(max(potential, 0), 1)
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "history_length": len(self.history),
            "cache_size": len(self._distance_cache)
        }
    
    def reset_stats(self):
        self._stats = {
            "items_scanned": 0,
            "items_filtered": 0,
            "enemies_scanned": 0,
            "enemies_filtered": 0,
            "distance_cache_hits": 0,
            "distance_cache_misses": 0
        }