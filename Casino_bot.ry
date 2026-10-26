"""
Telegram-бот «Казино»: 20 игр, профиль, пополнение через Telegram Stars и NFT, инвентарь, NFT-апгрейдер, автовыплата.
(Версия для Render + Neon + 3 админа)
"""
import asyncio
import json
import logging
import math
import os
import random
import time
import os.path
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton, LabeledPrice,
                           Message, PreCheckoutQuery)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ───────────────────────── настройки ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "1780243837:pes_lGqwdioIkn0AR4qXB09ewN5Ckg_GMVP")

# Список всех трех администраторов по ID
ADMIN_IDS = {1780243478, 1780243247, 1780243322}
ADMIN_ID = int(os.getenv("ADMIN_ID", "1780243478")) # Главный админ для команд

ADMIN_PASSWORD = "QBSBSH283672"   # пароль админ-панели
PANEL_MAX_TRIES, PANEL_LOCK_SEC = 5, 600                        # защита от подбора пароля
SPONSOR_CODE = "AKWB1937"            # код входа в меню спонсора
CREATOR_PCT = 7                                                 # % от пополнений игрока автору кода
# коды авторов: (код, название, slug для ссылки t.me/бот?start=c_<slug>)
CREATOR_SEEDS = [("woly", "WOLY", "woly"), ("about", "ABOUT", "about"), ("несквик", "несквик", "nesquik")]

HOUSE_EDGE = 0.10            # комиссия казино 10% (шансы и множители в играх считаются от неё)
MIN_BET, MAX_BET = 1, 5000
DEPOSIT_OPTIONS = [10, 50, 100, 250, 500, 1000]
DEPOSIT_MIN, DEPOSIT_MAX = 1, 10000               # лимиты своей суммы пополнения (макс. для Stars — 10000)
WD_MIN, WD_MAX = 1000, 20000                      # лимиты вывода (за одну заявку)
WD_DAILY_MAX = 100_000                            # лимит вывода на одного игрока в сутки (00:00–00:00)
WD_GLOBAL_DAILY = 100_000                         # общий лимит вывода по всему боту в сутки (00:00–00:00)
DAY_TZ_HOURS, DAY_TZ_NAME = 3, "МСК"              # часовой пояс «суток»: счётчик обнуляется в 00:00 по нему
WD_OPTIONS = [1000, 2500, 5000, 10000, 20000]     # суммы для вывода
QUICK_BETS = [1, 5, 10, 50, 100]

# игра «Куб»
DICE_MIN, DICE_MAX = 50, 2500                     # лимиты ставки
DICE_BETS = [50, 100, 250, 500, 1000, 2500]

# спонсоры и админы по username (без @, регистр не важен)
SPONSOR_USERS = {                                 # username -> код автора, который к нему привязан
    "nesquik": "несквик",
    "dural": "woly",
    "imabout": "about",
}
ADMIN_USERS = {"dural", "imabout"}                
MINES_OPTIONS = [1, 2, 3, 4, 5, 6]   # максимум 6 мин
UPGRADE_X = [1.5, 2, 3, 5, 10, 20]
GRID = 9                     # поле 3x3

# NFT-пополнение: игроки отправляют NFT на этот username, админ зачисляет ⭐
NFT_USERNAME = "RubUpdeppodarkami"
NFT_URL = f"https://t.me/{NFT_USERNAME}"
NFT_MAX_PENDING = 5          # максимум необработанных заявок «отправил NFT» от одного игрока
NFT_SELL_PCT = 100           # за сколько % от цены NFT продаётся из инвентаря (100 = по полной цене)
NFT_FLOOR_API_URL = os.getenv("NFT_FLOOR_API_URL", "")   # URL с floor-ценами в TON
NFT_PRICE_TTL = 1800         # как часто обновлять цены из API, сек
STAR_USD = 0.015             # цена одной звезды в $ (для перевода TON -> ⭐)
STARS_PER_TON_FALLBACK = 200 # курс ⭐ за 1 TON, пока не удалось получить реальный
NFT_UP_EDGE = HOUSE_EDGE     # комиссия казино в NFT-апгрейдере
NFT_UP_MIN_CHANCE = 0.05     # минимальный шанс, при котором цель апгрейда показывается
INV_PAGE, NUP_PAGE, NG_PAGE = 8, 8, 10   # размеры страниц: инвентарь / цели апгрейда / выдача админом

# автовыплата: после «Одобрить» в заявке на вывод бот сам отправляет звёзды через Telegram
AUTO_PAYOUT = True
MAX_PAYOUT = 100_000         # потолок выигрыша за одну игру в новых играх

rng = random.SystemRandom()  # криптостойкий генератор


def day_start_utc() -> str:
    """Начало текущих суток (00:00 по DAY_TZ) в UTC."""
    tz = timezone(timedelta(hours=DAY_TZ_HOURS))
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

router = Router()


# ───────────────────────── БАЗА ДАННЫХ (Neon / PostgreSQL или SQLite) ─────────────────────────
import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    conn.autocommit = True
    print("Успешное подключение к PostgreSQL (Neon)!")
else:
    import sqlite3
    conn = sqlite3.connect("casino.db", isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    print("Внимание: DATABASE_URL не найдена, используется локальная SQLite.")

class DBWrapper:
    def execute(self, query, params=None):
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) if DATABASE_URL else conn.cursor()
        if DATABASE_URL:
            query = query.replace("?", "%s")
        try:
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
        except Exception as e:
            pass
        return cur

    def executescript(self, script):
        cur = conn.cursor()
        for statement in script.split(';'):
            if statement.strip():
                try:
                    cur.execute(statement)
                except Exception:
                    pass

db = DBWrapper()

