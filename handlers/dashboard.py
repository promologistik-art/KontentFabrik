import logging
from datetime import datetime
import pytz
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
    
    await show_stats(update, context)


async def build_main_keyboard(user_id: int) -> list:
    keyboard = []
    
    # TG2TG — кнопка для каждого клона
    tg2tg_workers = registry.get_workers_for_type("tg2tg")
    if tg2tg_workers:
        for worker in tg2tg_workers:
            keyboard.append([
                InlineKeyboardButton(
                    f"📡 TG2TG (клон #{worker['clone_id']})",
                    url=f"https://t.me/{worker['bot_username']}?start=kf_{user_id}"
                )
            ])
    else:
        keyboard.append([
            InlineKeyboardButton("📡 TG2TG — Telegram→Telegram (нет клонов)", callback_data="noop")
        ])
    
    # U2TG — кнопка для каждого клона
    u2tg_workers = registry.get_workers_for_type("u2tg")
    if u2tg_workers:
        for worker in u2tg_workers:
            keyboard.append([
                InlineKeyboardButton(
                    f"📺 U2TG (клон #{worker['clone_id']})",
                    url=f"https://t.me/{worker['bot_username']}?start=kf_{user_id}"
                )
            ])
    else:
        keyboard.append([
            InlineKeyboardButton("📺 U2TG — YouTube→Telegram (скоро)", callback_data="noop")
        ])
    
    # TG2VK
    keyboard.append([InlineKeyboardButton("📱 TG2VK — Telegram→VK (скоро)", callback_data="noop")])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Обновить", callback_data="refresh")
    ])
    
    if user_id == Config.ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("👑 Админка", callback_data="admin")
        ])
    
    return keyboard


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_stats(update, context)


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    is_admin = (user_id == Config.ADMIN_ID)
    await registry.reload()
    
    user_data = await registry.get_all_user_data(user_id)
    
    msk_tz = pytz.timezone(Config.TIMEZONE)
    now_msk = datetime.now(msk_tz).strftime("%H:%M")
    
    if user_data:
        msg_text = f"📊 <b>Ваш дашборд</b>  <i>обновлено в {now_msk} МСК</i>\n\n"
        
        for bot_type, data in user_data.items():
            bot_link = f"https://t.me/{data['bot_username']}?start=kf_{user_id}"
            msg_text += (
                f"📡 <b><a href='{bot_link}'>{bot_type.upper()}</a></b> (клон #{data['clone_id']})\n"
                f"   📁 Проектов: {data['projects']}\n"
                f"   📥 Источников: {data['sources']}\n"
                f"   📬 В очереди: {data['pending']}\n"
                f"   📤 Опубликовано сегодня: {data['posted_today']}\n\n"
            )
            
            if data['projects_list']:
                msg_text += "<b>📁 Проекты:</b>\n"
                for p in data['projects_list']:
                    msg_text += (
                        f"{p['status']} <b>{p['name']}</b>\n"
                        f"   📥 {p['sources']} ист. | 📬 {p['pending']} в очереди | 📤 {p['posted_today']} сегодня | 🕐 {p['last_post']}\n"
                    )
                msg_text += "\n"
    else:
        has_any = bool(registry.get_workers_for_type("tg2tg")) or bool(registry.get_workers_for_type("u2tg"))
        if has_any:
            msg_text = (
                f"👋 <b>Добро пожаловать в KontentFabrik!</b>\n\n"
                f"Я — единый центр управления парсерами.\n\n"
                f"Нажмите кнопку ниже, чтобы открыть бота и создать привязку.\n"
                f"Затем нажмите «Обновить» для просмотра статистики.\n\n"
                f"/help — все команды"
            )
        else:
            msg_text = f"❌ Нет доступных клонов.\n\n📺 U2TG: скоро\n📱 TG2VK: скоро"
    
    keyboard = await build_main_keyboard(user_id)
    
    if query:
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML", disable_web_page_preview=True)


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
    
    msg_text = "👑 <b>Админ-панель KontentFabrik</b>\n\n"
    
    total_pending = 0
    
    if all_stats:
        for key, stats in all_stats.items():
            pending = stats.get('pending', 0)
            total_pending += pending
            
            alert = " ⚠️" if pending > 100 else ""
            msg_text += (
                f"📡 <b>{stats['bot_username']}</b> ({key}){alert}\n"
                f"   👥 Пользователей: {stats['active_users']} / {stats['total_users']}\n"
                f"   📁 Проектов: {stats['total_projects']}\n"
                f"   📥 Источников: {stats['total_sources']}\n"
                f"   📬 В очереди: {pending}\n"
                f"   📤 Опубликовано сегодня: {stats['posted_today']}\n\n"
            )
    else:
        msg_text += "❌ Нет данных о клонах.\n"
    
    msg_text += f"<b>Всего клонов:</b> {len(all_stats)}\n"
    msg_text += f"<b>Всего в очереди:</b> {total_pending}\n"
    
    if total_pending > 100:
        msg_text += "\n⚠️ <b>Очередь переполнена!</b> Рекомендуется очистить зависшие посты.\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin")],
        [InlineKeyboardButton("👥 Пользователи и тарифы", callback_data="admin_users")],
        [InlineKeyboardButton("ℹ️ Инфо о тарифах", callback_data="admin_tariffs_info")],
        [InlineKeyboardButton("🧹 Очистить зависшие посты", callback_data="admin_clear_stuck")],
        [InlineKeyboardButton("◀️ Назад", callback_data="refresh")],
    ]
    
    if query:
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_clear_stuck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("🧹 Очищаю зависшие посты...")
    
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return
    
    total_cleared = 0
    details = []
    
    for key, worker in registry._workers.items():
        prefix = worker["db_prefix"]
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text as sql_text
                result = await session.execute(
                    sql_text(f"UPDATE {prefix}post_queue SET status = 'failed', error_message = 'Завис в очереди > 24 часов (админ)' WHERE status = 'pending' AND scheduled_time < NOW() - INTERVAL '24 hours'")
                )
                await session.commit()
                cleared = result.rowcount
                total_cleared += cleared
                if cleared > 0:
                    details.append(f"📡 {worker['bot_username']}: {cleared} постов")
                logger.info(f"🧹 {worker['bot_username']}: cleared {cleared} stuck posts")
        except Exception as e:
            logger.error(f"Failed to clear stuck posts in {key}: {e}")
            details.append(f"📡 {worker['bot_username']}: ошибка")
    
    msg_text = f"🧹 <b>Очистка зависших постов</b>\n\n"
    if details:
        msg_text += "\n".join(details) + "\n\n"
    msg_text += f"✅ Всего очищено: <b>{total_cleared}</b> постов"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад в админку", callback_data="admin")]]
    
    if query:
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_tariffs_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return
    
    msg_text = (
        "ℹ️ <b>Тарифы</b>\n\n"
        "🎁 <b>Trial</b> (пробный, 5 дней)\n"
        "   📁 1 проект | 📥 3 источника\n"
        "   ⏰ Постинг от 120 мин | 🔍 Парсинг от 60 мин\n\n"
        "💳 <b>Basic</b> — 290 ₽/мес\n"
        "   📁 1 проект | 📥 3 источника\n"
        "   ⏰ Постинг от 120 мин | 🔍 Парсинг от 60 мин\n\n"
        "💎 <b>Standard</b> — 590 ₽/мес\n"
        "   📁 3 проекта | 📥 5 источников\n"
        "   ⏰ Постинг от 60 мин | 🔍 Парсинг от 30 мин\n\n"
        "👑 <b>PRO</b> — 990 ₽/мес\n"
        "   📁 10 проектов | 📥 10 источников\n"
        "   ⏰ Постинг от 30 мин | 🔍 Парсинг от 15 мин\n\n"
        "♾️ <b>Unlimited</b> — только для админа\n"
        "   📁 999 проектов | 📥 999 источников\n"
        "   ⏰ Постинг от 1 мин | 🔍 Парсинг от 5 мин"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin")]]
    
    if query:
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return
    
    await registry.reload()
    
    bot_labels = {
        "tg2tg": "из Telegram в Telegram",
        "u2tg": "из YouTube в Telegram",
        "tg2vk": "из Telegram в VK"
    }
    
    result_text = (
        "👥 <b>Пользователи</b>\n"
        "🎁Trial 💳Basic 💎Standard 👑PRO ♾️Unlimited\n\n"
    )
    keyboard = []
    
    for key, worker in registry._workers.items():
        prefix = worker["db_prefix"]
        label = bot_labels.get(worker['bot_type'], worker['bot_type'])
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text as sql_text
                result = await session.execute(
                    sql_text(f"SELECT telegram_id, full_name, username, tariff FROM {prefix}users ORDER BY telegram_id")
                )
                users = result.fetchall()
                
                result_text += f"📡 <b>{worker['bot_username']}</b> — {label}:\n"
                for u in users:
                    tariff_emoji = {
                        "trial": "🎁", "basic": "💳", "standard": "💎",
                        "pro": "👑", "unlimited": "♾️"
                    }.get(u[3], "❓")
                    
                    name = u[1] or '—'
                    uname = u[2] or '—'
                    result_text += f"  {tariff_emoji} {name} (@{uname}) [{u[3]}]\n"
                    keyboard.append([
                        InlineKeyboardButton(
                            f"✏️ Сменить тариф: {name}",
                            callback_data=f"tariff_{u[0]}"
                        )
                    ])
                result_text += "\n"
        except Exception as e:
            result_text += f"📡 {worker['bot_username']}: ошибка\n"
    
    keyboard.append([InlineKeyboardButton("ℹ️ Что дают тарифы", callback_data="admin_tariffs_info")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin")])
    
    if query:
        await query.edit_message_text(result_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_set_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return
    
    data = query.data
    
    if data.startswith("tariff_") and data.count("_") >= 2:
        parts = data.split("_", 2)
        if len(parts) == 3:
            worker_user_id = int(parts[1])
            tariff = parts[2]
            
            limits = {
                "trial": (1, 3, 120, 60),
                "basic": (1, 3, 120, 60),
                "standard": (3, 5, 60, 30),
                "pro": (10, 10, 30, 15),
                "unlimited": (999, 999, 1, 5),
            }
            mp, ms, pi, ci = limits.get(tariff, (1, 3, 120, 60))
            
            for key, worker in registry._workers.items():
                prefix = worker["db_prefix"]
                try:
                    async with AsyncSessionLocal() as session:
                        from sqlalchemy import text as sql_text
                        await session.execute(
                            sql_text(f"UPDATE {prefix}users SET tariff = :t, max_projects = :mp, max_sources_per_project = :ms, min_post_interval_minutes = :pi, min_check_interval_minutes = :ci WHERE telegram_id = :uid"),
                            {"t": tariff, "mp": mp, "ms": ms, "pi": pi, "ci": ci, "uid": worker_user_id}
                        )
                        await session.commit()
                except Exception as e:
                    logger.error(f"Failed to update tariff in {key}: {e}")
            
            tariff_names = {
                "trial": "🎁 Trial (пробный, 5 дней)",
                "basic": "💳 Basic (290 ₽/мес)",
                "standard": "💎 Standard (590 ₽/мес)",
                "pro": "👑 PRO (990 ₽/мес)",
                "unlimited": "♾️ Unlimited"
            }
            
            try:
                await context.bot.send_message(
                    chat_id=worker_user_id,
                    text=(
                        f"🔔 <b>Ваш тариф изменён!</b>\n\n"
                        f"Новый тариф: {tariff_names.get(tariff, tariff)}\n"
                        f"📁 Проектов: {mp}\n"
                        f"📥 Источников на проект: {ms}\n"
                        f"⏰ Мин. интервал постинга: {pi} мин\n"
                        f"🔍 Мин. интервал парсинга: {ci} мин\n\n"
                        f"По вопросам: @{Config.ADMIN_USERNAME}"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {worker_user_id}: {e}")
            
            await query.edit_message_text(f"✅ Тариф обновлён до «{tariff_names.get(tariff, tariff)}»")
            return
    
    if data.startswith("tariff_"):
        worker_user_id = int(data.replace("tariff_", ""))
        context.user_data['admin_user_id'] = worker_user_id
        
        msg_text = (
            f"Выберите тариф для пользователя:\n\n"
            f"🎁 <b>Trial</b> — 1 проект, 3 источника, 5 дней\n"
            f"💳 <b>Basic</b> — 1 проект, 3 источника, 290₽/мес\n"
            f"💎 <b>Standard</b> — 3 проекта, 5 источников, 590₽/мес\n"
            f"👑 <b>PRO</b> — 10 проектов, 10 источников, 990₽/мес\n"
            f"♾️ <b>Unlimited</b> — без ограничений"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎁 Trial", callback_data=f"tariff_{worker_user_id}_trial")],
            [InlineKeyboardButton("💳 Basic", callback_data=f"tariff_{worker_user_id}_basic")],
            [InlineKeyboardButton("💎 Standard", callback_data=f"tariff_{worker_user_id}_standard")],
            [InlineKeyboardButton("👑 PRO", callback_data=f"tariff_{worker_user_id}_pro")],
            [InlineKeyboardButton("♾️ Unlimited", callback_data=f"tariff_{worker_user_id}_unlimited")],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_users")],
        ]
        
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Обновлено ✅")
    await show_stats(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    msg_text = (
        "📚 <b>KontentFabrik — Справка</b>\n\n"
        "Я управляю всеми парсерами из одного места.\n\n"
        "<b>📡 Доступные сервисы:</b>\n"
        "• TG2TG — парсинг Telegram-каналов и постинг в Telegram\n"
        "• U2TG — парсинг YouTube и постинг в Telegram\n"
        "• TG2VK — парсинг Telegram и постинг в VK (скоро)\n\n"
        "<b>Команды:</b>\n"
        "/start — дашборд\n"
        "/dashboard — статистика\n"
        "/help — справка\n"
    )
    
    if user_id == Config.ADMIN_ID:
        msg_text += (
            "\n<b>👑 Админ:</b>\n"
            "/admin — админ-панель\n"
        )
    
    msg_text += (
        f"\n📲 <a href='https://t.me/{Config.ADMIN_USERNAME or 'admin'}'>Написать админу</a>"
        f"\n📢 <a href='https://t.me/+MAuGbcnBQmgxZTIy'>Больше ботов в канале</a>"
    )
    
    await update.message.reply_text(msg_text, parse_mode="HTML", disable_web_page_preview=True)


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await registry.reload()
    
    msg_text = f"🔍 <b>Debug info</b>\n\n"
    msg_text += f"Ваш ID: {user_id}\n\n"
    msg_text += f"<b>Workers:</b> {len(registry._workers)}\n"
    for k, w in registry._workers.items():
        msg_text += f"  {k}: {w['bot_username']}\n"
    
    msg_text += f"\n<b>Bindings:</b> {len(registry._bindings)}\n"
    for k, b in registry._bindings.items():
        msg_text += f"  head={b['head_user_id']} → {b['bot_type']}#{b['clone_id']}\n"
    
    msg_text += f"\n<b>Ваши привязки:</b>\n"
    for b in registry.get_user_bindings(user_id):
        msg_text += f"  {b['bot_type']}#{b['clone_id']}\n"
    
    user_data = await registry.get_all_user_data(user_id)
    msg_text += f"\n<b>Данные:</b> {list(user_data.keys())}"
    
    await update.message.reply_text(msg_text, parse_mode="HTML")