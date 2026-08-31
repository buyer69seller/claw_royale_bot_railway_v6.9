# src/utils/health.py
"""Health check server untuk monitoring dengan dashboard"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

logger = logging.getLogger(__name__)

class HealthServer:
    def __init__(self, port: int = 8080):
        self.port = port
        self._runner = None
        self._site = None
        self._running = False
        self._start_time = time.time()
        self._driver_ref = None
    
    async def start(self, driver=None):
        if not HAS_AIOHTTP:
            return
        
        if self._running:
            return
        
        self._driver_ref = driver
        
        try:
            app = web.Application()
            app.router.add_get('/health', self._health_handler)
            app.router.add_get('/ready', self._ready_handler)
            app.router.add_get('/metrics', self._metrics_handler)
            app.router.add_get('/stats', self._stats_handler)
            app.router.add_get('/dashboard', self._dashboard_handler)
            
            self._runner = web.AppRunner(app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, '0.0.0.0', self.port)
            await self._site.start()
            self._running = True
            logger.info(f"Health server started on port {self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")
    
    async def stop(self):
        if self._runner and self._running:
            await self._runner.cleanup()
            self._running = False
    
    @staticmethod
    async def _health_handler(request):
        return web.Response(text="OK", status=200)
    
    @staticmethod
    async def _ready_handler(request):
        return web.Response(text="READY", status=200)
    
    async def _metrics_handler(self, request):
        uptime = int(time.time() - self._start_time)
        
        metrics = {
            "uptime": uptime,
            "status": "running",
            "timestamp": int(time.time())
        }
        
        if self._driver_ref:
            try:
                perf = self._driver_ref.get_performance() if hasattr(self._driver_ref, 'get_performance') else {}
                metrics.update({
                    "game_count": perf.get("game_count", 0),
                    "total_actions": perf.get("total_actions", 0),
                    "success_rate": perf.get("success_rate", 0),
                    "is_in_game": perf.get("is_in_game", False),
                    "strategy_mode": perf.get("strategy_mode", "hybrid")
                })
                
                hybrid_stats = perf.get("hybrid_stats", {})
                if hybrid_stats:
                    metrics["hybrid_ai"] = {
                        "decisions": hybrid_stats.get("decisions_made", 0),
                        "ai_decisions": hybrid_stats.get("ai_decisions", 0),
                        "heuristic_decisions": hybrid_stats.get("heuristic_decisions", 0),
                        "survival_priority": hybrid_stats.get("survival_priority", 0),
                        "kill_priority": hybrid_stats.get("kill_priority", 0),
                        "loot_priority": hybrid_stats.get("loot_priority", 0),
                        "explore_priority": hybrid_stats.get("explore_priority", 0)
                    }
                
                rl_stats = perf.get("rl_stats", {})
                if rl_stats:
                    metrics["rl"] = {
                        "q_table_size": rl_stats.get("q_table_size", 0),
                        "epsilon": rl_stats.get("epsilon", 0),
                        "exploration": rl_stats.get("exploration_actions", 0),
                        "exploitation": rl_stats.get("exploitation_actions", 0)
                    }
                
                scan_stats = perf.get("scan_clear_stats", {})
                if scan_stats:
                    metrics["scan_clear"] = {
                        "regions_cleared": scan_stats.get("regions_cleared", 0),
                        "items_collected": scan_stats.get("items_collected", 0),
                        "enemies_killed": scan_stats.get("enemies_killed", 0)
                    }
            except Exception as e:
                logger.debug(f"Failed to get driver metrics: {e}")
        
        return web.json_response(metrics)
    
    async def _stats_handler(self, request):
        uptime = int(time.time() - self._start_time)
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60
        
        stats = {
            "bot": {
                "status": "running",
                "uptime": f"{hours}h {minutes}m {seconds}s",
                "version": "6.1.0"
            }
        }
        
        if self._driver_ref:
            try:
                perf = self._driver_ref.get_performance() if hasattr(self._driver_ref, 'get_performance') else {}
                stats["game"] = {
                    "games_played": perf.get("game_count", 0),
                    "total_actions": perf.get("total_actions", 0),
                    "success_rate": f"{perf.get('success_rate', 0) * 100:.1f}%",
                    "is_in_game": perf.get("is_in_game", False),
                    "strategy_mode": perf.get("strategy_mode", "hybrid")
                }
            except Exception as e:
                logger.debug(f"Failed to get driver stats: {e}")
        
        return web.json_response(stats)
    
    async def _dashboard_handler(self, request):
        uptime = int(time.time() - self._start_time)
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60
        
        dashboard = {
            "bot": {
                "status": "🟢 Running",
                "uptime": f"{hours}h {minutes}m {seconds}s",
                "version": "6.1.0",
                "engine": "Hybrid AI + RL"
            }
        }
        
        if self._driver_ref:
            try:
                perf = self._driver_ref.get_performance() if hasattr(self._driver_ref, 'get_performance') else {}
                
                dashboard["game"] = {
                    "games_played": perf.get("game_count", 0),
                    "total_actions": perf.get("total_actions", 0),
                    "success_rate": f"{perf.get('success_rate', 0) * 100:.1f}%",
                    "is_in_game": "✅ Yes" if perf.get("is_in_game", False) else "❌ No",
                    "strategy_mode": perf.get("strategy_mode", "hybrid")
                }
                
                hybrid_stats = perf.get("hybrid_stats", {})
                if hybrid_stats:
                    dashboard["hybrid_ai"] = {
                        "decisions": hybrid_stats.get("decisions_made", 0),
                        "ai_decisions": hybrid_stats.get("ai_decisions", 0),
                        "heuristic_decisions": hybrid_stats.get("heuristic_decisions", 0),
                        "survival": hybrid_stats.get("survival_priority", 0),
                        "kill": hybrid_stats.get("kill_priority", 0),
                        "loot": hybrid_stats.get("loot_priority", 0),
                        "explore": hybrid_stats.get("explore_priority", 0)
                    }
            except Exception as e:
                dashboard["error"] = str(e)
        
        html = self._format_dashboard_html(dashboard)
        return web.Response(text=html, content_type="text/html")
    
    def _format_dashboard_html(self, data: Dict) -> str:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Claw Royale Bot - Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }
                .container { max-width: 800px; margin: 0 auto; }
                .card { background: #16213e; border-radius: 10px; padding: 20px; margin: 10px 0; border-left: 4px solid #0f3460; }
                .card h2 { margin: 0 0 10px 0; color: #e94560; }
                .stat { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #1a1a3e; }
                .stat .label { color: #aaa; }
                .stat .value { color: #fff; font-weight: bold; }
                .green { color: #4ade80; }
                .yellow { color: #facc15; }
                .red { color: #f87171; }
                .header { text-align: center; padding: 20px 0; }
                .header h1 { color: #e94560; margin: 0; }
                .header p { color: #888; margin: 5px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🦀 Claw Royale Bot</h1>
                    <p>v6.1 - Hybrid AI Engine</p>
                </div>
        """
        
        bot = data.get("bot", {})
        html += f"""
                <div class="card">
                    <h2>🤖 Bot Status</h2>
                    <div class="stat"><span class="label">Status</span><span class="value green">{bot.get('status', 'Unknown')}</span></div>
                    <div class="stat"><span class="label">Uptime</span><span class="value">{bot.get('uptime', 'N/A')}</span></div>
                    <div class="stat"><span class="label">Version</span><span class="value">{bot.get('version', 'N/A')}</span></div>
                    <div class="stat"><span class="label">Engine</span><span class="value">{bot.get('engine', 'N/A')}</span></div>
                </div>
        """
        
        game = data.get("game", {})
        if game:
            html += f"""
                <div class="card">
                    <h2>🎮 Game Stats</h2>
                    <div class="stat"><span class="label">Games Played</span><span class="value">{game.get('games_played', 0)}</span></div>
                    <div class="stat"><span class="label">Total Actions</span><span class="value">{game.get('total_actions', 0)}</span></div>
                    <div class="stat"><span class="label">Success Rate</span><span class="value green">{game.get('success_rate', '0%')}</span></div>
                    <div class="stat"><span class="label">In Game</span><span class="value">{game.get('is_in_game', 'No')}</span></div>
                    <div class="stat"><span class="label">Strategy</span><span class="value yellow">{game.get('strategy_mode', 'hybrid')}</span></div>
                </div>
            """
        
        hybrid = data.get("hybrid_ai", {})
        if hybrid:
            html += f"""
                <div class="card">
                    <h2>🧠 Hybrid AI</h2>
                    <div class="stat"><span class="label">Total Decisions</span><span class="value">{hybrid.get('decisions', 0)}</span></div>
                    <div class="stat"><span class="label">AI Decisions</span><span class="value green">{hybrid.get('ai_decisions', 0)}</span></div>
                    <div class="stat"><span class="label">Heuristic Decisions</span><span class="value yellow">{hybrid.get('heuristic_decisions', 0)}</span></div>
                    <div class="stat"><span class="label">🛡️ Survival</span><span class="value">{hybrid.get('survival', 0)}</span></div>
                    <div class="stat"><span class="label">⚔️ Kill</span><span class="value red">{hybrid.get('kill', 0)}</span></div>
                    <div class="stat"><span class="label">📦 Loot</span><span class="value">{hybrid.get('loot', 0)}</span></div>
                    <div class="stat"><span class="label">🔍 Explore</span><span class="value">{hybrid.get('explore', 0)}</span></div>
                </div>
            """
        
        html += """
            </div>
        </body>
        </html>
        """
        
        return html
    
    def set_driver(self, driver):
        self._driver_ref = driver