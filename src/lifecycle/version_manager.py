# src/lifecycle/version_manager.py
"""Version manager dengan ETag-based caching dan lock"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Optional

from ..core.constants import BASE_API, CACHE_DIR, DOCS_TO_CACHE

logger = logging.getLogger(__name__)

class VersionManager:
    def __init__(self, key: str):
        self.key = key
        self.version: Optional[str] = None
        self.cache = Path(CACHE_DIR)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        
        try:
            self.meta = json.loads((self.cache / "etag_meta.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self.meta = {}
    
    async def ensure_current(self, session):
        async with self._lock:
            async with session.get(
                f"{BASE_API}/version",
                headers={"X-API-Key": self.key},
                timeout=15
            ) as resp:
                data = await resp.json()
                resp.raise_for_status()
                self.version = data.get("version") or data.get("data", {}).get("version")
            
            if (self.meta.get("_version") == self.version and 
                all(doc in self.meta for doc in DOCS_TO_CACHE)):
                return
            
            logger.info(f"Version changed to {self.version}, refreshing docs...")
            headers = {"X-API-Key": self.key, "X-Version": self.version}
            
            for path in DOCS_TO_CACHE:
                h = dict(headers)
                etag = self.meta.get(path, {}).get("etag")
                if etag:
                    h["If-None-Match"] = etag
                
                try:
                    async with session.get(
                        f"{BASE_API}{path}",
                        headers=h,
                        timeout=20
                    ) as resp:
                        if resp.status == 304:
                            continue
                        if resp.status != 200:
                            logger.warning(f"Doc {path} HTTP {resp.status}")
                            continue
                        
                        body = await resp.text()
                        cache_path = path.lstrip("/").replace("/", "__")
                        (self.cache / cache_path).write_text(body)
                        self.meta[path] = {"etag": resp.headers.get("ETag"), "version": self.version}
                except Exception as e:
                    logger.warning(f"Doc {path} refresh failed: {e}")
            
            self.meta["_version"] = self.version
            (self.cache / "etag_meta.json").write_text(json.dumps(self.meta, indent=2))