import logging
import json
import os
import re
from collections import Counter
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext,
)

# Replace with your Telegram bot token
TOKEN = "7642785974:AAHEkvLeAxHti3P-JMhQy0Q5srcHmW1puaU"

# File storage paths
FILE_STORE_PATH = "file_store.json"
STATS_FILE_PATH = "file_stats.json"
REQUESTS_FILE_PATH = "file_requests.json"
REVIEWS_FILE_PATH = "file_reviews.json"

# Enable logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Load stored files
def load_json(filepath, default_data={}):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            logger.error(f"❌ Error loading {filepath}. Resetting data.")
            return default_data
    return default_data

# Save JSON files
def save_json(filepath, data):
    with open(filepath, "w") as file:
        json.dump(data, file, indent=4)

# Load data
file_store = load_json(FILE_STORE_PATH, {})
file_stats = load_json(STATS_FILE_PATH, {"downloads": {}, "users": {}})
file_requests = load_json(REQUESTS_FILE_PATH, {})
file_reviews = load_json(REVIEWS_FILE_PATH, {})

# 📂 **Handle Document Upload**
async def handle_document(update: Update, context: CallbackContext):
    doc = update.message.document
    file_id = doc.file_id
    file_name = doc.file_name.lower()
    file_key = f"file_{len(file_store)}"

    file_store[file_key] = {"name": file_name, "id": file_id}
    save_json(FILE_STORE_PATH, file_store)

    await update.message.reply_text(f"✅ File '{file_name}' saved!")

# 🔍 **Search for Files**
async def search(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /search <filename>")
        return

    query = " ".join(context.args).lower()
    found_files = {key: data for key, data in file_store.items() if query in data["name"]}

    if found_files:
        keyboard = [
            [InlineKeyboardButton(f"{data['name']}", callback_data=key)]
            for key, data in found_files.items()
        ]
        await update.message.reply_text("📂 **Select a file to download:**", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("❌ No matching file found!")

    save_json(FILE_STORE_PATH, file_store)

# 📂 **Handle File Selection & Send (With User Mention & Stats)**
async def send_file(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    file_key = query.data
    user = query.from_user
    user_mention = f"[{user.first_name}](tg://user?id={user.id})"
    user_id = str(user.id)

    if file_key in file_store:
        file_data = file_store[file_key]
        filename, file_id = file_data["name"], file_data["id"]

        # Track downloads & users
        file_stats["downloads"][filename] = file_stats["downloads"].get(filename, 0) + 1
        file_stats["users"][user_id] = file_stats["users"].get(user_id, 0) + 1
        save_json(STATS_FILE_PATH, file_stats)

        await query.message.reply_document(
            file_id, 
            caption=f"📄 {filename}\n👤 Requested by: {user_mention}", 
            parse_mode="Markdown"
        )

# 📊 **Bot Statistics**
async def stats(update: Update, context: CallbackContext):
    total_files = len(file_store)
    total_downloads = sum(file_stats["downloads"].values())
    unique_users = len(file_stats["users"])

    await update.message.reply_text(
        f"📊 **Bot Statistics:**\n"
        f"📂 Total files stored: {total_files}\n"
        f"📥 Total downloads: {total_downloads}\n"
        f"👥 Unique users: {unique_users}"
    )

# 🏆 **User Download Stats**
async def userstats(update: Update, context: CallbackContext):
    if not file_stats["users"]:
        await update.message.reply_text("📊 No users have downloaded files yet.")
        return

    sorted_users = sorted(file_stats["users"].items(), key=lambda x: x[1], reverse=True)
    user_text = "\n".join([f"👤 [User {user_id}](tg://user?id={user_id}): {count} downloads" for user_id, count in sorted_users])

    await update.message.reply_text(f"🏆 **User Download Stats:**\n{user_text}", parse_mode="Markdown")

# 📄 **File Preview Before Download**
async def preview(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /preview <filename>")
        return

    query = " ".join(context.args).lower()
    for key, data in file_store.items():
        if query in data["name"]:
            preview_text = f"📄 Preview: {data['name'][:100]}..."
            await update.message.reply_text(preview_text)
            return

    await update.message.reply_text("❌ No file found with that name.")

# ⭐ **File Rating & Reviews**
async def rate(update: Update, context: CallbackContext):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /rate <filename> <1-5>")
        return

    filename, rating = " ".join(context.args[:-1]).lower(), context.args[-1]
    if not rating.isdigit() or not (1 <= int(rating) <= 5):
        await update.message.reply_text("⚠️ Rating must be between 1 and 5.")
        return

    file_reviews[filename] = file_reviews.get(filename, [])
    file_reviews[filename].append(int(rating))
    save_json(REVIEWS_FILE_PATH, file_reviews)

    await update.message.reply_text(f"✅ You rated '{filename}' {rating} ⭐.")

async def show_top_rated(update: Update, context: CallbackContext):
    if not file_reviews:
        await update.message.reply_text("No ratings available yet!")
        return

    sorted_reviews = sorted(file_reviews.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)[:5]
    review_text = "\n".join([f"⭐ {key}: {sum(vals) / len(vals):.1f}/5" for key, vals in sorted_reviews])
    await update.message.reply_text(f"🏆 **Top Rated Files**:\n{review_text}")

# 📢 **Request Missing Files**
async def request_file(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /request <filename>")
        return

    requested_file = " ".join(context.args).lower()
    file_requests[requested_file] = file_requests.get(requested_file, 0) + 1
    save_json(REQUESTS_FILE_PATH, file_requests)

    await update.message.reply_text(f"📢 Request for '{requested_file}' has been sent!")

# 🔧 **Start the Bot**
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("preview", preview))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("toprated", show_top_rated))
    app.add_handler(CommandHandler("request", request_file))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("userstats", userstats))  # ✅ New command
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(send_file))

    logger.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
