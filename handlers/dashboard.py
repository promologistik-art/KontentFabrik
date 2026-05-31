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
    
    await dashboard(update, context)


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
    
    all_stats = await registry.get_all_stats(user_id)
    
    if all_stats:
        text = "📊 <b>Ваш дашборд</b>\n\n"
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
            text = (
                f"👋 <b>Добро пожаловать в KontentFabrik!</b>\n\n"
                f"Выберите, с чем хотите работать:\n\n"
                f"📡 <b>TG2TG</b> — парсинг Telegram-каналов и постинг в Telegram\n"
                f"📺 <b>U2TG</b> — парсинг YouTube Shorts (скоро)\n"
                f"📱 <b>TG2VK</b> — парсинг Telegram и постинг в VK (скоро)\n\n"
                f"Нажмите кнопку ниже, чтобы перейти в бота и создать привязку."
            )
        else:
            text = "❌ Нет доступных клонов.\n\n📺 U2TG: скоро\n📱 TG2VK: скоро"
    
    keyboard = await build_main_keyboard(user_id)
    
    if query:
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.error(f"Edit error: {e}")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Обновлено ✅")
    await dashboard(update, context)


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await registry.reload()
    
    text = f"🔍 <b>Debug info</b>\n\n"
    text += f"Ваш ID: {user_id}\n\n"
    text += f"<b>Workers:</b> {len(registry._workers)}\n"
    for k, w in registry._workers.items():
        text += f"  {k}: {w['bot_username']}\n"
    
    text += f"\n<b>Bindings:</b> {len(registry._bindings)}\n"
    for k, b in registry._bindings.items():
        text += f"  head={b['head_user_id']} → {b['bot_type']}#{b['clone_id']}\n"
    
    binding = registry.get_user_binding(user_id)
    text += f"\n<b>Ваша привязка:</b> {binding}"
    
    stats = await registry.get_all_stats(user_id)
    text += f"\n\n<b>Статистика:</b> {stats}"
    
    await update.message.reply_text(text, parse_mode="HTML")