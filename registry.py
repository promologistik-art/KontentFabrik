"""Реестр ботов-исполнителей — PostgreSQL"""
import logging
from datetime import date, datetime, timedelta
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
                key = f"{b.head_user_id}:{b.bot_type}"
                self._bindings[key] = {
                    "head_user_id": b.head_user_id,
                    "worker_user_id": b.worker_user_id,
                    "bot_type": b.bot_type,
                    "clone_id": b.clone_id,
                }
    
    async def reload(self):
        await self.load()
    
    def get_workers_for_type(self, bot_type: str) -> list:
        return [w for w in self._workers.values() if w["bot_type"] == bot_type]
    
    def get_user_binding(self, head_user_id: int, bot_type: str = None) -> dict | None:
        if bot_type:
            return self._bindings.get(f"{head_user_id}:{bot_type}")
        return self._bindings.get(str(head_user_id))
    
    def get_user_bindings(self, head_user_id: int, bot_type: str = None) -> list:
        result = []
        for key, b in self._bindings.items():
            if b["head_user_id"] == head_user_id:
                if bot_type is None or b["bot_type"] == bot_type:
                    result.append(b)
        return result
    
    async def get_all_user_data(self, head_user_id: int) -> dict:
        result = {}
        
        for key, b in self._bindings.items():
            if b["head_user_id"] != head_user_id:
                continue
            
            bot_type = b["bot_type"]
            clone_id = b["clone_id"]
            worker_user_id = b["worker_user_id"]
            
            worker_key = f"{bot_type}:{clone_id}"
            worker = self._workers.get(worker_key)
            if not worker:
                continue
            
            prefix = worker["db_prefix"]
            
            try:
                async with AsyncSessionLocal() as session:
                    r_projects = await session.execute(
                        text(f"SELECT COUNT(*) FROM {prefix}projects WHERE user_id = :uid AND is_active = true"),
                        {"uid": worker_user_id}
                    )
                    projects = r_projects.scalar()
                    
                    r_sources = await session.execute(
                        text(f"SELECT COUNT(*) FROM {prefix}source_channels WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND is_active = true"),
                        {"uid": worker_user_id}
                    )
                    sources = r_sources.scalar()
                    
                    r_pending = await session.execute(
                        text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND status = 'pending'"),
                        {"uid": worker_user_id}
                    )
                    pending = r_pending.scalar()
                    
                    today_date = date.today()
                    r_posted = await session.execute(
                        text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE project_id IN (SELECT id FROM {prefix}projects WHERE user_id = :uid) AND status = 'published' AND published_at >= :today"),
                        {"uid": worker_user_id, "today": today_date}
                    )
                    posted_today = r_posted.scalar()
                    
                    r_proj_list = await session.execute(
                        text(f"""
                            SELECT p.name,
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
                    projects_list = []
                    for row in r_proj_list.fetchall():
                        status_icon = "🟢"
                        if row[3]:
                            last_post_msk = row[3] + timedelta(hours=3)
                            hours_since = (datetime.utcnow() - row[3]).total_seconds() / 3600
                            if hours_since > 24:
                                status_icon = "🔴"
                            elif hours_since > 6:
                                status_icon = "🟡"
                        else:
                            status_icon = "⚪"
                            last_post_msk = None
                        
                        projects_list.append({
                            "name": row[0],
                            "sources": row[1] or 0,
                            "pending": row[2] or 0,
                            "last_post": last_post_msk.strftime("%d.%m %H:%M") if last_post_msk else "нет данных",
                            "posted_today": row[4] or 0,
                            "status": status_icon
                        })
                    
                    result[bot_type] = {
                        "bot_username": worker["bot_username"],
                        "clone_id": clone_id,
                        "projects": projects,
                        "sources": sources,
                        "pending": pending,
                        "posted_today": posted_today,
                        "projects_list": projects_list
                    }
            except Exception as e:
                logger.error(f"Failed to get data for {bot_type}#{clone_id}: {e}")
        
        return result
    
    async def get_admin_stats(self) -> dict:
        all_stats = {}
        for key, worker in self._workers.items():
            prefix = worker["db_prefix"]
            try:
                async with AsyncSessionLocal() as session:
                    r1 = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}users"))
                    total_users = r1.scalar()
                    r2 = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}users WHERE is_active = true"))
                    active_users = r2.scalar()
                    
                    r3 = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}projects WHERE is_active = true"))
                    total_projects = r3.scalar()
                    
                    r4 = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}source_channels WHERE is_active = true"))
                    total_sources = r4.scalar()
                    
                    r5 = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE status = 'pending'"))
                    pending = r5.scalar()
                    
                    today = date.today()
                    r6 = await session.execute(text(f"SELECT COUNT(*) FROM {prefix}post_queue WHERE status = 'published' AND published_at >= :today"), {"today": today})
                    posted_today = r6.scalar()
                    
                    all_stats[key] = {
                        "bot_username": worker["bot_username"],
                        "total_users": total_users,
                        "active_users": active_users,
                        "total_projects": total_projects,
                        "total_sources": total_sources,
                        "pending": pending,
                        "posted_today": posted_today,
                        "_prefix": prefix
                    }
            except Exception as e:
                logger.error(f"Admin stats failed for {key}: {e}")
        
        return all_stats


registry = WorkerRegistry()