# Создание таблиц
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id BIGINT PRIMARY KEY,
    username TEXT,
    balance INTEGER NOT NULL DEFAULT 0,
    games INTEGER NOT NULL DEFAULT 0,
    wagered INTEGER NOT NULL DEFAULT 0,
    won INTEGER NOT NULL DEFAULT 0,
    deposited INTEGER NOT NULL DEFAULT 0,
    created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mines_games(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    bet INTEGER NOT NULL,
    mines_count INTEGER NOT NULL,
    mines TEXT NOT NULL,
    opened TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS withdrawals(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created TEXT DEFAULT CURRENT_TIMESTAMP,
    processed TEXT
);
CREATE TABLE IF NOT EXISTS payments(
    charge_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    created TEXT DEFAULT CURRENT_TIMESTAMP
);
""")


for _t, _col in (("payments", "refunded INTEGER NOT NULL DEFAULT 0"),
                 ("withdrawals", "paid INTEGER NOT NULL DEFAULT 0")):
    try:
        db.execute(f"ALTER TABLE {_t} ADD COLUMN {_col}")
    except Exception:
        pass                                              # колонка уже есть


# закрыть старые незавершённые игры с поля 5x5
for _g in db.execute("SELECT id, user_id, bet, mines FROM mines_games WHERE active=1").fetchall():
    if any(i >= GRID for i in json.loads(_g["mines"])):
        db.execute("UPDATE mines_games SET active=0 WHERE id=?", (_g["id"],))
        db.execute("UPDATE users SET balance=balance+? WHERE id=?", (_g["bet"], _g["user_id"]))


def is_sponsor_user(username: str | None) -> bool:
    return (username or "").lower() in SPONSOR_USERS


def is_admin_user(uid: int, username: str | None) -> bool:
    return uid in ADMIN_IDS or (username or "").lower() in ADMIN_USERS


def ensure_user(uid: int, username: str | None):
    db.execute("INSERT OR IGNORE INTO users(id, username) VALUES(?, ?)", (uid, username))
    db.execute("UPDATE users SET username=? WHERE id=?", (username, uid))
    code = SPONSOR_USERS.get((username or "").lower())
    if code:                                       # автопривязка кода автора к спонсору
        cur = db.execute("UPDATE creators SET owner_id=? WHERE code=? AND owner_id IS NULL",
                         (uid, code))
        if cur.rowcount == 1:
            creator_settle(code)                   # выплатить накопленное до привязки


def get_user(uid: int):
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def balance_of(uid: int) -> int:
    row = get_user(uid)
    return row["balance"] if row else 0


def take(uid: int, amount: int) -> bool:
    """Атомарно списать amount, если хватает баланса."""
    cur = db.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
                     (amount, uid, amount))
    return cur.rowcount == 1


def give(uid: int, amount: int):
    db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))


def stat(uid: int, wagered: int, won: int):
    db.execute("UPDATE users SET games=games+1, wagered=wagered+?, won=won+? WHERE id=?",
               (wagered, won, uid))


# ───────────────────────── утилиты ─────────────────────────
_locks: dict[int, asyncio.Lock] = {}


def lock_for(uid: int) -> asyncio.Lock:
    return _locks.setdefault(uid, asyncio.Lock())


async def show(target, text: str, kb=None):
    """Редактирует сообщение (callback) или отправляет новое (message)."""
    if isinstance(target, CallbackQuery):
        msg = target.message
        if msg.photo:                              # главное меню с фото: текстом не отредактировать
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.answer(text, reply_markup=kb)
        else:
            try:
                await msg.edit_text(text, reply_markup=kb)
            except Exception:
                await msg.answer(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "6590.jpg")
_logo_id: list[str] = []                           # кэш file_id после первой отправки
SUPPORT_USERS = ["Dural", "Nesquik"]


async def show_menu(target, text: str):
    """Главное меню: фото сверху, подпись и кнопки снизу."""
    msg = target.message if isinstance(target, CallbackQuery) else target
    if isinstance(target, CallbackQuery):
        try:
            await msg.delete()
        except Exception:
            pass
        await target.answer()
    try:
        photo = _logo_id[0] if _logo_id else FSInputFile(LOGO_PATH)
        sent = await msg.answer_photo(photo, caption=text, reply_markup=main_menu())
        if not _logo_id and sent.photo:
            _logo_id.append(sent.photo[-1].file_id)
    except Exception:
        logging.exception("не удалось отправить фото меню (%s)", LOGO_PATH)
        await msg.answer(text, reply_markup=main_menu())


def menu_text(uid: int, extra: str = "") -> str:
    return (extra + "🎰 <b>RubUP Casino</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"💰 Баланс: <b>{balance_of(uid)} ⭐</b>\n"
            "━━━━━━━━━━━━━━\n"
            "🆘 Поддержка: " + " ".join(f"@{u}" for u in SUPPORT_USERS) + "\n"
            "Выберите действие 👇")


def main_menu():
    b = InlineKeyboardBuilder()
    b.button(text="💣 Мины", callback_data="game:mines")
    b.button(text="🚀 Апгрейдер", callback_data="game:up")
    b.button(text="🪜 Лестница", callback_data="game:ladder")
    b.button(text="🎲 Куб", callback_data="dice:menu")
    b.button(text="🎮 Все игры", callback_data="games:all")
    b.button(text="👤 Профиль", callback_data="menu:profile")
    b.button(text="🏆 Топы", callback_data="top:menu")
    b.button(text="➕ Пополнить", callback_data="menu:deposit")
    b.button(text="💸 Вывод", callback_data="wd:menu")
    b.button(text="🎒 Инвентарь", callback_data="inv:menu")
    b.button(text="🔼 NFT Апгрейдер", callback_data="nup:menu")
    b.button(text="🎟 Код автора", callback_data="ac:enter")
    b.button(text="🎁 Промокод", callback_data="pc:enter")
    b.button(text="🤝 Меню спонсора", callback_data="sp:enter")
    b.button(text="🔐 Админ панель", callback_data="adm:enter")
    for u in SUPPORT_USERS:
        b.button(text=f"🆘 Поддержка @{u}", url=f"https://t.me/{u}")
    b.adjust(2, 2, 1, 2, 2, 2, 2, 2, 2)
    return b.as_markup()


def back_kb():
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ В меню", callback_data="menu:main")
    return b.as_markup()


# ───────────────────────── меню и профиль ─────────────────────────
@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    ensure_user(m.from_user.id, m.from_user.username)
    extra = ""
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("c_"):
        r = db.execute("SELECT * FROM creators WHERE slug=?", (parts[1][2:].lower(),)).fetchone()
        if r and apply_creator(m.from_user.id, r["code"]) == "ok":
            extra = f"🎟 Код автора <b>{r['title']}</b> применён.\n\n"
    await show_menu(m, menu_text(m.from_user.id, extra))


@router.callback_query(F.data == "menu:main")
async def cb_main(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ensure_user(c.from_user.id, c.from_user.username)
    await show_menu(c, menu_text(c.from_user.id))


@router.callback_query(F.data == "menu:profile")
async def cb_profile(c: CallbackQuery):
    ensure_user(c.from_user.id, c.from_user.username)
    u = get_user(c.from_user.id)
    pending = db.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM withdrawals WHERE user_id=? AND status='pending'",
        (c.from_user.id,)).fetchone()["s"]
    text = (
        "👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{u['id']}</code>\n"
        f"💰 Баланс: <b>{u['balance']} ⭐</b>\n"
        f"⏳ На выводе: {pending} ⭐\n"
        f"📥 Пополнено всего: {u['deposited']} ⭐\n"
        f"🎮 Игр сыграно: {u['games']}\n"
        f"🎯 Поставлено: {u['wagered']} ⭐\n"
        f"🏆 Выиграно: {u['won']} ⭐"
    )
    await show(c, text, back_kb())


TOPS = {
    "stars": ("⭐ Топ по звёздам", "balance", "на балансе"),
    "deps": ("💰 Топ по депам", "deposited", "пополнено"),
    "wins": ("🏆 Топ по выигрышам", "won", "выиграно"),
}
MEDALS = ["🥇", "🥈", "🥉"]


def mask_name(r) -> str:
    n = r["username"]
    if n:
        return "@" + (n[:3] + "***" if len(n) > 3 else n[0] + "***")
    return f"id•••{str(r['id'])[-3:]}"


def top_kb(active: str | None = None):
    b = InlineKeyboardBuilder()
    for key, (title, _, _) in TOPS.items():
        b.button(text=("• " if key == active else "") + title, callback_data=f"top:{key}")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "top:menu")
async def cb_top_menu(c: CallbackQuery):
    await show(c, "🏆 <b>Топы игроков</b>\nВыберите рейтинг:", top_kb())


@router.callback_query(F.data.in_({f"top:{k}" for k in TOPS}))
async def cb_top(c: CallbackQuery):
    ensure_user(c.from_user.id, c.from_user.username)
    title, col, word = TOPS[c.data.split(":")[1]]
    rows = db.execute(f"SELECT id, username, {col} v FROM users WHERE {col}>0 "
                      f"ORDER BY {col} DESC, id LIMIT 10").fetchall()
    lines = [f"{MEDALS[i] if i < 3 else str(i + 1) + '.'} {mask_name(r)} — <b>{r['v']} ⭐</b>"
             for i, r in enumerate(rows)]
    me = db.execute(f"SELECT {col} v FROM users WHERE id=?", (c.from_user.id,)).fetchone()
    mine = me["v"] if me else 0
    place = ""
    if mine > 0:
        n = db.execute(f"SELECT COUNT(*) FROM users WHERE {col}>?", (mine,)).fetchone()[0] + 1
        place = f"\n\n👤 Ваше место: <b>#{n}</b> — {mine} ⭐ {word}"
    await show(c, f"<b>{title}</b>\n━━━━━━━━━━━━━━\n"
                  + ("\n".join(lines) if lines else "Пока пусто.") + place,
               top_kb(c.data.split(":")[1]))


@router.message(Command("balance"))
async def cmd_balance(m: Message):
    ensure_user(m.from_user.id, m.from_user.username)
    await m.answer(f"💰 Ваш баланс: <b>{balance_of(m.from_user.id)} ⭐</b>")


@router.message(Command("profile"))
async def cmd_profile(m: Message):
    ensure_user(m.from_user.id, m.from_user.username)
    u = get_user(m.from_user.id)
    await m.answer(
        f"👤 <b>Профиль</b>\n💰 Баланс: <b>{u['balance']} ⭐</b>\n"
        f"🎮 Игр: {u['games']} | 🎯 Поставлено: {u['wagered']} | 🏆 Выиграно: {u['won']}",
        reply_markup=back_kb())


# ───────────────────────── пополнение звёздами ─────────────────────────
class DepositState(StatesGroup):
    waiting = State()


@router.callback_query(F.data == "menu:deposit")
async def cb_deposit(c: CallbackQuery, state: FSMContext):
    await state.clear()
    b = InlineKeyboardBuilder()
    for a in DEPOSIT_OPTIONS:
        b.button(text=f"{a} ⭐", callback_data=f"dep:{a}")
    b.button(text="✏️ Своя сумма", callback_data="depc")
    b.button(text="🖼 Пополнить NFT", url=NFT_URL)
    b.button(text="📨 Я отправил NFT", callback_data="nftreq:start")
    b.button(text="🎒 Инвентарь", callback_data="inv:menu")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(3, 3, 1, 1, 1, 1, 1)
    await show(c, "➕ <b>Пополнение</b>\nВыберите сумму или введите свою (оплата Telegram Stars).\n"
                  f"NFT: отправьте его на @{NFT_USERNAME} (кнопка «Пополнить NFT»), затем нажмите «📨 Я отправил NFT» — "
                  "заявка уйдёт администратору, цену бот определит сам.", b.as_markup())


async def send_deposit_invoice(bot: Bot, uid: int, amount: int):
    await bot.send_invoice(
        chat_id=uid,
        title=f"Пополнение {amount} ⭐",
        description=f"Игровой баланс +{amount} ⭐",
        payload=f"deposit:{uid}:{amount}",
        currency="XTR",
        prices=[LabeledPrice(label="Пополнение", amount=amount)],
        provider_token="",
    )


@router.callback_query(F.data.startswith("dep:"))
async def cb_dep_amount(c: CallbackQuery, bot: Bot):
    amount = int(c.data.split(":")[1])
    if amount not in DEPOSIT_OPTIONS:
        return await c.answer("Неверная сумма", show_alert=True)
    await send_deposit_invoice(bot, c.from_user.id, amount)
    await c.answer()


@router.callback_query(F.data == "depc")
async def cb_dep_custom(c: CallbackQuery, state: FSMContext):
    await state.set_state(DepositState.waiting)
    await show(c, f"✏️ Введите сумму пополнения числом ({DEPOSIT_MIN}–{DEPOSIT_MAX} ⭐):", back_kb())


@router.message(DepositState.waiting)
async def msg_dep_custom(m: Message, state: FSMContext, bot: Bot):
    text = (m.text or "").strip()
    if not text.isdigit():
        return await m.answer("Введите целое число.", reply_markup=back_kb())
    amount = int(text)
    if not DEPOSIT_MIN <= amount <= DEPOSIT_MAX:
        return await m.answer(f"Сумма должна быть от {DEPOSIT_MIN} до {DEPOSIT_MAX} ⭐.",
                              reply_markup=back_kb())
    await state.clear()
    await send_deposit_invoice(bot, m.from_user.id, amount)


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def paid(m: Message, bot: Bot):
    p = m.successful_payment
    ensure_user(m.from_user.id, m.from_user.username)
    cur = db.execute("INSERT OR IGNORE INTO payments(charge_id, user_id, amount) VALUES(?,?,?)",
                     (p.telegram_payment_charge_id, m.from_user.id, p.total_amount))
    if cur.rowcount == 1:
        give(m.from_user.id, p.total_amount)
        db.execute("UPDATE users SET deposited=deposited+? WHERE id=?",
                   (p.total_amount, m.from_user.id))
        await creator_commission(bot, m.from_user.id, p.total_amount)
    await m.answer(f"✅ Баланс пополнен на <b>{p.total_amount} ⭐</b>\n"
                   f"Теперь у вас: <b>{balance_of(m.from_user.id)} ⭐</b>",
                   reply_markup=main_menu())


# ───────────────────────── коды авторов и меню спонсора ─────────────────────────
db.execute("""CREATE TABLE IF NOT EXISTS creators(
    code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    owner_id BIGINT,
    pending_h INTEGER NOT NULL DEFAULT 0,
    earned INTEGER NOT NULL DEFAULT 0,
    donations INTEGER NOT NULL DEFAULT 0
)""")
for _col in ("creator_code TEXT", "creator_donated INTEGER NOT NULL DEFAULT 0"):
    try:
        db.execute(f"ALTER TABLE users ADD COLUMN {_col}")
    except Exception:
        pass
for _code, _title, _slug in CREATOR_SEEDS:
    db.execute("INSERT OR IGNORE INTO creators(code, title, slug) VALUES(?,?,?)",
               (_code, _title, _slug))

db.execute("""CREATE TABLE IF NOT EXISTS saved_logins(
    user_id BIGINT NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY(user_id, kind)
)""")


def login_saved(uid: int, kind: str) -> bool:
    return db.execute("SELECT 1 FROM saved_logins WHERE user_id=? AND kind=?", (uid, kind)).fetchone() is not None


def login_save(uid: int, kind: str):
    db.execute("INSERT OR IGNORE INTO saved_logins(user_id, kind) VALUES(?,?)", (uid, kind))


def login_forget(uid: int, kind: str):
    db.execute("DELETE FROM saved_logins WHERE user_id=? AND kind=?", (uid, kind))


def save_choice_kb(prefix: str):
    b = InlineKeyboardBuilder()
    b.button(text="💾 Сохранить вход (навсегда)", callback_data=f"{prefix}:save:1")
    b.button(text="🔁 Нет, вводить код при входе", callback_data=f"{prefix}:save:0")
    b.adjust(1)
    return b.as_markup()


SAVE_CHOICE_TEXT = ("✅ <b>{what} верный!</b>\n\nСохранить вход?\n"
                    "💾 <b>Сохранить</b> — больше вводить не нужно, вход останется навсегда "
                    "(сбросить можно кнопкой «🚪 Выйти»).\n"
                    "🔁 <b>Нет</b> — {what_lc} придётся вводить при каждом заходе.")

sponsor_sessions: set[int] = {r["user_id"] for r in
                              db.execute("SELECT user_id FROM saved_logins WHERE kind='sponsor'")}
_sp_fails: dict[int, list] = {}


class UserState(StatesGroup):
    author = State()


class SponsorState(StatesGroup):
    code = State()
    bind = State()


def find_creator(text: str):
    return db.execute("SELECT * FROM creators WHERE code=?",
                      ((text or "").strip().casefold(),)).fetchone()


def apply_creator(uid: int, code: str) -> str:
    u = get_user(uid)
    if u["creator_code"]:
        return "already"
    r = db.execute("SELECT owner_id FROM creators WHERE code=?", (code,)).fetchone()
    if r and r["owner_id"] == uid:
        return "own"
    db.execute("UPDATE users SET creator_code=? WHERE id=?", (code, uid))
    return "ok"


def creator_settle(code: str) -> tuple[int, int | None]:
    r = db.execute("SELECT * FROM creators WHERE code=?", (code,)).fetchone()
    if not r or not r["owner_id"]:
        return 0, None
    whole = r["pending_h"] // 100
    if whole <= 0:
        return 0, r["owner_id"]
    give(r["owner_id"], whole)
    db.execute("UPDATE creators SET pending_h=pending_h-?, earned=earned+? WHERE code=?",
               (whole * 100, whole, code))
    return whole, r["owner_id"]


async def creator_commission(bot: Bot, uid: int, amount: int):
    u = get_user(uid)
    code = u["creator_code"] if u else None
    if not code:
        return
    db.execute("UPDATE creators SET donations=donations+?, pending_h=pending_h+? WHERE code=?",
               (amount, amount * CREATOR_PCT, code))
    db.execute("UPDATE users SET creator_donated=creator_donated+? WHERE id=?", (amount, uid))
    got, owner = creator_settle(code)
    if got and owner:
        try:
            await bot.send_message(
                owner, f"💸 Вам начислено <b>{got} ⭐</b> — {CREATOR_PCT}% от пополнения игрока "
                       f"по вашему коду автора.\nБаланс: <b>{balance_of(owner)} ⭐</b>")
        except Exception:
            pass


@router.callback_query(F.data == "ac:enter")
async def cb_ac_enter(c: CallbackQuery, state: FSMContext):
    ensure_user(c.from_user.id, c.from_user.username)
    u = get_user(c.from_user.id)
    if u["creator_code"]:
        r = db.execute("SELECT title FROM creators WHERE code=?", (u["creator_code"],)).fetchone()
        return await show(c, f"🎟 Вы уже используете код автора <b>{r['title']}</b>.\n"
                             "Изменить его нельзя.", back_kb())
    await state.set_state(UserState.author)
    await show(c, f"🎟 Введите код автора.\nАвтор получит {CREATOR_PCT}% от ваших пополнений "
                  "за счёт казино — с вашего баланса ничего не списывается.", back_kb())


@router.message(UserState.author)
async def msg_author_code(m: Message, state: FSMContext):
    ensure_user(m.from_user.id, m.from_user.username)
    r = find_creator(m.text)
    if not r:
        return await m.answer("❌ Такого кода автора нет. Попробуйте ещё раз.", reply_markup=back_kb())
    st = apply_creator(m.from_user.id, r["code"])
    await state.clear()
    if st == "own":
        return await m.answer("❌ Нельзя использовать собственный код.", reply_markup=main_menu())
    if st == "already":
        return await m.answer("🎟 Код автора у вас уже выбран.", reply_markup=main_menu())
    await m.answer(f"✅ Код автора <b>{r['title']}</b> применён!", reply_markup=main_menu())


# ───────────────────────── промокоды ─────────────────────────
PROMO_SEEDS = [
    ("ОТКРЫТИЕ", 500, 50),
    ("сигмабой", 250, 3),
    ("JQG61Y", 250, 5),
    ("WKQH5", 300, 3),
    ("AKWJ6", 400, 4),
    ("WKS57", 750, 7),
]
db.executescript("""
CREATE TABLE IF NOT EXISTS promos(
    code TEXT PRIMARY KEY,
    reward INTEGER NOT NULL,
    max_uses INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS promo_uses(
    code TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    created TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(code, user_id)
);
""")
for _c, _r, _m in PROMO_SEEDS:
    db.execute("INSERT OR IGNORE INTO promos(code, reward, max_uses) VALUES(?,?,?)",
               (_c.strip().casefold(), _r, _m))


class PromoState(StatesGroup):
    code = State()


def redeem_promo(uid: int, text: str) -> tuple[str, int]:
    code = (text or "").strip().casefold()
    r = db.execute("SELECT * FROM promos WHERE code=?", (code,)).fetchone()
    if not r:
        return "none", 0
    db.execute("BEGIN IMMEDIATE")
    try:
        if db.execute("SELECT 1 FROM promo_uses WHERE code=? AND user_id=?", (code, uid)).fetchone():
            db.execute("ROLLBACK")
            return "used", 0
        cur = db.execute("UPDATE promos SET used=used+1 WHERE code=? AND used<max_uses", (code,))
        if cur.rowcount != 1:
            db.execute("ROLLBACK")
            return "empty", 0
        db.execute("INSERT INTO promo_uses(code, user_id) VALUES(?,?)", (code, uid))
        give(uid, r["reward"])
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return "ok", r["reward"]


@router.callback_query(F.data == "pc:enter")
async def cb_promo_enter(c: CallbackQuery, state: FSMContext):
    ensure_user(c.from_user.id, c.from_user.username)
    await state.set_state(PromoState.code)
    await show(c, "🎁 Введите промокод:", back_kb())


@router.message(PromoState.code)
async def msg_promo(m: Message, state: FSMContext):
    ensure_user(m.from_user.id, m.from_user.username)
    async with lock_for(m.from_user.id):
        st, reward = redeem_promo(m.from_user.id, m.text)
    if st == "none":
        return await m.answer("❌ Такого промокода нет. Попробуйте ещё раз.", reply_markup=back_kb())
    await state.clear()
    if st == "used":
        return await m.answer("⚠️ Вы уже активировали этот промокод.", reply_markup=main_menu())
    if st == "empty":
        return await m.answer("😔 У этого промокода закончились активации.", reply_markup=main_menu())
    await m.answer(f"✅ Промокод активирован! Начислено <b>{reward} ⭐</b>\n"
                   f"Баланс: <b>{balance_of(m.from_user.id)} ⭐</b>", reply_markup=main_menu())


# ── меню спонсора ──
def sponsor_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📊 Моя статистика", callback_data="sp:stats")
    b.button(text="👥 Мои игроки", callback_data="sp:players")
    b.button(text="🔗 Ссылка и промо-текст", callback_data="sp:link")
    b.button(text="🎁 Получить промокоды", callback_data="sp:promos")
    b.button(text="🏆 Рейтинг авторов", callback_data="sp:top")
    b.button(text="🚪 Выйти", callback_data="sp:logout")
    b.button(text="⬅️ В меню", callback_data="sp:exit")
    b.button(text="🔗 Привязать аккаунт", callback_data="sp:bind")
    b.adjust(1)
    return b.as_markup()


def sponsor_back_kb():
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ В меню спонсора", callback_data="sp:menu")
    return b.as_markup()


def my_creators(uid: int):
    return db.execute("SELECT * FROM creators WHERE owner_id=?", (uid,)).fetchall()


def sponsor_text(uid: int) -> str:
    rows = my_creators(uid)
    if rows:
        codes = ", ".join(f"<b>{r['title']}</b>" for r in rows)
        return f"🤝 <b>Меню спонсора</b>\n🎟 Ваш код: {codes}\nВыберите действие:"
    return ("🤝 <b>Меню спонсора</b>\n"
            "🔑 Ваш код автора ещё не привязан. Нажмите «📊 Моя статистика» или «🔗 Привязать аккаунт» "
            "и введите ваш код — после этого откроется статистика.\nВыберите действие:")


def creator_stats_text(r) -> str:
    n = db.execute("SELECT COUNT(*) c FROM users WHERE creator_code=?", (r["code"],)).fetchone()["c"]
    return (f"🎟 <b>{r['title']}</b>\n"
            f"👥 Игроков с вашим кодом: {n}\n"
            f"💵 Их пополнения: {r['donations']} ⭐\n"
            f"💰 Заработано ({CREATOR_PCT}%): <b>{r['earned']} ⭐</b>\n"
            f"⏳ Копится до следующей ⭐: {r['pending_h'] % 100 / 100:.2f}")


@router.callback_query(F.data == "sp:enter")
async def cb_sp_enter(c: CallbackQuery, state: FSMContext):
    ensure_user(c.from_user.id, c.from_user.username)
    if _sp_ok(c):
        await state.clear()
        return await show(c, sponsor_text(c.from_user.id), sponsor_kb())
    f = _sp_fails.get(c.from_user.id)
    if f and f[1] > time.time():
        return await c.answer(f"Слишком много попыток. Подождите {int(f[1] - time.time())} сек.",
                              show_alert=True)
    await state.set_state(SponsorState.code)
    await show(c, "🔑 Введите код спонсора:", back_kb())


@router.message(SponsorState.code)
async def msg_sp_code(m: Message, state: FSMContext):
    uid = m.from_user.id
    f = _sp_fails.setdefault(uid, [0, 0.0])
    if f[1] > time.time():
        return await m.answer(f"⛔ Слишком много попыток. Подождите {int(f[1] - time.time())} сек.")
    try:
        await m.delete()
    except Exception:
        pass
    ensure_user(uid, m.from_user.username)
    if (m.text or "").strip() == SPONSOR_CODE:
        _sp_fails.pop(uid, None)
        sponsor_sessions.add(uid)
        await state.clear()
        return await m.answer(SAVE_CHOICE_TEXT.format(what="Код", what_lc="код"),
                              reply_markup=save_choice_kb("sp"))
    f[0] += 1
    if f[0] >= PANEL_MAX_TRIES:
        f[0], f[1] = 0, time.time() + PANEL_LOCK_SEC
        await state.clear()
        return await m.answer("⛔ Неверный код. Доступ заблокирован на 10 минут.", reply_markup=back_kb())
    await m.answer(f"❌ Неверный код. Осталось попыток: {PANEL_MAX_TRIES - f[0]}", reply_markup=back_kb())


def _sp_ok_user(uid: int, username: str | None) -> bool:
    return uid in sponsor_sessions or is_sponsor_user(username)


def _sp_ok(c: CallbackQuery) -> bool:
    return _sp_ok_user(c.from_user.id, c.from_user.username)


@router.callback_query(F.data.in_({"sp:save:1", "sp:save:0"}))
async def cb_sp_save(c: CallbackQuery):
    uid = c.from_user.id
    if uid not in sponsor_sessions:
        return await c.answer("Сначала введите код спонсора", show_alert=True)
    if c.data == "sp:save:1":
        login_save(uid, "sponsor")
        note = "💾 Вход сохранён — код спонсора вводить больше не нужно."
    else:
        login_forget(uid, "sponsor")
        note = "🔁 Вход не сохранён — код нужно будет вводить при каждом заходе."
    await show(c, note + "\n\n" + sponsor_text(uid), sponsor_kb())


@router.callback_query(F.data == "sp:menu")
async def cb_sp_menu(c: CallbackQuery, state: FSMContext):
    if not _sp_ok(c):
        return await c.answer("Сначала введите код спонсора", show_alert=True)
    await state.clear()
    await show(c, sponsor_text(c.from_user.id), sponsor_kb())


@router.callback_query(F.data == "sp:exit")
async def cb_sp_exit(c: CallbackQuery, state: FSMContext):
    if not login_saved(c.from_user.id, "sponsor"):
        sponsor_sessions.discard(c.from_user.id)
    await cb_main(c, state)


@router.callback_query(F.data == "sp:logout")
async def cb_sp_logout(c: CallbackQuery, state: FSMContext):
    sponsor_sessions.discard(c.from_user.id)
    login_forget(c.from_user.id, "sponsor")
    await state.clear()
    await show(c, "🚪 Вы вышли из меню спонсора.", main_menu())


async def ask_my_code(c: CallbackQuery, state: FSMContext, nxt: str):
    await state.set_state(SponsorState.bind)
    await state.update_data(nxt=nxt)
    await show(c, "🔑 <b>Введите ваш код</b> (код автора).\n"
                  "Он привяжется к вашему аккаунту, и сразу откроется статистика.",
               sponsor_back_kb())


async def sp_render(kind: str, uid: int, bot: Bot) -> str:
    rows = my_creators(uid)
    if kind == "players":
        codes = [r["code"] for r in rows]
        if not codes:
            return "👥 Пока никто не ввёл ваш код."
        q = ",".join("?" * len(codes))
        pl = db.execute(f"SELECT username, id, creator_donated FROM users WHERE creator_code IN ({q}) "
                        "ORDER BY creator_donated DESC LIMIT 20", codes).fetchall()
        if not pl:
            return "👥 Пока никто не ввёл ваш код."
        lines = [f"{i}. {'@' + p['username'] if p['username'] else 'id' + str(p['id'])} — "
                 f"{p['creator_donated']} ⭐" for i, p in enumerate(pl, 1)]
        return "👥 <b>Ваши игроки</b> (пополнения)\n\n" + "\n".join(lines)
    if kind == "link":
        me = await bot.get_me()
        parts = []
        for r in rows:
            link = f"https://t.me/{me.username}?start=c_{r['slug']}"
            parts.append(f"🎟 <b>{r['title']}</b>\nСсылка: {link}\n\n"
                         f"📣 Промо-текст:\n<i>Заходи в казино @{me.username}! Мины, Апгрейдер, Лестница, Куб. "
                         f"Введи код автора «{r['title']}» или открой ссылку выше.</i>")
        return ("🔗 <b>Ссылка и промо</b>\nПо ссылке код применяется автоматически.\n\n"
                + "\n\n".join(parts))
    return "📊 <b>Ваша статистика</b>\n\n" + "\n\n".join(creator_stats_text(r) for r in rows)


async def sp_page(c: CallbackQuery, state: FSMContext, bot: Bot, kind: str):
    if not _sp_ok(c):
        return await c.answer("Сначала введите код спонсора", show_alert=True)
    if not my_creators(c.from_user.id):
        return await ask_my_code(c, state, kind)
    await state.clear()
    await show(c, await sp_render(kind, c.from_user.id, bot), sponsor_back_kb())


@router.callback_query(F.data == "sp:stats")
async def cb_sp_stats(c: CallbackQuery, state: FSMContext, bot: Bot):
    await sp_page(c, state, bot, "stats")


@router.callback_query(F.data == "sp:players")
async def cb_sp_players(c: CallbackQuery, state: FSMContext, bot: Bot):
    await sp_page(c, state, bot, "players")


@router.callback_query(F.data == "sp:link")
async def cb_sp_link(c: CallbackQuery, state: FSMContext, bot: Bot):
    await sp_page(c, state, bot, "link")


@router.callback_query(F.data == "sp:bind")
async def cb_sp_bind(c: CallbackQuery, state: FSMContext):
    if not _sp_ok(c):
        return await c.answer("Сначала введите код спонсора", show_alert=True)
    await ask_my_code(c, state, "stats")


@router.message(SponsorState.bind)
async def msg_sp_bind(m: Message, state: FSMContext, bot: Bot):
    uid = m.from_user.id
    if not _sp_ok_user(uid, m.from_user.username):
        await state.clear()
        return await m.answer("⛔ Сначала введите код спонсора.", reply_markup=back_kb())
    ensure_user(uid, m.from_user.username)
    nxt = (await state.get_data()).get("nxt", "stats")
    r = find_creator(m.text)
    if not r:
        return await m.answer("❌ Такого кода нет. Проверьте и введите ещё раз.",
                              reply_markup=sponsor_back_kb())
    me = (m.from_user.username or "").lower()
    if r["owner_id"] != uid:
        reserved_for_other = any(cd == r["code"] and u != me for u, cd in SPONSOR_USERS.items())
        if r["owner_id"] or reserved_for_other:
            return await m.answer("❌ Этот код уже закреплён за другим аккаунтом.",
                                  reply_markup=sponsor_back_kb())
        cur = db.execute("UPDATE creators SET owner_id=? WHERE code=? AND owner_id IS NULL",
                         (uid, r["code"]))
        if cur.rowcount != 1:
            return await m.answer("❌ Этот код уже закреплён за другим аккаунтом.",
                                  reply_markup=sponsor_back_kb())
        got, _ = creator_settle(r["code"])
    else:
        got = 0
    await state.clear()
    head = f"✅ Код <b>{r['title']}</b> привязан к вашему аккаунту." \
           + (f"\nВыплачено накопленное: {got} ⭐." if got else "")
    await m.answer(head + "\n\n" + await sp_render(nxt, uid, bot), reply_markup=sponsor_back_kb())


SPONSOR_PROMO_MIN, SPONSOR_PROMO_MAX = 500, 2500
SPONSOR_PROMO_USES = 2
SPONSOR_PROMO_PERIOD = 24 * 3600
db.execute("""CREATE TABLE IF NOT EXISTS sponsor_promos(
    user_id BIGINT PRIMARY KEY,
    claimed_at INTEGER NOT NULL,
    codes TEXT NOT NULL
)""")
_PROMO_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_promo_code() -> tuple[str, int]:
    reward = rng.randint(SPONSOR_PROMO_MIN, SPONSOR_PROMO_MAX)
    while True:
        code = "".join(rng.choice(_PROMO_ALPHABET) for _ in range(8))
        cur = db.execute("INSERT OR IGNORE INTO promos(code, reward, max_uses) VALUES(?,?,?)",
                         (code.casefold(), reward, SPONSOR_PROMO_USES))
        if cur.rowcount == 1:
            return code, reward


def _promos_text(codes: list[str], head: str) -> str:
    lines = []
    for c in codes:
        r = db.execute("SELECT reward, used, max_uses FROM promos WHERE code=?", (c.casefold(),)).fetchone()
        if r:
            lines.append(f"<code>{c}</code> — <b>{r['reward']} ⭐</b> "
                         f"(активаций: {r['used']}/{r['max_uses']})")
    return (f"{head}\n\n" + "\n".join(lines) +
            "\n\nВводится в «🎁 Промокод» в главном меню.")


@router.callback_query(F.data == "sp:promos")
async def cb_sp_promos(c: CallbackQuery):
    if not _sp_ok(c):
        return await c.answer("Сначала введите код спонсора", show_alert=True)
    uid = c.from_user.id
    async with lock_for(uid):
        row = db.execute("SELECT * FROM sponsor_promos WHERE user_id=?", (uid,)).fetchone()
        now = int(time.time())
        if row and now - row["claimed_at"] < SPONSOR_PROMO_PERIOD:
            left = SPONSOR_PROMO_PERIOD - (now - row["claimed_at"])
            h, m = left // 3600, left % 3600 // 60
            return await show(c, _promos_text(
                json.loads(row["codes"]),
                f"⏳ Новый промокод будет доступен через <b>{h} ч. {m} мин.</b>\n"
                "Ваш текущий промокод:"), sponsor_back_kb())
        code, _reward = _new_promo_code()
        db.execute("INSERT OR REPLACE INTO sponsor_promos(user_id, claimed_at, codes) VALUES(?,?,?)",
                   (uid, now, json.dumps([code])))
    await show(c, _promos_text([code], "🎁 <b>Ваш промокод на сегодня</b>"), sponsor_back_kb())


@router.callback_query(F.data == "sp:top")
async def cb_sp_top(c: CallbackQuery):
    if not _sp_ok(c):
        return await c.answer("Сначала введите код спонсора", show_alert=True)
    rows = db.execute("SELECT c.title, c.donations, "
                      "(SELECT COUNT(*) FROM users u WHERE u.creator_code=c.code) n "
                      "FROM creators c ORDER BY c.donations DESC").fetchall()
    lines = [f"{i}. <b>{r['title']}</b> — {r['n']} игр., {r['donations']} ⭐"
             for i, r in enumerate(rows, 1)]
    await show(c, "🏆 <b>Рейтинг авторов</b> (по пополнениям)\n\n" + "\n".join(lines),
               sponsor_back_kb())


# ───────────────────────── выбор ставки ─────────────────────────
class BetState(StatesGroup):
    waiting = State()


def bet_kb(game: str):
    b = InlineKeyboardBuilder()
    for v in QUICK_BETS:
        b.button(text=f"{v} ⭐", callback_data=f"bet:{game}:{v}")
    b.button(text="✏️ Своя ставка", callback_data=f"betc:{game}")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(3, 2, 1, 1)
    return b.as_markup()


@router.callback_query(F.data.startswith("game:"))
async def cb_game(c: CallbackQuery, state: FSMContext):
    await state.clear()
    game = c.data.split(":")[1]
    if is_new_game(game):
        return await show(c, f"{new_game_title(game)}\n\nБаланс: <b>{balance_of(c.from_user.id)} ⭐</b>\n"
                             "Выберите ставку:", bet_kb(game))
    title = {
        "mines": "💣 <b>Мины</b>\nОткрывайте безопасные клетки и забирайте выигрыш, пока не попали на мину.",
        "ladder": "🪜 <b>Лестница</b>\nПоднимайтесь по 13 ступенькам, выбирая безопасный слот, и забирайте выигрыш в любой момент.",
    }.get(game, "🚀 <b>Апгрейдер</b>\nВыберите множитель: чем он выше, тем меньше шанс.")
    await show(c, f"{title}\n\nБаланс: <b>{balance_of(c.from_user.id)} ⭐</b>\nВыберите ставку:",
               bet_kb(game))


@router.callback_query(F.data.startswith("betc:"))
async def cb_custom_bet(c: CallbackQuery, state: FSMContext):
    game = c.data.split(":")[1]
    await state.set_state(BetState.waiting)
    await state.update_data(game=game)
    await show(c, f"✏️ Введите ставку числом ({MIN_BET}–{MAX_BET} ⭐):", back_kb())


@router.message(BetState.waiting)
async def msg_custom_bet(m: Message, state: FSMContext):
    data = await state.get_data()
    if not (m.text or "").strip().isdigit():
        return await m.answer("Введите целое число.")
    bet = int(m.text.strip())
    if not MIN_BET <= bet <= MAX_BET:
        return await m.answer(f"Ставка должна быть от {MIN_BET} до {MAX_BET} ⭐.")
    await state.clear()
    await choose_options(m, data["game"], bet)


@router.callback_query(F.data.startswith("bet:"))
async def cb_bet(c: CallbackQuery):
    _, game, bet = c.data.split(":")
    await choose_options(c, game, int(bet))


async def choose_options(target, game: str, bet: int):
    uid = target.from_user.id
    if balance_of(uid) < bet:
        return await show(target, "❌ Недостаточно средств. Пополните баланс.", main_menu())
    if is_new_game(game):
        return await choose_new_game(target, game, bet)
    b = InlineKeyboardBuilder()
    if game == "mines":
        for mc in MINES_OPTIONS:
            b.button(text=f"💣 {mc}", callback_data=f"mstart:{bet}:{mc}")
        text = f"💣 Ставка: <b>{bet} ⭐</b>\nСколько мин на поле?"
        b.adjust(3)
    elif game == "ladder":
        lines = []
        for key, cfg in LADDER_MODES.items():
            b.button(text=f"{cfg['name']} • до x{cfg['top']}", callback_data=f"lstart:{bet}:{key}")
            ch = (cfg["slots"] - cfg["mines"]) / cfg["slots"] * 100
            lines.append(f"{cfg['name']}: {cfg['slots']} слота, мин {cfg['mines']}, "
                         f"шанс ступеньки {ch:.0f}%, на 13-й x{cfg['top']}")
        text = f"🪜 Ставка: <b>{bet} ⭐</b>\n\n" + "\n".join(lines) + "\n\nВыберите сложность:"
        b.adjust(1)
    else:
        for x in UPGRADE_X:
            chance = (1 - HOUSE_EDGE) / x * 100
            b.button(text=f"x{x:g} • {chance:.1f}%", callback_data=f"ugo:{bet}:{x}")
        text = f"🚀 Ставка: <b>{bet} ⭐</b>\nВыберите множитель (x • шанс):"
        b.adjust(2)
    b.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    await show(target, text, b.as_markup())


# ───────────────────────── игра: МИНЫ ─────────────────────────
def mines_mult(mines: int, opened: int) -> float:
    if opened == 0:
        return 1.0
    return (1 - HOUSE_EDGE) * math.comb(GRID, opened) / math.comb(GRID - mines, opened)


def mines_text(g, finished: str | None = None) -> str:
    opened = json.loads(g["opened"])
    mult = mines_mult(g["mines_count"], len(opened))
    payout = int(g["bet"] * mult)
    head = (f"💣 <b>Мины</b> | Ставка: {g['bet']} ⭐ | Мин: {g['mines_count']}\n"
            f"Открыто: {len(opened)} | Множитель: <b>x{mult:.2f}</b>\n")
    if finished == "win":
        return head + f"\n🏆 Вы забрали <b>{payout} ⭐</b>!"
    if finished == "lose":
        return head + f"\n💥 Мина! Вы потеряли <b>{g['bet']} ⭐</b>."
    return head + f"\n💰 Можно забрать: <b>{payout} ⭐</b>"


def mines_kb(g, reveal: bool = False):
    opened = json.loads(g["opened"])
    mines = json.loads(g["mines"])
    b = InlineKeyboardBuilder()
    for i in range(GRID):
        if reveal:
            if i in mines:
                b.button(text="💣", callback_data="noop")
            elif i in opened:
                b.button(text="💎", callback_data="noop")
            else:
                b.button(text="▫️", callback_data="noop")
        elif i in opened:
            b.button(text="💎", callback_data="noop")
        else:
            b.button(text="❓", callback_data=f"mcell:{g['id']}:{i}")
    b.adjust(3)
    if reveal:
        b.row(InlineKeyboardButton(text="🔁 Играть ещё", callback_data="game:mines"),
              InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main"))
    else:
        payout = int(g["bet"] * mines_mult(g["mines_count"], len(opened)))
        if opened:
            b.row(InlineKeyboardButton(
                text=f"💰 Забрать {payout} ⭐", callback_data=f"mcash:{g['id']}"))
    return b.as_markup()


def get_game(gid: int):
    return db.execute("SELECT * FROM mines_games WHERE id=?", (gid,)).fetchone()


@router.callback_query(F.data == "noop")
async def cb_noop(c: CallbackQuery):
    await c.answer()


@router.callback_query(F.data.startswith("mstart:"))
async def cb_mines_start(c: CallbackQuery):
    _, bet, mc = c.data.split(":")
    bet, mc = int(bet), int(mc)
    uid = c.from_user.id
    if not (MIN_BET <= bet <= MAX_BET and mc in MINES_OPTIONS):
        return await c.answer("Неверные параметры", show_alert=True)
    async with lock_for(uid):
        if db.execute("SELECT 1 FROM mines_games WHERE user_id=? AND active=1", (uid,)).fetchone():
            return await c.answer("Сначала завершите текущую игру!", show_alert=True)
        if not take(uid, bet):
            return await show(c, "❌ Недостаточно средств.", main_menu())
        mines = rng.sample(range(GRID), mc)
        cur = db.execute("INSERT INTO mines_games(user_id, bet, mines_count, mines) VALUES(?,?,?,?)",
                         (uid, bet, mc, json.dumps(mines)))
        g = get_game(cur.lastrowid)
    await show(c, mines_text(g), mines_kb(g))


@router.callback_query(F.data.startswith("mcell:"))
async def cb_mines_cell(c: CallbackQuery):
    _, gid, idx = c.data.split(":")
    gid, idx = int(gid), int(idx)
    uid = c.from_user.id
    async with lock_for(uid):
        g = get_game(gid)
        if not g or g["user_id"] != uid or not g["active"]:
            return await c.answer("Игра уже завершена", show_alert=True)
        opened = json.loads(g["opened"])
        mines = json.loads(g["mines"])
        if idx in opened:
            return await c.answer()
        if idx in mines:
            db.execute("UPDATE mines_games SET active=0 WHERE id=?", (gid,))
            stat(uid, g["bet"], 0)
            g = get_game(gid)
            await show(c, mines_text(g, "lose"), mines_kb(g, reveal=True))
            return
        opened.append(idx)
        db.execute("UPDATE mines_games SET opened=? WHERE id=?", (json.dumps(opened), gid))
        g = get_game(gid)
        if len(opened) == GRID - g["mines_count"]:
            payout = int(g["bet"] * mines_mult(g["mines_count"], len(opened)))
            db.execute("UPDATE mines_games SET active=0 WHERE id=?", (gid,))
            give(uid, payout)
            stat(uid, g["bet"], payout)
            g = get_game(gid)
            await show(c, mines_text(g, "win"), mines_kb(g, reveal=True))
            return
    await show(c, mines_text(g), mines_kb(g))


@router.callback_query(F.data.startswith("mcash:"))
async def cb_mines_cash(c: CallbackQuery):
    gid = int(c.data.split(":")[1])
    uid = c.from_user.id
    async with lock_for(uid):
        g = get_game(gid)
        if not g or g["user_id"] != uid or not g["active"]:
            return await c.answer("Игра уже завершена", show_alert=True)
        opened = json.loads(g["opened"])
        if not opened:
            return await c.answer("Откройте хотя бы одну клетку", show_alert=True)
        payout = int(g["bet"] * mines_mult(g["mines_count"], len(opened)))
        db.execute("UPDATE mines_games SET active=0 WHERE id=?", (gid,))
        give(uid, payout)
        stat(uid, g["bet"], payout)
        g = get_game(gid)
    await show(c, mines_text(g, "win") + f"\nБаланс: <b>{balance_of(uid)} ⭐</b>",
               mines_kb(g, reveal=True))


# ───────────────────────── игра: АПГРЕЙДЕР ─────────────────────────
@router.callback_query(F.data.startswith("ugo:"))
async def cb_upgrade(c: CallbackQuery):
    _, bet, x = c.data.split(":")
    bet, x = int(bet), float(x)
    uid = c.from_user.id
    if not (MIN_BET <= bet <= MAX_BET and x in UPGRADE_X):
        return await c.answer("Неверные параметры", show_alert=True)
    async with lock_for(uid):
        if not take(uid, bet):
            return await show(c, "❌ Недостаточно средств.", main_menu())
        chance = (1 - HOUSE_EDGE) / x
        roll = rng.random()
        win = roll < chance
        payout = int(bet * x) if win else 0
        if win:
            give(uid, payout)
        stat(uid, bet, payout)
        bal = balance_of(uid)
    filled = max(1, round(chance * 20))
    pos = min(19, int(roll * 20))
    bar = ["🟩" if i < filled else "🟥" for i in range(20)]
    bar[pos] = "⭐" if win else "💀"
    result = (f"🎉 <b>Успех!</b> Апгрейд x{x:g}: <b>+{payout} ⭐</b>" if win
              else f"💥 <b>Неудача.</b> Потеряно <b>{bet} ⭐</b>")
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data="game:up")
    b.button(text="⬅️ Меню", callback_data="menu:main")
    b.adjust(2)
    await show(c, f"🚀 <b>Апгрейдер</b> | Ставка {bet} ⭐ | x{x:g} | шанс {chance*100:.1f}%\n\n"
                  f"{''.join(bar)}\n\n{result}\nБаланс: <b>{bal} ⭐</b>", b.as_markup())


# ───────────────────────── игра: ЛЕСТНИЦА ─────────────────────────
LADDER_STEPS = 13
LADDER_MODES = {
    "easy":   {"name": "🟢 Лёгкий",  "slots": 3, "mines": 1, "top": 4},
    "medium": {"name": "🟡 Средний", "slots": 5, "mines": 2, "top": 8},
    "hard":   {"name": "🔴 Сложный", "slots": 3, "mines": 2, "top": 50},
}

db.execute("""CREATE TABLE IF NOT EXISTS ladder_games(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    bet INTEGER NOT NULL,
    mode TEXT NOT NULL,
    mines TEXT NOT NULL,
    picks TEXT NOT NULL DEFAULT '[]',
    step INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
)""")


def wipe_balances(uid: int | None = None):
    games = ("mines_games", "ladder_games", "bj_games", "hilo_games", "crash_games")
    if uid is None:
        for t in games:
            db.execute(f"UPDATE {t} SET active=0 WHERE active=1")
        db.execute("UPDATE users SET balance=0")
    else:
        for t in games:
            db.execute(f"UPDATE {t} SET active=0 WHERE active=1 AND user_id=?", (uid,))
        db.execute("UPDATE users SET balance=0 WHERE id=?", (uid,))


def ladder_mult(mode: str, step: int) -> float:
    if step <= 0:
        return 1.0
    return round(LADDER_MODES[mode]["top"] ** (step / LADDER_STEPS), 2)


def ladder_payout(g) -> int:
    return int(g["bet"] * ladder_mult(g["mode"], g["step"]))


def get_ladder(gid: int):
    return db.execute("SELECT * FROM ladder_games WHERE id=?", (gid,)).fetchone()


def ladder_rows(g) -> str:
    cfg = LADDER_MODES[g["mode"]]
    mines, picks = json.loads(g["mines"]), json.loads(g["picks"])
    lines = []
    for i in range(LADDER_STEPS - 1, -1, -1):
        row = []
        for sl in range(cfg["slots"]):
            chosen = i < len(picks) and picks[i] == sl
            if sl in mines[i]:
                row.append("💥" if chosen else "💣")
            else:
                row.append("💎" if chosen else "▫️")
        lines.append(f"{i + 1:>2}. {''.join(row)}  x{ladder_mult(g['mode'], i + 1):.2f}")
    return "\n".join(lines)


def ladder_text(g, finished: str | None = None) -> str:
    cfg = LADDER_MODES[g["mode"]]
    chance = (cfg["slots"] - cfg["mines"]) / cfg["slots"] * 100
    mult = ladder_mult(g["mode"], g["step"])
    head = (f"🪜 <b>Лестница</b> | {cfg['name']} | Ставка: {g['bet']} ⭐\n"
            f"Слотов: {cfg['slots']} • Мин: {cfg['mines']} • Шанс ступеньки: {chance:.0f}%\n"
            f"Пройдено: {g['step']}/{LADDER_STEPS} | Множитель: <b>x{mult:.2f}</b>\n")
    if finished == "win":
        return head + f"\n{ladder_rows(g)}\n\n🏆 Вы забрали <b>{ladder_payout(g)} ⭐</b>!"
    if finished == "lose":
        return head + f"\n{ladder_rows(g)}\n\n💥 Мина! Вы потеряли <b>{g['bet']} ⭐</b>."
    nxt = ladder_mult(g["mode"], g["step"] + 1)
    tail = f"\n⬆️ Ступенька {g['step'] + 1}: выберите слот (следующий x{nxt:.2f})"
    if g["step"] > 0:
        tail = f"\n💰 Можно забрать: <b>{ladder_payout(g)} ⭐</b>" + tail
    return head + tail


def ladder_kb(g, reveal: bool = False):
    b = InlineKeyboardBuilder()
    if reveal:
        b.button(text="🔁 Играть ещё", callback_data="game:ladder")
        b.button(text="⬅️ Меню", callback_data="menu:main")
        b.adjust(2)
        return b.as_markup()
    slots = LADDER_MODES[g["mode"]]["slots"]
    for sl in range(slots):
        b.button(text="❓", callback_data=f"lcell:{g['id']}:{sl}")
    b.adjust(slots)
    if g["step"] > 0:
        b.row(InlineKeyboardButton(text=f"💰 Забрать {ladder_payout(g)} ⭐",
                                   callback_data=f"lcash:{g['id']}"))
    return b.as_markup()


@router.callback_query(F.data.startswith("lstart:"))
async def cb_ladder_start(c: CallbackQuery):
    _, bet, mode = c.data.split(":")
    bet = int(bet)
    uid = c.from_user.id
    if not (MIN_BET <= bet <= MAX_BET and mode in LADDER_MODES):
        return await c.answer("Неверные параметры", show_alert=True)
    cfg = LADDER_MODES[mode]
    async with lock_for(uid):
        if db.execute("SELECT 1 FROM ladder_games WHERE user_id=? AND active=1", (uid,)).fetchone():
            return await c.answer("Сначала завершите текущую игру!", show_alert=True)
        if not take(uid, bet):
            return await show(c, "❌ Недостаточно средств.", main_menu())
        mines = [rng.sample(range(cfg["slots"]), cfg["mines"]) for _ in range(LADDER_STEPS)]
        cur = db.execute("INSERT INTO ladder_games(user_id, bet, mode, mines) VALUES(?,?,?,?)",
                         (uid, bet, mode, json.dumps(mines)))
        g = get_ladder(cur.lastrowid)
    await show(c, ladder_text(g), ladder_kb(g))


@router.callback_query(F.data.startswith("lcell:"))
async def cb_ladder_cell(c: CallbackQuery):
    _, gid, idx = c.data.split(":")
    gid, idx = int(gid), int(idx)
    uid = c.from_user.id
    async with lock_for(uid):
        g = get_ladder(gid)
        if not g or g["user_id"] != uid or not g["active"]:
            return await c.answer("Игра уже завершена", show_alert=True)
        cfg = LADDER_MODES[g["mode"]]
        if not 0 <= idx < cfg["slots"]:
            return await c.answer()
        mines, picks = json.loads(g["mines"]), json.loads(g["picks"])
        step = g["step"]
        picks.append(idx)
        if idx in mines[step]:
            db.execute("UPDATE ladder_games SET active=0, picks=? WHERE id=?",
                       (json.dumps(picks), gid))
            stat(uid, g["bet"], 0)
            g = get_ladder(gid)
            return await show(c, ladder_text(g, "lose"), ladder_kb(g, reveal=True))
        step += 1
        if step == LADDER_STEPS:
            db.execute("UPDATE ladder_games SET active=0, picks=?, step=? WHERE id=?",
                       (json.dumps(picks), step, gid))
            g = get_ladder(gid)
            payout = ladder_payout(g)
            give(uid, payout)
            stat(uid, g["bet"], payout)
            return await show(c, ladder_text(g, "win"), ladder_kb(g, reveal=True))
        db.execute("UPDATE ladder_games SET picks=?, step=? WHERE id=?",
                   (json.dumps(picks), step, gid))
        g = get_ladder(gid)
    await show(c, ladder_text(g), ladder_kb(g))


@router.callback_query(F.data.startswith("lcash:"))
async def cb_ladder_cash(c: CallbackQuery):
    gid = int(c.data.split(":")[1])
    uid = c.from_user.id
    async with lock_for(uid):
        g = get_ladder(gid)
        if not g or g["user_id"] != uid or not g["active"]:
            return await c.answer("Игра уже завершена", show_alert=True)
        if g["step"] < 1:
            return await c.answer("Поднимитесь хотя бы на одну ступеньку", show_alert=True)
        payout = ladder_payout(g)
        db.execute("UPDATE ladder_games SET active=0 WHERE id=?", (gid,))
        give(uid, payout)
        stat(uid, g["bet"], payout)
    await show(c, ladder_text(g, "win") + f"\nБаланс: <b>{balance_of(uid)} ⭐</b>",
               ladder_kb(g, reveal=True))


# ───────────────────────── игра: КУБ ─────────────────────────
class DiceState(StatesGroup):
    bet = State()


DICE_SIDES = {"hi": ("⬆️ Больше 3", (4, 5, 6)), "lo": ("⬇️ Меньше 3", (1, 2))}


def dice_mult(side: str) -> float:
    return round(6 / len(DICE_SIDES[side][1]) * (1 - HOUSE_EDGE), 2)


def dice_menu_kb():
    b = InlineKeyboardBuilder()
    for v in DICE_BETS:
        b.button(text=f"{v} ⭐", callback_data=f"dice:bet:{v}")
    b.button(text="✏️ Своя ставка", callback_data="dice:custom")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(3, 3, 1, 1)
    return b.as_markup()


async def dice_menu(target):
    await show(target,
               "🎲 <b>Куб</b>\n"
               f"Ставка от {DICE_MIN} до {DICE_MAX} ⭐. Угадайте: выпадет <b>больше 3</b> (4, 5, 6) "
               "или <b>меньше 3</b> (1, 2).\n"
               f"⬆️ Больше 3 — <b>x{dice_mult('hi')}</b> (шанс 50%)\n"
               f"⬇️ Меньше 3 — <b>x{dice_mult('lo')}</b> (шанс 33%)\n"
               "Если выпала тройка — ставка проиграла.\n\n"
               f"Баланс: <b>{balance_of(target.from_user.id)} ⭐</b>\nВыберите ставку:",
               dice_menu_kb())


async def dice_choose_side(target, bet: int):
    if balance_of(target.from_user.id) < bet:
        return await show(target, "❌ Недостаточно средств. Пополните баланс.", main_menu())
    b = InlineKeyboardBuilder()
    for key, (name, _) in DICE_SIDES.items():
        b.button(text=f"{name} • x{dice_mult(key)}", callback_data=f"dice:go:{bet}:{key}")
    b.button(text="⬅️ Назад", callback_data="dice:menu")
    b.adjust(2, 1)
    await show(target, f"🎲 Ставка: <b>{bet} ⭐</b>\n"
                       "На что ставите?", b.as_markup())


@router.callback_query(F.data == "dice:menu")
async def cb_dice_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ensure_user(c.from_user.id, c.from_user.username)
    await dice_menu(c)


@router.callback_query(F.data == "dice:custom")
async def cb_dice_custom(c: CallbackQuery, state: FSMContext):
    await state.set_state(DiceState.bet)
    await show(c, f"✏️ Введите ставку числом ({DICE_MIN}–{DICE_MAX} ⭐):", back_kb())


@router.message(DiceState.bet)
async def msg_dice_bet(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t.isdigit():
        return await m.answer("Введите целое число.")
    bet = int(t)
    if not DICE_MIN <= bet <= DICE_MAX:
        return await m.answer(f"Ставка должна быть от {DICE_MIN} до {DICE_MAX} ⭐.")
    await state.clear()
    ensure_user(m.from_user.id, m.from_user.username)
    await dice_choose_side(m, bet)


@router.callback_query(F.data.startswith("dice:bet:"))
async def cb_dice_bet(c: CallbackQuery):
    bet = int(c.data.split(":")[2])
    if not DICE_MIN <= bet <= DICE_MAX:
        return await c.answer("Неверная ставка", show_alert=True)
    ensure_user(c.from_user.id, c.from_user.username)
    await dice_choose_side(c, bet)


@router.callback_query(F.data.startswith("dice:go:"))
async def cb_dice_go(c: CallbackQuery):
    _, _, bet, side = c.data.split(":")
    bet = int(bet)
    uid = c.from_user.id
    if side not in DICE_SIDES or not DICE_MIN <= bet <= DICE_MAX:
        return await c.answer("Неверные параметры", show_alert=True)
    ensure_user(uid, c.from_user.username)
    await c.answer()
    async with lock_for(uid):
        if not take(uid, bet):
            return await show(c, "❌ Недостаточно средств.", main_menu())
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        name, wins = DICE_SIDES[side]
        try:
            msg = await c.message.answer_dice(emoji="🎲")
            value = msg.dice.value
            await asyncio.sleep(4)
        except Exception:
            value = rng.randint(1, 6)
        win = value in wins
        mult = dice_mult(side)
        payout = int(bet * mult) if win else 0
        if win:
            give(uid, payout)
        stat(uid, bet, payout)
        bal = balance_of(uid)
    result = (f"🎉 <b>Победа!</b> +<b>{payout} ⭐</b> (x{mult})" if win
              else f"💥 <b>Проигрыш.</b> Потеряно <b>{bet} ⭐</b>")
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data="dice:menu")
    b.button(text="⬅️ Меню", callback_data="menu:main")
    b.adjust(2)
    await c.message.answer(f"🎲 <b>Куб</b> | Ставка {bet} ⭐ | {name}\n"
                           f"Выпало: <b>{value}</b>\n\n{result}\nБаланс: <b>{bal} ⭐</b>",
                           reply_markup=b.as_markup())


# ═════════════════════════ НОВЫЕ ИГРЫ ═════════════════════════
from html import escape as esc


def cap(x: float) -> int:
    return min(int(x), MAX_PAYOUT)


def mult_for(p: float) -> float:
    return round((1 - HOUSE_EDGE) / p, 2)


async def tg_dice(msg: Message, emoji: str, lo: int, hi: int, wait: float = 4.0) -> int:
    try:
        d = await msg.answer_dice(emoji=emoji)
        value = d.dice.value
    except Exception:
        return rng.randint(lo, hi)
    await asyncio.sleep(wait)
    return value


IGAMES: dict[str, dict] = {}


def igame(key: str, icon: str, name: str, desc: str, choices: list, cols: int = 2):
    def deco(fn):
        IGAMES[key] = {"icon": icon, "name": name, "desc": desc,
                       "choices": choices, "cols": cols, "play": fn}
        return fn
    return deco


def dice_game(key: str, icon: str, name: str, emoji: str, hi: int, wait: float,
              desc: str, options: dict, cols: int = 1):
    choices = [(k, label, mult_for(len(win) / hi)) for k, (label, win) in options.items()]

    async def play(msg, choice):
        v = await tg_dice(msg, emoji, 1, hi, wait)
        win = options[choice][1]
        return (mult_for(len(win) / hi) if v in win else 0.0), f"Выпало: <b>{v}</b>"

    IGAMES[key] = {"icon": icon, "name": name, "desc": desc,
                   "choices": choices, "cols": cols, "play": play}


@igame("coin", "🪙", "Монетка", f"Угадайте сторону монеты. Выигрыш x{mult_for(0.5):g}.",
       [("h", "🦅 Орёл", mult_for(0.5)), ("t", "🪙 Решка", mult_for(0.5))])
async def g_coin(msg, choice):
    side = rng.choice("ht")
    name = "🦅 Орёл" if side == "h" else "🪙 Решка"
    return (mult_for(0.5) if side == choice else 0.0), f"Выпало: <b>{name}</b>"


SLOT_PAY = {3: 25, 0: 10, 2: 8, 1: 6}
SLOT_NAME = {3: "7️⃣7️⃣7️⃣", 0: "BAR BAR BAR", 2: "🍋🍋🍋", 1: "🍇🍇🍇"}


def slot_decode(v: int) -> tuple[int, int, int]:
    n = v - 1
    return n % 4, (n // 4) % 4, n // 16


def slot_mult(v: int) -> float:
    r = slot_decode(v)
    if r[0] == r[1] == r[2]:
        return float(SLOT_PAY[r[0]])
    if r.count(3) == 2:
        return 1.0
    return 0.0


@igame("slots", "🎰", "Слоты",
       "Три в ряд: 7️⃣ — x25, BAR — x10, 🍋 — x8, 🍇 — x6.\nДве семёрки — возврат ставки.",
       [("spin", "🎰 Крутить", None)], cols=1)
async def g_slots(msg, choice):
    v = await tg_dice(msg, "🎰", 1, 64, 4.5)
    r = slot_decode(v)
    if r[0] == r[1] == r[2]:
        detail = f"Комбинация: <b>{SLOT_NAME[r[0]]}</b>"
    elif r.count(3) == 2:
        detail = "Две семёрки!"
    else:
        detail = "Комбинации нет."
    return slot_mult(v), detail


dice_game("darts", "🎯", "Дартс", "🎯", 6, 3.5,
          "Бросок дротика: 1 — мимо, 6 — яблочко.",
          {"bull": ("🎯 Яблочко (6)", {6}), "hi": ("🔴 4–6", {4, 5, 6}), "lo": ("⚪ 1–3", {1, 2, 3})})
dice_game("basket", "🏀", "Баскетбол", "🏀", 5, 4.0,
          "Бросок в кольцо: 4–5 — попадание, 5 — чистый.",
          {"goal": ("🏀 Попадёт (4–5)", {4, 5}), "swish": ("✨ Чистый (5)", {5}),
           "miss": ("🙅 Промах (1–3)", {1, 2, 3})})
dice_game("football", "⚽", "Футбол", "⚽", 5, 4.0,
          "Удар по воротам: 3–5 — гол.",
          {"goal": ("⚽ Гол (3–5)", {3, 4, 5}), "miss": ("🙅 Мимо (1–2)", {1, 2})})
dice_game("bowling", "🎳", "Боулинг", "🎳", 6, 4.0,
          "Бросок шара: 6 — страйк.",
          {"strike": ("🎳 Страйк (6)", {6}), "hi": ("⬆️ 4–6", {4, 5, 6}), "lo": ("⬇️ 1–3", {1, 2, 3})})

RL_RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
RL_BETS = {
    "red":   ("🔴 Красное",   lambda n: n in RL_RED, 18),
    "black": ("⚫ Чёрное",    lambda n: n != 0 and n not in RL_RED, 18),
    "even":  ("2️⃣ Чётное",   lambda n: n != 0 and n % 2 == 0, 18),
    "odd":   ("1️⃣ Нечётное", lambda n: n % 2 == 1, 18),
    "low":   ("⬇️ 1–18",     lambda n: 1 <= n <= 18, 18),
    "high":  ("⬆️ 19–36",    lambda n: 19 <= n <= 36, 18),
    "d1":    ("1–12",        lambda n: 1 <= n <= 12, 12),
    "d2":    ("13–24",       lambda n: 13 <= n <= 24, 12),
    "d3":    ("25–36",       lambda n: 25 <= n <= 36, 12),
    "zero":  ("🟢 Зеро",     lambda n: n == 0, 1),
}


def rl_color(n: int) -> str:
    return "🟢" if n == 0 else ("🔴" if n in RL_RED else "⚫")


@igame("roulette", "🎡", "Рулетка", "Европейская рулетка 0–36. Ставьте на цвет, чёт/нечет, половину, дюжину или зеро.",
       [(k, label, mult_for(cnt / 37)) for k, (label, _, cnt) in RL_BETS.items()], cols=2)
async def g_roulette(msg, choice):
    n = rng.randrange(37)
    label, test, cnt = RL_BETS[choice]
    return (mult_for(cnt / 37) if test(n) else 0.0), f"Выпало: {rl_color(n)} <b>{n}</b>"


_duel_p = [0.0] * 13
for _a in range(1, 7):
    for _b in range(1, 7):
        _duel_p[_a + _b] += 1 / 36
_DUEL_TIE = sum(p * p for p in _duel_p)
DUEL_MULT = round(((1 - HOUSE_EDGE) - _DUEL_TIE) / ((1 - _DUEL_TIE) / 2), 2)


@igame("duel", "⚔️", "Дуэль", f"Вы и бот бросаете по 2 кубика. У кого сумма больше — тот победил (x{DUEL_MULT:g}). "
       "Ничья — возврат ставки.",
       [("go", "⚔️ Бросить кости", DUEL_MULT)], cols=1)
async def g_duel(msg, choice):
    a, b = rng.randint(1, 6), rng.randint(1, 6)
    c, d = rng.randint(1, 6), rng.randint(1, 6)
    me, bot_sum = a + b, c + d
    detail = f"Вы: 🎲 {a} + {b} = <b>{me}</b>\nБот: 🎲 {c} + {d} = <b>{bot_sum}</b>"
    if me > bot_sum:
        return DUEL_MULT, detail
    return (1.0 if me == bot_sum else 0.0), detail


SEVEN = {"gt": ("⬆️ Больше 7", lambda s: s > 7, 15), "lt": ("⬇️ Меньше 7", lambda s: s < 7, 15),
         "eq": ("7️⃣ Ровно 7", lambda s: s == 7, 6)}


@igame("seven", "7️⃣", "Семёрка", "Бросаются два кубика. Угадайте: сумма больше 7, меньше 7 или ровно 7.",
       [(k, label, mult_for(cnt / 36)) for k, (label, _, cnt) in SEVEN.items()], cols=1)
async def g_seven(msg, choice):
    a, b = rng.randint(1, 6), rng.randint(1, 6)
    label, test, cnt = SEVEN[choice]
    return (mult_for(cnt / 36) if test(a + b) else 0.0), f"Выпало: 🎲 {a} + {b} = <b>{a + b}</b>"


@igame("guess", "🔢", "Угадай число", f"Загадано число от 1 до 10. Угадаете — x{mult_for(0.1):g}.",
       [(str(i), str(i), None) for i in range(1, 11)], cols=5)
async def g_guess(msg, choice):
    n = rng.randint(1, 10)
    return (mult_for(0.1) if n == int(choice) else 0.0), f"Загадано: <b>{n}</b>"


WHEEL = [0] * 21 + [0.5] * 8 + [1] * 3 + [2] * 4 + [3] * 2 + [5] + [10]


@igame("wheel", "🍀", "Колесо фортуны",
       "Крутите колесо: x0, x0.5, x1, x2, x3, x5 или x10. Чем выше множитель, тем реже он выпадает.",
       [("spin", "🍀 Крутить", None)], cols=1)
async def g_wheel(msg, choice):
    x = rng.choice(WHEEL)
    return float(x), f"Сектор: <b>x{x:g}</b>"


@igame("chests", "🎁", "Три сундука", f"В одном из трёх сундуков приз x{mult_for(1 / 3):g}. Выберите сундук.",
       [("1", "🎁 1", None), ("2", "🎁 2", None), ("3", "🎁 3", None)], cols=3)
async def g_chests(msg, choice):
    prize = rng.randint(1, 3)
    row = " ".join("💎" if i == prize else "💨" for i in (1, 2, 3))
    return (mult_for(1 / 3) if prize == int(choice) else 0.0), f"{row}\nПриз был в сундуке <b>{prize}</b>"


PLINKO = [9, 3, 1.2, 0.6, 0.4, 0.6, 1.2, 3, 9]


@igame("plinko", "⚪", "Плинко", "Шарик падает через 8 рядов колышков. Края платят больше, центр — меньше: "
       "x9 / x3 / x1.2 / x0.6 / x0.4.",
       [("drop", "⚪ Бросить шарик", None)], cols=1)
async def g_plinko(msg, choice):
    path = [rng.randint(0, 1) for _ in range(8)]
    slot = sum(path)
    arrows = "".join("↘" if s else "↙" for s in path)
    return float(PLINKO[slot]), f"Путь: {arrows}\nЯчейка: <b>x{PLINKO[slot]:g}</b>"


SGAMES = {
    "crash": ("📈", "Краш", "Множитель растёт каждую секунду. Нажмите «Забрать» до того, как он «упадёт». "
                            "Чем дольше ждёте — тем больше выигрыш и риск."),
    "bj":    ("🃏", "Блэкджек", "Наберите 21 или больше дилера, но не перебор. Победа — x" f"{1.9:g}"
                               ", блэкджек — x2.35, ничья — возврат. Дилер берёт до 17."),
    "hilo":  ("🔺", "Выше/Ниже", "Угадывайте, будет следующая карта выше или ниже. Множители копятся — "
                                 "забирайте выигрыш в любой момент. Равная карта — проигрыш."),
}
START_CB = {"crash": "crstart", "bj": "bjstart", "hilo": "hlstart"}
NEW_ORDER = ["crash", "bj", "hilo", "slots", "roulette", "coin", "darts", "basket", "football",
             "bowling", "duel", "seven", "guess", "wheel", "chests", "plinko"]


def new_game_title(game: str) -> str:
    if game in IGAMES:
        g = IGAMES[game]
        return f"{g['icon']} <b>{g['name']}</b>\n{g['desc']}"
    icon, name, desc = SGAMES[game]
    return f"{icon} <b>{name}</b>\n{desc}"


def is_new_game(game: str) -> bool:
    return game in IGAMES or game in SGAMES


async def choose_new_game(target, game: str, bet: int):
    b = InlineKeyboardBuilder()
    if game in IGAMES:
        cfg = IGAMES[game]
        for key, label, m in cfg["choices"]:
            b.button(text=label + (f" • x{m:g}" if m else ""), callback_data=f"igo:{game}:{bet}:{key}")
        b.adjust(cfg["cols"])
        text = f"{cfg['icon']} Ставка: <b>{bet} ⭐</b>\nСделайте выбор:"
    else:
        icon = SGAMES[game][0]
        b.button(text="▶️ Играть", callback_data=f"{START_CB[game]}:{bet}")
        text = f"{icon} Ставка: <b>{bet} ⭐</b>\nНачинаем?"
    b.row(InlineKeyboardButton(text="⬅️ К играм", callback_data="games:all"))
    await show(target, text, b.as_markup())


@router.callback_query(F.data == "games:all")
async def cb_games_all(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ensure_user(c.from_user.id, c.from_user.username)
    items = [("💣 Мины", "game:mines"), ("🚀 Апгрейдер", "game:up"),
             ("🪜 Лестница", "game:ladder"), ("🎲 Куб", "dice:menu")]
    for key in NEW_ORDER:
        icon, name = (IGAMES[key]["icon"], IGAMES[key]["name"]) if key in IGAMES else SGAMES[key][:2]
        items.append((f"{icon} {name}", f"game:{key}"))
    b = InlineKeyboardBuilder()
    for text, cb in items:
        b.button(text=text, callback_data=cb)
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(2)
    await show(c, f"🎮 <b>Все игры</b> ({len(items)})\n\nБаланс: <b>{balance_of(c.from_user.id)} ⭐</b>\n"
                  "Выберите игру:", b.as_markup())


@router.callback_query(F.data.startswith("igo:"))
async def cb_igo(c: CallbackQuery):
    try:
        _, game, bet, choice = c.data.split(":")
        bet = int(bet)
    except ValueError:
        return await c.answer("Неверные параметры", show_alert=True)
    cfg = IGAMES.get(game)
    if not cfg or not MIN_BET <= bet <= MAX_BET or choice not in {k for k, _, _ in cfg["choices"]}:
        return await c.answer("Неверные параметры", show_alert=True)
    uid = c.from_user.id
    ensure_user(uid, c.from_user.username)
    await c.answer()
    async with lock_for(uid):
        if not take(uid, bet):
            return await c.message.answer("❌ Недостаточно средств. Пополните баланс.", reply_markup=main_menu())
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            mult, detail = await cfg["play"](c.message, choice)
        except Exception:
            logging.exception("ошибка в игре %s", game)
            give(uid, bet)
            return await c.message.answer("⚠️ Ошибка игры, ставка возвращена.", reply_markup=main_menu())
        payout = cap(bet * mult)
        if payout:
            give(uid, payout)
        stat(uid, bet, payout)
        bal = balance_of(uid)
    if payout > bet:
        result = f"🎉 <b>Победа!</b> +<b>{payout - bet} ⭐</b> (выплата {payout} ⭐, x{mult:g})"
    elif payout == bet:
        result = "🤝 <b>Возврат ставки.</b>"
    elif payout > 0:
        result = f"➖ <b>Частичный возврат:</b> {payout} ⭐ (потеряно {bet - payout} ⭐)"
    else:
        result = f"💥 <b>Проигрыш.</b> Потеряно <b>{bet} ⭐</b>"
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data=f"bet:{game}:{bet}")
    b.button(text="🎮 Все игры", callback_data="games:all")
    b.button(text="⬅️ Меню", callback_data="menu:main")
    b.adjust(1, 2)
    await c.message.answer(f"{cfg['icon']} <b>{cfg['name']}</b> | Ставка {bet} ⭐\n{detail}\n\n"
                           f"{result}\nБаланс: <b>{bal} ⭐</b>", reply_markup=b.as_markup())


def end_kb(game: str, bet: int):
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Ещё раз", callback_data=f"bet:{game}:{bet}")
    b.button(text="🎮 Все игры", callback_data="games:all")
    b.button(text="⬅️ Меню", callback_data="menu:main")
    b.adjust(1, 2)
    return b.as_markup()


def valid_bet(bet: int) -> bool:
    return MIN_BET <= bet <= MAX_BET


# ───────── 🃏 БЛЭКДЖЕК ─────────
BJ_WIN_X, BJ_NATURAL_X = 1.9, 2.35
db.execute("""CREATE TABLE IF NOT EXISTS bj_games(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    bet INTEGER NOT NULL,
    deck TEXT NOT NULL,
    player TEXT NOT NULL,
    dealer TEXT NOT NULL,
    doubled INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
)""")
SUITS = "♠♥♦♣"
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def card_str(c: int) -> str:
    return f"{RANKS[c % 13]}{SUITS[c // 13]}"


def hand_str(cards: list) -> str:
    return " ".join(card_str(c) for c in cards)


def hand_value(cards: list) -> int:
    total, aces = 0, 0
    for c in cards:
        r = c % 13
        if r == 0:
            total, aces = total + 11, aces + 1
        elif r >= 9:
            total += 10
        else:
            total += r + 1
    while total > 21 and aces:
        total, aces = total - 10, aces - 1
    return total


def is_natural(cards: list) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


def get_bj(gid: int):
    return db.execute("SELECT * FROM bj_games WHERE id=?", (gid,)).fetchone()


def bj_text(g, outcome: str | None = None, payout: int = 0) -> str:
    p, d = json.loads(g["player"]), json.loads(g["dealer"])
    lines = [f"🃏 <b>Блэкджек</b> | Ставка: {g['bet']} ⭐", ""]
    if outcome is None:
        lines.append(f"Дилер: {card_str(d[0])} 🎴")
    else:
        lines.append(f"Дилер: {hand_str(d)} = <b>{hand_value(d)}</b>")
    lines.append(f"Вы: {hand_str(p)} = <b>{hand_value(p)}</b>")
    res = {"win": f"🎉 <b>Победа!</b> Выплата: <b>{payout} ⭐</b>",
           "natural": f"🔥 <b>Блэкджек!</b> Выплата: <b>{payout} ⭐</b>",
           "push": "🤝 <b>Ничья.</b> Ставка возвращена.",
           "lose": f"💥 <b>Проигрыш.</b> Потеряно <b>{g['bet']} ⭐</b>"}
    if outcome:
        lines += ["", res[outcome]]
    return "\n".join(lines)


def bj_kb(g):
    b = InlineKeyboardBuilder()
    b.button(text="🃏 Взять", callback_data=f"bj:hit:{g['id']}")
    b.button(text="✋ Хватит", callback_data=f"bj:stand:{g['id']}")
    if len(json.loads(g["player"])) == 2 and balance_of(g["user_id"]) >= g["bet"]:
        b.button(text=f"💰 Удвоить (+{g['bet']} ⭐)", callback_data=f"bj:dbl:{g['id']}")
    b.adjust(2, 1)
    return b.as_markup()


def bj_close(g, p, d, deck, outcome: str, bet: int, doubled: int):
    mult = {"lose": 0.0, "push": 1.0, "win": BJ_WIN_X, "natural": BJ_NATURAL_X}[outcome]
    payout = cap(bet * mult)
    cur = db.execute("UPDATE bj_games SET active=0, player=?, dealer=?, deck=?, bet=?, doubled=? "
                     "WHERE id=? AND active=1",
                     (json.dumps(p), json.dumps(d), json.dumps(deck), bet, doubled, g["id"]))
    if cur.rowcount == 1:
        if payout:
            give(g["user_id"], payout)
        stat(g["user_id"], bet, payout)
    return get_bj(g["id"]), payout


def bj_resolve(g, p, d, deck, bet: int, doubled: int):
    pv = hand_value(p)
    if pv > 21:
        outcome = "lose"
    else:
        while hand_value(d) < 17:
            d.append(deck.pop())
        dv = hand_value(d)
        outcome = "win" if (dv > 21 or pv > dv) else ("push" if pv == dv else "lose")
    g2, payout = bj_close(g, p, d, deck, outcome, bet, doubled)
    return g2, payout, outcome


@router.callback_query(F.data.startswith("bjstart:"))
async def cb_bj_start(c: CallbackQuery):
    bet = int(c.data.split(":")[1])
    uid = c.from_user.id
    if not valid_bet(bet):
        return await c.answer("Неверная ставка", show_alert=True)
    ensure_user(uid, c.from_user.username)
    async with lock_for(uid):
        g = db.execute("SELECT * FROM bj_games WHERE user_id=? AND active=1", (uid,)).fetchone()
        if g:
            return await show(c, "ℹ️ Продолжаем незавершённую партию.\n\n" + bj_text(g), bj_kb(g))
        if not take(uid, bet):
            return await show(c, "❌ Недостаточно средств.", main_menu())
        deck = list(range(52))
        rng.shuffle(deck)
        p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
        cur = db.execute("INSERT INTO bj_games(user_id, bet, deck, player, dealer) VALUES(?,?,?,?,?)",
                         (uid, bet, json.dumps(deck), json.dumps(p), json.dumps(d)))
        g = get_bj(cur.lastrowid)
        if is_natural(p) or is_natural(d):
            outcome = "push" if (is_natural(p) and is_natural(d)) else ("natural" if is_natural(p) else "lose")
            g, payout = bj_close(g, p, d, deck, outcome, bet, 0)
            return await show(c, bj_text(g, outcome, payout), end_kb("bj", bet))
    await show(c, bj_text(g), bj_kb(g))


@router.callback_query(F.data.startswith("bj:"))
async def cb_bj(c: CallbackQuery):
    try:
        _, act, gid = c.data.split(":")
        gid = int(gid)
    except ValueError:
        return await c.answer("Неверные параметры", show_alert=True)
    uid = c.from_user.id
    async with lock_for(uid):
        g = get_bj(gid)
        if not g or g["user_id"] != uid or not g["active"]:
            return await c.answer("Партия уже завершена", show_alert=True)
        p, d, deck = json.loads(g["player"]), json.loads(g["dealer"]), json.loads(g["deck"])
        bet, doubled = g["bet"], 0
        if act == "hit":
            p.append(deck.pop())
            if hand_value(p) < 21:
                db.execute("UPDATE bj_games SET player=?, deck=? WHERE id=?",
                           (json.dumps(p), json.dumps(deck), gid))
                g = get_bj(gid)
                return await show(c, bj_text(g), bj_kb(g))
        elif act == "dbl":
            if len(p) != 2:
                return await c.answer("Удвоить можно только на первом ходу", show_alert=True)
            if not take(uid, bet):
                return await c.answer("Недостаточно средств для удвоения", show_alert=True)
            bet, doubled = bet * 2, 1
            p.append(deck.pop())
        elif act != "stand":
            return await c.answer("Неверное действие", show_alert=True)
        g, payout, outcome = bj_resolve(g, p, d, deck, bet, doubled)
    orig = g["bet"] // 2 if g["doubled"] else g["bet"]
    await show(c, bj_text(g, outcome, payout), end_kb("bj", orig))


# ───────── 🔺 ВЫШЕ / НИЖЕ ─────────
HILO_MAX_X = 200.0
db.execute("""CREATE TABLE IF NOT EXISTS hilo_games(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    bet INTEGER NOT NULL,
    card INTEGER NOT NULL,
    fair REAL NOT NULL DEFAULT 1.0,
    steps INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
)""")


def hl_name(r: int) -> str:
    return {11: "J", 12: "Q", 13: "K", 14: "A"}.get(r, str(r))


def hilo_probs(card: int) -> tuple[float, float]:
    return (14 - card) / 13, (card - 2) / 13


def hl_mult(g) -> float:
    return (1 - HOUSE_EDGE) * g["fair"]


def get_hl(gid: int):
    return db.execute("SELECT * FROM hilo_games WHERE id=?", (gid,)).fetchone()


def hl_text(g, note: str = "", finished: str | None = None, payout: int = 0) -> str:
    head = (f"🔺 <b>Выше/Ниже</b> | Ставка: {g['bet']} ⭐\n"
            f"Ходов: {g['steps']} | Множитель: <b>x{hl_mult(g) if g['steps'] else 1.0:.2f}</b>\n\n")
    if note:
        head += note + "\n"
    head += f"Карта: 🎴 <b>{hl_name(g['card'])}</b>\n"
    if finished == "win":
        return head + f"\n🏆 Вы забрали <b>{payout} ⭐</b>!"
    if finished == "lose":
        return head + f"\n💥 Не угадали. Потеряно <b>{g['bet']} ⭐</b>."
    return head + "\nБудет следующая карта выше или ниже?"


def hl_kb(g):
    hi, lo = hilo_probs(g["card"])
    b = InlineKeyboardBuilder()
    if hi > 0:
        b.button(text=f"⬆️ Выше • x{hl_mult(g) / hi:.2f}", callback_data=f"hl:hi:{g['id']}")
    if lo > 0:
        b.button(text=f"⬇️ Ниже • x{hl_mult(g) / lo:.2f}", callback_data=f"hl:lo:{g['id']}")
    b.adjust(2)
    if g["steps"]:
        b.row(InlineKeyboardButton(text=f"💰 Забрать {cap(g['bet'] * hl_mult(g))} ⭐",
                                   callback_data=f"hl:cash:{g['id']}"))
    return b.as_markup()


def hl_cashout(g) -> int:
    cur = db.execute("UPDATE hilo_games SET active=0 WHERE id=? AND active=1", (g["id"],))
    payout = cap(g["bet"] * hl_mult(g))
    if cur.rowcount == 1:
        give(g["user_id"], payout)
        stat(g["user_id"], g["bet"], payout)
    return payout


@router.callback_query(F.data.startswith("hlstart:"))
async def cb_hl_start(c: CallbackQuery):
    bet = int(c.data.split(":")[1])
    uid = c.from_user.id
    if not valid_bet(bet):
        return await c.answer("Неверная ставка", show_alert=True)
    ensure_user(uid, c.from_user.username)
    async with lock_for(uid):
        g = db.execute("SELECT * FROM hilo_games WHERE user_id=? AND active=1", (uid,)).fetchone()
        if g:
            return await show(c, "ℹ️ Продолжаем незавершённую игру.\n\n" + hl_text(g), hl_kb(g))
        if not take(uid, bet):
            return await show(c, "❌ Недостаточно средств.", main_menu())
        cur = db.execute("INSERT INTO hilo_games(user_id, bet, card) VALUES(?,?,?)",
                         (uid, bet, rng.randint(2, 14)))
        g = get_hl(cur.lastrowid)
    await show(c, hl_text(g), hl_kb(g))


@router.callback_query(F.data.startswith("hl:"))
async def cb_hl(c: CallbackQuery):
    try:
        _, act, gid = c.data.split(":")
        gid = int(gid)
    except ValueError:
        return await c.answer("Неверные параметры", show_alert=True)
    uid = c.from_user.id
    async with lock_for(uid):
        g = get_hl(gid)
        if not g or g["user_id"] != uid or not g["active"]:
            return await c.answer("Игра уже завершена", show_alert=True)
        if act == "cash":
            if not g["steps"]:
                return await c.answer("Сначала сделайте хотя бы один ход", show_alert=True)
            payout = hl_cashout(g)
            return await show(c, hl_text(g, finished="win", payout=payout), end_kb("hilo", g["bet"]))
        if act not in ("hi", "lo"):
            return await c.answer("Неверное действие", show_alert=True)
        hi, lo = hilo_probs(g["card"])
        p = hi if act == "hi" else lo
        if p <= 0:
            return await c.answer("Так ходить нельзя", show_alert=True)
        new = rng.randint(2, 14)
        ok = new > g["card"] if act == "hi" else new < g["card"]
        note = f"Было: <b>{hl_name(g['card'])}</b> → выпало: <b>{hl_name(new)}</b>"
        if not ok:
            cur = db.execute("UPDATE hilo_games SET active=0, card=? WHERE id=? AND active=1", (new, gid))
            if cur.rowcount == 1:
                stat(uid, g["bet"], 0)
            g = get_hl(gid)
            return await show(c, hl_text(g, note, "lose"), end_kb("hilo", g["bet"]))
        db.execute("UPDATE hilo_games SET card=?, fair=?, steps=steps+1 WHERE id=?",
                   (new, g["fair"] / p, gid))
        g = get_hl(gid)
        if hl_mult(g) >= HILO_MAX_X:
            payout = hl_cashout(g)
            return await show(c, hl_text(g, note, "win", payout), end_kb("hilo", g["bet"]))
    await show(c, hl_text(g, note), hl_kb(g))


# ───────── 📈 КРАШ ─────────
CRASH_K = 0.1
CRASH_MAX_X = 1000.0
db.execute("""CREATE TABLE IF NOT EXISTS crash_games(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    bet INTEGER NOT NULL,
    crash_x REAL NOT NULL,
    started REAL NOT NULL,
    chat_id BIGINT,
    msg_id BIGINT,
    active INTEGER NOT NULL DEFAULT 1
)""")
for _g in db.execute("SELECT id, user_id, bet FROM crash_games WHERE active=1").fetchall():
    db.execute("UPDATE crash_games SET active=0 WHERE id=?", (_g["id"],))
    db.execute("UPDATE users SET balance=balance+? WHERE id=?", (_g["bet"], _g["user_id"]))


def crash_point() -> float:
    x = (1 - HOUSE_EDGE) / (1 - rng.random())
    if x < 1.0:
        return 1.0
    return min(math.floor(x * 100) / 100, CRASH_MAX_X)


def crash_mult(t: float) -> float:
    return math.floor(math.exp(CRASH_K * max(t, 0.0)) * 100) / 100


def get_crash(gid: int):
    return db.execute("SELECT * FROM crash_games WHERE id=?", (gid,)).fetchone()


def crash_text(g, state: str, m: float = 1.0, payout: int = 0) -> str:
    head = f"📈 <b>Краш</b> | Ставка: {g['bet']} ⭐\n\n"
    if state == "run":
        return (head + f"Множитель: <b>x{m:.2f}</b>\n💰 Сейчас можно забрать: <b>{cap(g['bet'] * m)} ⭐</b>\n\n"
                "Нажмите «Забрать» до падения!")
    if state == "win":
        return head + f"✅ Вы забрали на <b>x{m:.2f}</b>: <b>+{payout} ⭐</b>"
    return head + f"💥 Упало на <b>x{g['crash_x']:.2f}</b>! Потеряно <b>{g['bet']} ⭐</b>."


def crash_run_kb(g, m: float):
    b = InlineKeyboardBuilder()
    b.button(text=f"💰 Забрать x{m:.2f}", callback_data=f"cr:cash:{g['id']}")
    return b.as_markup()


def crash_bust(g) -> bool:
    cur = db.execute("UPDATE crash_games SET active=0 WHERE id=? AND active=1", (g["id"],))
    if cur.rowcount == 1:
        stat(g["user_id"], g["bet"], 0)
        return True
    return False


_crash_tasks: set = set()


async def crash_edit(bot: Bot, g, text: str, kb):
    try:
        await bot.edit_message_text(text, chat_id=g["chat_id"], message_id=g["msg_id"], reply_markup=kb)
    except Exception:
        pass


async def crash_loop(bot: Bot, gid: int):
    try:
        while True:
            await asyncio.sleep(1.3)
            g = get_crash(gid)
            if not g or not g["active"]:
                return
            m = crash_mult(time.time() - g["started"])
            if m >= g["crash_x"]:
                if crash_bust(g):
                    await crash_edit(bot, g, crash_text(g, "bust"), end_kb("crash", g["bet"]))
                return
            await crash_edit(bot, g, crash_text(g, "run", m), crash_run_kb(g, m))
    except Exception:
        logging.exception("crash loop")


@router.callback_query(F.data.startswith("crstart:"))
async def cb_crash_start(c: CallbackQuery, bot: Bot):
    bet = int(c.data.split(":")[1])
    uid = c.from_user.id
    if not valid_bet(bet):
        return await c.answer("Неверная ставка", show_alert=True)
    ensure_user(uid, c.from_user.username)
    async with lock_for(uid):
        if db.execute("SELECT 1 FROM crash_games WHERE user_id=? AND active=1", (uid,)).fetchone():
            return await c.answer("Дождитесь окончания текущего раунда", show_alert=True)
        if not take(uid, bet):
            return await show(c, "❌ Недостаточно средств.", main_menu())
        cx = crash_point()
        cur = db.execute("INSERT INTO crash_games(user_id, bet, crash_x, started, chat_id, msg_id) "
                         "VALUES(?,?,?,?,?,?)",
                         (uid, bet, cx, time.time(), c.message.chat.id, c.message.message_id))
        g = get_crash(cur.lastrowid)
        if cx <= 1.0:
            crash_bust(g)
            return await show(c, crash_text(g, "bust"), end_kb("crash", bet))
    text, kb = crash_text(g, "run", 1.0), crash_run_kb(g, 1.0)
    try:
        sent = await c.message.edit_text(text, reply_markup=kb)
    except Exception:
        sent = await c.message.answer(text, reply_markup=kb)
    if sent and getattr(sent, "message_id", None) and sent.message_id != g["msg_id"]:
        db.execute("UPDATE crash_games SET chat_id=?, msg_id=? WHERE id=?",
                   (sent.chat.id, sent.message_id, g["id"]))
    await c.answer()
    task = asyncio.create_task(crash_loop(bot, g["id"]))
    _crash_tasks.add(task)
    task.add_done_callback(_crash_tasks.discard)


@router.callback_query(F.data.startswith("cr:cash:"))
async def cb_crash_cash(c: CallbackQuery):
    try:
        gid = int(c.data.split(":")[2])
    except ValueError:
        return await c.answer("Неверные параметры", show_alert=True)
    uid = c.from_user.id
    async with lock_for(uid):
        g = get_crash(gid)
        if not g or g["user_id"] != uid or not g["active"]:
            return await c.answer("Раунд уже закончился", show_alert=True)
        m = crash_mult(time.time() - g["started"])
        if m >= g["crash_x"]:
            if crash_bust(g):
                return await show(c, crash_text(g, "bust"), end_kb("crash", g["bet"]))
            return await c.answer("Раунд уже закончился", show_alert=True)
        cur = db.execute("UPDATE crash_games SET active=0 WHERE id=? AND active=1", (gid,))
        if cur.rowcount != 1:
            return await c.answer("Раунд уже закончился", show_alert=True)
        payout = cap(g["bet"] * m)
        give(uid, payout)
        stat(uid, g["bet"], payout)
    await show(c, crash_text(g, "win", m, payout), end_kb("crash", g["bet"]))


# ═════════════════════════ NFT ═════════════════════════
db.execute("""CREATE TABLE IF NOT EXISTS nfts(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    value INTEGER NOT NULL,
    created TEXT DEFAULT CURRENT_TIMESTAMP
)""")


def nft_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🖼 Пополнить NFT", url=NFT_URL)
    b.button(text="📨 Я отправил NFT", callback_data="nftreq:start")
    b.button(text="🎒 Инвентарь", callback_data="inv:menu")
    b.button(text="➕ Пополнение", callback_data="menu:deposit")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "menu:nft")
async def cb_my_nft(c: CallbackQuery):
    ensure_user(c.from_user.id, c.from_user.username)
    rows = db.execute("SELECT * FROM nfts WHERE user_id=? ORDER BY id DESC LIMIT 30",
                      (c.from_user.id,)).fetchall()
    tot = db.execute("SELECT COUNT(*) n, COALESCE(SUM(value),0) s FROM nfts WHERE user_id=?",
                     (c.from_user.id,)).fetchone()
    if not rows:
        text = ("🖼 <b>Мои NFT</b>\n\nПока вы не пополняли NFT.\n\n"
                f"Отправьте NFT на @{NFT_USERNAME} — после проверки админ зачислит ⭐ на баланс, "
                "а подарок появится здесь.")
    else:
        lines = [f"{i}. <b>{esc(r['name'])}</b> — {r['value']} ⭐ <i>({str(r['created'])[:10]})</i>"
                 for i, r in enumerate(rows, 1)]
        more = f"\n…показаны последние 30 из {tot['n']}" if tot["n"] > 30 else ""
        text = (f"🖼 <b>Мои NFT</b>\nВсего пополнено: <b>{tot['n']}</b> шт на <b>{tot['s']} ⭐</b>\n\n"
                + "\n".join(lines) + more)
    await show(c, text, nft_kb())


async def nft_credit(bot: Bot, uid: int, name: str, value: int) -> int:
    cur = db.execute("INSERT INTO nfts(user_id, name, value) VALUES(?,?,?)", (uid, name, value))
    give(uid, value)
    db.execute("UPDATE users SET deposited=deposited+? WHERE id=?", (value, uid))
    try:
        await bot.send_message(uid, f"🖼 NFT <b>{esc(name)}</b> принят! На баланс зачислено <b>{value} ⭐</b>.\n"
                                    f"Баланс: <b>{balance_of(uid)} ⭐</b>", reply_markup=nft_kb())
    except Exception:
        pass
    return cur.lastrowid


# ═════════════════════════ АВТОВЫПЛАТА ЧЕРЕЗ TELEGRAM ═════════════════════════
GIFT_MAX_PER_PAYOUT = 40


async def auto_payout(bot: Bot, uid: int, amount: int) -> tuple[int, list[str]]:
    left, paid, log = amount, 0, []
    pays = db.execute("SELECT charge_id, amount FROM payments WHERE user_id=? AND refunded=0 AND amount<=? "
                      "ORDER BY amount DESC", (uid, amount)).fetchall()
    for p in pays:
        if p["amount"] > left:
            continue
        try:
            await bot.refund_star_payment(user_id=uid, telegram_payment_charge_id=p["charge_id"])
        except Exception as e:
            log.append(f"возврат платежа на {p['amount']} ⭐ не удался: {e}")
            continue
        db.execute("UPDATE payments SET refunded=1 WHERE charge_id=?", (p["charge_id"],))
        left -= p["amount"]
        paid += p["amount"]
        log.append(f"возвращён платёж {p['amount']} ⭐")
    if left > 0:
        try:
            gifts = (await bot.get_available_gifts()).gifts
        except Exception as e:
            gifts = []
            log.append(f"не удалось получить список подарков: {e}")
        pool = sorted((g for g in gifts if g.star_count <= left
                       and (getattr(g, "remaining_count", None) is None or g.remaining_count > 0)),
                      key=lambda g: -g.star_count)
        sent = 0
        for g in pool:
            while g.star_count <= left and sent < GIFT_MAX_PER_PAYOUT:
                try:
                    await bot.send_gift(user_id=uid, gift_id=g.id, text="Выплата из RubUP Casino")
                except Exception as e:
                    log.append(f"подарок за {g.star_count} ⭐ не отправлен: {e}")
                    break
                left -= g.star_count
                paid += g.star_count
                sent += 1
                await asyncio.sleep(0.3)
        if sent:
            log.append(f"отправлено подарков: {sent}")
    return paid, log


# ───────────────────────── вывод средств ─────────────────────────
class WdState(StatesGroup):
    waiting = State()


def add_withdrawal(uid: int, amount: int) -> int:
    cur = db.execute("INSERT INTO withdrawals(user_id, amount) VALUES(?, ?)", (uid, amount))
    return cur.lastrowid


def get_withdrawal(wid: int):
    return db.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()


def set_withdrawal(wid: int, status: str):
    db.execute("UPDATE withdrawals SET status=?, processed=CURRENT_TIMESTAMP WHERE id=?",
               (status, wid))


def wd_today() -> tuple[int, int]:
    r = db.execute("SELECT COALESCE(SUM(amount),0), COUNT(DISTINCT user_id) FROM withdrawals "
                   "WHERE status!='rejected' AND created >= ?", (day_start_utc(),)).fetchone()
    return r[0], r[1]


def wd_today_line() -> str:
    used, people = wd_today()
    return (f"📊 Выведено сегодня: <b>{used} из {WD_GLOBAL_DAILY} ⭐</b> "
            f"(человек: <b>{people}</b>)\n🕛 Лимит обновляется в 00:00 ({DAY_TZ_NAME})")


def wd_status_icon(status: str) -> str:
    return {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(status, "❓")


def admin_wd_kb(wid: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Одобрить", callback_data=f"wadm:ok:{wid}")
    b.button(text="❌ Отклонить", callback_data=f"wadm:no:{wid}")
    b.adjust(2)
    return b.as_markup()


async def make_withdrawal(target, bot: Bot, uid: int, amount: int):
    if not WD_MIN <= amount <= WD_MAX:
        return await show(target, f"❌ Сумма вывода должна быть от {WD_MIN} до {WD_MAX} ⭐.",
                          main_menu())
    used = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=? "
        "AND status!='rejected' AND created >= ?", (uid, day_start_utc())).fetchone()[0]
    if used + amount > WD_DAILY_MAX:
        left = max(0, WD_DAILY_MAX - used)
        return await show(target, f"❌ Суточный лимит вывода — {WD_DAILY_MAX} ⭐. "
                                  f"Сегодня доступно ещё: <b>{left} ⭐</b>.", main_menu())
    g_used, _ = wd_today()
    if g_used + amount > WD_GLOBAL_DAILY:
        left = max(0, WD_GLOBAL_DAILY - g_used)
        return await show(target, f"❌ Общий суточный лимит вывода ({WD_GLOBAL_DAILY} ⭐) почти исчерпан. "
                                  f"Сейчас можно вывести не больше <b>{left} ⭐</b>.\n\n" + wd_today_line(),
                          main_menu())
    if not take(uid, amount):
        return await show(target, "❌ Недостаточно средств для вывода.", main_menu())
    wid = add_withdrawal(uid, amount)
    user = get_user(uid)
    name = f"@{user['username']}" if user and user["username"] else f"id{uid}"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💸 <b>Заявка на вывод #{wid}</b>\n\n"
            f"👤 Игрок: {name} (<code>{uid}</code>)\n"
            f"💰 Сумма: <b>{amount} ⭐</b>\n"
            f"🕐 {db.execute('SELECT CURRENT_TIMESTAMP').fetchone()[0]}\n\n"
            f"Звёзды уже списаны с баланса игрока.",
            reply_markup=admin_wd_kb(wid))
    except Exception:
        pass
    await show(target,
               f"✅ Заявка <b>#{wid}</b> на вывод <b>{amount} ⭐</b> создана!\n"
               f"Средства заморожены до решения администратора.\n"
               f"Баланс: <b>{balance_of(uid)} ⭐</b>\n\n" + wd_today_line(), main_menu())


async def process_withdrawal(wid: int, action: str, bot: Bot) -> str:
    w = get_withdrawal(wid)
    if not w:
        return "Заявка не найдена."
    if w["status"] != "pending":
        return f"Заявка #{wid} уже обработана ({w['status']})."
    if action == "ok":
        set_withdrawal(wid, "approved")
        if not AUTO_PAYOUT:
            try:
                await bot.send_message(w["user_id"],
                    f"✅ Ваша заявка <b>#{wid}</b> на вывод <b>{w['amount']} ⭐</b> одобрена! "
                    f"Звёзды будут отправлены вам.")
            except Exception:
                pass
            return f"✅ Заявка #{wid} ({w['amount']} ⭐, игрок {w['user_id']}) ОДОБРЕНА."
        try:
            paid, log = await auto_payout(bot, w["user_id"], w["amount"])
        except Exception as e:
            logging.exception("автовыплата")
            paid, log = 0, [f"ошибка автовыплаты: {e}"]
        left = w["amount"] - paid
        db.execute("UPDATE withdrawals SET paid=? WHERE id=?", (paid, wid))
        if left > 0:
            give(w["user_id"], left)
        user_msg = (f"✅ Заявка <b>#{wid}</b> одобрена! Выплачено через Telegram: <b>{paid} ⭐</b>."
                    if paid else f"⚠️ Заявка <b>#{wid}</b> одобрена, но выплатить автоматически не удалось.")
        if left > 0:
            user_msg += f"\nНевыплаченные <b>{left} ⭐</b> возвращены на ваш баланс."
        try:
            await bot.send_message(w["user_id"], user_msg)
        except Exception:
            pass
        try:
            await bot.send_message(ADMIN_ID, f"📋 Выплата по заявке #{wid}: {paid} из {w['amount']} ⭐\n"
                                             + ("\n".join("• " + x for x in log) or "• без деталей"))
        except Exception:
            pass
        return (f"✅ Заявка #{wid} одобрена. Выплачено {paid} из {w['amount']} ⭐"
                + (f", {left} ⭐ вернулись игроку на баланс." if left > 0 else "."))
    set_withdrawal(wid, "rejected")
    give(w["user_id"], w["amount"])
    try:
        await bot.send_message(w["user_id"],
            f"❌ Ваша заявка <b>#{wid}</b> на вывод <b>{w['amount']} ⭐</b> отклонена. "
            f"Средства возвращены на баланс.")
    except Exception:
        pass
    return f"❌ Заявка #{wid} ({w['amount']} ⭐, игрок {w['user_id']}) ОТКЛОНЕНА, средства возвращены."


@router.callback_query(F.data == "wd:menu")
async def cb_wd_menu(c: CallbackQuery):
    b = InlineKeyboardBuilder()
    for a in WD_OPTIONS:
        b.button(text=f"{a} ⭐", callback_data=f"wd:req:{a}")
    b.button(text="✏️ Своя сумма", callback_data="wd:custom")
    b.button(text="📜 История выводов", callback_data="wd:history")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(3)
    await show(c, "💸 <b>Вывод средств</b>\n\n"
                  f"Баланс: <b>{balance_of(c.from_user.id)} ⭐</b>\n"
                  f"Лимиты: от <b>{WD_MIN}</b> до <b>{WD_MAX} ⭐</b>\n\n"
                  + wd_today_line() + "\n\n"
                  + ("Выплата — автоматически через Telegram после одобрения.\n\n" if AUTO_PAYOUT else "")
                  + "Выберите сумму для вывода:", b.as_markup())


@router.callback_query(F.data.startswith("wd:req:"))
async def cb_wd_req(c: CallbackQuery, bot: Bot):
    amount = int(c.data.split(":")[2])
    await make_withdrawal(c, bot, c.from_user.id, amount)


@router.callback_query(F.data == "wd:custom")
async def cb_wd_custom(c: CallbackQuery, state: FSMContext):
    await state.set_state(WdState.waiting)
    await show(c, f"✏️ Введите сумму вывода числом (от {WD_MIN} до {WD_MAX} ⭐):", back_kb())


@router.message(WdState.waiting)
async def msg_wd_custom(m: Message, state: FSMContext, bot: Bot):
    if not (m.text or "").strip().isdigit():
        return await m.answer("Введите целое число.")
    await state.clear()
    await make_withdrawal(m, bot, m.from_user.id, int(m.text.strip()))


@router.callback_query(F.data == "wd:history")
async def cb_wd_history(c: CallbackQuery):
    rows = db.execute(
        "SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT 15",
        (c.from_user.id,)).fetchall()
    if not rows:
        return await show(c, "📜 У вас пока нет заявок на вывод.", back_kb())
    lines = [f"{wd_status_icon(r['status'])} #{r['id']} — <b>{r['amount']} ⭐</b> "
             f"({r['status']}, {r['created']})" for r in rows]
    await show(c, "📜 <b>История выводов</b>\n\n" + "\n".join(lines), back_kb())


@router.callback_query(F.data.startswith("wadm:"))
async def cb_wd_admin(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS and c.from_user.id not in admin_sessions:
        return await c.answer("Нет доступа", show_alert=True)
    _, action, wid = c.data.split(":")
    result = await process_withdrawal(int(wid), action, bot)
    try:
        await c.message.edit_text(c.message.text + f"\n\n———\n<b>{result}</b>")
    except Exception:
        pass
    await c.answer(result, show_alert=True)


# ───────────────────────── админ ─────────────────────────
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

@router.message(Command("take"))
async def cmd_take(m: Message):
    if not is_admin(m.from_user.id):
        return
    try:
        _, uid, amount = m.text.split()
        uid, amount = int(uid), int(amount)
    except ValueError:
        return await m.answer("Использование: /take <user_id> <сумма>")
    ensure_user(uid, None)
    if take(uid, amount):
        await m.answer(f"➖ Списано {amount} ⭐ у игрока {uid}. Баланс: {balance_of(uid)} ⭐")
    else:
        await m.answer(f"Не удалось списать: у игрока {uid} недостаточно средств "
                       f"(баланс: {balance_of(uid)} ⭐).")


@router.message(Command("resetbalances"))
async def cmd_resetbalances(m: Message):
    if not is_admin(m.from_user.id):
        return
    if m.text.split()[1:] != ["confirm"]:
        n = db.execute("SELECT COUNT(*) c, COALESCE(SUM(balance),0) s FROM users").fetchone()
        return await m.answer(
            f"⚠️ Будут обнулены балансы {n['c']} игроков (суммарно {n['s']} ⭐).\n"
            "Подтвердите: /resetbalances confirm")
    wipe_balances()
    await m.answer("✅ Все балансы обнулены.")


@router.message(Command("wdlist"))
async def cmd_wdlist(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = db.execute(
        "SELECT * FROM withdrawals WHERE status='pending' ORDER BY id").fetchall()
    if not rows:
        return await m.answer("⏳ Ожидающих заявок на вывод нет.")
    await m.answer(f"⏳ Ожидающих заявок: {len(rows)}")
    for r in rows:
        u = get_user(r["user_id"])
        name = f"@{u['username']}" if u and u["username"] else "без username"
        await m.answer(
            f"💸 Заявка <b>#{r['id']}</b>\n"
            f"👤 Игрок: {name} (<code>{r['user_id']}</code>)\n"
            f"💰 Сумма: <b>{r['amount']} ⭐</b>\n🕐 {r['created']}",
            reply_markup=admin_wd_kb(r["id"]))


@router.message(Command("wdok", "wdno"))
async def cmd_wd_proc(m: Message, bot: Bot):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await m.answer("Использование: /wdok <id> или /wdno <id>")
    action = "ok" if parts[0].startswith("/wdok") else "no"
    result = await process_withdrawal(int(parts[1]), action, bot)
    await m.answer(result)


@router.message(Command("wdlog"))
async def cmd_wdlog(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        rows = db.execute(
            "SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT 20",
            (int(parts[1]),)).fetchall()
        title = f"История выводов игрока {parts[1]}:"
    else:
        rows = db.execute(
            "SELECT * FROM withdrawals ORDER BY id DESC LIMIT 20").fetchall()
        title = "Последние заявки на вывод:"
    if not rows:
        return await m.answer("Заявок нет.")
    lines = [f"{wd_status_icon(r['status'])} #{r['id']} — игрок {r['user_id']} — "
             f"<b>{r['amount']} ⭐</b> ({r['status']}, {r['created']})" for r in rows]
    await m.answer(title + "\n\n" + "\n".join(lines))


@router.message(Command("adminstats"))
async def cmd_adminstats(m: Message):
    if not is_admin(m.from_user.id):
        return
    u = db.execute("SELECT COUNT(*) c, COALESCE(SUM(deposited),0) dep, "
                   "COALESCE(SUM(wagered),0) wag, COALESCE(SUM(won),0) won "
                   "FROM users").fetchone()
    p = db.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM withdrawals "
                   "WHERE status='pending'").fetchone()
    a = db.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM withdrawals "
                   "WHERE status='approved'").fetchone()
    r = db.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM withdrawals "
                   "WHERE status='rejected'").fetchone()
    await m.answer(
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Игроков: {u['c']}\n"
        f"📥 Пополнено всего: {u['dep']} ⭐\n"
        f"🎯 Поставлено: {u['wag']} ⭐\n"
        f"🏆 Выиграно: {u['won']} ⭐\n\n"
        f"⏳ Выводы в ожидании: {p['c']} шт на {p['s']} ⭐\n"
        f"✅ Выведено (одобрено): {a['c']} шт на {a['s']} ⭐\n"
        f"❌ Отклонено: {r['c']} шт на {r['s']} ⭐")


@router.message(Command("admin"))
async def cmd_admin(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer(
        "🛠 <b>Админ-команды</b>\n\n"
        "/give <user_id> <сумма> — выдать звёзды\n"
        "/take <user_id> <сумма> — списать звёзды\n"
        "/wdlist — список ожидающих заявок на вывод\n"
        "/wdok <id> — одобрить вывод\n"
        "/wdno <id> — отклонить и вернуть средства\n"
        "/wdlog <user_id> — история выводов\n"
        "/resetbalances — обнулить балансы всех\n"
        "/adminstats — статистика бота")

@router.message(Command("give"))
async def cmd_give(m: Message):
    if not is_admin(m.from_user.id):
        return
    try:
        _, uid, amount = m.text.split()
        uid, amount = int(uid), int(amount)
    except ValueError:
        return await m.answer("Использование: /give <user_id> <сумма>")
    ensure_user(uid, None)
    give(uid, amount)
    await m.answer(f"Выдано {amount} ⭐ пользователю {uid}. Баланс: {balance_of(uid)} ⭐")


# ───────────────────────── админ-панель (по паролю) ─────────────────────────
admin_sessions: set[int] = set()
for _r in db.execute("SELECT s.user_id, u.username FROM saved_logins s "
                     "LEFT JOIN users u ON u.id=s.user_id WHERE s.kind='admin'").fetchall():
    admin_sessions.add(_r["user_id"])
_pw_fails: dict[int, list] = {}


class AdminState(StatesGroup):
    password = State()
    credit_user = State()
    credit_self = State()
    reset_user = State()
    link_creator = State()
    new_promo = State()
    new_creator = State()
    bind_self = State()
    new_nft = State()


def panel_kb():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Начислить по username", callback_data="adm:credit_user")
    b.button(text="⭐ Начислить себе", callback_data="adm:credit_self")
    b.button(text="🏦 Баланс бота", callback_data="adm:bot")
    b.button(text="🎟 Коды авторов", callback_data="adm:codes")
    b.button(text="🎁 Создать промокод", callback_data="adm:newpromo")
    b.button(text="🆕 Создать код автора", callback_data="adm:newcreator")
    b.button(text="📥 Заявки на вывод", callback_data="adm:wd")
    b.button(text="🖼 Зачислить NFT", callback_data="adm:nft")
    b.button(text="📨 Заявки на NFT", callback_data="adm:nreq")
    b.button(text="🎁 Выдать NFT себе", callback_data="adm:ngive_self")
    b.button(text="🎁 Выдать NFT по username", callback_data="adm:ngive_user")
    b.button(text="🧽 Обнулить по username", callback_data="adm:reset_user")
    b.button(text="🧹 Обнулить все балансы", callback_data="adm:reset")
    b.button(text="🚪 Выйти", callback_data="adm:logout")
    b.button(text="⬅️ В меню", callback_data="adm:exit")
    b.button(text="🔗 Привязать аккаунт", callback_data="adm:bind")
    b.adjust(1)
    return b.as_markup()


def panel_back_kb():
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ В админ панель", callback_data="adm:panel")
    return b.as_markup()


PANEL_TEXT = "🔐 <b>Админ панель</b>\nВыберите действие:"


@router.callback_query(F.data == "adm:enter")
async def cb_adm_enter(c: CallbackQuery, state: FSMContext):
    if c.from_user.id in admin_sessions:
        await state.clear()
        return await show(c, PANEL_TEXT, panel_kb())
    fails = _pw_fails.get(c.from_user.id)
    if fails and fails[1] > time.time():
        left = int(fails[1] - time.time())
        return await c.answer(f"Слишком много попыток. Подождите {left} сек.", show_alert=True)
    await state.set_state(AdminState.password)
    await show(c, "🔑 Введите код админ панели:", back_kb())


@router.message(AdminState.password)
async def msg_adm_password(m: Message, state: FSMContext):
    uid = m.from_user.id
    fails = _pw_fails.setdefault(uid, [0, 0.0])
    if fails[1] > time.time():
        return await m.answer(f"⛔ Слишком много попыток. Подождите {int(fails[1] - time.time())} сек.")
    try:
        await m.delete()
    except Exception:
        pass
    if (m.text or "").strip() == ADMIN_PASSWORD:
        _pw_fails.pop(uid, None)
        admin_sessions.add(uid)
        await state.clear()
        return await m.answer(SAVE_CHOICE_TEXT.format(what="Пароль", what_lc="пароль"),
                              reply_markup=save_choice_kb("adm"))
    fails[0] += 1
    if fails[0] >= PANEL_MAX_TRIES:
        fails[0], fails[1] = 0, time.time() + PANEL_LOCK_SEC
        await state.clear()
        return await m.answer("⛔ Неверный пароль. Доступ заблокирован на 10 минут.",
                              reply_markup=back_kb())
    await m.answer(f"❌ Неверный пароль. Осталось попыток: {PANEL_MAX_TRIES - fails[0]}",
                   reply_markup=back_kb())


def _need_session(c: CallbackQuery) -> bool:
    return c.from_user.id in admin_sessions


@router.callback_query(F.data == "adm:panel")
async def cb_adm_panel(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.clear()
    await show(c, PANEL_TEXT, panel_kb())


@router.callback_query(F.data.in_({"adm:save:1", "adm:save:0"}))
async def cb_adm_save(c: CallbackQuery):
    uid = c.from_user.id
    if uid not in admin_sessions:
        return await c.answer("Сначала введите пароль", show_alert=True)
    if c.data == "adm:save:1":
        login_save(uid, "admin")
        note = "💾 Вход сохранён — пароль вводить больше не нужно."
    else:
        login_forget(uid, "admin")
        note = "🔁 Вход не сохранён — пароль нужно будет вводить при каждом заходе."
    await show(c, note + "\n\n" + PANEL_TEXT, panel_kb())


@router.callback_query(F.data == "adm:exit")
async def cb_adm_exit(c: CallbackQuery, state: FSMContext):
    if not login_saved(c.from_user.id, "admin"):
        admin_sessions.discard(c.from_user.id)
    await cb_main(c, state)


@router.callback_query(F.data == "adm:bind")
async def cb_adm_bind(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.bind_self)
    await show(c, "🔑 <b>Введите ваш код</b> (код автора).\n"
                  "Он привяжется к вашему аккаунту, и сразу покажется статистика.", panel_back_kb())


@router.message(AdminState.bind_self)
async def msg_adm_bind(m: Message, state: FSMContext):
    uid = m.from_user.id
    if uid not in admin_sessions:
        return await state.clear()
    ensure_user(uid, m.from_user.username)
    r = find_creator(m.text)
    if not r:
        return await m.answer("❌ Такого кода нет. Проверьте и введите ещё раз.", reply_markup=panel_back_kb())
    if r["owner_id"] and r["owner_id"] != uid:
        return await m.answer("❌ Этот код уже привязан к другому аккаунту.\n"
                              "Переназначить можно в «🎟 Коды авторов» → «Привязать владельца».",
                              reply_markup=panel_back_kb())
    got = 0
    if r["owner_id"] != uid:
        db.execute("UPDATE creators SET owner_id=? WHERE code=?", (uid, r["code"]))
        got, _ = creator_settle(r["code"])
        r = find_creator(m.text)
    await state.clear()
    await m.answer(f"✅ Код <b>{r['title']}</b> привязан к вашему аккаунту."
                   + (f"\nВыплачено накопленное: {got} ⭐." if got else "")
                   + "\n\n" + creator_stats_text(r), reply_markup=panel_back_kb())


@router.callback_query(F.data == "adm:logout")
async def cb_adm_logout(c: CallbackQuery, state: FSMContext):
    admin_sessions.discard(c.from_user.id)
    login_forget(c.from_user.id, "admin")
    await state.clear()
    await show(c, "🚪 Вы вышли из админ панели.", main_menu())


@router.callback_query(F.data == "adm:credit_user")
async def cb_adm_credit_user(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.credit_user)
    await show(c, "➕ Введите <b>username и сумму</b> через пробел, например:\n"
                  "<code>@durov 100</code>\n\nИгрок должен хотя бы раз запустить бота.",
               panel_back_kb())


@router.message(AdminState.credit_user)
async def msg_adm_credit_user(m: Message, state: FSMContext, bot: Bot):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        return await m.answer("Формат: <code>@username сумма</code> (сумма — целое число > 0)",
                              reply_markup=panel_back_kb())
    username, amount = parts[0].lstrip("@"), int(parts[1])
    row = db.execute("SELECT id, username FROM users WHERE LOWER(username)=LOWER(?)",
                     (username,)).fetchone()
    if not row:
        return await m.answer(f"❌ Игрок @{username} не найден (он должен запустить бота).",
                              reply_markup=panel_back_kb())
    give(row["id"], amount)
    await state.clear()
    await m.answer(f"✅ Начислено {amount} ⭐ игроку @{row['username']}.\n"
                   f"Его баланс: <b>{balance_of(row['id'])} ⭐</b>", reply_markup=panel_kb())
    try:
        await bot.send_message(row["id"], f"🎁 Вам начислено <b>{amount} ⭐</b>.\n"
                                          f"Баланс: <b>{balance_of(row['id'])} ⭐</b>")
    except Exception:
        pass


@router.callback_query(F.data == "adm:credit_self")
async def cb_adm_credit_self(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.credit_self)
    await show(c, "⭐ Введите сумму, которую нужно начислить себе:", panel_back_kb())


@router.message(AdminState.credit_self)
async def msg_adm_credit_self(m: Message, state: FSMContext):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    t = (m.text or "").strip()
    if not t.isdigit() or int(t) <= 0:
        return await m.answer("Введите целое число больше 0.", reply_markup=panel_back_kb())
    ensure_user(m.from_user.id, m.from_user.username)
    give(m.from_user.id, int(t))
    await state.clear()
    await m.answer(f"✅ Начислено {t} ⭐.\nВаш баланс: <b>{balance_of(m.from_user.id)} ⭐</b>",
                   reply_markup=panel_kb())


@router.callback_query(F.data == "adm:bot")
async def cb_adm_bot(c: CallbackQuery, bot: Bot):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    stars = None
    try:
        stars = (await bot.get_my_star_balance()).amount
    except Exception:
        pass
    q = lambda sql: db.execute(sql).fetchone()[0]
    dep = q("SELECT COALESCE(SUM(amount),0) FROM payments")
    paid_out = q("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'")
    pend = q("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='pending'")
    players = q("SELECT COALESCE(SUM(balance),0) FROM users")
    free = dep - paid_out - pend - players
    real = f"<b>{stars} ⭐</b>" if stars is not None else "недоступно (API не отдал баланс)"
    await show(c,
        "🏦 <b>Баланс бота</b>\n\n"
        f"⭐ Stars на счёте бота (Telegram): {real}\n\n"
        "<b>По учёту казино:</b>\n"
        f"📥 Пополнено игроками: {dep} ⭐\n"
        f"📤 Выплачено (одобренные выводы): {paid_out} ⭐\n"
        f"⏳ Ожидает вывода: {pend} ⭐\n"
        f"👥 На балансах игроков: {players} ⭐\n"
        f"💎 Свободно после обязательств: <b>{free} ⭐</b>\n\n"
        "Начисления админом и комиссии авторов в «Пополнено» не входят, поэтому уменьшают свободный остаток.",
        panel_back_kb())


@router.callback_query(F.data == "adm:codes")
async def cb_adm_codes(c: CallbackQuery):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    rows = db.execute("SELECT * FROM creators ORDER BY title").fetchall()
    parts = []
    for r in rows:
        o = get_user(r["owner_id"]) if r["owner_id"] else None
        owner = (f"@{o['username']}" if o and o["username"] else f"id{r['owner_id']}") if o else "не привязан"
        parts.append(f"{creator_stats_text(r)}\n👤 Владелец: {owner}")
    b = InlineKeyboardBuilder()
    b.button(text="🔗 Привязать владельца", callback_data="adm:link")
    b.button(text="⬅️ В админ панель", callback_data="adm:panel")
    b.adjust(1)
    await show(c, "🎟 <b>Коды авторов</b>\n\n" + "\n\n".join(parts), b.as_markup())


@router.callback_query(F.data == "adm:link")
async def cb_adm_link(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.link_creator)
    await show(c, "🔗 Введите <b>код автора и username владельца</b> через пробел:\n"
                  "<code>WOLY @username</code>\n\nЧтобы отвязать владельца: <code>WOLY -</code>",
               panel_back_kb())


@router.message(AdminState.link_creator)
async def msg_adm_link(m: Message, state: FSMContext, bot: Bot):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    parts = (m.text or "").split()
    if len(parts) != 2:
        return await m.answer("Формат: <code>КОД @username</code>", reply_markup=panel_back_kb())
    r = find_creator(parts[0])
    if not r:
        return await m.answer("❌ Такого кода автора нет.", reply_markup=panel_back_kb())
    if parts[1] == "-":
        db.execute("UPDATE creators SET owner_id=NULL WHERE code=?", (r["code"],))
        await state.clear()
        return await m.answer(f"✅ Владелец кода {r['title']} отвязан.", reply_markup=panel_kb())
    u = db.execute("SELECT id, username FROM users WHERE LOWER(username)=LOWER(?)",
                   (parts[1].lstrip("@"),)).fetchone()
    if not u:
        return await m.answer("❌ Игрок не найден (он должен запустить бота).",
                              reply_markup=panel_back_kb())
    db.execute("UPDATE creators SET owner_id=? WHERE code=?", (u["id"], r["code"]))
    got, _ = creator_settle(r["code"])
    await state.clear()
    await m.answer(f"✅ Код <b>{r['title']}</b> привязан к @{u['username']}."
                   + (f"\nВыплачено накопленное: {got} ⭐." if got else ""), reply_markup=panel_kb())
    try:
        await bot.send_message(u["id"], f"🎟 Вам выдан код автора <b>{r['title']}</b>. "
                                        f"Вы получаете {CREATOR_PCT}% от пополнений игроков по этому коду. "
                                        "Статистика — в меню спонсора.")
    except Exception:
        pass


@router.callback_query(F.data == "adm:newpromo")
async def cb_adm_newpromo(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.new_promo)
    await show(c, "🎁 <b>Создание промокода</b>\n"
                  "Введите через пробел: <b>код, сколько ⭐ даёт, сколько активаций</b>\n\n"
                  "Пример: <code>NEWYEAR 500 10</code>", panel_back_kb())


@router.message(AdminState.new_promo)
async def msg_adm_newpromo(m: Message, state: FSMContext):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    parts = (m.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit() \
            or int(parts[1]) <= 0 or int(parts[2]) <= 0:
        return await m.answer("Формат: <code>КОД звёзды активации</code>\n"
                              "Звёзды и активации — целые числа больше 0.\nПример: <code>NEWYEAR 500 10</code>",
                              reply_markup=panel_back_kb())
    title, reward, uses = parts[0], int(parts[1]), int(parts[2])
    if len(title) > 32:
        return await m.answer("❌ Код слишком длинный (максимум 32 символа).", reply_markup=panel_back_kb())
    cur = db.execute("INSERT OR IGNORE INTO promos(code, reward, max_uses) VALUES(?,?,?)",
                     (title.casefold(), reward, uses))
    if cur.rowcount != 1:
        return await m.answer("❌ Такой промокод уже существует. Придумайте другой.",
                              reply_markup=panel_back_kb())
    await state.clear()
    await m.answer(f"✅ Промокод создан!\n\n🎁 Код: <code>{title}</code>\n"
                   f"⭐ Награда: <b>{reward}</b>\n🔢 Активаций: <b>{uses}</b>", reply_markup=panel_kb())


_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
                "r", "s", "t", "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def make_slug(text: str) -> str:
    out = "".join(_TR.get(ch, ch) for ch in text.casefold())
    return "".join(ch for ch in out if ch in "abcdefghijklmnopqrstuvwxyz0123456789_-")[:40]


@router.callback_query(F.data == "adm:newcreator")
async def cb_adm_newcreator(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.new_creator)
    await show(c, "🆕 <b>Создание кода автора</b>\n"
                  "Введите <b>код</b> (одним словом). Для ссылки бот сам сделает слово из латинских букв.\n"
                  "Своё слово для ссылки можно дописать через пробел.\n\n"
                  "Примеры:\n<code>SIGMA</code>\n<code>несквик nesquik</code>\n\n"
                  "Владельца привяжите потом кнопкой «Коды авторов» → «Привязать владельца».",
               panel_back_kb())


@router.message(AdminState.new_creator)
async def msg_adm_newcreator(m: Message, state: FSMContext):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    parts = (m.text or "").split()
    if len(parts) not in (1, 2):
        return await m.answer("Формат: <code>КОД</code> или <code>КОД слово_для_ссылки</code>",
                              reply_markup=panel_back_kb())
    title = parts[0]
    if len(title) > 32:
        return await m.answer("❌ Код слишком длинный (максимум 32 символа).", reply_markup=panel_back_kb())
    slug = (parts[1] if len(parts) == 2 else make_slug(title)).lower()
    if not slug or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in slug):
        return await m.answer("❌ Слово для ссылки: только латиница, цифры, _ и -.\n"
                              "Напишите его вторым словом, например: <code>несквик nesquik</code>",
                              reply_markup=panel_back_kb())
    if find_creator(title):
        return await m.answer("❌ Такой код автора уже есть.", reply_markup=panel_back_kb())
    if db.execute("SELECT 1 FROM creators WHERE slug=?", (slug,)).fetchone():
        return await m.answer("❌ Такое слово для ссылки уже занято. Укажите другое вторым словом.",
                              reply_markup=panel_back_kb())
    db.execute("INSERT INTO creators(code, title, slug) VALUES(?,?,?)", (title.casefold(), title, slug))
    await state.clear()
    me = await m.bot.get_me()
    await m.answer(f"✅ Код автора создан!\n\n🎟 Код: <b>{title}</b>\n"
                   f"🔗 Ссылка: <code>https://t.me/{me.username}?start=c_{slug}</code>\n\n"
                   "Владельца можно привязать в «Коды авторов».", reply_markup=panel_kb())


@router.callback_query(F.data == "adm:wd")
async def cb_adm_wd(c: CallbackQuery):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    rows = db.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id").fetchall()
    if not rows:
        return await show(c, "⏳ Ожидающих заявок на вывод нет.", panel_back_kb())
    total = sum(r["amount"] for r in rows)
    note = "\nПоказаны первые 20." if len(rows) > 20 else ""
    await show(c, f"📥 <b>Заявки на вывод</b>\nОжидают: {len(rows)} шт на {total} ⭐{note}",
               panel_back_kb())
    for r in rows[:20]:
        u = get_user(r["user_id"])
        name = f"@{u['username']}" if u and u["username"] else "без username"
        await c.message.answer(
            f"💸 Заявка <b>#{r['id']}</b>\n"
            f"👤 Игрок: {name} (<code>{r['user_id']}</code>)\n"
            f"💰 Сумма: <b>{r['amount']} ⭐</b>\n🕐 {r['created']}",
            reply_markup=admin_wd_kb(r["id"]))


@router.callback_query(F.data == "adm:reset_user")
async def cb_adm_reset_user(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.reset_user)
    await show(c, "🧽 Введите username игрока, которому нужно обнулить баланс, "
                  "например: <code>@durov</code>", panel_back_kb())


@router.message(AdminState.reset_user)
async def msg_adm_reset_user(m: Message, state: FSMContext):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    username = (m.text or "").strip().lstrip("@")
    row = db.execute("SELECT id, username, balance FROM users WHERE LOWER(username)=LOWER(?)",
                     (username,)).fetchone()
    if not row:
        return await m.answer(f"❌ Игрок @{username} не найден.", reply_markup=panel_back_kb())
    wipe_balances(row["id"])
    await state.clear()
    await m.answer(f"✅ Баланс @{row['username']} обнулён (было {row['balance']} ⭐).",
                   reply_markup=panel_kb())


@router.callback_query(F.data == "adm:reset")
async def cb_adm_reset(c: CallbackQuery):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    n = db.execute("SELECT COUNT(*) c, COALESCE(SUM(balance),0) s FROM users").fetchone()
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да, обнулить", callback_data="adm:reset_ok")
    b.button(text="❌ Отмена", callback_data="adm:panel")
    b.adjust(2)
    await show(c, f"⚠️ Будут обнулены балансы <b>{n['c']}</b> игроков "
                  f"(суммарно <b>{n['s']} ⭐</b>). Отменить это нельзя.\nПодтвердить?",
               b.as_markup())


@router.callback_query(F.data == "adm:reset_ok")
async def cb_adm_reset_ok(c: CallbackQuery):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    wipe_balances()
    await show(c, "✅ Все балансы обнулены.", panel_kb())


def _nft_admin(uid: int) -> bool:
    return uid in ADMIN_IDS or uid in admin_sessions


async def nft_add_from_text(m: Message, bot: Bot, text: str) -> str | None:
    parts = text.split(maxsplit=2)
    if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) <= 0:
        return "Формат: <code>@username звёзды название</code>\nПример: <code>@durov 500 Plush Pepe #123</code>"
    username, value, name = parts[0].lstrip("@"), int(parts[1]), parts[2].strip()
    if len(name) > 64:
        return "❌ Название слишком длинное (максимум 64 символа)."
    row = db.execute("SELECT id, username FROM users WHERE LOWER(username)=LOWER(?)", (username,)).fetchone()
    if not row:
        return f"❌ Игрок @{esc(username)} не найден (он должен хотя бы раз запустить бота)."
    nid = await nft_credit(bot, row["id"], name, value)
    await m.answer(f"✅ NFT #{nid} <b>{esc(name)}</b> зачислен игроку @{esc(row['username'])}: +{value} ⭐")
    return None


@router.message(Command("nftadd"))
async def cmd_nftadd(m: Message, bot: Bot):
    if not _nft_admin(m.from_user.id):
        return
    parts = (m.text or "").split(maxsplit=1)
    err = await nft_add_from_text(m, bot, parts[1] if len(parts) == 2 else "")
    if err:
        await m.answer(err)


@router.callback_query(F.data == "adm:nft")
async def cb_adm_nft(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(AdminState.new_nft)
    await show(c, "🖼 <b>Зачислить NFT</b>\nВведите: <b>@username, сколько ⭐ зачислить, название NFT</b>\n\n"
                  "Пример: <code>@durov 500 Plush Pepe #123</code>", panel_back_kb())


@router.message(AdminState.new_nft)
async def msg_adm_nft(m: Message, state: FSMContext, bot: Bot):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    err = await nft_add_from_text(m, bot, m.text or "")
    if err:
        return await m.answer(err, reply_markup=panel_back_kb())
    await state.clear()
    await m.answer(PANEL_TEXT, reply_markup=panel_kb())


# ═════════════════════════ NFT: ЦЕНЫ, ЗАЯВКИ, ИНВЕНТАРЬ, АПГРЕЙДЕР ═════════════════════════
import difflib
import re

import aiohttp

db.executescript("""
CREATE TABLE IF NOT EXISTS inventory(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    number INTEGER,
    source TEXT NOT NULL DEFAULT 'admin',
    created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS nft_requests(
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    link TEXT,
    name TEXT NOT NULL,
    number INTEGER,
    auto_price INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    credited INTEGER NOT NULL DEFAULT 0,
    created TEXT DEFAULT CURRENT_TIMESTAMP,
    processed TEXT
);
CREATE TABLE IF NOT EXISTS nft_prices(
    name TEXT PRIMARY KEY,
    stars INTEGER NOT NULL,
    updated BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS nft_overrides(
    name TEXT PRIMARY KEY,
    stars INTEGER NOT NULL
);
""")

NFT_CATALOG: dict[str, float] = {
    "Plush Pepe": 4000, "Heart Locket": 800, "Durov's Cap": 700, "Precious Peach": 300,
    "Heroic Helmet": 250, "Astral Shard": 150, "Nail Bracelet": 120, "Magic Potion": 100,
    "Loot Bag": 100, "Mini Oscar": 90, "Signet Ring": 80, "Perfume Bottle": 60,
    "Ion Gem": 50, "Mighty Arm": 40, "Bonded Ring": 40, "Neko Helmet": 40,
    "Swiss Watch": 30, "Scared Cat": 25, "Kissed Frog": 25, "Vintage Cigar": 20,
    "Diamond Ring": 15, "Eternal Rose": 15, "Electric Skull": 12, "Top Hat": 10,
    "Love Potion": 8, "Genie Lamp": 8, "Sharp Tongue": 7, "Gem Signet": 7,
    "Toy Bear": 6, "Crystal Ball": 6, "Record Player": 5, "Light Sword": 5,
    "Artisan Brick": 5, "Jester Hat": 4, "Snake Box": 4, "Jack-in-the-Box": 4,
    "Bunny Muffin": 3.5, "Easter Egg": 3, "Cookie Heart": 3, "Jelly Bunny": 3,
    "Hex Pot": 3, "Evil Eye": 3, "Spiced Wine": 3, "Holiday Drink": 3,
    "Snow Globe": 3, "Trapped Heart": 3, "Sleigh Bell": 3, "Voodoo Doll": 3,
    "Flying Broom": 3, "Candy Cane": 2.5, "Hypno Lollipop": 2.5, "Mad Pumpkin": 2.5,
    "Desk Calendar": 2, "Jingle Bells": 2, "Snow Mittens": 2, "Winter Wreath": 2,
    "Star Notepad": 2, "Pet Snake": 2, "Big Year": 2, "Lunar Snake": 2,
    "B-Day Candle": 2, "Party Sparkler": 2, "Homemade Cake": 2, "Lol Pop": 2,
    "Ginger Cookie": 2, "Santa Hat": 2, "Xmas Stocking": 2, "Restless Jar": 2,
    "Tama Gadget": 2, "Witch Hat": 2, "Berry Box": 2, "Spy Agaric": 2,
    "Skull Flower": 2, "Joyful Bundle": 2, "Lush Bouquet": 2, "Cupid Charm": 2,
    "Whip Cupcake": 2, "Instant Ramen": 2, "Faith Amulet": 2, "Bow Tie": 2,
    "Pool Float": 2, "Moon Pendant": 2, "Ice Cream": 2, "Input Key": 2,
    "Clover Pin": 2, "Sakura Flower": 2,
}
CAT_NAMES = sorted(NFT_CATALOG)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


_CAT_BY_NORM = {_norm(n): n for n in NFT_CATALOG}


def match_catalog(text: str) -> str | None:
    n = _norm(text)
    if not n:
        return None
    if n in _CAT_BY_NORM:
        return _CAT_BY_NORM[n]
    close = difflib.get_close_matches(n, list(_CAT_BY_NORM), n=1, cutoff=0.8)
    return _CAT_BY_NORM[close[0]] if close else None


_LINK_RE = re.compile(r"t\.me/nft/([A-Za-z0-9_]+?)-(\d+)", re.I)


def parse_nft_input(text: str) -> tuple[str | None, int | None, str]:
    text = (text or "").strip()
    m = _LINK_RE.search(text)
    if m:
        slug, num = m.group(1), int(m.group(2))
        return match_catalog(slug), num, slug
    m = re.search(r"#?\s*(\d{1,9})\s*$", text)
    num = int(m.group(1)) if m else None
    base = (text[:m.start()] if m else text).strip(" #-_")
    return match_catalog(base), num, base or text


def nft_label(name: str, number: int | None = None) -> str:
    return f"{name} #{number}" if number else name


_rate = {"spt": float(STARS_PER_TON_FALLBACK), "t": 0.0}
_floor = {"t": 0.0}


async def _get_json(url: str):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
        async with s.get(url) as r:
            r.raise_for_status()
            return await r.json(content_type=None)


async def refresh_rate():
    if time.time() - _rate["t"] < 3600:
        return
    _rate["t"] = time.time()
    try:
        d = await _get_json("https://api.coingecko.com/api/v3/simple/price"
                            "?ids=the-open-network&vs_currencies=usd")
        _rate["spt"] = max(1.0, float(d["the-open-network"]["usd"]) / STAR_USD)
    except Exception as e:
        logging.warning("курс TON не обновлён: %s", e)


async def refresh_prices():
    await refresh_rate()
    if not NFT_FLOOR_API_URL or time.time() - _floor["t"] < NFT_PRICE_TTL:
        return
    _floor["t"] = time.time()
    try:
        data = await _get_json(NFT_FLOOR_API_URL)
        if isinstance(data, dict):
            pairs = list(data.items())
        else:
            pairs = [(x.get("name") or x.get("collection"),
                      x.get("floor") if x.get("floor") is not None else
                      x.get("floor_price", x.get("price"))) for x in data]
        now = int(time.time())
        for raw, ton in pairs:
            name = match_catalog(str(raw))
            if not name or ton is None:
                continue
            stars = max(1, int(float(ton) * _rate["spt"]))
            db.execute("INSERT INTO nft_prices(name, stars, updated) VALUES(?,?,?) "
                       "ON CONFLICT(name) DO UPDATE SET stars=excluded.stars, updated=excluded.updated",
                       (name, stars, now))
    except Exception as e:
        logging.warning("цены NFT не обновлены: %s", e)


def nft_price(name: str) -> int:
    r = db.execute("SELECT stars FROM nft_overrides WHERE name=?", (name,)).fetchone()
    if r:
        return r["stars"]
    r = db.execute("SELECT stars FROM nft_prices WHERE name=?", (name,)).fetchone()
    if r:
        return r["stars"]
    ton = NFT_CATALOG.get(name)
    return max(1, int(ton * _rate["spt"])) if ton else 0


def nft_sell_value(name: str) -> int:
    return nft_price(name) * NFT_SELL_PCT // 100


def _rows(b: InlineKeyboardBuilder, buttons: list, per_row: int = 1):
    for i in range(0, len(buttons), per_row):
        b.row(*buttons[i:i + per_row])


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _nav(prefix: str, page: int, pages: int) -> list:
    nav = []
    if page > 0:
        nav.append(_btn("◀️", f"{prefix}{page - 1}"))
    nav.append(_btn(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        nav.append(_btn("▶️", f"{prefix}{page + 1}"))
    return nav


class NftReq(StatesGroup):
    waiting = State()
    admin_amount = State()


@router.callback_query(F.data == "nftreq:start")
async def cb_nftreq_start(c: CallbackQuery, state: FSMContext):
    ensure_user(c.from_user.id, c.from_user.username)
    n = db.execute("SELECT COUNT(*) FROM nft_requests WHERE user_id=? AND status='pending'",
                   (c.from_user.id,)).fetchone()[0]
    if n >= NFT_MAX_PENDING:
        return await c.answer(f"У вас уже {n} необработанных заявок. Дождитесь ответа администратора.",
                              show_alert=True)
    await state.set_state(NftReq.waiting)
    await show(c, "📨 <b>Заявка: я отправил NFT</b>\n\n"
                  f"1. Отправьте NFT на @{NFT_USERNAME}\n"
                  "2. Пришлите сюда <b>ссылку на NFT</b> (например <code>https://t.me/nft/PlushPepe-123</code>) "
                  "или название и номер (<code>Plush Pepe #123</code>)\n\n"
                  "Цену бот определит сам, администратор проверит поступление и зачислит ⭐.",
               back_kb())


@router.message(NftReq.waiting)
async def msg_nftreq(m: Message, state: FSMContext, bot: Bot):
    text = (m.text or "").strip()
    if not text or len(text) > 300:
        return await m.answer("Пришлите ссылку на NFT или «Название #номер» (до 300 символов).",
                              reply_markup=back_kb())
    uid = m.from_user.id
    ensure_user(uid, m.from_user.username)
    await refresh_prices()
    name, num, raw = parse_nft_input(text)
    price = nft_price(name) if name else 0
    cur = db.execute("INSERT INTO nft_requests(user_id, link, name, number, auto_price) VALUES(?,?,?,?,?)",
                     (uid, text, (name or raw)[:64], num, price))
    rid = cur.lastrowid
    await state.clear()
    uname = f"@{m.from_user.username}" if m.from_user.username else f"id{uid}"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📨 <b>Заявка на NFT #{rid}</b>\n\n👤 Игрок: {esc(uname)} (<code>{uid}</code>)\n"
            f"🖼 NFT: <b>{esc(nft_label(name or raw, num))}</b>"
            + ("" if name else " <i>(нет в каталоге)</i>") + "\n"
            f"🔗 Ввод: {esc(text)}\n"
            + (f"💰 Авто-цена: <b>{price} ⭐</b>" if price else "💰 Цена не определена — введите сумму вручную")
            + f"\n\nПроверьте, что NFT пришёл на @{NFT_USERNAME}.",
            reply_markup=nreq_kb(rid, price))
    except Exception:
        logging.exception("не удалось отправить заявку на NFT админу")
    await m.answer(f"✅ Заявка <b>#{rid}</b> отправлена администратору.\n"
                   f"🖼 {esc(nft_label(name or raw, num))}\n"
                   + (f"💰 Предварительная цена: <b>{price} ⭐</b>\n" if price else "")
                   + "Как только NFT будет проверен, ⭐ придут на баланс.", reply_markup=back_kb())


def nreq_kb(rid: int, price: int):
    b = InlineKeyboardBuilder()
    if price > 0:
        b.button(text=f"✅ Начислить {price} ⭐", callback_data=f"nreq:ok:{rid}")
    b.button(text="✏️ Своя сумма", callback_data=f"nreq:amt:{rid}")
    b.button(text="❌ Отклонить", callback_data=f"nreq:no:{rid}")
    b.adjust(1)
    return b.as_markup()


async def nreq_process(bot: Bot, rid: int, action: str, amount: int | None = None) -> str:
    r = db.execute("SELECT * FROM nft_requests WHERE id=?", (rid,)).fetchone()
    if not r:
        return "Заявка не найдена."
    if r["status"] != "pending":
        return f"Заявка #{rid} уже обработана ({r['status']})."
    label = nft_label(r["name"], r["number"])
    if action == "no":
        cur = db.execute("UPDATE nft_requests SET status='rejected', processed=CURRENT_TIMESTAMP "
                         "WHERE id=? AND status='pending'", (rid,))
        if cur.rowcount != 1:
            return f"Заявка #{rid} уже обработана."
        try:
            await bot.send_message(r["user_id"], f"❌ Заявка <b>#{rid}</b> на NFT <b>{esc(label)}</b> отклонена.")
        except Exception:
            pass
        return f"❌ Заявка #{rid} отклонена."
    amount = r["auto_price"] if amount is None else amount
    if amount <= 0:
        return "Сумма должна быть больше 0."
    cur = db.execute("UPDATE nft_requests SET status='approved', credited=?, processed=CURRENT_TIMESTAMP "
                     "WHERE id=? AND status='pending'", (amount, rid))
    if cur.rowcount != 1:
        return f"Заявка #{rid} уже обработана."
    await nft_credit(bot, r["user_id"], label, amount)
    return f"✅ Заявка #{rid}: игроку {r['user_id']} начислено {amount} ⭐ за {label}."


@router.callback_query(F.data.startswith("nreq:"))
async def cb_nreq(c: CallbackQuery, bot: Bot, state: FSMContext):
    if not _nft_admin(c.from_user.id):
        return await c.answer("Нет доступа", show_alert=True)
    _, action, rid = c.data.split(":")
    rid = int(rid)
    if action == "amt":
        r = db.execute("SELECT status FROM nft_requests WHERE id=?", (rid,)).fetchone()
        if not r or r["status"] != "pending":
            return await c.answer("Заявка уже обработана", show_alert=True)
        await state.set_state(NftReq.admin_amount)
        await state.update_data(rid=rid)
        await c.message.answer(f"✏️ Введите сумму ⭐ для заявки #{rid} (целое число):")
        return await c.answer()
    result = await nreq_process(bot, rid, action)
    try:
        await c.message.edit_text(c.message.html_text + f"\n\n———\n<b>{esc(result)}</b>", reply_markup=None)
    except Exception:
        pass
    await c.answer(result, show_alert=True)


@router.message(NftReq.admin_amount)
async def msg_nreq_amount(m: Message, state: FSMContext, bot: Bot):
    if not _nft_admin(m.from_user.id):
        return await state.clear()
    t = (m.text or "").strip()
    if not t.isdigit() or not 0 < int(t) <= 10_000_000:
        return await m.answer("Введите целое число ⭐ больше 0.")
    rid = (await state.get_data()).get("rid")
    await state.clear()
    await m.answer(await nreq_process(bot, rid, "ok", int(t)))


@router.callback_query(F.data == "adm:nreq")
async def cb_adm_nreq(c: CallbackQuery):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    rows = db.execute("SELECT * FROM nft_requests WHERE status='pending' ORDER BY id").fetchall()
    if not rows:
        return await show(c, "📨 Необработанных заявок на NFT нет.", panel_back_kb())
    await show(c, f"📨 <b>Заявки на NFT</b>: ожидают {len(rows)} шт." +
               ("\nПоказаны первые 20." if len(rows) > 20 else ""), panel_back_kb())
    for r in rows[:20]:
        u = get_user(r["user_id"])
        name = f"@{u['username']}" if u and u["username"] else f"id{r['user_id']}"
        await c.message.answer(
            f"📨 <b>Заявка #{r['id']}</b>\n👤 {esc(name)} (<code>{r['user_id']}</code>)\n"
            f"🖼 <b>{esc(nft_label(r['name'], r['number']))}</b>\n🔗 {esc(r['link'] or '')}\n"
            + (f"💰 Авто-цена: <b>{r['auto_price']} ⭐</b>" if r["auto_price"] else "💰 Цена не определена"),
            reply_markup=nreq_kb(r["id"], r["auto_price"]))


@router.message(Command("nftprice"))
async def cmd_nftprice(m: Message):
    if not _nft_admin(m.from_user.id):
        return
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await refresh_prices()
        lines = [f"{n} — {nft_price(n)} ⭐" for n in sorted(NFT_CATALOG, key=lambda x: -NFT_CATALOG[x])[:40]]
        return await m.answer("💲 <b>Цены NFT</b> (топ-40)\n" + "\n".join(lines) +
                              "\n\nИзменить: <code>/nftprice Plush Pepe 450000</code>\n"
                              "Вернуть авто-цену: <code>/nftprice Plush Pepe auto</code>")
    body = parts[1].rsplit(maxsplit=1)
    name = match_catalog(body[0]) if len(body) == 2 else None
    if not name:
        return await m.answer("Формат: <code>/nftprice Название звёзды</code> (название из каталога)")
    if body[1].lower() == "auto":
        db.execute("DELETE FROM nft_overrides WHERE name=?", (name,))
        return await m.answer(f"✅ {esc(name)}: авто-цена, сейчас {nft_price(name)} ⭐")
    if not body[1].isdigit() or int(body[1]) <= 0:
        return await m.answer("Цена — целое число ⭐ больше 0, либо слово auto.")
    db.execute("INSERT INTO nft_overrides(name, stars) VALUES(?,?) "
               "ON CONFLICT(name) DO UPDATE SET stars=excluded.stars", (name, int(body[1])))
    await m.answer(f"✅ {esc(name)}: ручная цена {int(body[1])} ⭐")


def inv_add(uid: int, name: str, number: int | None = None, source: str = "admin") -> int:
    return db.execute("INSERT INTO inventory(user_id, name, number, source) VALUES(?,?,?,?)",
                      (uid, name, number, source)).lastrowid


async def inv_render(uid: int, page: int):
    await refresh_prices()
    rows = db.execute("SELECT * FROM inventory WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    total = sum(nft_sell_value(r["name"]) for r in rows)
    b = InlineKeyboardBuilder()
    if not rows:
        text = ("🎒 <b>Инвентарь</b>\n\nПока пусто.\nNFT попадают сюда от администрации и из NFT-апгрейдера. "
                "Их можно продать за ⭐ или апгрейднуть.")
    else:
        pages = max(1, math.ceil(len(rows) / INV_PAGE))
        page = max(0, min(page, pages - 1))
        chunk = rows[page * INV_PAGE:(page + 1) * INV_PAGE]
        lines = [f"• <b>{esc(nft_label(r['name'], r['number']))}</b> — {nft_sell_value(r['name'])} ⭐" for r in chunk]
        text = (f"🎒 <b>Инвентарь</b>\nNFT: <b>{len(rows)}</b> шт · стоимость при продаже: <b>{total} ⭐</b>\n\n"
                + "\n".join(lines) + "\n\nНажмите на NFT, чтобы продать.")
        _rows(b, [_btn(f"💰 {nft_label(r['name'], r['number'])} · {nft_sell_value(r['name'])} ⭐", f"inv:s:{r['id']}")
                  for r in chunk])
        if pages > 1:
            b.row(*_nav("inv:p:", page, pages))
        b.row(_btn(f"💰 Продать все ({total} ⭐)", "inv:sa"))
    b.row(_btn("🚀 NFT Апгрейдер", "nup:menu"))
    b.row(_btn("📨 Я отправил NFT", "nftreq:start"), _btn("📜 История NFT", "menu:nft"))
    b.row(_btn("⬅️ В меню", "menu:main"))
    return text, b.as_markup()


@router.callback_query(F.data == "inv:menu")
async def cb_inv_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ensure_user(c.from_user.id, c.from_user.username)
    text, kb = await inv_render(c.from_user.id, 0)
    await show(c, text, kb)


@router.callback_query(F.data.startswith("inv:p:"))
async def cb_inv_page(c: CallbackQuery):
    text, kb = await inv_render(c.from_user.id, int(c.data.split(":")[2]))
    await show(c, text, kb)


def _back_inv_kb(extra: list | None = None):
    b = InlineKeyboardBuilder()
    for e in extra or []:
        b.row(e)
    b.row(_btn("🎒 Инвентарь", "inv:menu"))
    return b.as_markup()


async def _sell_confirm(c: CallbackQuery, row):
    val = nft_sell_value(row["name"])
    if val <= 0:
        return await show(c, "❌ Для этого NFT пока не удалось определить цену.", _back_inv_kb())
    await show(c, f"💰 Продать <b>{esc(nft_label(row['name'], row['number']))}</b> за <b>{val} ⭐</b>?",
               _back_inv_kb([_btn(f"✅ Продать за {val} ⭐", f"inv:y:{row['id']}:{val}")]))


@router.callback_query(F.data.startswith("inv:s:"))
async def cb_inv_sell(c: CallbackQuery):
    await refresh_prices()
    row = db.execute("SELECT * FROM inventory WHERE id=? AND user_id=?",
                     (int(c.data.split(":")[2]), c.from_user.id)).fetchone()
    if not row:
        return await c.answer("Этого NFT уже нет в инвентаре", show_alert=True)
    await _sell_confirm(c, row)


@router.callback_query(F.data.startswith("inv:y:"))
async def cb_inv_sell_ok(c: CallbackQuery):
    _, _, iid, shown = c.data.split(":")
    uid = c.from_user.id
    await refresh_prices()
    async with lock_for(uid):
        row = db.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (int(iid), uid)).fetchone()
        if not row:
            return await c.answer("Этого NFT уже нет в инвентаре", show_alert=True)
        val = nft_sell_value(row["name"])
        if val != int(shown):
            return await _sell_confirm(c, row)
        if val <= 0 or db.execute("DELETE FROM inventory WHERE id=? AND user_id=?", (row["id"], uid)).rowcount != 1:
            return await c.answer("Не удалось продать", show_alert=True)
        give(uid, val)
        bal = balance_of(uid)
    await show(c, f"✅ Продано: <b>{esc(nft_label(row['name'], row['number']))}</b> за <b>{val} ⭐</b>\n"
                  f"Баланс: <b>{bal} ⭐</b>", _back_inv_kb())


async def _sell_all_confirm(c: CallbackQuery, total: int):
    await show(c, f"💰 Продать <b>все</b> NFT за <b>{total} ⭐</b>?",
               _back_inv_kb([_btn(f"✅ Продать все за {total} ⭐", f"inv:ya:{total}")]))


@router.callback_query(F.data == "inv:sa")
async def cb_inv_sell_all(c: CallbackQuery):
    await refresh_prices()
    rows = db.execute("SELECT * FROM inventory WHERE user_id=?", (c.from_user.id,)).fetchall()
    total = sum(nft_sell_value(r["name"]) for r in rows)
    if total <= 0:
        return await c.answer("Продавать нечего", show_alert=True)
    await _sell_all_confirm(c, total)


@router.callback_query(F.data.startswith("inv:ya:"))
async def cb_inv_sell_all_ok(c: CallbackQuery):
    uid, shown = c.from_user.id, int(c.data.split(":")[2])
    await refresh_prices()
    async with lock_for(uid):
        rows = [r for r in db.execute("SELECT * FROM inventory WHERE user_id=?", (uid,)).fetchall()
                if nft_sell_value(r["name"]) > 0]
        total = sum(nft_sell_value(r["name"]) for r in rows)
        if not rows:
            return await c.answer("Продавать нечего", show_alert=True)
        if total != shown:
            return await _sell_all_confirm(c, total)
        db.execute(f"DELETE FROM inventory WHERE user_id=? AND id IN ({','.join('?' * len(rows))})",
                   (uid, *[r["id"] for r in rows]))
        give(uid, total)
        bal = balance_of(uid)
    await show(c, f"✅ Продано NFT: <b>{len(rows)}</b> шт за <b>{total} ⭐</b>\nБаланс: <b>{bal} ⭐</b>",
               _back_inv_kb())


def nup_chance(v: int, t: int) -> float:
    return (1 - NFT_UP_EDGE) * v / t


def nup_targets(v: int) -> list[tuple[int, str, int]]:
    out = []
    for i, n in enumerate(CAT_NAMES):
        p = nft_price(n)
        if p >= v * 1.1 and nup_chance(v, p) >= NFT_UP_MIN_CHANCE:
            out.append((i, n, p))
    return sorted(out, key=lambda x: x[2])


@router.callback_query(F.data == "nup:menu")
async def cb_nup_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_nup_menu(c, 0)


async def show_nup_menu(c: CallbackQuery, page: int):
    uid = c.from_user.id
    await refresh_prices()
    rows = [r for r in db.execute("SELECT * FROM inventory WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
            if nft_price(r["name"]) > 0]
    head = ("🚀 <b>NFT Апгрейдер</b>\nПоставьте свой NFT и выберите более дорогой. "
            f"Шанс = (цена вашего ÷ цена цели) × {100 - int(NFT_UP_EDGE * 100)}%. "
            "Успех — вы получаете целевой NFT, неудача — ваш NFT сгорает.\n\n")
    b = InlineKeyboardBuilder()
    if not rows:
        text = head + "У вас нет NFT в инвентаре."
    else:
        pages = max(1, math.ceil(len(rows) / INV_PAGE))
        page = max(0, min(page, pages - 1))
        chunk = rows[page * INV_PAGE:(page + 1) * INV_PAGE]
        text = head + "Выберите NFT, который поставите:"
        _rows(b, [_btn(f"{nft_label(r['name'], r['number'])} · {nft_price(r['name'])} ⭐", f"nup:s:{r['id']}:0")
                  for r in chunk])
        if pages > 1:
            b.row(*_nav("nup:p:", page, pages))
    b.row(_btn("🎒 Инвентарь", "inv:menu"), _btn("⬅️ В меню", "menu:main"))
    await show(c, text, b.as_markup())


@router.callback_query(F.data.startswith("nup:p:"))
async def cb_nup_page(c: CallbackQuery):
    await show_nup_menu(c, int(c.data.split(":")[2]))


@router.callback_query(F.data.startswith("nup:s:"))
async def cb_nup_stake(c: CallbackQuery):
    _, _, iid, page = c.data.split(":")
    page = int(page)
    uid = c.from_user.id
    await refresh_prices()
    row = db.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (int(iid), uid)).fetchone()
    if not row:
        return await c.answer("Этого NFT уже нет в инвентаре", show_alert=True)
    v = nft_price(row["name"])
    targets = nup_targets(v)
    b = InlineKeyboardBuilder()
    if not targets:
        text = (f"🚀 Ваш NFT: <b>{esc(nft_label(row['name'], row['number']))}</b> ({v} ⭐)\n\n"
                "Для него нет подходящих целей (нужен NFT дороже, с шансом не ниже "
                f"{int(NFT_UP_MIN_CHANCE * 100)}%).")
    else:
        pages = max(1, math.ceil(len(targets) / NUP_PAGE))
        page = max(0, min(page, pages - 1))
        chunk = targets[page * NUP_PAGE:(page + 1) * NUP_PAGE]
        text = (f"🚀 Ваш NFT: <b>{esc(nft_label(row['name'], row['number']))}</b> ({v} ⭐)\n"
                "Выберите цель апгрейда (название · цена · шанс):")
        _rows(b, [_btn(f"{n} · {p} ⭐ · {nup_chance(v, p) * 100:.1f}%", f"nup:c:{iid}:{i}")
                  for i, n, p in chunk])
        if pages > 1:
            b.row(*_nav(f"nup:s:{iid}:", page, pages))
    b.row(_btn("⬅️ Выбор NFT", "nup:menu"))
    await show(c, text, b.as_markup())


async def _nup_confirm(c: CallbackQuery, row, idx: int):
    tname = CAT_NAMES[idx]
    v, t = nft_price(row["name"]), nft_price(tname)
    if t < v * 1.1 or nup_chance(v, t) < NFT_UP_MIN_CHANCE:
        return await show(c, "❌ Эта цель больше не подходит (цены изменились).",
                          _back_inv_kb([_btn("🔄 Выбрать цель", f"nup:s:{row['id']}:0")]))
    b = InlineKeyboardBuilder()
    b.row(_btn("🚀 Апгрейд!", f"nup:go:{row['id']}:{idx}:{v}:{t}"))
    b.row(_btn("⬅️ Другая цель", f"nup:s:{row['id']}:0"))
    await show(c, f"🚀 <b>NFT Апгрейдер</b>\n\n"
                  f"Ставка: <b>{esc(nft_label(row['name'], row['number']))}</b> — {v} ⭐\n"
                  f"Цель: <b>{esc(tname)}</b> — {t} ⭐ (x{t / v:.2f})\n"
                  f"Шанс успеха: <b>{nup_chance(v, t) * 100:.1f}%</b>\n\n"
                  "При неудаче ваш NFT сгорает.", b.as_markup())


@router.callback_query(F.data.startswith("nup:c:"))
async def cb_nup_confirm(c: CallbackQuery):
    _, _, iid, idx = c.data.split(":")
    await refresh_prices()
    row = db.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (int(iid), c.from_user.id)).fetchone()
    if not row or not 0 <= int(idx) < len(CAT_NAMES):
        return await c.answer("Этого NFT уже нет в инвентаре", show_alert=True)
    await _nup_confirm(c, row, int(idx))


@router.callback_query(F.data.startswith("nup:go:"))
async def cb_nup_go(c: CallbackQuery):
    _, _, iid, idx, vs, ts = c.data.split(":")
    idx, uid = int(idx), c.from_user.id
    if not 0 <= idx < len(CAT_NAMES):
        return await c.answer("Неверные параметры", show_alert=True)
    await refresh_prices()
    async with lock_for(uid):
        row = db.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (int(iid), uid)).fetchone()
        if not row:
            return await c.answer("Этого NFT уже нет в инвентаре", show_alert=True)
        tname = CAT_NAMES[idx]
        v, t = nft_price(row["name"]), nft_price(tname)
        if (v, t) != (int(vs), int(ts)):
            return await _nup_confirm(c, row, idx)
        if t < v * 1.1 or nup_chance(v, t) < NFT_UP_MIN_CHANCE:
            return await _nup_confirm(c, row, idx)
        if db.execute("DELETE FROM inventory WHERE id=? AND user_id=?", (row["id"], uid)).rowcount != 1:
            return await c.answer("Этого NFT уже нет в инвентаре", show_alert=True)
        chance = nup_chance(v, t)
        roll = rng.random()
        win = roll < chance
        if win:
            inv_add(uid, tname, None, "upgrade")
        stat(uid, v, t if win else 0)
    filled = max(1, round(chance * 20))
    pos = min(19, int(roll * 20))
    bar = ["🟩" if i < filled else "🟥" for i in range(20)]
    bar[pos] = "⭐" if win else "💀"
    result = (f"🎉 <b>Успех!</b> Вы получили <b>{esc(tname)}</b> ({t} ⭐) — он в инвентаре."
              if win else f"💥 <b>Неудача.</b> <b>{esc(nft_label(row['name'], row['number']))}</b> сгорел.")
    b = InlineKeyboardBuilder()
    b.row(_btn("🔁 Ещё апгрейд", "nup:menu"))
    b.row(_btn("🎒 Инвентарь", "inv:menu"), _btn("⬅️ В меню", "menu:main"))
    await show(c, f"🚀 <b>NFT Апгрейдер</b> | шанс {chance * 100:.1f}%\n\n{''.join(bar)}\n\n{result}", b.as_markup())


class NftGive(StatesGroup):
    username = State()


async def ng_show(target, state: FSMContext, page: int, note: str = ""):
    data = await state.get_data()
    pages = max(1, math.ceil(len(CAT_NAMES) / NG_PAGE))
    page = max(0, min(page, pages - 1))
    text = (f"🎁 <b>Выдать NFT → {esc(data.get('ng_name', '?'))}</b>\n"
            "Нажмите на NFT — он сразу попадёт в инвентарь. Можно нажимать несколько раз.\n"
            f"Выдано за сессию: <b>{data.get('ng_count', 0)}</b>"
            + (f"\n\n{note}" if note else ""))
    b = InlineKeyboardBuilder()
    start = page * NG_PAGE
    _rows(b, [_btn(f"{n} · {nft_price(n)} ⭐", f"ng:a:{start + k}:{page}")
              for k, n in enumerate(CAT_NAMES[start:start + NG_PAGE])], per_row=2)
    if pages > 1:
        b.row(*_nav("ng:p:", page, pages))
    b.row(_btn("⬅️ В админ панель", "adm:panel"))
    await show(target, text, b.as_markup())


@router.callback_query(F.data == "adm:ngive_self")
async def cb_ngive_self(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    ensure_user(c.from_user.id, c.from_user.username)
    await state.clear()
    await state.update_data(ng_uid=c.from_user.id, ng_name="себе", ng_count=0)
    await refresh_prices()
    await ng_show(c, state, 0)


@router.callback_query(F.data == "adm:ngive_user")
async def cb_ngive_user(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    await state.set_state(NftGive.username)
    await show(c, "🎁 Введите username игрока, которому выдать NFT, например: <code>@durov</code>",
               panel_back_kb())


@router.message(NftGive.username)
async def msg_ngive_username(m: Message, state: FSMContext):
    if m.from_user.id not in admin_sessions:
        return await state.clear()
    username = (m.text or "").strip().lstrip("@")
    row = db.execute("SELECT id, username FROM users WHERE LOWER(username)=LOWER(?)", (username,)).fetchone()
    if not row:
        return await m.answer(f"❌ Игрок @{esc(username)} не найден (он должен хотя бы раз запустить бота).",
                              reply_markup=panel_back_kb())
    await state.clear()
    await state.update_data(ng_uid=row["id"], ng_name=f"@{row['username']}", ng_count=0)
    await refresh_prices()
    await ng_show(m, state, 0)


@router.callback_query(F.data.startswith("ng:p:"))
async def cb_ng_page(c: CallbackQuery, state: FSMContext):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    if "ng_uid" not in await state.get_data():
        return await c.answer("Сессия выдачи истекла, начните заново", show_alert=True)
    await ng_show(c, state, int(c.data.split(":")[2]))


@router.callback_query(F.data.startswith("ng:a:"))
async def cb_ng_add(c: CallbackQuery, state: FSMContext, bot: Bot):
    if not _need_session(c):
        return await c.answer("Сначала введите пароль", show_alert=True)
    data = await state.get_data()
    if "ng_uid" not in data:
        return await c.answer("Сессия выдачи истекла, начните заново", show_alert=True)
    _, _, idx, page = c.data.split(":")
    idx = int(idx)
    if not 0 <= idx < len(CAT_NAMES):
        return await c.answer("Неверный NFT", show_alert=True)
    name, uid = CAT_NAMES[idx], data["ng_uid"]
    inv_add(uid, name, None, "admin")
    await state.update_data(ng_count=data.get("ng_count", 0) + 1)
    if uid != c.from_user.id:
        try:
            await bot.send_message(uid, f"🎁 Вам выдан NFT <b>{esc(name)}</b> — он в вашем инвентаре.",
                                   reply_markup=_back_inv_kb())
        except Exception:
            pass
    await ng_show(c, state, int(page), note=f"✅ Добавлено: <b>{esc(name)}</b> ({nft_price(name)} ⭐)")


# ───────────────────────── запуск ─────────────────────────
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

API_SERVER = TelegramAPIServer.from_base("https://bot.catup.lol")


async def main():
    logging.basicConfig(level=logging.INFO)
    session = AiohttpSession(api=API_SERVER)
    bot = Bot(BOT_TOKEN, session=session,
              default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    import sys
    import rubup_server
    await rubup_server.start(sys.modules[__name__], bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
