import os
import json
import asyncio
import sqlite3
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ─────── تنظیمات اولیه ───────
TOKEN = os.getenv("TOKEN")  # توکن را از Secret های Replit بگیر
PRIVATE_GROUP_ID = -1001311582958
PUBLIC_GROUP_ID = -1001081524118
ADMINS = [123456789]  # آیدی عددی ادمین‌ها
DB_PATH = "movies.db"
LANG_PATH = "users_lang.json"
USER_LIST_FILE = "users.txt"
os.makedirs("movie_files", exist_ok=True)

# ─────── پیام‌ها ───────
MESSAGES = {
    "start": {"fa": "سلام! با کلیک روی دکمه‌ها می‌تونی فایل فیلم رو دریافت کنی.",
              "en": "Hi! You can receive the movie files by clicking the buttons."},
    "must_join": {"fa": "ابتدا عضو گروه عمومی شوید.",
                  "en": "Please join the public group first."},
    "file_not_found": {"fa": "❌ فایل پیدا نشد.", "en": "❌ File not found."},
    "not_admin": {"fa": "⛔ این دستور فقط برای مدیران است.", "en": "⛔ This command is for admins only."}
}

# ─────── دیتابیس ───────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            movie_id TEXT PRIMARY KEY,
            poster_file_id TEXT,
            description TEXT,
            full_file_path TEXT,
            sticker_file_id TEXT
        )
    """)
    conn.close()

def add_movie(movie_id, poster_file_id, description, full_file_path, sticker_file_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO movies (movie_id, poster_file_id, description, full_file_path, sticker_file_id)
        VALUES (?, ?, ?, ?, ?)
    """, (movie_id, poster_file_id, description, full_file_path, sticker_file_id))
    conn.commit()
    conn.close()

def get_movie(movie_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT * FROM movies WHERE movie_id = ?", (movie_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"poster_file_id": row[1], "description": row[2], "full_file_path": row[3], "sticker_file_id": row[4]}
    return None

def delete_movie_db(movie_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM movies WHERE movie_id = ?", (movie_id,))
    conn.commit()
    conn.close()

# ─────── زبان کاربر ───────
def get_lang(user_id):
    if os.path.exists(LANG_PATH):
        with open(LANG_PATH, "r") as f:
            data = json.load(f)
            return data.get(str(user_id), "fa")
    return "fa"

def set_lang(user_id, lang):
    data = {}
    if os.path.exists(LANG_PATH):
        with open(LANG_PATH, "r") as f:
            data = json.load(f)
    data[str(user_id)] = lang
    with open(LANG_PATH, "w") as f:
        json.dump(data, f)

# ─────── ذخیره کاربران ───────
def save_user(user_id):
    if not os.path.exists(USER_LIST_FILE):
        with open(USER_LIST_FILE, "w") as f:
            f.write(f"{user_id}\n")
    else:
        with open(USER_LIST_FILE, "r") as f:
            lines = f.read().splitlines()
        if str(user_id) not in lines:
            with open(USER_LIST_FILE, "a") as f:
                f.write(f"{user_id}\n")

# ─────── بررسی عضویت ───────
async def is_member_public_group(context, user_id):
    try:
        member = await context.bot.get_chat_member(PUBLIC_GROUP_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

# ─────── ارسال پوستر به گروه عمومی ───────
async def send_poster_to_public(context, movie_id):
    movie = get_movie(movie_id)
    if movie:
        keyboard = [[InlineKeyboardButton("🎬 دریافت فایل کامل", callback_data=movie_id)]]
        markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_photo(chat_id=PUBLIC_GROUP_ID, photo=movie["poster_file_id"],
                                     caption=movie["description"], reply_markup=markup)

# ─────── فرمان‌ها ───────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id)
    lang = get_lang(user_id)
    await update.message.reply_text(MESSAGES["start"][lang])

async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🇮🇷 فارسی", "🇺🇸 English"]]
    await update.message.reply_text("زبان خود را انتخاب کنید / Choose your language:",
                                    reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    if "فارسی" in text:
        set_lang(uid, "fa")
        await update.message.reply_text("✅ زبان به فارسی تنظیم شد.")
    elif "English" in text:
        set_lang(uid, "en")
        await update.message.reply_text("✅ Language set to English.")

# ─────── فقط ادمین ───────
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        lang = get_lang(user_id)
        if user_id not in ADMINS:
            await update.message.reply_text(MESSAGES["not_admin"][lang])
            return
        return await func(update, context)
    return wrapper

# ─────── فرمان /broadcast ───────
@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ استفاده: /broadcast پیام شما")
        return
    message = " ".join(context.args)
    sent, failed = 0, 0
    with open(USER_LIST_FILE, "r") as f:
        ids = [int(line.strip()) for line in f if line.strip()]
    for uid in ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            sent += 1
        except:
            failed += 1
    await update.message.reply_text(f"📤 ارسال موفق: {sent} - ناموفق: {failed}")

# ─────── فرمان /delete_movie ───────
@admin_only
async def delete_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ استفاده: /delete_movie <movie_id>")
        return
    movie_id = context.args[0]
    delete_movie_db(movie_id)
    try:
        os.remove(f"movie_files/{movie_id}.mp4")
    except:
        pass
    await update.message.reply_text(f"✅ فیلم {movie_id} حذف شد.")

# ─────── دریافت فیلم جدید از گروه خصوصی ───────
async def private_group_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    movie_id = str(message.message_id)
    poster = message.photo[-1].file_id if message.photo else None
    caption = message.caption or "توضیحی وارد نشده"
    full_path = f"movie_files/{movie_id}.mp4"
    sticker_id = "STICKER_FILE_ID_HERE"
    add_movie(movie_id, poster, caption, full_path, sticker_id)
    await send_poster_to_public(context, movie_id)

# ─────── پاسخ دکمه دریافت فایل ───────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    movie_id = query.data
    lang = get_lang(user_id)
    if not await is_member_public_group(context, user_id):
        await query.edit_message_text(MESSAGES["must_join"][lang])
        return
    movie = get_movie(movie_id)
    if not movie:
        await query.edit_message_text(MESSAGES["file_not_found"][lang])
        return
    try:
        with open(movie["full_file_path"], "rb") as video:
            msg = await context.bot.send_document(chat_id=user_id, document=video)
        await context.bot.send_sticker(chat_id=user_id, sticker=movie["sticker_file_id"])
        await context.bot.send_message(chat_id=user_id, text="⌛ این فایل تا 2 دقیقه دیگر حذف می‌شود.")
        await asyncio.sleep(120)
        await context.bot.delete_message(chat_id=user_id, message_id=msg.message_id)
    except:
        await query.edit_message_text(MESSAGES["file_not_found"][lang])

# ─────── اجرا ───────
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", choose_language))
    app.add_handler(MessageHandler(filters.Regex("فارسی|English"), set_language))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("delete_movie", delete_movie))
    app.add_handler(MessageHandler(
        filters.Chat(PRIVATE_GROUP_ID) & (filters.PHOTO | filters.Document.VIDEO),
        private_group_monitor
    ))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
