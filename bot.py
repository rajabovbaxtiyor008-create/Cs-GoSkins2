import logging
import os
import random
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # обязателен, без него бот не запустится
START_BALANCE = 1000

# --- Каталог: предметы ---
# value — виртуальные очки (внутриигровая валюта ⭐), начисляются в инвентарь
# и используются для покупки кейсов / продажи предметов обратно.
# market_price_usd — ориентировочная цена аналогичного предмета на Steam
# Community Market (середина 2026 года). Реальные цены скинов постоянно
# колеблются (float, стикеры, издание), поэтому это ориентир, а не
# котировка в реальном времени. Цены AWP | Dragon Lore и ★ Karambit |
# Doppler сверены с текущими агрегаторами рынка (csmarketcap.com,
# steamanalyst.com); остальные — усреднённые ориентировочные значения.
# Никакого вывода в реальные деньги/скины — только коллекционная механика.
ITEMS = {
    # --- Обычные (common) ⚪ ---
    "common_1": {"name": "AK-47 | Safari Mesh", "rarity": "common", "value": 20, "market_price_usd": 0.20, "emoji": "⚪"},
    "common_2": {"name": "Glock-18 | Sand Dune", "rarity": "common", "value": 15, "market_price_usd": 0.15, "emoji": "⚪"},
    "common_3": {"name": "P250 | Sand Dune", "rarity": "common", "value": 12, "market_price_usd": 0.12, "emoji": "⚪"},
    "common_4": {"name": "MP9 | Storm", "rarity": "common", "value": 18, "market_price_usd": 0.18, "emoji": "⚪"},
    "sticker_common_1": {"name": "Sticker | Ninjas in Pyjamas (Holo)", "rarity": "common", "value": 10, "market_price_usd": 0.10, "emoji": "🏷️"},

    # --- Необычные (uncommon) 🟢 ---
    "uncommon_1": {"name": "M4A4 | Faded Zebra", "rarity": "uncommon", "value": 60, "market_price_usd": 1.50, "emoji": "🟢"},
    "uncommon_2": {"name": "Five-SeveN | Case Hardened", "rarity": "uncommon", "value": 75, "market_price_usd": 2.00, "emoji": "🟢"},
    "uncommon_3": {"name": "Desert Eagle | Corinthian", "rarity": "uncommon", "value": 90, "market_price_usd": 3.50, "emoji": "🟢"},
    "sticker_uncommon_1": {"name": "Sticker | Astralis (Holo) Katowice 2019", "rarity": "uncommon", "value": 65, "market_price_usd": 1.80, "emoji": "🏷️"},

    # --- Редкие (rare) 🔵 ---
    "rare_1": {"name": "AWP | Pit Viper", "rarity": "rare", "value": 250, "market_price_usd": 10.0, "emoji": "🔵"},
    "rare_2": {"name": "SG 553 | Basket Halftone", "rarity": "rare", "value": 300, "market_price_usd": 14.0, "emoji": "🔵"},
    "rare_3": {"name": "USP-S | Kill Confirmed", "rarity": "rare", "value": 350, "market_price_usd": 18.0, "emoji": "🔵"},
    "sticker_rare_1": {"name": "Sticker | Katowice 2015 (Foil)", "rarity": "rare", "value": 400, "market_price_usd": 25.0, "emoji": "🏷️"},

    # --- Эпические (epic) 🟣 ---
    "epic_1": {"name": "AK-47 | Bloodsport", "rarity": "epic", "value": 900, "market_price_usd": 45.0, "emoji": "🟣"},
    "epic_2": {"name": "M4A1-S | Hyper Beast", "rarity": "epic", "value": 1100, "market_price_usd": 55.0, "emoji": "🟣"},
    "sticker_epic_1": {"name": "Sticker | iBUYPOWER (Holo) Katowice 2014", "rarity": "epic", "value": 1600, "market_price_usd": 120.0, "emoji": "🏷️"},

    # --- Легендарные (legendary) 🟡 ---
    "legendary_1": {"name": "AWP | Dragon Lore", "rarity": "legendary", "value": 5000, "market_price_usd": 5000.0, "emoji": "🟡"},
    "legendary_2": {"name": "M4A4 | Howl", "rarity": "legendary", "value": 2500, "market_price_usd": 2500.0, "emoji": "🟡"},

    # --- Ножи (knife) 🔪 — топовая редкость ---
    "knife_1": {"name": "★ Karambit | Doppler", "rarity": "knife", "value": 8000, "market_price_usd": 8200.0, "emoji": "🔪"},
    "knife_2": {"name": "★ Butterfly Knife | Fade", "rarity": "knife", "value": 2200, "market_price_usd": 2200.0, "emoji": "🔪"},
    "knife_3": {"name": "★ M9 Bayonet | Crimson Web", "rarity": "knife", "value": 1500, "market_price_usd": 1500.0, "emoji": "🔪"},

    # --- Перчатки (gloves) 🧤 — топовая редкость ---
    "glove_1": {"name": "★ Sport Gloves | Pandora's Box", "rarity": "glove", "value": 2500, "market_price_usd": 2500.0, "emoji": "🧤"},
    "glove_2": {"name": "★ Specialist Gloves | Crimson Kimono", "rarity": "glove", "value": 1200, "market_price_usd": 1200.0, "emoji": "🧤"},
}

RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary", "knife", "glove"]
RARITY_LABELS = {
    "common": "Обычные",
    "uncommon": "Необычные",
    "rare": "Редкие",
    "epic": "Эпические",
    "legendary": "Легендарные",
    "knife": "Ножи",
    "glove": "Перчатки",
}

# --- Кейсы ---
# Каждый кейс теперь заточен под свою редкость:
# GRASS -> обычные, ROCK -> необычные, IRON -> редкие,
# DIAMOND -> эпические + легендарные, KNIFES -> ножи + перчатки
# (для перчаток отдельного кейса не просили — добавлены сюда же, как
# вторая топовая ★-категория).
CASES = {
    "grass": {
        "name": "🟩 GRASS",
        "price": 20,
        "odds": [
            ("common_1", 25), ("common_2", 25), ("common_3", 20),
            ("common_4", 20), ("sticker_common_1", 10),
        ],
    },
    "rock": {
        "name": "🪨 ROCK",
        "price": 90,
        "odds": [
            ("uncommon_1", 30), ("uncommon_2", 28),
            ("uncommon_3", 25), ("sticker_uncommon_1", 17),
        ],
    },
    "iron": {
        "name": "⚙️ IRON",
        "price": 380,
        "odds": [
            ("rare_1", 30), ("rare_2", 28),
            ("rare_3", 25), ("sticker_rare_1", 17),
        ],
    },
    "diamond": {
        "name": "💎 DIAMOND",
        "price": 1900,
        "odds": [
            ("epic_1", 35), ("epic_2", 30), ("sticker_epic_1", 20),
            ("legendary_1", 10), ("legendary_2", 5),
        ],
    },
    "knifes": {
        "name": "🔪 KNIFES",
        "price": 3300,
        "odds": [
            ("knife_1", 15), ("knife_2", 25), ("knife_3", 25),
            ("glove_1", 15), ("glove_2", 20),
        ],
    },
}

