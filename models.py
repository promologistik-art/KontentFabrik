from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class HeadUser(Base):
    """Пользователь головного бота"""
    __tablename__ = "kf_users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Worker(Base):
    """Реестр ботов-исполнителей (общая таблица)"""
    __tablename__ = "workers"
    id = Column(Integer, primary_key=True)
    bot_type = Column(String, nullable=False)
    clone_id = Column(Integer, nullable=False)
    bot_username = Column(String, nullable=False)
    db_prefix = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class UserBinding(Base):
    """Привязки пользователей (общая таблица)"""
    __tablename__ = "user_bindings"
    id = Column(Integer, primary_key=True)
    head_user_id = Column(BigInteger, nullable=False)
    worker_user_id = Column(BigInteger, nullable=False)
    bot_type = Column(String, nullable=False)
    clone_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)