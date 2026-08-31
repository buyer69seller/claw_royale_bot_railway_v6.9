# src/game/actions.py
"""Builder untuk berbagai action game"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class ActionBuilder:
    """Builder untuk berbagai jenis action"""
    
    @staticmethod
    def pickup(item) -> Optional[Dict]:
        """Build action pickup - FIXED"""
        if not item:
            return None
        
        if isinstance(item, str):
            return {"type": "pickup", "itemInstanceId": item}
        
        if isinstance(item, dict):
            item_id = (
                item.get("instanceId") or 
                item.get("itemInstanceId") or 
                item.get("id")
            )
            if item_id:
                return {"type": "pickup", "itemInstanceId": item_id}
        
        logger.warning(f"⚠️ Cannot pickup: no item id found in {item}")
        return None
    
    @staticmethod
    def attack(target: Dict) -> Optional[Dict]:
        target_id = target.get("agentId") or target.get("monsterId") or target.get("targetId") or target.get("id")
        if not target_id:
            return None
        return {"type": "attack", "targetId": target_id}
    
    @staticmethod
    def interact(obj: Dict) -> Optional[Dict]:
        obj_id = obj.get("interactableId") or obj.get("id")
        if not obj_id:
            return None
        return {"type": "interact", "interactableId": obj_id}
    
    @staticmethod
    def explore(obj: Dict) -> Optional[Dict]:
        obj_id = obj.get("interactableId") or obj.get("id")
        if not obj_id:
            return None
        return {"type": "explore", "interactableId": obj_id}
    
    @staticmethod
    def move(target) -> Optional[Dict]:
        if isinstance(target, dict):
            region_id = target.get("regionId")
        else:
            region_id = target
        if not region_id:
            return None
        return {"type": "move", "regionId": region_id}
    
    @staticmethod
    def use_item(item: Dict) -> Optional[Dict]:
        if not item:
            return None
        item_id = item.get("instanceId") or item.get("id")
        if not item_id:
            return None
        return {"type": "use", "itemInstanceId": item_id}
    
    @staticmethod
    def use_item_by_id(item_id: str) -> Optional[Dict]:
        if not item_id:
            return None
        return {"type": "use", "itemInstanceId": item_id}