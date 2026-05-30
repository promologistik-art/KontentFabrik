"""Реестр ботов-исполнителей — через общие файлы в /app/shared"""
import json
import os
import sqlite3
import logging
from config import Config

logger = logging.getLogger(__name__)

WORKERS_FILE = os.path.join(Config.DATA_DIR, "workers.json")
BINDINGS_FILE = os.path.join(Config.DATA_DIR, "bindings.json")


class WorkerRegistry:
    def __init__(self):
        self._workers = {}
        self._bindings = {}
    
    def load(self):
        """Загружает реестр workers и привязок из общих файлов"""
        self._load_workers()
        self._load_bindings()
        logger.info(f"📋 Loaded {len(self._workers)} workers, {len(self._bindings)} bindings")
    
    def _load_workers(self):
        """Читает workers.json"""
        if os.path.exists(WORKERS_FILE):
            try:
                with open(WORKERS_FILE, "r") as f:
                    self._workers = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read workers.json: {e}")
                self._workers = {}
        else:
            logger.info("workers.json not found yet — waiting for clones to register")
    
    def _load_bindings(self):
        """Читает bindings.json"""
        if os.path.exists(BINDINGS_FILE):
            try:
                with open(BINDINGS_FILE, "r") as f:
                    self._bindings = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read bindings.json: {e}")
                self._bindings = {}
    
    def reload(self):
        """Перезагружает данные из файлов"""
        self.load()
    
    def get_least_loaded(self, bot_type: str) -> dict | None:
        """Выбирает первого доступного worker для bot_type"""
        candidates = [
            w for w in self._workers.values()
            if w.get("bot_type") == bot_type
        ]
        if not candidates:
            return None
        return candidates[0]
    
    def get_workers_for_type(self, bot_type: str) -> list:
        """Возвращает всех workers для bot_type"""
        return [
            w for w in self._workers.values()
            if w.get("bot_type") == bot_type
        ]
    
    def get_user_binding(self, head_user_id: int) -> dict | None:
        """Возвращает привязку пользователя к клону"""
        return self._bindings.get(str(head_user_id))
    
    def get_user_stats(self, head_user_id: int) -> dict | None:
        """Читает статистику напрямую из БД клона"""
        binding = self.get_user_binding(head_user_id)
        if not binding:
            return None
        
        db_path = binding.get("db_path")
        if not db_path or not os.path.exists(db_path):
            logger.warning(f"DB not found: {db_path}")
            return None
        
        worker_user_id = binding.get("worker_user_id")
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Проекты
            cursor.execute(
                "SELECT COUNT(*) FROM projects WHERE user_id = ? AND is_active = 1",
                (worker_user_id,)
            )
            projects = cursor.fetchone()[0]
            
            # Источники
            cursor.execute(
                """SELECT COUNT(*) FROM source_channels 
                   WHERE project_id IN 
                   (SELECT id FROM projects WHERE user_id = ? AND is_active = 1)
                   AND is_active = 1""",
                (worker_user_id,)
            )
            sources = cursor.fetchone()[0]
            
            # Опубликовано сегодня
            from datetime import datetime
            today = datetime.utcnow().strftime("%Y-%m-%d")
            cursor.execute(
                """SELECT COUNT(*) FROM post_queue 
                   WHERE project_id IN 
                   (SELECT id FROM projects WHERE user_id = ?)
                   AND status = 'published' 
                   AND date(published_at) = ?""",
                (worker_user_id, today)
            )
            posted_today = cursor.fetchone()[0]
            
            # В очереди
            cursor.execute(
                """SELECT COUNT(*) FROM post_queue 
                   WHERE project_id IN 
                   (SELECT id FROM projects WHERE user_id = ?)
                   AND status = 'pending'""",
                (worker_user_id,)
            )
            pending = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "projects": projects,
                "sources": sources,
                "posted_today": posted_today,
                "pending": pending,
                "bot_type": binding.get("bot_type", "tg2tg"),
                "clone_id": binding.get("clone_id", 1)
            }
            
        except Exception as e:
            logger.error(f"Failed to read stats from {db_path}: {e}")
            return None
    
    def get_all_stats(self, head_user_id: int) -> dict:
        """Собирает статистику по всем типам ботов для пользователя"""
        stats = {}
        
        # Проверяем все известные привязки
        for uid, binding in self._bindings.items():
            if int(uid) == head_user_id:
                bot_type = binding.get("bot_type", "unknown")
                bot_stats = self.get_user_stats(head_user_id)
                if bot_stats:
                    stats[bot_type] = bot_stats
        
        return stats


# Глобальный экземпляр
registry = WorkerRegistry()