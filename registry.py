"""Реестр ботов-исполнителей — PostgreSQL"""
import logging
from datetime import date, datetime
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
    
    async def get_least_loaded_worker(self, bot_type: str) -> dict | None:
        candidates = []
        for key, worker in self._workers.items():
            if worker["bot_type"] == bot_type:
                prefix = worker["db_prefix"]
                try:
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            text(f"SELECT COUNT(*) FROM {prefix}users WHERE is_active = true")
                        )
                        user_count = result.scalar()
                        candidates.append((worker, user_count))
                except Exception as e:
                    logger.error(f"Failed to count users for {key}: {e}")
                    candidates.append((worker, 999))
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x[1])
        logger.info(f"⚖️ Selected {candidates[0][0]['bot_username']} ({candidates[0][1]} users)")
        return candidates[0][0]
    
    async def get_user_projects(self, head_user_id: int) -> list:
        """Возвращает список проектов пользователя из его клона"""
        binding = self.get_user_binding(head_user_id)
        if not binding:
            return []
        
        prefix = f"tg{binding['clone_id']}_"
        worker_user_id = binding["worker_user_id"]
        
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(f"""
                        SELECT p.id, p.name, p.is_active,
                               (SELECT COUNT(*) FROM {prefix}source_channels WHERE project_id = p.id AND is_active = true) as sources,
                               (SELECT COUNT(*) FROM {prefix}post_queue WHERE project_id = p.id AND status = 'pending') as pending,
                               (SELECT MAX(published_at) FROM {prefix}post_queue WHERE project_id = p.id AND status = 'published') as last_post,
                               p.posts_posted_today
                        FROM {prefix}projects p
                        WHERE p.user_id = :uid AND p.is_active = true
                        ORDER BY p.id
                    """),
                    {"uid": worker_user_id}
                )
                projects = []
                for row in result.fetchall():
                    status = "🟢"
                    if row[5]:
                        hours_since = (datetime.utcnow() - row[5]).total_seconds() / 3600
                        if hours_since > 24:
                            status = "🔴"
                        elif hours_since > 6:
                            status = "🟡"
                    else:
                        status = "⚪"
                    
                    projects.append({
                        "id": row[0],
                        "name": row[1],
                        "is_active": row[2],
                        "sources": row[3] or 0,
                        "pending": row[4] or 0,
                        "last_post": row[5].strftime("%d.%m %H:%M") if row[5] else "нет данных",
                        "posted_today": row[6] or 0,
                        "status": status
                    })
                return projects
        except Exception as e:
            logger.error(f"Failed to get user projects: {e}")
            return []
    
    async def get_user_stats(self, head_user_id: int) -> dict | None:
        binding = self.get_user_binding(head_user_id)
        if not binding:
            return None
        
        prefix = f"tg{binding['clone_id']}_"
        worker_user_id = binding["worker_user_id"]
        
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}users")
                )
                total_users = result.scalar()
                
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}users WHERE is_active = true")
                )
                active_users = result.scalar()
                
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}projects WHERE user_id = :uid AND is_active = true"),
                    {"uid": worker_user_id}
                )
                projects = result.scalar()
                
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}projects WHERE is_active = true")
                )
                total_projects = result.scalar()
                
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}source_channels WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND is_active = true"),
                    {"uid": worker_user_id}
                )
                sources = result.scalar()
                
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}source_channels WHERE is_active = true")
                )
                total_sources = result.scalar()
                
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND status = 'pending'"),
                    {"uid": worker_user_id}
                )
                pending = result.scalar()
                
                today = date.today()
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE status = 'published' AND published_at >= :today"),
                    {"today": today}
                )
                posted_today = result.scalar()
                
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND status = 'published' AND published_at >= :today"),
                    {"uid": worker_user_id, "today": today}
                )
                user_posted_today = result.scalar()
                
                return {
                    "total_users": total_users,
                    "active_users": active_users,
                    "projects": projects,
                    "total_projects": total_projects,
                    "sources": sources,
                    "total_sources": total_sources,
                    "pending": pending,
                    "posted_today": posted_today,
                    "user_posted_today": user_posted_today,
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
    
    async def get_admin_stats(self) -> dict:
        all_stats = {}
        for key, worker in self._workers.items():
            prefix = worker["db_prefix"]
            try:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}users"))
                    total_users = result.scalar()
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}users WHERE is_active = true"))
                    active_users = result.scalar()
                    
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}projects WHERE is_active = true"))
                    total_projects = result.scalar()
                    
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}source_channels WHERE is_active = true"))
                    total_sources = result.scalar()
                    
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE status = 'pending'"))
                    pending = result.scalar()
                    
                    today = date.today()
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE status = 'published' AND published_at >= :today"), {"today": today})
                    posted_today = result.scalar()
                    
                    all_stats[key] = {
                        "bot_username": worker["bot_username"],
                        "total_users": total_users,
                        "active_users": active_users,
                        "total_projects": total_projects,
                        "total_sources": total_sources,
                        "pending": pending,
                        "posted_today": posted_today
                    }
            except Exception as e:
                logger.error(f"Admin stats failed for {key}: {e}")
        
        return all_stats


registry = WorkerRegistry()