# src/services/auth_service.py
"""Service untuk authentication dan login"""

import logging
from typing import Dict, Any, Optional

from ..client.rest_client import RestClient
from ..client.ws_client import WSClient
from ..core.constants import JOIN_WS
from ..core.exceptions import AuthenticationError, AgentTokenRequiredError

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self, rest_client: RestClient):
        self.rest = rest_client
        self._account: Optional[Dict] = None
        self._agent_token: Optional[str] = None
    
    async def login(self) -> Dict[str, Any]:
        logger.info("🔐 Logging in to Claw Royale...")
        
        self._account = await self.rest.get_account()
        
        if not self._account:
            raise AuthenticationError("Failed to get account info")
        
        logger.info(f"✅ Logged in as: {self._account.get('name')}")
        logger.info(f"   Account ID: {self._account.get('id')}")
        logger.info(f"   Wallet: {self._account.get('walletAddress')}")
        
        readiness = self._account.get("readiness", {})
        logger.info(f"📊 Readiness:")
        logger.info(f"   - Wallet: {readiness.get('walletAddress')}")
        logger.info(f"   - Whitelist: {readiness.get('whitelistApproved')}")
        logger.info(f"   - Agent Token: {readiness.get('agentToken')}")
        logger.info(f"   - sMoltz: {readiness.get('sMoltzSufficient')}")
        
        if not readiness.get("agentToken"):
            logger.info("🔑 Agent token missing, registering...")
            await self.rest.ensure_agent_token()
            self._account = await self.rest.get_account()
        
        return self._account
    
    async def get_websocket_auth(self) -> Dict[str, str]:
        return {
            "Authorization": f"mr-auth {self.rest.api_key}",
            "X-Version": self.rest.version or "1.15.0"
        }
    
    def get_account(self) -> Optional[Dict]:
        return self._account
    
    def is_logged_in(self) -> bool:
        return self._account is not None