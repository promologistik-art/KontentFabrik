#!/usr/bin/env python3
"""KontentFabrik — Head Parser Bot"""
import asyncio
import logging
import sys
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config import Config
from database import init_db
from registry import registry
from handlers import start, dashboard, refresh, debug

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    await registry.load()
    logger.info(f"📋 Registry: {len(registry._workers)} workers, {len(registry._bindings)} bindings")
    
    app = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(60)
        .build()
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CallbackQueryHandler(dashboard, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(refresh, pattern="^refresh$"))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["message", "callback_query"])
    
    logger.info("🟢 KontentFabrik started")
    
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("🔴 KontentFabrik stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)