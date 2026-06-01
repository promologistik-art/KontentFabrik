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
    
    if user_id == Config.ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("👑 Админка", callback_data="admin")
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
                f"   👥 Пользователей: {stats.get('active_users', 0)} / {stats.get('total_users', 0)}\n"
                f"   📁 Ваших проектов: {stats.get('projects', 0)} (всего: {stats.get('total_projects', 0)})\n"
                f"   📥 Ваших источников: {stats.get('sources', 0)} (всего: {stats.get('total_sources', 0)})\n"
                f"   📬 В очереди: {stats.get('pending', 0)}\n"
                f"   📤 Опубликовано сегодня: {stats.get('posted_today', 0)} (ваших: {stats.get('user_posted_today', 0)})\n\n"
            )
    else:
        workers = registry.get_workers_for_type("tg2tg")
        if workers:
            text = (
                f"👋 <b>Добро пожаловать в KontentFabrik!</b>\n\n"
                f"Я — единый центр управления парсерами.\n\n"
                f"📡 <b>TG2TG</b> — парсинг Telegram → постинг в Telegram\n"
                f"📺 <b>U2TG</b> — парсинг YouTube Shorts (скоро)\n"
                f"📱 <b>TG2VK</b> — Telegram → VK (скоро)\n\n"
                f"Нажмите кнопку ниже, чтобы перейти в нужный сервис.\n"
                f"Затем вернитесь сюда и нажмите «Статистика».\n\n"
                f"/help — все команды"
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


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        if query:
            await query.edit_message_text("❌ Доступ запрещён")
        return
    
    await registry.reload()
    all_stats = await registry.get_admin_stats()
    
    text = "👑 <b>Админ-панель KontentFabrik</b>\n\n"
    
    if all_stats:
        for key, stats in all_stats.items():
            text += (
                f"📡 <b>{stats['bot_username']}</b> ({key})\n"
                f"   👥 Пользователей: {stats['active_users']} / {stats['total_users']}\n"
                f"   📁 Проектов: {stats['total_projects']}\n"
                f"   📥 Источников: {stats['total_sources']}\n"
                f"   📬 В очереди: {stats['pending']}\n"
                f"   📤 Опубликовано сегодня: {stats['posted_today']}\n\n"
            )
    else:
        text += "❌ Нет данных о клонах.\n"
    
    text += f"<b>Всего клонов:</b> {len(all_stats)}\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin")],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("◀️ Назад", callback_data="stats")],
    ]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей из всех клонов"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return
    
    await registry.reload()
    
    text = "👥 <b>Пользователи</b>\n\n"
    keyboard = []
    
    for key, worker in registry._workers.items():
        prefix = worker["db_prefix"]
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text
                result = await session.execute(
                    text(f"SELECT telegram_id, full_name, username, tariff FROM {prefix}users ORDER BY telegram_id")
                )
                users = result.fetchall()
                
                text += f"📡 <b>{worker['bot_username']}</b>:\n"
                for u in users:
                    text += f"  • {u[1] or '—'} (@{u[2] or '—'}) [{u[3]}]\n"
                    keyboard.append([
                        InlineKeyboardButton(
                            f"✏️ {u[1] or u[2] or u[0]}",
                            callback_data=f"admin_tariff_{u[0]}"
                        )
                    ])
                text += "\n"
        except Exception as e:
            text += f"📡 {worker['bot_username']}: ошибка\n"
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin")])
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_set_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка тарифа пользователю"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return
    
    data = query.data.replace("admin_tariff_", "")
    
    if "_" in data and data.count("_") >= 2:
        # admin_tariff_USERID_TARIFF
        parts = data.split("_", 1)
        worker_user_id = int(parts[0])
        tariff = parts[1]
        
        # Обновляем тариф во всех клонах
        for key, worker in registry._workers.items():
            prefix = worker["db_prefix"]
            try:
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import text
                    limits = {
                        "trial": (1, 3, 120, 60),
                        "basic": (1, 3, 120, 60),
                        "standard": (3, 5, 60, 30),
                        "pro": (10, 10, 30, 15),
                        "unlimited": (999, 999, 1, 5),
                    }
                    mp, ms, pi, ci = limits.get(tariff, (1, 3, 120, 60))
                    
                    await session.execute(
                        text(f"UPDATE {prefix}users SET tariff = :t, max_projects = :mp, max_sources_per_project = :ms, min_post_interval_minutes = :pi, min_check_interval_minutes = :ci WHERE telegram_id = :uid"),
                        {"t": tariff, "mp": mp, "ms": ms, "pi": pi, "ci": ci, "uid": worker_user_id}
                    )
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to update tariff in {key}: {e}")
        
        await query.edit_message_text(f"✅ Тариф обновлён до «{tariff}»")
        return
    
    # Показываем выбор тарифа
    worker_user_id = int(data)
    context.user_data['admin_user_id'] = worker_user_id
    
    keyboard = [
        [InlineKeyboardButton("🎁 Trial", callback_data=f"admin_tariff_{worker_user_id}_trial")],
        [InlineKeyboardButton("💳 Basic", callback_data=f"admin_tariff_{worker_user_id}_basic")],
        [InlineKeyboardButton("💎 Standard", callback_data=f"admin_tariff_{worker_user_id}_standard")],
        [InlineKeyboardButton("👑 PRO", callback_data=f"admin_tariff_{worker_user_id}_pro")],
        [InlineKeyboardButton("♾️ Unlimited", callback_data=f"admin_tariff_{worker_user_id}_unlimited")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_users")],
    ]
    
    await query.edit_message_text(
        f"Выберите тариф для пользователя:\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Обновлено ✅")
    await dashboard(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    text = (
        "📚 <b>KontentFabrik — Справка</b>\n\n"
        "Я управляю всеми парсерами из одного места.\n\n"
        "<b>📡 Доступные сервисы:</b>\n"
        "• TG2TG — парсинг Telegram-каналов и постинг в Telegram\n"
        "• U2TG — парсинг YouTube Shorts (скоро)\n"
        "• TG2VK — парсинг Telegram и постинг в VK (скоро)\n\n"
        "<b>Команды:</b>\n"
        "/start — дашборд\n"
        "/dashboard — статистика\n"
        "/help — справка\n"
    )
    
    if user_id == Config.ADMIN_ID:
        text += (
            "\n<b>👑 Админ:</b>\n"
            "/admin — админ-панель\n"
        )
    
    text += (
        f"\n📲 <a href='https://t.me/{Config.ADMIN_USERNAME or 'admin'}'>Написать админу</a>"
        f"\n📢 <a href='https://t.me/+MAuGbcnBQmgxZTIy'>Больше ботов в канале</a>"
    )
    
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


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