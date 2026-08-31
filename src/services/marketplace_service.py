# src/services/marketplace_service.py
"""Service untuk marketplace (optional)"""

import logging
from typing import Dict, Any, Optional, List

from ..client.rest_client import RestClient

logger = logging.getLogger(__name__)

class MarketplaceService:
    def __init__(self, rest_client: RestClient):
        self.rest = rest_client
    
    async def scan_listings(self, filters: Optional[Dict] = None) -> List[Dict]:
        try:
            listings = await self.rest.get_marketplace_listings(filters or {})
            return listings.get("items", [])
        except Exception as e:
            logger.error(f"Failed to scan marketplace: {e}")
            return []
    
    async def find_bargains(self, max_price: int = 1000) -> List[Dict]:
        try:
            listings = await self.scan_listings({"maxPrice": max_price, "sortBy": "price", "sortOrder": "asc"})
            bargains = []
            for item in listings:
                price = item.get("price", 0)
                tier = item.get("tier", 0)
                value_score = (tier * 100) / (price + 1)
                if value_score > 0.5:
                    bargains.append({**item, "valueScore": value_score})
            return bargains
        except Exception as e:
            logger.error(f"Failed to find bargains: {e}")
            return []
    
    async def buy_item(self, listing_id: str) -> bool:
        try:
            result = await self.rest.buy_marketplace_listing(listing_id)
            logger.info(f"Bought item {listing_id}: {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to buy item: {e}")
            return False