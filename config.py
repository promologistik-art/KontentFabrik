import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
    
    # Пути
    SHARED_DIR = os.getenv("SHARED_DIR", "/app/shared")
    DATA_DIR = os.path.join(SHARED_DIR, "data")
    DB_PATH = os.path.join(DATA_DIR, "kontentfabrik.db")
    
    BOT_CONNECT_TIMEOUT = 30
    BOT_READ_TIMEOUT = 60
    BOT_WRITE_TIMEOUT = 60

    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")

Config.validate()