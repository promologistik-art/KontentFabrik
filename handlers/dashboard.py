import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import AsyncSessionLocal
from models import HeadUser
from registry import registry
from config import Config

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(HeadUser).where(HeadUser.telegram_id == user.id)
        )
        if not result.scalar_one_or_none():
            session.add(HeadUser(
                telegram_id=user.id,
                username=user.username,
                full_name=user.full_name,
                is_admin=(user.id == Config.ADMIN_ID)
            ))
            await session.commit()
    
    await registry.reload()
    
    text = (
        f"👋 <b>Добро пожаловать в KontentFabrik!</b>\n\n"
        f"Я управляю парсерами контента.\n"
        f"Выберите, с чем хотите работать:\n\n"
        f"📡 <b>TG2TG</b> — парсинг Telegram-каналов и постинг в Telegram\n"
        f"📺 <b>U2TG</b> — парсинг YouTube Shorts (скоро)\n"
        f"📱 <b>TG2VK</b> — парсинг Telegram и постинг в VK (скоро)\n"
    )
    
    keyboard = await build_main_keyboard(user.id)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def build_main_keyboard(user_id: int) -> list:
    keyboard = []
    
    tg2tg_workers = registry.get_workers_for_type("tg2tg")
    if tg2tg_workers:
        worker = tg2tg_workers[0]
        keyboard.append([
            InlineKeyboardButton(
                "📡 TG2TG — Telegram→Telegram",
                url=f"https://t.me/{worker['bot_username']}?start=kf_{user_id}"
            )
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📡 TG2TG — Telegram→Telegram (нет клонов)", callback_data="noop")
        ])
    
    keyboard.append([InlineKeyboardButton("📺 U2TG — YouTube→Telegram (скоро)", callback_data="noop")])
    keyboard.append([InlineKeyboardButton("📱 TG2VK — Telegram→VK (скоро)", callback_data="noop")])
    keyboard.append([
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🔄 Обновить", callback_data="refresh")
    ])
    
    return keyboard


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    await registry.reload()
    
    text = "📊 <b>Ваш дашборд</b>\n\n"
    
    all_stats = await registry.get_all_stats(user_id)
    
    if all_stats:
        for bot_type, stats in all_stats.items():
            text += (
                f"📡 <b>{bot_type.upper()}</b> (клон #{stats.get('clone_id', '?')})\n"
                f"   📁 Проектов: {stats.get('projects', 0)}\n"
                f"   📥 Источников: {stats.get('sources', 0)}\n"
                f"   📬 В очереди: {stats.get('pending', 0)}\n"
                f"   📤 Сегодня: {stats.get('posted_today', 0)}\n\n"
            )
    else:
        workers = registry.get_workers_for_type("tg2tg")
        if workers:
            text += "📡 <b>TG2TG</b>\n   У вас пока нет привязки к клону.\n   Нажмите кнопку ниже.\n\n"
        else:
            text += "❌ Нет доступных клонов.\n\n"
    
    text += "📺 <b>U2TG</b>: скоро\n📱 <b>TG2VK</b>: скоро\n\n"
    
    keyboard = await build_main_keyboard(user_id)
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Обновлено ✅")
    await registry.reload()
    await dashboard(update, context)