# --- База данных ---
DB_PATH = os.environ.get("DB_PATH", "shop.db")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER NOT NULL DEFAULT 1000
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL
        );
        """
    )
    # Миграция для уже существующей базы (если бот уже был задеплоен раньше
    # без этой колонки) — просто игнорируем ошибку, если колонка уже есть.
    try:
        conn.execute("ALTER TABLE users ADD COLUMN trade_url TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def get_or_create_user(telegram_id: int, username: str) -> sqlite3.Row:
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (telegram_id, username, balance) VALUES (?, ?, ?)",
            (telegram_id, username, START_BALANCE),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.close()
    return row


def get_balance(telegram_id: int) -> int:
    conn = db()
    row = conn.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.close()
    return row["balance"] if row else 0


def try_spend(telegram_id: int, amount: int) -> bool:
    conn = db()
    cur = conn.execute(
        "UPDATE users SET balance = balance - ? WHERE telegram_id = ? AND balance >= ?",
        (amount, telegram_id, amount),
    )
    conn.commit()
    ok = cur.rowcount == 1
    conn.close()
    return ok


def add_inventory(telegram_id: int, item_id: str):
    conn = db()
    conn.execute(
        "INSERT INTO inventory (telegram_id, item_id, obtained_at) VALUES (?, ?, ?)",
        (telegram_id, item_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_trade_url(telegram_id: int):
    conn = db()
    row = conn.execute("SELECT trade_url FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.close()
    return row["trade_url"] if row else None


def set_trade_url(telegram_id: int, url: str):
    conn = db()
    conn.execute("UPDATE users SET trade_url = ? WHERE telegram_id = ?", (url, telegram_id))
    conn.commit()
    conn.close()


def get_inventory(telegram_id: int, limit: int = 15):
    conn = db()
    rows = conn.execute(
        "SELECT id, item_id, obtained_at FROM inventory WHERE telegram_id = ? ORDER BY obtained_at DESC LIMIT ?",
        (telegram_id, limit),
    ).fetchall()
    conn.close()
    return rows


def get_inventory_stats(telegram_id: int):
    """Возвращает (кол-во предметов, суммарная стоимость) по ВСЕМУ инвентарю."""
    conn = db()
    rows = conn.execute(
        "SELECT item_id FROM inventory WHERE telegram_id = ?", (telegram_id,)
    ).fetchall()
    conn.close()
    count = len(rows)
    total_value = sum(ITEMS[r["item_id"]]["value"] for r in rows)
    return count, total_value


def sell_item(telegram_id: int, row_id: int):
    """Продаёт один предмет из инвентаря по его id. Возвращает начисленную
    сумму или None, если предмет не найден / не принадлежит пользователю."""
    conn = db()
    row = conn.execute(
        "SELECT item_id FROM inventory WHERE id = ? AND telegram_id = ?",
        (row_id, telegram_id),
    ).fetchone()
    if row is None:
        conn.close()
        return None
    value = ITEMS[row["item_id"]]["value"]
    conn.execute("DELETE FROM inventory WHERE id = ?", (row_id,))
    conn.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (value, telegram_id))
    conn.commit()
    conn.close()
    return value


def sell_all(telegram_id: int):
    """Продаёт весь инвентарь пользователя. Возвращает (кол-во предметов, сумма)."""
    conn = db()
    rows = conn.execute(
        "SELECT item_id FROM inventory WHERE telegram_id = ?", (telegram_id,)
    ).fetchall()
    total = sum(ITEMS[r["item_id"]]["value"] for r in rows)
    conn.execute("DELETE FROM inventory WHERE telegram_id = ?", (telegram_id,))
    conn.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (total, telegram_id))
    conn.commit()
    conn.close()
    return len(rows), total


def roll_case(case_id: str) -> str:
    odds = CASES[case_id]["odds"]
    total = sum(w for _, w in odds)
    r = random.uniform(0, total)
    upto = 0
    for item_id, weight in odds:
        upto += weight
        if r <= upto:
            return item_id
    return odds[-1][0]  # fallback на случай погрешности float


# --- Экраны ---
def main_menu_keyboard():
    buttons = [
        [InlineKeyboardButton(f"{c['name']} — {c['price']} ⭐", callback_data=f"case:{cid}")]
        for cid, c in CASES.items()
    ]
    buttons.append([InlineKeyboardButton("👤 Профиль", callback_data="profile")])
    buttons.append([InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")])
    buttons.append([InlineKeyboardButton("🔗 Steam Trade", callback_data="trade")])
    return InlineKeyboardMarkup(buttons)


def case_keyboard(case_id: str):
    buttons = [
        [InlineKeyboardButton("🎲 Открыть", callback_data=f"open:{case_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back")],
    ]
    return InlineKeyboardMarkup(buttons)


def after_open_keyboard(case_id: str):
    buttons = [
        [InlineKeyboardButton("🎲 Открыть ещё", callback_data=f"open:{case_id}")],
        [InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")],
        [InlineKeyboardButton("⬅️ В магазин", callback_data="back")],
    ]
    return InlineKeyboardMarkup(buttons)


def case_preview_text(case_id: str) -> str:
    """Список предметов кейса, аккуратно в столбик (по одному в строке)."""
    case = CASES[case_id]
    odds = case["odds"]
    total = sum(w for _, w in odds)
    by_rarity = {}
    for item_id, w in odds:
        by_rarity.setdefault(ITEMS[item_id]["rarity"], []).append((item_id, w))

    blocks = []
    for rarity in RARITY_ORDER:
        group = by_rarity.get(rarity)
        if not group:
            continue
        prob = sum(w for _, w in group) / total * 100
        item_lines = "\n".join(f"{ITEMS[i]['emoji']} {ITEMS[i]['name']}" for i, _ in group)
        blocks.append(f"<b>{RARITY_LABELS[rarity]}</b> ({prob:.2f}%):\n{item_lines}")
    return "\n\n".join(blocks)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_or_create_user(user.id, user.username or user.first_name)
    text = (
        f"🏪 <b>Магазин кейсов</b>\n\n"
        f"⭐ Баланс: <b>{row['balance']}</b>\n\n"
        f"Выбери кейс:"
    )
    await update.message.reply_html(text, reply_markup=main_menu_keyboard())


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "back":
        context.user_data["awaiting_trade_url"] = False
        balance = get_balance(user_id)
        text = f"🏪 <b>Магазин кейсов</b>\n\n⭐ Баланс: <b>{balance}</b>\n\nВыбери кейс:"
        await query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")
        return

    if data == "profile":
        balance = get_balance(user_id)
        count, total_value = get_inventory_stats(user_id)
        trade_url = get_trade_url(user_id)
        trade_status = "указан ✅" if trade_url else "не указан ❌"
        text = (
            f"👤 <b>Профиль</b>\n\n"
            f"⭐ Баланс: <b>{balance}</b>\n"
            f"🎒 Предметов в инвентаре: <b>{count}</b>\n"
            f"💰 Стоимость инвентаря: <b>{total_value}</b> ⭐\n"
            f"🔗 Steam Trade URL: {trade_status}"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")],
                [InlineKeyboardButton("🔗 Steam Trade", callback_data="trade")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back")],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if data == "inventory":
        rows = get_inventory(user_id)
        if not rows:
            text = "🎒 Инвентарь пуст. Открой кейс, чтобы получить первый предмет."
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back")]])
        else:
            lines = ["🎒 <b>Инвентарь</b> (последние {}):\n".format(len(rows))]
            buttons = []
            for r in rows:
                item = ITEMS[r["item_id"]]
                lines.append(f"{item['emoji']} {item['name']} — {item['value']} ⭐ (≈${item['market_price_usd']:.2f} на Steam)")
                buttons.append([
                    InlineKeyboardButton(
                        f"💰 Продать {item['emoji']} {item['name'][:22]} — {item['value']}⭐",
                        callback_data=f"sell:{r['id']}",
                    )
                ])
            text = "\n".join(lines)
            buttons.append([InlineKeyboardButton("💰 Продать всё", callback_data="sellall")])
            buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
            keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if data.startswith("sell:"):
        row_id = int(data.split(":", 1)[1])
        value = sell_item(user_id, row_id)
        if value is None:
            await query.answer("Предмет не найден (уже продан?)", show_alert=True)
        else:
            await query.answer(f"Продано за {value} ⭐", show_alert=False)
        # Обновляем экран инвентаря
        query.data = "inventory"
        await on_callback(update, context)
        return

    if data == "sellall":
        count, total = sell_all(user_id)
        if count == 0:
            await query.answer("Инвентарь и так пуст", show_alert=True)
        else:
            await query.answer(f"Продано предметов: {count}, получено {total} ⭐", show_alert=True)
        query.data = "inventory"
        await on_callback(update, context)
        return

    if data == "trade":
        current = get_trade_url(user_id)
        if current:
            text = (
                f"🔗 <b>Steam Trade URL</b>\n\n"
                f"Текущая ссылка:\n<code>{current}</code>\n\n"
                f"Чтобы изменить — просто пришли новую ссылку сообщением."
            )
        else:
            text = (
                "🔗 <b>Steam Trade URL</b>\n\n"
                "Ссылка ещё не указана.\n\n"
                "Пришли её сообщением. Взять можно тут:\n"
                "Steam → Инвентарь → Обмен предметами → "
                "«Кто может отправлять мне предложения обмена?» → "
                "скопировать ссылку.\n\n"
                "Выглядит так:\n"
                "<code>https://steamcommunity.com/tradeoffer/new/?partner=...&token=...</code>"
            )
        context.user_data["awaiting_trade_url"] = True
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back")]])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if data.startswith("case:"):
        case_id = data.split(":", 1)[1]
        case = CASES[case_id]
        text = (
            f"📦 <b>{case['name']}</b>\n"
            f"Цена: {case['price']} ⭐\n\n"
            f"Возможные предметы:\n\n{case_preview_text(case_id)}"
        )
        await query.edit_message_text(text, reply_markup=case_keyboard(case_id), parse_mode="HTML")
        return

    if data.startswith("open:"):
        case_id = data.split(":", 1)[1]
        case = CASES[case_id]

        if not try_spend(user_id, case["price"]):
            await query.answer("Недостаточно монет для покупки кейса", show_alert=True)
            return

        item_id = roll_case(case_id)
        item = ITEMS[item_id]
        add_inventory(user_id, item_id)
        balance = get_balance(user_id)

        text = (
            f"📦 Открыт кейс «{case['name']}»\n\n"
            f"{item['emoji']} <b>{item['name']}</b>\n"
            f"Редкость: {RARITY_LABELS[item['rarity']]}\n"
            f"+{item['value']} ⭐ в инвентарь (≈${item['market_price_usd']:.2f} на Steam Market)\n\n"
            f"⭐ Баланс: <b>{balance}</b>"
        )
        await query.edit_message_text(text, reply_markup=after_open_keyboard(case_id), parse_mode="HTML")
        return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_trade_url"):
        return  # обычное сообщение не по делу — игнорируем

    url = update.message.text.strip()
    if not url.startswith("https://steamcommunity.com/tradeoffer/"):
        await update.message.reply_text(
            "Похоже, это не похоже на Steam Trade URL.\n"
            "Ссылка должна начинаться с:\n"
            "https://steamcommunity.com/tradeoffer/\n\n"
            "Пришли её ещё раз, либо нажми /start чтобы отменить."
        )
        return

    set_trade_url(update.effective_user.id, url)
    context.user_data["awaiting_trade_url"] = False
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В магазин", callback_data="back")]])
    await update.message.reply_text(
        "✅ Ссылка сохранена!",
        reply_markup=keyboard,
    )


async def balance_cmd(update: Update, context: ContextTypes.DEFAUL
