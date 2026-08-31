# src/client/ws_client.py
"""WebSocket client untuk Claw Royale"""

import json
import logging
from typing import Optional, Dict, Any, AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosed

from ..core.constants import JOIN_WS
from ..core.exceptions import AuthenticationError, ResumeTargetDeadError

logger = logging.getLogger(__name__)

class WSClient:
    def __init__(self, api_key: str, version: str):
        self.api_key = api_key
        self.version = version
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected_at: Optional[float] = None
        self._connection_count: int = 0
    
    async def connect(self) -> AsyncIterator[Dict]:
        self._connection_count += 1
        
        headers = {
            "Authorization": f"mr-auth {self.api_key}",
            "X-Version": self.version
        }
        
        try:
            async with websockets.connect(
                JOIN_WS,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5
            ) as ws:
                self._ws = ws
                self._connected_at = __import__('time').time()
                
                welcome = json.loads(await ws.recv())
                yield welcome
                
                while True:
                    try:
                        msg = json.loads(await ws.recv())
                        yield msg
                    except ConnectionClosed as e:
                        if e.code == 1013 and "RESUME_TARGET_DEAD" in str(e.reason):
                            raise ResumeTargetDeadError(f"Resume target dead: {e.reason}")
                        logger.warning(f"Connection closed: {e.code} - {e.reason}")
                        break
        except websockets.exceptions.InvalidStatusCode as e:
            if e.status_code == 403:
                raise AuthenticationError("Not primary agent or forbidden")
            raise
    
    async def recv(self) -> Dict:
        if not self._ws:
            raise RuntimeError("Not connected")
        try:
            msg = await self._ws.recv()
            return json.loads(msg)
        except ConnectionClosed as e:
            if e.code == 1013 and "RESUME_TARGET_DEAD" in str(e.reason):
                raise ResumeTargetDeadError(f"Resume target dead: {e.reason}")
            raise
    
    async def send(self, data: Dict):
        if not self._ws:
            raise RuntimeError("Not connected")
        await self._ws.send(json.dumps(data))
    
    async def close(self):
        if self._ws:
            await self._ws.close()
    
    async def send_hello(self, entry_type: str = "free", mode: str = "offchain"):
        hello = {"type": "hello", "entryType": entry_type}
        if entry_type == "paid":
            hello["mode"] = mode
        await self.send(hello)
        logger.info(f"📤 Sent hello: {entry_type}" + (f" mode={mode}" if entry_type == "paid" else ""))
    
    async def send_action(self, data: Dict, thought: str = "AI Adaptive Strategy"):
        await self.send({
            "type": "action",
            "data": data,
            "thought": thought
        })
    
    def should_reset_backoff(self) -> bool:
        if self._connected_at is None:
            return False
        import time
        return (time.time() - self._connected_at) >= 10.0