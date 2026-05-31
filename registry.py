"""Реестр ботов-исполнителей — PostgreSQL"""
import logging
from datetime import date
from sqlalchemy import select, text
from database import AsyncSessionLocal
from models import Worker, UserBinding

logger = logging.getLogger(__name__)


class WorkerRegistry:
    def __init__(self):
        self._workers = {}
        self._bindings = {}
    
    async def load(self):
        await self._load_workers()
        await self._load_bindings()
        logger.info(f"📋 Loaded {len(self._workers)} workers, {len(self._bindings)} bindings")
    
    async def _load_workers(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Worker).where(Worker.is_active == True)
            )
            self._workers = {}
            for w in result.scalars().all():
                key = f"{w.bot_type}:{w.clone_id}"
                self._workers[key] = {
                    "bot_type": w.bot_type,
                    "clone_id": w.clone_id,
                    "bot_username": w.bot_username,
                    "db_prefix": w.db_prefix,
                }
    
    async def _load_bindings(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserBinding))
            self._bindings = {}
            for b in result.scalars().all():
                self._bindings[str(b.head_user_id)] = {
                    "head_user_id": b.head_user_id,
                    "worker_user_id": b.worker_user_id,
                    "bot_type": b.bot_type,
                    "clone_id": b.clone_id,
                }
    
    async def reload(self):
        await self.load()
    
    def get_least_loaded(self, bot_type: str) -> dict | None:
        candidates = [w for w in self._workers.values() if w["bot_type"] == bot_type]
        return candidates[0] if candidates else None
    
    def get_workers_for_type(self, bot_type: str) -> list:
        return [w for w in self._workers.values() if w["bot_type"] == bot_type]
    
    def get_user_binding(self, head_user_id: int) -> dict | None:
        return self._bindings.get(str(head_user_id))
    
    async def get_user_stats(self, head_user_id: int) -> dict | None:
        binding = self.get_user_binding(head_user_id)
        if not binding:
            return None
        
        prefix = f"tg{binding['clone_id']}_"
        worker_user_id = binding["worker_user_id"]
        
        try:
            async with AsyncSessionLocal() as session:
                # Проекты
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}projects WHERE user_id = :uid AND is_active = true"),
                    {"uid": worker_user_id}
                )
                projects = result.scalar()
                
                # Источники
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}source_channels WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND is_active = true"),
                    {"uid": worker_user_id}
                )
                sources = result.scalar()
                
                # В очереди
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND status = 'pending'"),
                    {"uid": worker_user_id}
                )
                pending = result.scalar()
                
                # Сегодня
                today = date.today()
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND status = 'published' AND published_at >= :today"),
                    {"uid": worker_user_id, "today": today}
                )
                posted_today = result.scalar()
                
                return {
                    "projects": projects,
                    "sources": sources,
                    "pending": pending,
                    "posted_today": posted_today,
                    "clone_id": binding["clone_id"],
                    "bot_type": binding["bot_type"]
                }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return None
    
    async def get_all_stats(self, head_user_id: int) -> dict:
        stats = {}
        binding = self.get_user_binding(head_user_id)
        if binding:
            bot_stats = await self.get_user_stats(head_user_id)
            if bot_stats:
                stats[binding["bot_type"]] = bot_stats
        return stats


registry = WorkerRegistry()