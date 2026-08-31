# src/main.py
"""Entry point bot Claw Royale dengan Hybrid AI + RL"""

import asyncio
import logging
import sys
import signal
import os
from pathlib import Path

# Tambahkan src ke path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .client.rest_client import RestClient
from .lifecycle.driver import Driver
from .core.config import API_KEY, STRATEGY_MODE
from .utils.logger import setup_logging
from .services.reward_service import RewardService
from .services.loadout_service import LoadoutService
from .services.inventory_service import InventoryService
from .utils.health import HealthServer
from .ai.knowledge import KnowledgeBase
from .core.constants import ensure_directories
from .services.auth_service import AuthService

# Global untuk cleanup
health_server = None
driver_task = None
knowledge = None


async def shutdown(signal, loop):
    """Graceful shutdown"""
    logger = logging.getLogger(__name__)
    logger.info(f"🛑 Received signal {signal}, shutting down...")

    # Save knowledge
    if knowledge:
        knowledge.save()
        logger.info("💾 Knowledge saved")

    # Stop health server
    if health_server:
        await health_server.stop()
        logger.info("🛑 Health server stopped")

    # Cancel driver task
    if driver_task:
        driver_task.cancel()
        logger.info("🛑 Driver task cancelled")
        try:
            await driver_task
        except asyncio.CancelledError:
            pass

    loop.stop()
    logger.info("✅ Shutdown complete")


async def main():
    """Main entry point"""
    global health_server, driver_task, knowledge

    # Setup logging FIRST
    setup_logging()
    logger = logging.getLogger(__name__)

    # Ensure directories exist
    ensure_directories()
    logger.info("📁 Directories ensured")

    # Cek API key
    if not API_KEY:
        logger.error("❌ CLAW_API_KEY not set! Please set in .env or environment")
        sys.exit(1)

    logger.info("🦀 Starting Claw Royale Bot v6.1 - Hybrid AI")
    logger.info("=" * 60)
    logger.info(f"🧠 Strategy Mode: {STRATEGY_MODE}")
    logger.info("=" * 60)

    # Init Knowledge Base dengan cleanup
    knowledge = KnowledgeBase()
    
    # Cleanup old data
    try:
        removed = knowledge.clear_old_data(days=30)
        if removed > 0:
            logger.info(f"🧹 Cleaned {removed} old knowledge entries (>30 days)")
    except Exception as e:
        logger.debug(f"Knowledge cleanup skipped: {e}")
    
    # Get insights dengan memory info
    insights = knowledge.get_insights()
    logger.info(f"📊 AI Knowledge:")
    logger.info(f"   - Win Rate: {insights['performance']['win_rate']*100:.1f}%")
    logger.info(f"   - Avg Survival: {insights['performance']['avg_survival']:.0f} turns")
    logger.info(f"   - Kills/Game: {insights['performance']['kills_per_game']:.1f}")
    logger.info(f"   - Success Rate: {insights['performance']['success_rate']*100:.1f}%")
    logger.info(f"   - Total Games: {insights['total_games']}")
    
    if "memory" in insights:
        logger.info(f"   - Memory Usage: {insights['memory']['usage_percent']:.1f}% ({insights['memory']['history_entries']}/{insights['memory']['max_history']} entries)")
    logger.info("=" * 60)

    # Setup health check server
    health_server = HealthServer(port=8080)
    await health_server.start()
    logger.info("✅ Health server started on port 8080")

    # Start bot
    async with RestClient(API_KEY) as rest:
        # === LOGIN ===
        logger.info("🔐 Starting authentication flow...")
        auth_service = AuthService(rest)
        
        try:
            account = await auth_service.login()
            logger.info("=" * 60)
            logger.info("✅ LOGIN SUCCESSFUL")
            logger.info(f"   Account: {account.get('name')}")
            logger.info(f"   ID: {account.get('id')}")
            logger.info(f"   Wallet: {account.get('walletAddress')}")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"❌ Login failed: {e}")
            sys.exit(1)

        # Auto-claim rewards
        try:
            logger.info("🎁 Checking rewards...")
            reward_service = RewardService(rest)
            await reward_service.redeem_welcome_bundle()
        except Exception as e:
            logger.debug(f"Reward check skipped: {e}")

        # Loadout optimization
        try:
            logger.info("🔧 Checking loadout...")
            loadout_service = LoadoutService(rest)
            if not await loadout_service.is_full_set():
                logger.info("🔧 Loadout not full, optimizing...")
                await loadout_service.optimize_loadout()
            else:
                logger.info("✅ Loadout already full")
        except Exception as e:
            logger.debug(f"Loadout optimization skipped: {e}")

        # Auto-equip best items
        try:
            inventory_service = InventoryService(rest)
            logger.info("🔧 Auto-equipping best items...")
            result = await inventory_service.auto_equip_best()
            if result.get("changes"):
                logger.info(f"✅ Auto-equipped: {result['changes']}")
            if result.get("errors"):
                logger.warning(f"⚠️ Auto-equip errors: {result['errors']}")
        except Exception as e:
            logger.debug(f"Auto-equip skipped: {e}")

        # ===== DRIVER SETUP =====
        logger.info("=" * 60)
        logger.info("🚀 Starting Hybrid AI Auto-Pilot...")
        logger.info(f"🧠 Strategy Mode: {STRATEGY_MODE}")
        logger.info("🎮 Ready to join games...")
        logger.info("=" * 60)
        
        logger.info("🔧 Creating driver instance...")
        driver = Driver(rest)
        driver.knowledge = knowledge
        driver.auth_service = auth_service
        driver.set_strategy_mode(STRATEGY_MODE)
        logger.info("✅ Driver instance created")
        
        if health_server:
            health_server.set_driver(driver)
            logger.info("✅ Health server connected to driver")
        
        logger.info("🚀 Starting driver task...")
        driver_task = asyncio.create_task(driver.run())
        logger.info("✅ Driver task created and scheduled")
        logger.info("⏳ Waiting for driver to complete...")
        
        try:
            await driver_task
            logger.info("✅ Driver task completed normally")
        except asyncio.CancelledError:
            logger.info("🛑 Driver task was cancelled")
        except Exception as e:
            logger.error(f"💥 Driver crashed with error: {e}")
            import traceback
            logger.error("📋 Full traceback:")
            logger.error(traceback.format_exc())
            raise


if __name__ == "__main__":
    # Setup logging FIRST before anything else
    setup_logging()
    logger = logging.getLogger(__name__)
    
    print("=" * 60)
    print("🦀 Claw Royale Bot v6.1 - Hybrid AI")
    print(f"🧠 Strategy Mode: {STRATEGY_MODE}")
    print("=" * 60)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Setup signal handlers
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, loop))
        )

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if knowledge:
            knowledge.save()
            logger.info("💾 Final knowledge saved")
        loop.close()
        logger.info("✅ Loop closed, exiting")
        sys.exit(0)