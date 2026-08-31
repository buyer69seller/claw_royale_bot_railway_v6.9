# src/lifecycle/driver.py
"""Driver utama dengan Hybrid AI + RL + Scan & Clear + Region Tracking"""

import asyncio
import logging
import json
from typing import Optional, Dict, Any, Set

from websockets.exceptions import ConnectionClosed

from ..client.rest_client import RestClient
from ..client.ws_client import WSClient
from ..game.state import GameState
from ..game.actions import ActionBuilder
from ..strategy.engine import StrategyEngine
from ..strategy.scan_clear import ScanClearStrategy
from .router import StateRouter
from .version_manager import VersionManager
from ..core.exceptions import (
    AgentDeadError,
    ResumeTargetDeadError,
    NotSelectedError,
    AgentTokenRequiredError
)
from ..core.constants import (
    MIN_RETRY_DELAY,
    MAX_RETRY_DELAY,
    RETRY_BACKOFF_MULTIPLIER,
    JOIN_WS,
    ACTION_INTERVAL_SECONDS
)
from ..ai.hybrid_engine import HybridAIEngine
from ..ai.knowledge import KnowledgeBase

logger = logging.getLogger(__name__)


class Driver:
    def __init__(self, rest_client: RestClient):
        self.rest = rest_client
        self.router = StateRouter(rest_client)
        self.version_mgr = VersionManager(rest_client.api_key)

        self.ai = HybridAIEngine()
        self.knowledge: Optional[KnowledgeBase] = None
        self.auth_service = None

        self.strategy = StrategyEngine()
        self.scan_clear = ScanClearStrategy()
        self.strategy_mode = "hybrid"
        self._pack_modifiers_loaded = False

        self.current_game: Optional[GameState] = None
        self.delay = MIN_RETRY_DELAY
        self.game_count = 0
        self.ai_enabled = True

        self.start_time = None
        self.total_actions = 0
        self.successful_actions = 0
        
        self._last_action_time = 0
        
        self._rl_action_tracking: Dict[str, Any] = {
            "action": None,
            "state": None,
            "timestamp": 0,
            "success": False
        }
        self._rl_reward_buffer = []
        
        self._visited_regions: Set[str] = set()
        self._region_visit_count: Dict[str, int] = {}
        self._current_region_id: Optional[str] = None
        self._region_loop_detected: bool = False

    def set_strategy_mode(self, mode: str):
        if mode in ["hybrid", "scan_clear"]:
            self.strategy_mode = mode
            logger.info(f"🔄 Strategy mode changed to: {mode}")
            if mode == "scan_clear":
                self.scan_clear.reset()
        else:
            logger.warning(f"⚠️ Unknown strategy mode: {mode}, keeping current")

    async def run(self):
        logger.info("🚀 Driver run() started!")
        self.delay = MIN_RETRY_DELAY
        self.start_time = __import__('time').time()
        logger.info(f"⏰ Start time: {self.start_time}")

        loop_count = 0

        while True:
            loop_count += 1
            logger.info(f"🔄 Driver loop iteration #{loop_count}")

            try:
                logger.info("📥 Checking version...")
                await self.version_mgr.ensure_current(self.rest._session)
                logger.info(f"✅ Version: {self.version_mgr.version}")

                logger.info("🔍 Determining game state...")
                state_info = await self.router.resolve_state()
                logger.info(f"📊 State: {state_info['state']} -> {state_info['action']}")

                if state_info["action"] in ["start_free", "start_paid"]:
                    logger.info(f"🎮 Attempting to join game: {state_info['action']}")
                    await self._start_game(state_info["entry_type"])
                elif state_info["action"] in ["resume_free", "resume_paid"]:
                    logger.info(f"🔄 Attempting to resume game: {state_info['action']}")
                    await self._resume_game(state_info["entry_type"])
                elif state_info["action"] == "idle":
                    logger.info("⏳ Idle, waiting for game...")
                    await asyncio.sleep(5)
                elif state_info["action"] == "error":
                    logger.warning("⚠️ Error state, waiting...")
                    await asyncio.sleep(10)
                else:
                    logger.warning(f"⚠️ Unknown action: {state_info['action']}")
                    await asyncio.sleep(2)

                self.delay = MIN_RETRY_DELAY

            except ResumeTargetDeadError as e:
                logger.warning(f"🔄 Resume target dead: {e}, re-dialing...")
                await asyncio.sleep(1)
                self.delay = MIN_RETRY_DELAY
                continue

            except ConnectionClosed as e:
                logger.warning(f"🔌 WebSocket closed: {e.code} - {e.reason}")
                
                if e.code == 1013:
                    logger.info("🔄 Resume target dead, starting new game...")
                    self.current_game = None
                    self._reset_region_tracking()
                    await asyncio.sleep(2)
                    continue
                elif e.code == 4008:
                    logger.warning("⏳ Rate limited, waiting 10s...")
                    await asyncio.sleep(10)
                    self.delay = MIN_RETRY_DELAY
                    continue
                elif e.code in (4030, 4031):
                    logger.info("🔄 Agent in game or game full, retrying...")
                    await asyncio.sleep(3)
                    continue
                elif e.code == 4032:
                    logger.info("💀 Agent dead (from close code), restarting...")
                    self.current_game = None
                    self._reset_region_tracking()
                    await asyncio.sleep(2)
                    continue
                else:
                    if e.code in (1013, 4008, 4030, 4031):
                        await asyncio.sleep(3)
                    else:
                        await asyncio.sleep(self.delay)
                        self.delay = min(self.delay * RETRY_BACKOFF_MULTIPLIER, MAX_RETRY_DELAY)

            except AgentDeadError:
                logger.info("💀 Agent died, restarting...")
                if self.current_game and self.knowledge:
                    self.knowledge.record_outcome("death", {
                        "kills": self.current_game.kills,
                        "survival_time": self.current_game.survival_time
                    })
                self.current_game = None
                self.strategy.reset_rejection_counter()
                self.scan_clear.reset()
                self._reset_region_tracking()
                self.ai.stats = {
                    "decisions_made": 0,
                    "ai_decisions": 0,
                    "heuristic_decisions": 0,
                    "survival_priority": 0,
                    "kill_priority": 0,
                    "loot_priority": 0,
                    "explore_priority": 0
                }
                self._stuck_counter = 0
                self._last_hp = 0
                self._last_turn = 0
                await asyncio.sleep(1)
                self.delay = MIN_RETRY_DELAY
                logger.info("🔄 Force rejoining new game...")
                continue

            except NotSelectedError:
                logger.info("❌ Not selected, retrying...")
                await asyncio.sleep(2)
                self.delay = MIN_RETRY_DELAY

            except AgentTokenRequiredError:
                logger.warning("🔑 Agent token required! Trying to register...")
                if self.auth_service:
                    await self.auth_service.rest.ensure_agent_token()
                await asyncio.sleep(2)
                self.delay = MIN_RETRY_DELAY

            except Exception as e:
                logger.exception(f"💥 Driver error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await asyncio.sleep(self.delay)
                self.delay = min(self.delay * RETRY_BACKOFF_MULTIPLIER, MAX_RETRY_DELAY)

    def _reset_region_tracking(self):
        self._visited_regions.clear()
        self._region_visit_count.clear()
        self._current_region_id = None
        self._region_loop_detected = False
        logger.debug("🗺️ Region tracking reset for new game")

    def _track_region(self, region_id: str):
        if not region_id:
            return
        
        self._visited_regions.add(region_id)
        self._region_visit_count[region_id] = self._region_visit_count.get(region_id, 0) + 1
        self._current_region_id = region_id
        
        visit_count = self._region_visit_count[region_id]
        if visit_count > 3:
            self._region_loop_detected = True
            logger.warning(f"⚠️ Region {region_id[:8]} visited {visit_count}x - possible loop!")
        else:
            self._region_loop_detected = False

    async def _load_pack_modifiers(self):
        try:
            loadout = await self.rest.get_loadout()
            main_pack = loadout.get("mainPack", {})
            sub_pack = loadout.get("subPack", {})
            
            self.strategy.set_pack_modifiers(main_pack, sub_pack)
            self._pack_modifiers_loaded = True
            
            if main_pack:
                logger.info(f"📦 Main Pack: {main_pack.get('name', 'unknown')} (T{main_pack.get('tier', 0)})")
            if sub_pack:
                logger.info(f"📦 Sub Pack: {sub_pack.get('name', 'unknown')} (T{sub_pack.get('tier', 0)})")
            
            relics = loadout.get("relics", [])
            logger.info(f"📦 Relics: {len(relics)} equipped")
            
            return True
            
        except Exception as e:
            logger.debug(f"Failed to load pack modifiers: {e}")
            self._pack_modifiers_loaded = False
            return False

    async def _start_game(self, entry_type: str):
        logger.info(f"🎮 Joining {entry_type} game...")
        logger.info(f"🔑 API Key: {self.rest.api_key[:10]}...")
        
        self._reset_region_tracking()
        logger.info("🗺️ Region tracking reset for new game")

        try:
            await self._load_pack_modifiers()
            
            if not self.auth_service:
                from ..services.auth_service import AuthService
                self.auth_service = AuthService(self.rest)
                logger.info("✅ Auth service initialized")

            headers = await self.auth_service.get_websocket_auth()
            logger.info(f"📨 Headers: {headers}")

            import websockets
            import json
            from ..core.constants import JOIN_WS

            logger.info(f"🔗 Connecting to {JOIN_WS}...")

            connection = await websockets.connect(
                JOIN_WS,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5
            )
            logger.info("✅ WebSocket connected!")

            welcome = json.loads(await connection.recv())
            decision = welcome.get("decision")
            logger.info(f"📨 Welcome decision: {decision}")

            hello = {"type": "hello", "entryType": entry_type}
            if entry_type == "paid":
                hello["mode"] = "offchain"
            await connection.send(json.dumps(hello))
            logger.info(f"📤 Sent hello: {entry_type}")

            while True:
                msg = json.loads(await connection.recv())
                msg_type = msg.get("type")
                logger.info(f"📨 Received: {msg_type}")

                if msg_type in ("assigned", "joined"):
                    self.current_game = GameState(entry_type=entry_type)
                    self.current_game.game_id = msg.get("gameId")
                    self.game_count += 1
                    logger.info(f"✅ {msg_type} to game {self.current_game.game_id}")

                    ws = WSClient(self.rest.api_key, self.rest.version)
                    ws._ws = connection

                    await self._play_game(ws)
                    return

                elif msg_type == "not_selected":
                    logger.warning("❌ Not selected for game")
                    await asyncio.sleep(2)
                    return

                elif msg_type == "queued":
                    logger.info("⏳ Queued, waiting for match...")
                    continue

                elif msg_type == "waiting":
                    logger.info("⏳ Waiting for game...")
                    continue

                elif msg_type == "error":
                    error = msg.get("error", {})
                    code = error.get("code")
                    message = error.get("message", "")
                    logger.error(f"❌ Server error: {code} - {message}")

                    if code == "AGENT_TOKEN_REQUIRED":
                        raise AgentTokenRequiredError("Agent token required!")
                    if code == "BLOCKED":
                        logger.warning("⛔ Account blocked - check API key")
                        await asyncio.sleep(5)
                        return

                    raise RuntimeError(f"Error from server: {msg}")

                else:
                    logger.debug(f"📨 Unknown message: {msg_type}")

        except Exception as e:
            logger.error(f"❌ Failed to join game: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def _resume_game(self, entry_type: str):
        logger.info(f"🔄 Resuming {entry_type} game...")
        
        try:
            await self._load_pack_modifiers()
        except Exception as e:
            logger.debug(f"Failed to load pack modifiers: {e}")
        
        try:
            await self._start_game(entry_type)
        except ResumeTargetDeadError:
            logger.info(f"{entry_type} resume target dead, re-dialing...")
            raise
        except Exception as e:
            logger.error(f"Failed to resume game: {e}")
            raise

    async def _rejoin_game(self, entry_type: str):
        logger.info(f"🔄 Attempting to REJOIN {entry_type} game...")
        
        try:
            await self._load_pack_modifiers()
        except Exception as e:
            logger.debug(f"Failed to load pack modifiers: {e}")
        
        try:
            account = await self.rest.get_account()
            current_games = account.get("currentGames", [])
            
            live_game = None
            for game in current_games:
                if game.get("entryType") == entry_type and game.get("isAlive") and game.get("gameStatus") != "finished":
                    live_game = game
                    break
            
            if not live_game:
                logger.info("ℹ️ No live game found, starting new game...")
                await self._start_game(entry_type)
                return
            
            logger.info(f"✅ Found live game: {live_game.get('gameId')}")
            logger.info(f"   - Entry Type: {live_game.get('entryType')}")
            logger.info(f"   - Is Alive: {live_game.get('isAlive')}")
            logger.info(f"   - Status: {live_game.get('gameStatus')}")
            
            if not self.auth_service:
                from ..services.auth_service import AuthService
                self.auth_service = AuthService(self.rest)
            
            headers = await self.auth_service.get_websocket_auth()
            
            import websockets
            import json
            from ..core.constants import JOIN_WS
            
            logger.info(f"🔗 Reconnecting to {JOIN_WS}...")
            
            connection = await websockets.connect(
                JOIN_WS,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5
            )
            logger.info("✅ WebSocket reconnected!")
            
            welcome = json.loads(await connection.recv())
            decision = welcome.get("decision")
            logger.info(f"📨 Welcome decision: {decision}")
            
            hello = {"type": "hello", "entryType": entry_type}
            if entry_type == "paid":
                hello["mode"] = "offchain"
            await connection.send(json.dumps(hello))
            logger.info(f"📤 Sent hello: {entry_type}")
            
            while True:
                msg = json.loads(await connection.recv())
                msg_type = msg.get("type")
                logger.info(f"📨 Received: {msg_type}")
                
                if msg_type in ("assigned", "joined"):
                    self.current_game = GameState(entry_type=entry_type)
                    self.current_game.game_id = msg.get("gameId")
                    logger.info(f"✅ REJOIN success! {msg_type} to game {self.current_game.game_id}")
                    
                    ws = WSClient(self.rest.api_key, self.rest.version)
                    ws._ws = connection
                    
                    await self._play_game(ws)
                    return
                    
                elif msg_type == "queued":
                    logger.info("⏳ Queued, waiting for match...")
                    continue
                    
                elif msg_type == "waiting":
                    logger.info("⏳ Waiting for game...")
                    continue
                    
                elif msg_type == "error":
                    error = msg.get("error", {})
                    code = error.get("code")
                    message = error.get("message", "")
                    logger.error(f"❌ Server error: {code} - {message}")
                    
                    if code == "GAME_NOT_FOUND":
                        logger.info("ℹ️ Game not found, starting new game...")
                        await self._start_game(entry_type)
                        return
                    
                    raise RuntimeError(f"Error from server: {msg}")
                    
                else:
                    logger.debug(f"📨 Unknown message: {msg_type}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to rejoin game: {e}")
            logger.info("🔄 Falling back to new game...")
            await self._start_game(entry_type)

    async def _play_game(self, ws: WSClient):
        logger.info("🎮 Starting Hybrid AI-powered gameplay loop...")
        logger.info("🧠 Hybrid AI = AI Auto-Pilot + Competitive v7 + RL")
        logger.info("👻 Only detecting OWN death, ignoring other agents")
        logger.info("🗺️ Ruin & Alert monitoring active")
        logger.info("🗺️ Region tracking active - avoiding loops")

        last_action_time = __import__('time').time()
        no_action_timeout = 120
        last_view_time = __import__('time').time()
        view_timeout = 90
        stuck_counter = 0
        last_hp = 0
        last_turn = 0
        
        last_ping_time = __import__('time').time()
        ping_interval = 30

        while True:
            try:
                current_time = __import__('time').time()
                if current_time - last_ping_time > ping_interval:
                    try:
                        await ws.send({"type": "ping"})
                        last_ping_time = current_time
                        logger.debug("📤 Sent ping")
                    except Exception as e:
                        logger.debug(f"Ping failed: {e}")

                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg_type = msg.get("type")

                if msg_type in ("agent_view", "turn_advanced", "action_sync"):
                    last_view_time = __import__('time').time()
                    
                    if msg_type == "agent_view":
                        view = msg.get("view", {})
                        region = view.get("currentRegion", {})
                        region_id = region.get("id")
                        if region_id:
                            self._track_region(region_id)

                current_time = __import__('time').time()
                if current_time - last_view_time > view_timeout:
                    logger.warning(f"⏰ No view for {view_timeout}s, attempting REJOIN...")
                    try:
                        if self.current_game:
                            entry_type = self.current_game.entry_type
                            await self._rejoin_game(entry_type)
                            return
                        else:
                            await self._start_game("free")
                            return
                    except Exception as e:
                        logger.error(f"❌ Rejoin failed: {e}")
                        raise AgentDeadError(f"View timeout - rejoin failed: {e}")

                if msg_type == "agent_died":
                    if msg.get("meta", {}).get("youDied") is True:
                        self.current_game.mark_dead()
                        if self.knowledge:
                            self.knowledge.record_outcome("death", {
                                "kills": self.current_game.kills,
                                "survival_time": self.current_game.survival_time
                            })
                        logger.info(f"💀 YOU DIED! Survival: {self.current_game.survival_time}, Kills: {self.current_game.kills}")
                        raise AgentDeadError("You died!")
                    continue

                if msg_type == "game_settled":
                    self.current_game.mark_finished()
                    winners = msg.get("winners", [])
                    logger.info(f"🏆 Game settled! Winners: {len(winners)}")
                    if self.knowledge:
                        self.knowledge.record_outcome("win", {
                            "kills": self.current_game.kills,
                            "survival_time": self.current_game.survival_time
                        })
                    self._log_hybrid_stats()
                    break

                if msg_type == "game_ended":
                    self.current_game.mark_finished()
                    placement = msg.get("placement")
                    logger.info(f"🏆 Game ended! Placement: {placement}")
                    if self.knowledge and placement and placement <= 5:
                        self.knowledge.record_outcome("win", {
                            "kills": self.current_game.kills,
                            "survival_time": self.current_game.survival_time
                        })
                    self._log_hybrid_stats()
                    break

                if msg_type == "can_act_changed":
                    self.current_game.can_act = bool(msg.get("canAct"))
                    if self.current_game.can_act:
                        last_action_time = current_time
                    continue

                if msg_type in ("agent_view", "turn_advanced"):
                    view = msg.get("view", {})
                    reason = msg.get("reason", "sync")

                    if view:
                        self.current_game.update_view(view, reason)

                        if not self.current_game.is_alive:
                            logger.info("💀 Agent is dead (from view), restarting...")
                            if self.knowledge:
                                self.knowledge.record_outcome("death", {
                                    "kills": self.current_game.kills,
                                    "survival_time": self.current_game.survival_time
                                })
                            raise AgentDeadError("Agent dead (from view)")

                        if self.current_game.hp <= 0:
                            logger.info("💀 Agent HP is 0, restarting...")
                            if self.knowledge:
                                self.knowledge.record_outcome("death", {
                                    "kills": self.current_game.kills,
                                    "survival_time": self.current_game.survival_time
                                })
                            raise AgentDeadError("Agent HP is 0")

                        if last_hp == self.current_game.hp and last_turn == self.current_game.turn:
                            stuck_counter += 1
                            if stuck_counter > 10:
                                logger.warning(f"⚠️ Game stuck for {stuck_counter} turns, attempting rejoin...")
                                try:
                                    await self._rejoin_game(self.current_game.entry_type)
                                    return
                                except Exception as e:
                                    logger.error(f"❌ Rejoin on stuck failed: {e}")
                                    raise AgentDeadError("Game stuck - rejoin failed")
                        else:
                            stuck_counter = 0
                        last_hp = self.current_game.hp
                        last_turn = self.current_game.turn

                        can_act = msg.get("canAct", self.current_game.can_act)
                        await self._act(ws, can_act)

                        if can_act:
                            last_action_time = current_time
                    continue

                if msg_type == "action_sync":
                    view = msg.get("view", {})
                    if view:
                        self.current_game.update_view(view, "action_sync")
                        if not self.current_game.is_alive:
                            logger.info("💀 Agent is dead (from action_sync), restarting...")
                            if self.knowledge:
                                self.knowledge.record_outcome("death", {
                                    "kills": self.current_game.kills,
                                    "survival_time": self.current_game.survival_time
                                })
                            raise AgentDeadError("Agent dead (from action_sync)")
                    self.current_game.can_act = bool(msg.get("canAct", self.current_game.can_act))
                    if self.current_game.can_act:
                        last_action_time = current_time
                    continue

                if msg_type == "action_rejected":
                    view = msg.get("view", {})
                    if view:
                        self.current_game.update_view(view, "action_rejected")
                        if not self.current_game.is_alive:
                            logger.info("💀 Agent is dead (from action_rejected), restarting...")
                            if self.knowledge:
                                self.knowledge.record_outcome("death", {
                                    "kills": self.current_game.kills,
                                    "survival_time": self.current_game.survival_time
                                })
                            raise AgentDeadError("Agent dead (from action_rejected)")
                    self.current_game.can_act = bool(msg.get("canAct", self.current_game.can_act))
                    if view and self.current_game.is_alive:
                        await self._act(ws, self.current_game.can_act)
                    continue

                if msg_type == "action_result":
                    self.current_game.can_act = bool(msg.get("canAct", self.current_game.can_act))
                    error = msg.get("error")
                    action = msg.get("action")

                    if action:
                        action_type = action.get("type", "")
                        item_id = action.get("itemInstanceId")
                        
                        if error:
                            self._rl_action_tracking["success"] = False
                            if self.ai and hasattr(self.ai, '_update_rl_reward'):
                                self.ai._update_rl_reward(self.current_game, action_type, False)
                            logger.debug(f"❌ RL: Action {action_type} failed")
                        else:
                            self._rl_action_tracking["success"] = True
                            if self.ai and hasattr(self.ai, '_update_rl_reward'):
                                self.ai._update_rl_reward(self.current_game, action_type, True)
                            logger.debug(f"✅ RL: Action {action_type} succeeded")

                    if action and action.get("type") == "pickup":
                        item_id = action.get("itemInstanceId")
                        if error:
                            if item_id:
                                self.current_game.mark_item_attempted(item_id)
                                self.current_game.mark_item_collected(item_id)
                                logger.debug(f"❌ Pickup failed for {item_id[:8]}, marked as collected")
                        else:
                            if item_id:
                                self.current_game.mark_item_collected(item_id)
                                logger.info(f"✅ Pickup success for {item_id[:8]}, marked as collected")

                    if error:
                        code = error.get("code")
                        message = error.get("message", "")

                        if code == "AGENT_DEAD":
                            logger.info(f"💀 Agent dead from action_result: {message}")
                            raise AgentDeadError(f"Agent dead: {message}")

                        if code == "TARGET_DEAD":
                            logger.info(f"🎯 TARGET_DEAD - recomputing (turn {self.current_game.turn})")
                            view = msg.get("view", {})
                            if view:
                                self.current_game.update_view(view, "action_result")
                                if not self.current_game.is_alive:
                                    raise AgentDeadError("Agent dead from action_result view")
                                await self._act(ws, self.current_game.can_act)
                            continue

                        if code == "ACTION_FAILED":
                            logger.warning(f"⚠️ Action failed: {message}")
                            view = msg.get("view", {})
                            if view:
                                self.current_game.update_view(view, "action_result")
                                if not self.current_game.is_alive:
                                    raise AgentDeadError("Agent dead from action_result view")
                                await self._act(ws, self.current_game.can_act)
                            continue

                    if msg.get("action"):
                        self.total_actions += 1
                        self.successful_actions += 1
                        self.strategy.reset_rejection_counter()
                        last_action_time = current_time
                    continue

                if msg_type == "ruin_state_changed":
                    try:
                        ruin_data = msg.get("ruin", {})
                        if ruin_data and self.current_game:
                            self.current_game.update_ruin_state(ruin_data)
                            ruin_id = ruin_data.get("ruinId", "unknown")[:8]
                            gauge = ruin_data.get("gauge", 0)
                            max_gauge = ruin_data.get("maxGauge", 3)
                            content_type = ruin_data.get("contentType", "unknown")
                            is_empty = ruin_data.get("isEmpty", False)
                            
                            if is_empty:
                                logger.info(f"🗺️ Ruin {ruin_id} cleared! (content: {content_type})")
                            else:
                                logger.debug(f"🗺️ Ruin {ruin_id}: gauge {gauge}/{max_gauge} ({content_type})")
                    except Exception as e:
                        logger.debug(f"Ruin state handler error: {e}")
                    continue

                if msg_type == "alert_gauge_changed":
                    try:
                        alert_gauge = msg.get("alertGauge", 0)
                        alert_active = msg.get("alertActive", False)
                        
                        if self.current_game:
                            self.current_game.update_alert_gauge({
                                "alertGauge": alert_gauge,
                                "alertActive": alert_active
                            })
                        
                        if alert_active:
                            logger.warning(f"⚠️⚠️ ALERT ACTIVE! Gauge: {alert_gauge}/10 ⚠️⚠️")
                            if self.current_game and self.current_game.can_act:
                                logger.info("🛡️ Alert active - focusing on survival!")
                        else:
                            if alert_gauge > 5:
                                logger.info(f"⚡ Alert gauge: {alert_gauge}/10 (moderate)")
                            else:
                                logger.debug(f"📊 Alert gauge: {alert_gauge}/10")
                    except Exception as e:
                        logger.debug(f"Alert gauge handler error: {e}")
                    continue

                if msg_type not in ["log", "message_sent", "rest_completed"]:
                    logger.debug(f"📨 Unknown message type: {msg_type}")

            except asyncio.TimeoutError:
                logger.warning("⏰ WebSocket receive timeout, checking connection...")
                continue
            except ResumeTargetDeadError:
                raise
            except AgentDeadError:
                raise
            except ConnectionClosed as e:
                if e.code == 1013 and "RESUME_TARGET_DEAD" in str(e.reason):
                    raise ResumeTargetDeadError(f"Resume target dead: {e.reason}")
                raise
            except Exception as e:
                logger.exception(f"💥 Gameplay error: {e}")
                raise

    async def _act(self, ws: WSClient, can_act: bool):
        if not can_act or not self.current_game or not self.current_game.is_alive:
            return

        current_time = __import__('time').time()
        min_action_interval = 0.5
        
        if self._last_action_time > 0:
            elapsed = current_time - self._last_action_time
            if elapsed < min_action_interval:
                wait_time = min_action_interval - elapsed
                logger.debug(f"⏳ Rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        self._last_action_time = current_time

        try:
            if self.strategy_mode == "scan_clear":
                # Scan & Clear Strategy
                decision = self.scan_clear.decide(self.current_game)
                action = self._execute_scan_clear_decision(decision)
                if action:
                    thought = f"Scan & Clear: {decision.get('kind', 'action')}"
                    await ws.send_action(action, thought=thought)
                    await asyncio.sleep(ACTION_INTERVAL_SECONDS)
                    return
            else:
                # Hybrid AI (default)
                if self.ai_enabled:
                    decision = await self.ai.decide(self.current_game)
                    action = self._build_action_from_decision(decision)
                    if action:
                        thought = f"Hybrid AI: {decision.reasoning[0] if decision.reasoning else decision.action_type}"
                        logger.info(f"📤 Sending action: {action}")
                        
                        self._rl_action_tracking["action"] = decision.action_type
                        if hasattr(self.ai, 'rl_agent') and self.ai.rl_agent:
                            self._rl_action_tracking["state"] = self.ai.rl_agent.get_state_features(self.current_game)
                        self._rl_action_tracking["timestamp"] = __import__('time').time()
                        
                        await ws.send_action(action, thought=thought)

                        if decision.action_type != "wait":
                            if self.knowledge:
                                self.knowledge.data["stats"]["successful_actions"] += 1
                                self.knowledge.save()

                        await asyncio.sleep(ACTION_INTERVAL_SECONDS)
                        return

            await self._act_heuristic(ws, can_act)

        except Exception as e:
            logger.error(f"💥 Action error: {e}")
            await self._act_heuristic(ws, can_act)

    def _execute_scan_clear_decision(self, decision: Dict) -> Optional[Dict]:
        kind = decision.get("kind")
        obj = decision.get("obj")
        
        if kind == "pickup":
            return self.scan_clear.action_builder.pickup(obj)
        elif kind == "attack":
            return self.scan_clear.action_builder.attack(obj)
        elif kind == "move":
            return self.scan_clear.action_builder.move(obj)
        elif kind == "interact":
            return self.scan_clear.action_builder.interact(obj)
        elif kind == "explore":
            return self.scan_clear.action_builder.explore(obj)
        
        return None

    def _build_action_from_decision(self, decision) -> Optional[Dict]:
        action_type = decision.action_type
        target_id = decision.target_id

        if action_type == "attack":
            target = self._find_target(target_id, "enemies")
            if target:
                return ActionBuilder.attack(target)

        elif action_type == "pickup":
            item = self._find_target(target_id, "items")
            if item:
                return ActionBuilder.pickup(item)

        elif action_type == "interact":
            obj = self._find_target(target_id, "interactables")
            if obj:
                return ActionBuilder.interact(obj)

        elif action_type == "explore":
            obj = self._find_target(target_id, "interactables")
            if obj:
                return ActionBuilder.explore(obj)

        elif action_type == "move":
            conn = self._find_target(target_id, "connections")
            if conn:
                return ActionBuilder.move(conn)
        
        elif action_type == "use":
            item = self._find_target(target_id, "items")
            if item:
                return ActionBuilder.use_item(item)
            if target_id:
                return ActionBuilder.use_item_by_id(target_id)

        return None

    def _find_target(self, target_id: str, category: str) -> Optional[Dict]:
        if not self.current_game:
            return None

        if category == "enemies":
            for enemy in self.current_game.get_enemies():
                if enemy.get("id") == target_id or enemy.get("agentId") == target_id:
                    return enemy
                if enemy.get("metadata", {}).get("id") == target_id:
                    return enemy

        elif category == "items":
            for item in self.current_game.get_items():
                if item.get("id") == target_id or item.get("instanceId") == target_id:
                    return item

        elif category == "interactables":
            for obj in self.current_game.get_interactables():
                if obj.get("id") == target_id or obj.get("interactableId") == target_id:
                    return obj

        elif category == "connections":
            for conn in self.current_game.get_connections():
                if conn.get("id") == target_id or conn.get("regionId") == target_id:
                    return conn

        return None

    async def _act_heuristic(self, ws: WSClient, can_act: bool):
        if not can_act or not self.current_game:
            return

        decision = self.strategy.decide(self.current_game)
        action = self.strategy.execute(self.current_game, decision)

        if action:
            thought = f"Heuristic (v7): {decision.get('kind', 'action')}"
            await ws.send_action(action, thought=thought)
            await asyncio.sleep(ACTION_INTERVAL_SECONDS)

    def _log_hybrid_stats(self):
        stats = self.ai.get_stats() if hasattr(self.ai, 'get_stats') else {}

        logger.info("=" * 60)
        logger.info("📊 Hybrid AI Performance Summary")
        logger.info("=" * 60)
        logger.info(f"   Total Decisions: {stats.get('decisions_made', 0)}")
        logger.info(f"   AI Decisions: {stats.get('ai_decisions', 0)}")
        logger.info(f"   Heuristic Decisions: {stats.get('heuristic_decisions', 0)}")
        logger.info(f"   Survival Priority: {stats.get('survival_priority', 0)}")
        logger.info(f"   Kill Priority: {stats.get('kill_priority', 0)}")
        logger.info(f"   Loot Priority: {stats.get('loot_priority', 0)}")
        logger.info(f"   Explore Priority: {stats.get('explore_priority', 0)}")
        logger.info(f"   Total Actions: {self.total_actions}")
        logger.info(f"   Success Rate: {self.successful_actions / max(self.total_actions, 1) * 100:.1f}%")
        
        logger.info("-" * 40)
        logger.info("🗺️ Region Stats")
        logger.info(f"   Visited Regions: {len(self._visited_regions)}")
        logger.info(f"   Region Loop Detected: {self._region_loop_detected}")
        if self._visited_regions:
            logger.info(f"   Last 5 Regions: {list(self._visited_regions)[-5:]}")
        
        if hasattr(self.ai, 'rl_agent') and self.ai.rl_agent:
            rl_stats = self.ai.rl_agent.get_stats()
            logger.info("-" * 40)
            logger.info("🧠 Reinforcement Learning Stats")
            logger.info(f"   Q-Table Size: {rl_stats.get('q_table_size', 0)}")
            logger.info(f"   Memory Size: {rl_stats.get('memory_size', 0)}")
            logger.info(f"   Epsilon: {rl_stats.get('epsilon', 0)}")
            logger.info(f"   Exploration: {rl_stats.get('exploration_actions', 0)}")
            logger.info(f"   Exploitation: {rl_stats.get('exploitation_actions', 0)}")
            logger.info(f"   Learning Updates: {rl_stats.get('learning_updates', 0)}")
            logger.info(f"   Total Reward: {rl_stats.get('total_reward', 0):.2f}")
        
        if self.strategy_mode == "scan_clear":
            scan_stats = self.scan_clear.get_stats()
            logger.info("-" * 40)
            logger.info("📦 Scan & Clear Stats")
            logger.info(f"   Regions Cleared: {scan_stats.get('regions_cleared', 0)}")
            logger.info(f"   Items Collected: {scan_stats.get('items_collected', 0)}")
            logger.info(f"   Enemies Killed: {scan_stats.get('enemies_killed', 0)}")
            logger.info(f"   Turns Spent: {scan_stats.get('turns_spent', 0)}")
        
        logger.info("=" * 60)

    def get_performance(self) -> Dict[str, Any]:
        uptime = int(__import__('time').time() - (self.start_time or 0))

        result = {
            "uptime": uptime,
            "game_count": self.game_count,
            "total_actions": self.total_actions,
            "success_rate": self.successful_actions / max(self.total_actions, 1),
            "hybrid_stats": self.ai.get_stats() if hasattr(self.ai, 'get_stats') else {},
            "current_state": self.current_game.entry_type if self.current_game else "none",
            "is_in_game": self.current_game is not None and self.current_game.is_alive,
            "strategy_mode": self.strategy_mode,
            "region_stats": {
                "visited_regions": len(self._visited_regions),
                "loop_detected": self._region_loop_detected,
                "regions": list(self._visited_regions)
            }
        }
        
        if hasattr(self.ai, 'rl_agent') and self.ai.rl_agent:
            result["rl_stats"] = self.ai.rl_agent.get_stats()
        
        if self.strategy_mode == "scan_clear":
            result["scan_clear_stats"] = self.scan_clear.get_stats()
        
        return result