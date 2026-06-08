import asyncio
import logging
from datetime import datetime, timedelta
from database import AsyncSessionLocal
from registry import registry
from config import Config

logger = logging.getLogger(__name__)


class ReportScheduler:
    def __init__(self):
        self._running = False
        self._last_report = None

    async def start(self):
        self._running = True
        logger.info("🟢 ReportScheduler started")
        
        while self._running:
            try:
                await self._check_and_send()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"ReportScheduler error: {e}")
                await asyncio.sleep(60)

    async def _check_and_send(self):
        from datetime import datetime
        import pytz
        
        msk_tz = pytz.timezone(Config.TIMEZONE)
        now_msk = datetime.now(msk_tz)
        
        if now_msk.hour == 9 and now_msk.minute == 0:
            today = now_msk.date()
            if self._last_report != today:
                self._last_report = today
                await self._send_daily_report()

    async def _send_daily_report(self):
        try:
            now = datetime.utcnow()
            yesterday = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            await registry.reload()
            all_stats = await registry.get_admin_stats()
            
            yesterday_str = yesterday.strftime('%d.%m.%Y')
            text = f"📊 <b>KontentFabrik — отчёт за {yesterday_str}</b>\n\n"
            
            total_users = 0
            total_projects = 0
            total_sources = 0
            total_parsed = 0
            total_posted = 0
            total_pending = 0
            total_failed = 0
            
            for key, stats in all_stats.items():
                prefix = stats.get('_prefix', '')
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import text as sql_text
                    
                    # Спарсено за вчера
                    r = await session.execute(
                        sql_text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE created_at >= :y AND created_at < :t"),
                        {"y": yesterday, "t": today_start}
                    )
                    parsed = r.scalar()
                    
                    # Опубликовано за вчера
                    r = await session.execute(
                        sql_text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE status = 'published' AND published_at >= :y AND published_at < :t"),
                        {"y": yesterday, "t": today_start}
                    )
                    posted = r.scalar()
                    
                    # Ошибок за вчера
                    r = await session.execute(
                        sql_text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE status = 'failed' AND created_at >= :y AND created_at < :t"),
                        {"y": yesterday, "t": today_start}
                    )
                    failed = r.scalar()
                    
                    total_parsed += parsed
                    total_posted += posted
                    total_failed += failed
                
                total_users += stats.get('active_users', 0)
                total_projects += stats.get('total_projects', 0)
                total_sources += stats.get('total_sources', 0)
                total_pending += stats.get('pending', 0)
                
                text += (
                    f"📡 <b>{stats['bot_username']}</b>\n"
                    f"   🔄 Спарсено: {parsed}\n"
                    f"   📤 Опубликовано: {posted}\n"
                    f"   ❌ Ошибок: {failed}\n\n"
                )
            
            text += (
                f"<b>Итого:</b>\n"
                f"👥 Пользователей: {total_users}\n"
                f"📁 Проектов: {total_projects}\n"
                f"📥 Источников: {total_sources}\n"
                f"🔄 Спарсено: {total_parsed}\n"
                f"📤 Опубликовано: {total_posted}\n"
                f"📬 В очереди: {total_pending}\n"
                f"❌ Ошибок: {total_failed}\n"
            )
            
            from telegram import Bot
            bot = Bot(token=Config.BOT_TOKEN)
            await bot.send_message(chat_id=Config.ADMIN_ID, text=text, parse_mode="HTML")
            logger.info("📊 Daily report sent")
            
        except Exception as e:
            logger.error(f"Daily report failed: {e}")

    async def stop(self):
        self._running = False
        logger.info("🔴 ReportScheduler stopped")