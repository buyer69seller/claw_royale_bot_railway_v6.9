# src/services/loadout_service.py
"""Service untuk manajemen loadout dengan Pre-Season 1 support"""

import logging
from typing import Dict, Any, Optional, List

from ..client.rest_client import RestClient
from ..core.constants import (
    MAIN_ONLY_PACKS,
    SUB_CAPABLE_PACKS,
    PACK_EFFECTS,
    RELIC_AFFIX_PRIORITY,
    RELIC_SLOTS,
    INVENTORY_CAPS,
    PACK_ATTENUATION
)

logger = logging.getLogger(__name__)

class LoadoutService:
    def __init__(self, rest_client: RestClient):
        self.rest = rest_client
        self._current_loadout = None
    
    async def get_current_loadout(self) -> Dict[str, Any]:
        if self._current_loadout:
            return self._current_loadout
        try:
            loadout = await self.rest.get_loadout()
            self._current_loadout = loadout
            return loadout
        except Exception as e:
            logger.warning(f"Could not get loadout: {e}")
            return {}
    
    async def is_full_set(self) -> bool:
        loadout = await self.get_current_loadout()
        has_main = bool(loadout.get("mainPack"))
        has_sub = bool(loadout.get("subPack"))
        relics = loadout.get("relics", [])
        return has_main and has_sub and len(relics) >= 3
    
    def is_main_only(self, pack_name: str) -> bool:
        return pack_name in MAIN_ONLY_PACKS
    
    def is_sub_capable(self, pack_name: str) -> bool:
        return pack_name in SUB_CAPABLE_PACKS
    
    def get_pack_effect(self, pack_name: str, slot: str = "main") -> Optional[Dict]:
        effects = PACK_EFFECTS.get(pack_name)
        if not effects:
            return None
        if slot == "main":
            return effects.get("main")
        else:
            return effects.get("sub")
    
    def get_sub_attenuation(self, pack_name: str) -> Dict[str, Any]:
        attenuation = PACK_ATTENUATION.get(pack_name, {})
        mode = attenuation.get("mode", "MULTIPLY_0_5")
        
        if mode == "MAIN_ONLY":
            return {
                "mode": "MAIN_ONLY",
                "can_use_sub": False,
                "description": "Cannot be placed in Sub slot",
                "priority_penalty": 0
            }
        elif mode == "MULTIPLY_0_5":
            factor = attenuation.get("sub_factor", 0.5)
            return {
                "mode": "MULTIPLY_0_5",
                "can_use_sub": True,
                "factor": factor,
                "description": f"Final value halved (×{factor})",
                "priority_penalty": 0.5
            }
        elif mode == "PARTIAL":
            sub_factors = attenuation.get("sub_factors", {})
            return {
                "mode": "PARTIAL",
                "can_use_sub": True,
                "factors": sub_factors,
                "description": "Only certain coefficients reduced",
                "priority_penalty": 0.3
            }
        elif mode == "SUB_VALUE":
            sub_effect = attenuation.get("sub_effect", {})
            return {
                "mode": "SUB_VALUE",
                "can_use_sub": True,
                "effect": sub_effect,
                "description": "Replaced with Sub-only value",
                "priority_penalty": 0.2
            }
        
        return {"mode": "UNKNOWN", "can_use_sub": True, "priority_penalty": 0.5}
    
    def get_pack_tier_effect(self, pack_name: str, tier: int, slot: str = "main") -> Dict:
        base_effect = self.get_pack_effect(pack_name, slot)
        if not base_effect:
            return {}
        
        tier_multiplier = {1: 1.0, 2: 0.8, 3: 0.6}.get(tier, 1.0)
        sub_info = self.get_sub_attenuation(pack_name)
        
        result = {}
        for key, value in base_effect.items():
            if isinstance(value, (int, float)):
                tiered_value = value * tier_multiplier
                if slot == "sub" and sub_info.get("mode") == "MULTIPLY_0_5":
                    tiered_value *= sub_info.get("factor", 0.5)
                result[key] = tiered_value
            else:
                result[key] = value
        
        return result
    
    def get_pack_tier_priority(self, pack_name: str, tier: int, slot: str = "main") -> float:
        tier_priority = {1: 3.0, 2: 2.0, 3: 1.0}.get(tier, 0)
        slot_bonus = 1.5 if slot == "main" else 1.0
        sub_info = self.get_sub_attenuation(pack_name)
        
        if sub_info.get("mode") == "MAIN_ONLY":
            return 0 if slot == "sub" else tier_priority * 2
        
        pack_bonus = self._get_pack_bonus(pack_name, slot)
        penalty = sub_info.get("priority_penalty", 0)
        if slot == "sub":
            slot_bonus *= (1 - penalty)
        
        return tier_priority * slot_bonus * pack_bonus
    
    def _get_pack_bonus(self, pack_name: str, slot: str) -> float:
        bonuses = {
            "Thorns": 1.3,
            "Heart of the Giant": 1.25,
            "Berserker": 1.2,
            "Double Attack": 1.15,
            "Last Stand": 1.15,
            "Iron Heart": 1.1,
            "Ruin Expert": 1.1,
            "Assassin": 1.2,
            "Goliath": 1.1,
            "Item Expert": 1.05,
            "Moltz Expert": 1.05
        }
        
        base_bonus = bonuses.get(pack_name, 1.0)
        if slot == "sub" and pack_name in ["Assassin", "Scout"]:
            return 0
        return base_bonus
    
    async def get_best_pack_for_slot(self, slot: str, excluded: List[str] = None) -> Optional[Dict]:
        inventory = await self.rest.get_inventory()
        packs = inventory.get("packs", [])
        
        if excluded is None:
            excluded = []
        
        best_pack = None
        best_score = 0
        
        for pack in packs:
            pack_name = pack.get("name", "")
            if pack_name in excluded:
                continue
            
            if slot == "main":
                if not self.is_main_only(pack_name) and not self.is_sub_capable(pack_name):
                    continue
            else:
                sub_info = self.get_sub_attenuation(pack_name)
                if not sub_info.get("can_use_sub", False):
                    continue
            
            tier = pack.get("tier", 0)
            score = self.get_pack_tier_priority(pack_name, tier, slot)
            
            if score > best_score:
                best_score = score
                best_pack = pack
        
        return best_pack
    
    async def get_best_pack_combo(self) -> Dict[str, Any]:
        inventory = await self.rest.get_inventory()
        packs = inventory.get("packs", [])
        
        main_packs = [p for p in packs if self.is_sub_capable(p.get("name", "")) or self.is_main_only(p.get("name", ""))]
        sub_packs = [p for p in packs if self.is_sub_capable(p.get("name", ""))]
        
        best_combo = {
            "main": None,
            "sub": None,
            "score": 0,
            "relics": []
        }
        
        for main in main_packs:
            main_name = main.get("name", "")
            main_tier = main.get("tier", 0)
            main_score = self.get_pack_tier_priority(main_name, main_tier, "main")
            
            for sub in sub_packs:
                sub_name = sub.get("name", "")
                sub_tier = sub.get("tier", 0)
                
                if main_name == sub_name:
                    continue
                
                sub_score = self.get_pack_tier_priority(sub_name, sub_tier, "sub")
                synergy = self._evaluate_synergy(main, sub)
                
                total_score = main_score + sub_score + synergy
                
                if total_score > best_combo["score"]:
                    best_combo["main"] = main
                    best_combo["sub"] = sub
                    best_combo["score"] = total_score
        
        relics = inventory.get("relics", [])
        best_relics = await self.get_best_relics(3)
        best_combo["relics"] = best_relics
        
        return best_combo
    
    def _evaluate_synergy(self, main: Dict, sub: Dict) -> float:
        main_name = main.get("name", "")
        sub_name = sub.get("name", "")
        main_tier = main.get("tier", 0)
        sub_tier = sub.get("tier", 0)
        
        score = 0
        score += main_tier * 10
        score += sub_tier * 8
        
        synergies = [
            ("Thorns", "Heart of the Giant", 30),
            ("Berserker", "Last Stand", 25),
            ("Item Expert", "Moltz Expert", 20),
            ("Goliath", "Double Attack", 15),
            ("Ranged", "Sword Master", 10),
            ("Assassin", "Pickpocket", 15),
            ("Ruin Expert", "Scout", 10),
        ]
        
        for pack1, pack2, bonus in synergies:
            if (pack1 in main_name and pack2 in sub_name) or (pack1 in sub_name and pack2 in main_name):
                tier_bonus = 1 + (main_tier + sub_tier) * 0.05
                score += bonus * tier_bonus
        
        return score
    
    async def get_best_relics(self, count: int = 3) -> List[Dict]:
        inventory = await self.rest.get_inventory()
        relics = inventory.get("relics", [])
        
        if not relics:
            return []
        
        scored_relics = []
        for relic in relics:
            score = self._score_relic(relic)
            slot = self._get_relic_slot(relic)
            scored_relics.append({
                "relic": relic,
                "score": score,
                "slot": slot,
                "affix_count": len(relic.get("affixes", []))
            })
        
        scored_relics.sort(key=lambda x: (x["score"], x["affix_count"]), reverse=True)
        best = scored_relics[:count]
        
        for i, r in enumerate(best):
            relic = r["relic"]
            affixes = relic.get("affixes", [])
            affix_names = [a.get("stat", "") for a in affixes]
            logger.info(f"🔮 Relic {i+1}: {relic.get('name', 'unknown')} "
                       f"(score: {r['score']:.0f}, affixes: {affix_names})")
        
        return [r["relic"] for r in best]
    
    def _score_relic(self, relic: Dict) -> float:
        affixes = relic.get("affixes", [])
        tier = relic.get("tier", 0)
        
        score = tier * 10
        
        for affix in affixes:
            stat = affix.get("stat", "")
            value = affix.get("value", 0)
            priority = RELIC_AFFIX_PRIORITY.get(stat, 1)
            
            if value > 0:
                score += value * priority * 1.5
            else:
                score += value * priority * 0.5
        
        affix_count = len(affixes)
        if affix_count >= 3:
            score *= 1.3
        elif affix_count >= 2:
            score *= 1.15
        
        return max(score, -100)
    
    def _get_relic_slot(self, relic: Dict) -> int:
        name = relic.get("name", "")
        for gem_name, slot in RELIC_SLOTS.items():
            if gem_name in name:
                return slot
        return 0
    
    def _get_relic_display_name(self, relic: Dict) -> str:
        name = relic.get("name", "Unknown")
        affixes = relic.get("affixes", [])
        
        if not affixes:
            return name
        
        affix_names = []
        for affix in affixes:
            stat = affix.get("stat", "")
            value = affix.get("value", 0)
            
            from ..core.constants import RELIC_AFFIXES
            affix_data = RELIC_AFFIXES.get(stat)
            if affix_data:
                if value >= 0:
                    affix_names.append(affix_data["positive"]["name"])
                else:
                    affix_names.append(affix_data["negative"]["name"])
        
        return " ".join(affix_names + [name])
    
    def get_relic_farming_priority(self, current_relics: List[Dict]) -> Dict[str, Any]:
        if not current_relics:
            return {
                "priority": "high",
                "reason": "No relics equipped",
                "target_slots": [0, 1, 2]
            }
        
        equipped_slots = set()
        for relic in current_relics:
            slot = self._get_relic_slot(relic)
            equipped_slots.add(slot)
        
        missing_slots = [s for s in range(3) if s not in equipped_slots]
        
        if missing_slots:
            return {
                "priority": "high",
                "reason": f"Missing slots: {missing_slots}",
                "target_slots": missing_slots
            }
        
        avg_score = sum(self._score_relic(r) for r in current_relics) / max(len(current_relics), 1)
        
        if avg_score < 30:
            return {
                "priority": "medium",
                "reason": f"Low quality relics (avg score: {avg_score:.0f})",
                "target_slots": [0, 1, 2]
            }
        
        return {
            "priority": "low",
            "reason": f"Good relics equipped (avg score: {avg_score:.0f})",
            "target_slots": []
        }
    
    async def get_inventory_status(self) -> Dict[str, Any]:
        inventory = await self.rest.get_inventory()
        
        relics = inventory.get("relics", [])
        packs = inventory.get("packs", [])
        items = inventory.get("items", [])
        
        return {
            "relics": {
                "count": len(relics),
                "cap": INVENTORY_CAPS["lobby_relics"],
                "remaining": INVENTORY_CAPS["lobby_relics"] - len(relics),
                "items": relics
            },
            "packs": {
                "count": len(packs),
                "cap": INVENTORY_CAPS["lobby_packs"],
                "remaining": INVENTORY_CAPS["lobby_packs"] - len(packs),
                "items": packs
            },
            "items": {
                "count": len(items),
                "cap": INVENTORY_CAPS["items"],
                "remaining": INVENTORY_CAPS["items"] - len(items),
                "items": items
            }
        }
    
    async def optimize_loadout(self) -> Dict[str, Any]:
        try:
            best = await self.get_best_pack_combo()
            current = await self.get_current_loadout()
            
            result = {"changes": [], "current": current, "suggested": best}
            
            if best["main"] and best["main"].get("id") != current.get("mainPack", {}).get("id"):
                await self.rest.equip_main_pack(best["main"]["id"])
                main_name = best["main"].get("name", "unknown")
                main_tier = best["main"].get("tier", 0)
                result["changes"].append(f"Main: {main_name} (T{main_tier})")
            
            if best["sub"] and best["sub"].get("id") != current.get("subPack", {}).get("id"):
                await self.rest.equip_sub_pack(best["sub"]["id"])
                sub_name = best["sub"].get("name", "unknown")
                sub_tier = best["sub"].get("tier", 0)
                sub_info = self.get_sub_attenuation(sub_name)
                result["changes"].append(f"Sub: {sub_name} (T{sub_tier}) - {sub_info.get('description', '')}")
            
            current_relic_ids = [r.get("id") for r in current.get("relics", [])]
            for relic in best["relics"]:
                if relic.get("id") not in current_relic_ids:
                    slot = self._get_relic_slot(relic)
                    await self.rest.equip_relic(relic["id"])
                    display_name = self._get_relic_display_name(relic)
                    result["changes"].append(f"Relic slot {slot}: {display_name}")
            
            self._current_loadout = None
            await self.get_current_loadout()
            
            logger.info(f"📊 Pack synergy score: {best['score']:.0f}")
            
            relic_scores = [self._score_relic(r) for r in best.get("relics", [])]
            if relic_scores:
                logger.info(f"🔮 Relic scores: {relic_scores}")
            
            return result
            
        except Exception as e:
            logger.debug(f"Loadout optimization skipped: {e}")
            return {"error": str(e), "changes": []}