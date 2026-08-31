# src/lifecycle/router.py
"""State router untuk menentukan tindakan berikutnya"""

import logging
from typing import Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

class GameState(str, Enum):
    NO_ACCOUNT = "NO_ACCOUNT"
    READY_FREE = "READY_FREE"
    READY_PAID = "READY_PAID"
    IN_GAME_FREE = "IN_GAME_FREE"
    IN_GAME_PAID = "IN_GAME_PAID"
    ERROR = "ERROR"
    IDLE = "IDLE"

class StateRouter:
    def __init__(self, rest_client):
        self.rest = rest_client
        self.current_state = GameState.IDLE
        self.live_games: Dict[str, Dict] = {}
    
    async def determine_state(self) -> GameState:
        try:
            logger.info("🔍 Determining game state...")
            
            account = await self.rest.get_account()
            logger.info(f"📡 Account data received: {account.get('id')}")
            
            readiness = account.get("readiness", {})
            current_games = account.get("currentGames", [])
            
            logger.info(f"📊 Current games: {len(current_games)}")
            logger.info(f"🔓 Free ready: {readiness.get('free', {}).get('ready', False)}")
            
            self.live_games = {}
            for game in current_games:
                entry_type = game.get("entryType")
                if entry_type and game.get("isAlive") and game.get("gameStatus") != "finished":
                    self.live_games[entry_type] = game
                    logger.info(f"🎮 Live game found: {entry_type}")
            
            if "free" in self.live_games:
                logger.info("✅ Free game live, resuming...")
                return GameState.IN_GAME_FREE
            
            if "paid" in self.live_games:
                logger.info("✅ Paid game live, resuming...")
                return GameState.IN_GAME_PAID
            
            free_ready = readiness.get("free", {}).get("ready", False)
            paid_ready = readiness.get("paid", {}).get("ready", False)
            
            logger.info(f"🔓 Free ready: {free_ready}, Paid ready: {paid_ready}")
            
            if not free_ready and not paid_ready:
                logger.info("🔄 No readiness - attempting direct WebSocket join...")
                return GameState.READY_FREE
            
            if free_ready:
                logger.info("✅ Free game ready, starting...")
                return GameState.READY_FREE
            
            if paid_ready:
                logger.info("✅ Paid game ready, starting...")
                return GameState.READY_PAID
            
            logger.info("⏳ No game available, idle...")
            return GameState.IDLE
            
        except Exception as e:
            logger.error(f"❌ Failed to determine state: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return GameState.ERROR
    
    async def resolve_state(self) -> Dict[str, Any]:
        state = await self.determine_state()
        self.current_state = state
        
        if state in [GameState.READY_FREE, GameState.IN_GAME_FREE]:
            entry_type = "free"
        elif state in [GameState.READY_PAID, GameState.IN_GAME_PAID]:
            entry_type = "paid"
        else:
            entry_type = "free"
        
        return {
            "state": state,
            "entry_type": entry_type,
            "action": self._get_action_for_state(state),
            "game": self.live_games.get(entry_type)
        }
    
    def _get_action_for_state(self, state: GameState) -> str:
        action_map = {
            GameState.READY_FREE: "start_free",
            GameState.READY_PAID: "start_paid",
            GameState.IN_GAME_FREE: "resume_free",
            GameState.IN_GAME_PAID: "resume_paid",
            GameState.IDLE: "idle",
            GameState.ERROR: "error",
            GameState.NO_ACCOUNT: "setup_account"
        }
        return action_map.get(state, "idle")