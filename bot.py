import logging
import time
import sys
import os
from datetime import datetime, timedelta
from bson import ObjectId
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import qrcode
from io import BytesIO

# -----------------------
# CONFIG - YAHAN APNI VALUES DAALEIN
# -----------------------
BOT_TOKEN = '8249817052:AAG4w0Xk3CF23PKjDhwyR3ga_q1N1By5_nc'  # Apna bot token yahan daalein
ADMIN_ID = 8413263061  # Apna Telegram ID yahan daalein
MONGO_URL = 'mongodb+srv://userbot:userbot@cluster0.iweqz.mongodb.net/test?retryWrites=true&w=majority'

# -----------------------
# INIT
# -----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)

# MongoDB Setup
try:
    from pymongo import MongoClient, DESCENDING
    client = MongoClient(MONGO_URL)
    db = client['bgmi_keys_bot']
    users_col = db['users']
    keys_col = db['keys']
    orders_col = db['orders']
    wallets_col = db['wallets']
    recharges_col = db['recharges']
    banned_users_col = db['banned_users']
    transactions_col = db['transactions']
    coupons_col = db['coupons']
    admin_logs_col = db['admin_logs']
    categories_col = db['categories']
    admins_col = db['admins']
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    exit(1)

# Store temporary data
user_states = {}
upi_payment_states = {}
admin_deduct_state = {}
admin_add_key_state = {}
edit_loader_state = {}
add_loader_state = {}
add_loader_button_state = {}
dynamic_price_state = {}
admin_add_admin_state = {}
delete_loader_state = {}  # New state for loader deletion

# Default Categories
DEFAULT_CATEGORIES = {
    "weekend": {"name": "Weekend Challenge", "price": 49, "emoji": "🎮", "description": "Weekend special challenge keys"},
    "royalty": {"name": "Royalty Pass", "price": 399, "emoji": "🏆", "description": "Premium royalty pass"},
    "uc": {"name": "UC", "price": 99, "emoji": "⚡", "description": "Unknown Cash for BGMI"},
    "event": {"name": "Event Pass", "price": 199, "emoji": "🎯", "description": "Special event passes"},
    "aqm": {"name": "AQM Keys", "price": 299, "emoji": "💎", "description": "AQM premium keys"}
}

# Admin list
ADMINS = [ADMIN_ID]

def load_admins():
    """Load all admin IDs from database"""
    global ADMINS
    try:
        admin_data = list(admins_col.find())
        admins = [ADMIN_ID]
        for admin in admin_data:
            if admin.get('admin_id') and admin['admin_id'] not in admins:
                admins.append(admin['admin_id'])
        ADMINS = admins
    except:
        ADMINS = [ADMIN_ID]
    return ADMINS

# Load categories from database
def load_categories():
    global KEY_CATEGORIES
    KEY_CATEGORIES = {}
    
    try:
        db_categories = list(categories_col.find())
        
        if db_categories:
            for cat in db_categories:
                KEY_CATEGORIES[cat['key']] = {
                    "name": cat['name'],
                    "price": float(cat.get('price', 0)),
                    "emoji": cat.get('emoji', '📌'),
                    "description": cat.get('description', ''),
                    "buttons": cat.get('buttons', [])
                }
        else:
            KEY_CATEGORIES = DEFAULT_CATEGORIES.copy()
            for key, data in DEFAULT_CATEGORIES.items():
                categories_col.update_one(
                    {"key": key},
                    {"$set": {
                        "key": key,
                        "name": data['name'],
                        "price": float(data['price']),
                        "emoji": data['emoji'],
                        "description": data['description'],
                        "buttons": [],
                        "status": "active"
                    }},
                    upsert=True
                )
    except Exception as e:
        logger.error(f"Error loading categories: {e}")
        KEY_CATEGORIES = DEFAULT_CATEGORIES.copy()
    
    return KEY_CATEGORIES

# Load initial data
load_admins()
KEY_CATEGORIES = load_categories()
_current_user_id = None

# -----------------------
# UTILITY FUNCTIONS
# -----------------------
def set_current_user_id(user_id):
    global _current_user_id
    _current_user_id = user_id

def get_current_user_id():
    return _current_user_id

def ensure_user_exists(user_id, user_name=None, username=None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id,
            "name": user_name or "Unknown",
            "username": username,
            "joined_at": datetime.utcnow(),
            "total_purchases": 0,
            "total_spent": 0
        })
    
    wallets_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "balance": 0.0}},
        upsert=True
    )

def get_balance(user_id):
    rec = wallets_col.find_one({"user_id": user_id})
    return float(rec.get("balance", 0)) if rec else 0.0

def add_balance(user_id, amount):
    wallets_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": float(amount)}},
        upsert=True
    )

def deduct_balance(user_id, amount):
    wallets_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": -float(amount)}},
        upsert=True
    )

def format_currency(x):
    try:
        x = float(x)
        if x.is_integer():
            return f"₹{int(x)}"
        return f"₹{x:.2f}"
    except:
        return "₹0"

def is_admin(user_id):
    load_admins()
    return user_id in ADMINS

def is_user_banned(user_id):
    return banned_users_col.find_one({"user_id": user_id, "status": "active"}) is not None

def log_admin_action(admin_id, action, details):
    try:
        admin_logs_col.insert_one({
            "admin_id": admin_id,
            "action": action,
            "details": details,
            "timestamp": datetime.utcnow()
        })
    except:
        pass

def refresh_categories():
    global KEY_CATEGORIES
    KEY_CATEGORIES = load_categories()
    return KEY_CATEGORIES

def generate_dynamic_qr(amount, upi_id="anurag99999@fam"):
    try:
        upi_url = f"upi://pay?pa={upi_id}&pn=BGMI%20Keys&am={amount}&cu=INR"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        bio.name = 'qr.png'
        img.save(bio, format='PNG')
        bio.seek(0)
        return bio
    except Exception as e:
        logger.error(f"QR generation error: {e}")
        return None

def set_user_context(func):
    def wrapper(message):
        set_current_user_id(message.from_user.id)
        return func(message)
    return wrapper

def restart_bot():
    """Restart the bot"""
    logger.info("🔄 Restarting bot...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

# -----------------------
# KEYBOARDS
# -----------------------
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("🛒 Buy Keys"),
        KeyboardButton("💰 Balance")
    )
    keyboard.add(
        KeyboardButton("💳 Recharge"),
        KeyboardButton("🎁 Redeem Coupon")
    )
    keyboard.add(
        KeyboardButton("📞 Support"),
        KeyboardButton("ℹ️ About")
    )
    from_user_id = get_current_user_id()
    if from_user_id and is_admin(from_user_id):
        keyboard.add(KeyboardButton("👑 Admin Panel"))
    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🔙 Main Menu"))
    return keyboard

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("➕ Add Key"),
        KeyboardButton("📋 Key List")
    )
    keyboard.add(
        KeyboardButton("🗑 Remove Key"),
        KeyboardButton("📦 Bulk Add Keys")
    )
    keyboard.add(
        KeyboardButton("📁 Manage Categories"),
        KeyboardButton("➕ Add Loader")
    )
    keyboard.add(
        KeyboardButton("🗑 Delete Loader"),  # New button
        KeyboardButton("👥 Users List")
    )
    keyboard.add(
        KeyboardButton("💸 Pending Recharges"),
        KeyboardButton("📢 Broadcast")
    )
    keyboard.add(
        KeyboardButton("📈 Sales Report"),
        KeyboardButton("🚫 Ban User")
    )
    keyboard.add(
        KeyboardButton("✅ Unban User"),
        KeyboardButton("💳 Deduct Balance")
    )
    keyboard.add(
        KeyboardButton("➕ Add Balance"),
        KeyboardButton("🎟 Coupons")
    )
    keyboard.add(
        KeyboardButton("⚙️ Loader Settings"),
        KeyboardButton("👑 Admin Management")
    )
    keyboard.add(
        KeyboardButton("🔄 Restart Bot"),  # New button
        KeyboardButton("🔙 Main Menu")
    )
    return keyboard

def get_admin_management_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("➕ Add Admin"),
        KeyboardButton("🗑 Remove Admin")
    )
    keyboard.add(
        KeyboardButton("📋 List Admins"),
        KeyboardButton("🔙 Admin Panel")
    )
    return keyboard

def get_loader_settings_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("✏️ Edit Loader Name"),
        KeyboardButton("💰 Edit Loader Price")
    )
    keyboard.add(
        KeyboardButton("🔘 Add Price Button"),
        KeyboardButton("🗑 Remove Price Button")
    )
    keyboard.add(
        KeyboardButton("📋 List Price Buttons"),
        KeyboardButton("🔙 Admin Panel")
    )
    return keyboard

def get_buy_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for key, data in KEY_CATEGORIES.items():
        keyboard.add(KeyboardButton(f"{data['emoji']} {data['name']}"))
    keyboard.add(KeyboardButton("🔙 Main Menu"))
    return keyboard

def get_loader_edit_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for key, data in KEY_CATEGORIES.items():
        keyboard.add(KeyboardButton(f"📌 {data['name']}"))
    keyboard.add(KeyboardButton("🔙 Admin Panel"))
    return keyboard

# -----------------------
# START HANDLER WITH RESTART
# -----------------------
@bot.message_handler(commands=['start'])
@set_user_context
def start(msg):
    user_id = msg.from_user.id
    
    # Check if user is admin and wants to restart
    if is_admin(user_id) and len(msg.text.split()) > 1 and msg.text.split()[1] == "restart":
        bot.reply_to(msg, "🔄 Restarting bot...")
        time.sleep(2)
        restart_bot()
        return
    
    if is_user_banned(user_id):
        bot.reply_to(msg, "🚫 **You are banned!** Contact admin.", parse_mode="Markdown")
        return
    
    ensure_user_exists(user_id, msg.from_user.first_name, msg.from_user.username)
    
    welcome = """
╔══════════════════╗
   🎮 BGMI KEY SHOP 🎮   
╚══════════════════╝

🔥 Available Loaders:"""
    
    for data in KEY_CATEGORIES.values():
        welcome += f"\n• {data['emoji']} {data['name']}"
    
    welcome += """
\n✅ Instant Delivery
💳 Secure Payment
📞 24/7 Support

Use buttons below to navigate!"""
    
    bot.send_message(user_id, welcome, reply_markup=get_main_keyboard())

# -----------------------
# RESTART BOT HANDLER
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🔄 Restart Bot" and is_admin(msg.from_user.id))
@set_user_context
def restart_command(msg):
    bot.send_message(msg.from_user.id, "🔄 Restarting bot...")
    time.sleep(2)
    restart_bot()

# -----------------------
# DELETE LOADER HANDLER
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🗑 Delete Loader" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['delloader'])
@set_user_context
def delete_loader_start(msg):
    user_id = msg.from_user.id
    
    if msg.text.startswith('/delloader'):
        try:
            key = msg.text.split()[1].lower()
            
            if key not in KEY_CATEGORIES:
                bot.reply_to(msg, f"❌ Loader '{key}' not found!")
                return
            
            cat_data = KEY_CATEGORIES[key]
            keys_count = keys_col.count_documents({"category": key})
            
            # Ask for confirmation
            text = f"🗑 **Delete Loader?**\n\n"
            text += f"{cat_data['emoji']} **{cat_data['name']}**\n"
            text += f"Key: `{key}`\n"
            text += f"Price: {format_currency(cat_data['price'])}\n"
            text += f"Total Keys: {keys_count}\n\n"
            text += "⚠️ This will delete ALL keys in this loader!\n\n"
            text += "Type `YES` to confirm or `NO` to cancel:"
            
            delete_loader_state[user_id] = {"key": key, "step": "confirm"}
            bot.reply_to(msg, text, parse_mode="Markdown")
            return
            
        except IndexError:
            bot.reply_to(msg, "❌ Usage: /delloader [loader_key]")
            return
        except Exception as e:
            bot.reply_to(msg, f"❌ Error: {str(e)}")
            return
    
    # Show list of loaders to delete
    text = "🗑 **Delete Loader**\n\nSelect loader to delete:\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    
    for key, data in KEY_CATEGORIES.items():
        keys_count = keys_col.count_documents({"category": key})
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']} ({keys_count} keys)",
            callback_data=f"delloader_{key}"
        ))
    
    bot.send_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delloader_"))
def delete_loader_callback(call):
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    key = call.data.replace("delloader_", "")
    
    if key not in KEY_CATEGORIES:
        bot.answer_callback_query(call.id, "❌ Loader not found!", show_alert=True)
        return
    
    cat_data = KEY_CATEGORIES[key]
    keys_count = keys_col.count_documents({"category": key})
    
    text = f"🗑 **Delete Loader?**\n\n"
    text += f"{cat_data['emoji']} **{cat_data['name']}**\n"
    text += f"Key: `{key}`\n"
    text += f"Price: {format_currency(cat_data['price'])}\n"
    text += f"Total Keys: {keys_count}\n\n"
    text += "⚠️ This will delete ALL keys in this loader!\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_del_{key}"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_del")
    )
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                         reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_del_"))
def confirm_delete_loader(call):
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    key = call.data.replace("confirm_del_", "")
    
    try:
        if key not in KEY_CATEGORIES:
            bot.answer_callback_query(call.id, "❌ Loader not found!", show_alert=True)
            return
        
        cat_data = KEY_CATEGORIES[key]
        keys_count = keys_col.count_documents({"category": key})
        
        # Delete all keys in this category
        keys_col.delete_many({"category": key})
        
        # Delete the category
        categories_col.delete_one({"key": key})
        
        # Refresh categories
        refresh_categories()
        
        text = f"✅ **Loader Deleted!**\n\n"
        text += f"{cat_data['emoji']} **{cat_data['name']}**\n"
        text += f"Key: `{key}`\n"
        text += f"Keys Deleted: {keys_count}\n"
        text += f"Price: {format_currency(cat_data['price'])}"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            parse_mode="Markdown")
        bot.answer_callback_query(call.id, "✅ Loader deleted!")
        
        log_admin_action(user_id, "DELETE_LOADER", {"key": key, "name": cat_data['name'], "keys_deleted": keys_count})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_del")
def cancel_delete_loader(call):
    bot.edit_message_text("✅ Deletion cancelled!", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Cancelled")

@bot.message_handler(func=lambda msg: msg.from_user.id in delete_loader_state and 
                    delete_loader_state[msg.from_user.id].get("step") == "confirm" and is_admin(msg.from_user.id))
@set_user_context
def process_delete_loader_confirm(msg):
    user_id = msg.from_user.id
    text = msg.text.strip().upper()
    
    if text == "YES":
        key = delete_loader_state[user_id]["key"]
        
        try:
            cat_data = KEY_CATEGORIES[key]
            keys_count = keys_col.count_documents({"category": key})
            
            # Delete all keys
            keys_col.delete_many({"category": key})
            
            # Delete category
            categories_col.delete_one({"key": key})
            
            # Refresh
            refresh_categories()
            
            bot.send_message(user_id, 
                f"✅ **Loader Deleted!**\n\n"
                f"{cat_data['emoji']} **{cat_data['name']}**\n"
                f"Keys Deleted: {keys_count}",
                parse_mode="Markdown"
            )
            
            log_admin_action(user_id, "DELETE_LOADER", {"key": key, "name": cat_data['name'], "keys_deleted": keys_count})
            
        except Exception as e:
            bot.send_message(user_id, f"❌ Error: {str(e)}")
    
    elif text == "NO":
        bot.send_message(user_id, "✅ Deletion cancelled!")
    
    else:
        bot.send_message(user_id, "❌ Please type YES or NO")
        return
    
    delete_loader_state.pop(user_id, None)

# -----------------------
# HELP COMMAND
# -----------------------
@bot.message_handler(commands=['help'])
@set_user_context
def help_command(msg):
    user_id = msg.from_user.id
    
    text = "📚 **Help & Commands**\n\n"
    text += "**User Commands:**\n"
    text += "/start - Start the bot\n"
    text += "/help - Show this help\n"
    text += "/balance - Check your balance\n"
    text += "/buy - Buy keys\n"
    text += "/recharge - Recharge wallet\n"
    text += "/coupon - Redeem coupon\n"
    text += "/support - Contact support\n\n"
    
    if is_admin(user_id):
        text += "**Admin Commands:**\n"
        text += "/admin - Open admin panel\n"
        text += "/stats - View bot statistics\n"
        text += "/keys - List all keys\n"
        text += "/users - List users\n"
        text += "/pending - View pending recharges\n"
        text += "/sales - View sales report\n"
        text += "/admins - List all admins\n"
        text += "/delloader [key] - Delete a loader\n"
        text += "/start restart - Restart bot"
    
    bot.reply_to(msg, text, parse_mode="Markdown")

# -----------------------
# MAIN MENU
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🔙 Main Menu")
@set_user_context
def main_menu(msg):
    bot.send_message(msg.from_user.id, "🏠 Main Menu", reply_markup=get_main_keyboard())

# -----------------------
# BUY KEYS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text in ["🛒 Buy Keys", "🛒"] or msg.text.startswith("🛒"))
@bot.message_handler(commands=['buy'])
@set_user_context
def buy_keys(msg):
    user_id = msg.from_user.id
    text = "🎮 **Select Loader:**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        count = keys_col.count_documents({"category": key, "status": "available"})
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"💰 Base Price: {format_currency(data['price'])} | 📦 Available: {count}\n"
        if data.get('buttons'):
            text += f"   **Options:** "
            options = [f"{b['name']} ({format_currency(b['price'])})" for b in data['buttons']]
            text += f"{', '.join(options[:3])}\n"
        text += "\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_buy_keyboard())

# -----------------------
# SHOW KEYS
# -----------------------
@bot.message_handler(func=lambda msg: any(msg.text.startswith(data['emoji']) for data in KEY_CATEGORIES.values()))
@set_user_context
def show_keys(msg):
    user_id = msg.from_user.id
    
    # Find category
    cat_key = None
    cat_data = None
    for key, data in KEY_CATEGORIES.items():
        if msg.text.startswith(data['emoji']):
            cat_key = key
            cat_data = data
            break
    
    if not cat_data:
        bot.send_message(user_id, "❌ Loader not found!", reply_markup=get_buy_keyboard())
        return
    
    # Get available keys
    keys = list(keys_col.find({"category": cat_key, "status": "available"}).limit(10))
    
    if not keys:
        bot.send_message(user_id, f"❌ No {cat_data['name']} keys available!", reply_markup=get_buy_keyboard())
        return
    
    text = f"{cat_data['emoji']} **{cat_data['name']}**\n"
    text += f"💰 Price: {format_currency(cat_data['price'])} per key\n"
    text += f"📦 Available: {len(keys)}\n\n"
    text += "**👇 Select a key:**\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for i, key in enumerate(keys[:8], 1):
        btn_text = f"🔑 Key #{i}"
        if key.get('details'):
            btn_text = f"📝 Key #{i}"
        if key.get('apk_file_id'):
            btn_text += " 📁"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"view_{key['_id']}"))
    
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

# -----------------------
# VIEW KEY DETAILS
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("view_"))
def view_key_details(call):
    user_id = call.from_user.id
    key_id = call.data.replace("view_", "")
    
    try:
        key = keys_col.find_one({"_id": ObjectId(key_id)})
        if not key or key['status'] != 'available':
            bot.answer_callback_query(call.id, "❌ Key not available!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
        cat_data = KEY_CATEGORIES.get(key['category'], {})
        
        text = f"{cat_data.get('emoji', '🔑')} **{cat_data.get('name', 'Unknown')}**\n"
        text += f"💰 **Price:** {format_currency(key.get('price', 0))}\n\n"
        
        if key.get('details'):
            details_lines = key['details'].split('\n')
            text += f"📝 **Key Details:**\n"
            for line in details_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    text += f"**{parts[0]}:**{parts[1]}\n"
                else:
                    text += f"**{line}**\n"
        else:
            text += "ℹ️ No additional details available.\n\n"
        
        if key.get('apk_file_id'):
            text += "📁 **APK File:** Available with this key\n\n"
        
        # Check for price buttons
        if cat_data and cat_data.get('buttons'):
            text += "\n**💵 Select Price:**\n"
            markup = InlineKeyboardMarkup(row_width=2)
            for btn in cat_data['buttons']:
                markup.add(InlineKeyboardButton(
                    f"{btn['name']} - {format_currency(btn['price'])}", 
                    callback_data=f"buyprice_{key_id}_{btn['price']}"
                ))
            markup.add(InlineKeyboardButton(
                f"Base Price - {format_currency(key['price'])}", 
                callback_data=f"buy_{key_id}"
            ))
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_view"))
        else:
            text += "\n🛒 **Purchase this key?**"
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("✅ Buy Now", callback_data=f"buy_{key_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_view")
            )
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            reply_markup=markup, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"View error: {e}")
        bot.answer_callback_query(call.id, "❌ Error!", show_alert=True)

# -----------------------
# PROCESS PURCHASE
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_") or call.data.startswith("buyprice_"))
def process_purchase(call):
    user_id = call.from_user.id
    
    try:
        if call.data.startswith("buyprice_"):
            parts = call.data.split('_')
            key_id = parts[1]
            price = float(parts[2])
        else:
            key_id = call.data.replace("buy_", "")
            key = keys_col.find_one({"_id": ObjectId(key_id)})
            if not key:
                bot.answer_callback_query(call.id, "❌ Key not found!", show_alert=True)
                return
            price = key.get('price', 0)
        
        key = keys_col.find_one({"_id": ObjectId(key_id), "status": "available"})
        if not key:
            bot.answer_callback_query(call.id, "❌ Key sold out!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
        balance = get_balance(user_id)
        
        if balance < price:
            bot.answer_callback_query(call.id, f"❌ Need {format_currency(price)}!", show_alert=True)
            return
        
        # Process purchase
        deduct_balance(user_id, price)
        
        keys_col.update_one(
            {"_id": ObjectId(key_id)},
            {"$set": {
                "status": "sold",
                "sold_to": user_id,
                "sold_at": datetime.utcnow(),
                "sold_price": price
            }}
        )
        
        users_col.update_one(
            {"user_id": user_id},
            {"$inc": {"total_purchases": 1, "total_spent": price}}
        )
        
        orders_col.insert_one({
            "user_id": user_id,
            "key_id": key_id,
            "key": key['key'],
            "category": key['category'],
            "price": price,
            "details": key.get('details', ''),
            "apk_file_id": key.get('apk_file_id'),
            "apk_file_name": key.get('apk_file_name'),
            "purchased_at": datetime.utcnow()
        })
        
        cat_data = KEY_CATEGORIES.get(key['category'], {})
        
        text = f"✅ **Purchase Successful!**\n\n"
        text += f"{cat_data.get('emoji', '🔑')} **{cat_data.get('name', 'Key')}**\n"
        text += f"💰 Paid: {format_currency(price)}\n"
        text += f"💳 Balance: {format_currency(get_balance(user_id))}\n\n"
        
        if key.get('details'):
            text += f"📝 **Details:**\n"
            for line in key['details'].split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    text += f"**{parts[0]}:**{parts[1]}\n"
                else:
                    text += f"**{line}**\n"
            text += "\n"
        
        text += f"🔑 **Key:**\n`{key['key']}`"
        
        # Pehle key details bhejo
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            parse_mode="Markdown")
        
        # Agar APK file hai toh usse alag se bhejo
        if key.get('apk_file_id'):
            apk_caption = f"📁 **APK File:**\n{key.get('apk_file_name', 'Game File')}"
            bot.send_document(
                user_id,
                key['apk_file_id'],
                caption=apk_caption,
                parse_mode="Markdown"
            )
        
        bot.answer_callback_query(call.id, "✅ Purchased!")
        
    except Exception as e:
        logger.error(f"Purchase error: {e}")
        bot.answer_callback_query(call.id, "❌ Failed!", show_alert=True)

# -----------------------
# CANCEL VIEW
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data == "cancel_view")
def cancel_view(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Cancelled")

# -----------------------
# BALANCE
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "💰 Balance")
@bot.message_handler(commands=['balance'])
@set_user_context
def show_balance(msg):
    user_id = msg.from_user.id
    balance = get_balance(user_id)
    user = users_col.find_one({"user_id": user_id}) or {}
    
    text = f"💰 **Your Wallet**\n\n"
    text += f"Balance: {format_currency(balance)}\n"
    text += f"Purchases: {user.get('total_purchases', 0)}\n"
    text += f"Total Spent: {format_currency(user.get('total_spent', 0))}"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# -----------------------
# RECHARGE
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "💳 Recharge")
@bot.message_handler(commands=['recharge'])
@set_user_context
def recharge(msg):
    user_id = msg.from_user.id
    bot.send_message(user_id, "💳 Enter amount (min ₹1):", reply_markup=get_back_keyboard())
    user_states[user_id] = "waiting_recharge"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "waiting_recharge")
@set_user_context
def process_recharge(msg):
    user_id = msg.from_user.id
    
    try:
        amount = float(msg.text.strip())
        if amount < 1:
            bot.send_message(user_id, "❌ Minimum ₹1! Try again:", reply_markup=get_back_keyboard())
            return
        
        upi_payment_states[user_id] = {"amount": amount}
        user_states.pop(user_id, None)
        
        qr_image = generate_dynamic_qr(amount)
        
        if qr_image:
            caption = f"""💳 **UPI Payment**

Amount: {format_currency(amount)}
UPI ID: `anurag99999@fam`

📌 Scan QR for {format_currency(amount)}
After payment, click I HAVE PAID"""
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💰 I HAVE PAID", callback_data="upi_paid"))
            
            bot.send_photo(user_id, qr_image, caption=caption, 
                          parse_mode="Markdown", reply_markup=markup)
        else:
            caption = f"""💳 **UPI Payment**

Amount: {format_currency(amount)}
UPI ID: `anurag99999@fam`

📌 Send exact amount and click I HAVE PAID"""
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💰 I HAVE PAID", callback_data="upi_paid"))
            
            bot.send_photo(user_id, "https://files.catbox.moe/a310jr.jpg", caption=caption, 
                          parse_mode="Markdown", reply_markup=markup)
    except:
        bot.send_message(user_id, "❌ Invalid amount!", reply_markup=get_back_keyboard())

# -----------------------
# UPI PAYMENT HANDLERS
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data == "upi_paid")
def upi_paid_callback(call):
    user_id = call.from_user.id
    amount = upi_payment_states.get(user_id, {}).get("amount", 0)
    
    if amount <= 0:
        bot.answer_callback_query(call.id, "❌ Error!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id, "📝 Send UTR")
    upi_payment_states[user_id] = {"amount": amount, "step": "utr"}
    bot.send_message(user_id, "📝 Enter 12-digit UTR number:")

@bot.message_handler(func=lambda msg: upi_payment_states.get(msg.from_user.id, {}).get("step") == "utr")
@set_user_context
def handle_utr(msg):
    user_id = msg.from_user.id
    utr = msg.text.strip()
    
    if not utr.isdigit() or len(utr) != 12:
        bot.send_message(user_id, "❌ Invalid UTR! Enter 12 digits:")
        return
    
    upi_payment_states[user_id]["utr"] = utr
    upi_payment_states[user_id]["step"] = "screenshot"
    bot.send_message(user_id, "📸 Send payment screenshot:")

@bot.message_handler(content_types=['photo'], func=lambda msg: upi_payment_states.get(msg.from_user.id, {}).get("step") == "screenshot")
@set_user_context
def handle_screenshot(msg):
    user_id = msg.from_user.id
    data = upi_payment_states[user_id]
    
    recharge_id = recharges_col.insert_one({
        "user_id": user_id,
        "amount": data['amount'],
        "utr": data['utr'],
        "screenshot": msg.photo[-1].file_id,
        "status": "pending",
        "created_at": datetime.utcnow()
    }).inserted_id
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"app_req_{recharge_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"rej_req_{recharge_id}")
    )
    
    for admin_id in ADMINS:
        try:
            bot.send_photo(
                admin_id,
                msg.photo[-1].file_id,
                caption=f"💰 New Recharge\nUser: {user_id}\nAmount: {format_currency(data['amount'])}\nUTR: {data['utr']}",
                reply_markup=markup
            )
        except:
            pass
    
    bot.send_message(user_id, "✅ Payment submitted! Admin will approve soon.", reply_markup=get_main_keyboard())
    upi_payment_states.pop(user_id, None)

# -----------------------
# REDEEM COUPON
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🎁 Redeem Coupon")
@bot.message_handler(commands=['coupon'])
@set_user_context
def redeem(msg):
    user_id = msg.from_user.id
    bot.send_message(user_id, "🎟 Enter coupon code:", reply_markup=get_back_keyboard())
    user_states[user_id] = "waiting_coupon"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "waiting_coupon")
@set_user_context
def process_coupon(msg):
    user_id = msg.from_user.id
    code = msg.text.strip().upper()
    user_states.pop(user_id, None)
    
    coupon = coupons_col.find_one({"code": code, "status": "active"})
    
    if not coupon:
        bot.send_message(user_id, "❌ Invalid coupon!", reply_markup=get_main_keyboard())
        return
    
    if user_id in coupon.get("used_by", []):
        bot.send_message(user_id, "❌ Already used!", reply_markup=get_main_keyboard())
        return
    
    if len(coupon.get("used_by", [])) >= coupon.get("max_uses", 1):
        bot.send_message(user_id, "❌ Coupon expired!", reply_markup=get_main_keyboard())
        return
    
    amount = coupon.get("amount", 0)
    add_balance(user_id, amount)
    
    coupons_col.update_one(
        {"code": code},
        {"$push": {"used_by": user_id}, "$inc": {"used_count": 1}}
    )
    
    bot.send_message(user_id, f"✅ Added {format_currency(amount)}!", reply_markup=get_main_keyboard())

# -----------------------
# SUPPORT & ABOUT
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📞 Support")
@bot.message_handler(commands=['support'])
@set_user_context
def support(msg):
    bot.send_message(msg.from_user.id, "📞 Contact: @UROGGY", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ About")
@bot.message_handler(commands=['about'])
@set_user_context
def about(msg):
    total = keys_col.count_documents({"status": "available"})
    sold = keys_col.count_documents({"status": "sold"})
    users = users_col.count_documents({})
    
    text = f"ℹ️ **About Bot**\n\n"
    text += f"📦 Available Keys: {total}\n"
    text += f"✅ Sold Keys: {sold}\n"
    text += f"👥 Total Users: {users}\n"
    text += f"📁 Loaders: {len(KEY_CATEGORIES)}"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# -----------------------
# ADMIN PANEL
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Panel")
@bot.message_handler(commands=['admin'])
@set_user_context
def admin_panel(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    
    total = keys_col.count_documents({})
    available = keys_col.count_documents({"status": "available"})
    sold = keys_col.count_documents({"status": "sold"})
    users = users_col.count_documents({})
    pending = recharges_col.count_documents({"status": "pending"})
    
    text = f"👑 **Admin Panel**\n\n"
    text += f"📊 **Stats:**\n"
    text += f"• Keys: {total} (Avail: {available}, Sold: {sold})\n"
    text += f"• Users: {users}\n"
    text += f"• Pending: {pending}\n\n"
    text += "📁 **Loaders:**\n"
    
    for key, data in KEY_CATEGORIES.items():
        count = keys_col.count_documents({"category": key})
        text += f"• {data['emoji']} {data['name']}: {count} keys\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

# -----------------------
# ADMIN MANAGEMENT
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Management" and is_admin(msg.from_user.id))
@set_user_context
def admin_management(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.send_message(msg.from_user.id, "❌ Only main admin can manage admins!")
        return
    
    bot.send_message(
        msg.from_user.id,
        "👑 **Admin Management**\n\nUse buttons below to manage admins.",
        parse_mode="Markdown",
        reply_markup=get_admin_management_keyboard()
    )

# -----------------------
# ADD ADMIN
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Admin" and is_admin(msg.from_user.id))
@set_user_context
def add_admin_start(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.send_message(msg.from_user.id, "❌ Only main admin can add admins!")
        return
    
    bot.send_message(msg.from_user.id, "➕ Enter Telegram User ID of new admin:")
    admin_add_admin_state[msg.from_user.id] = {"action": "add"}

@bot.message_handler(commands=['addadmin'])
@set_user_context
def add_admin_command(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.reply_to(msg, "❌ Only main admin can add admins!")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            bot.reply_to(msg, "❌ Usage: /addadmin [user_id]")
            return
        
        new_admin_id = int(parts[1])
        
        if new_admin_id in ADMINS:
            bot.reply_to(msg, "❌ Already an admin!")
            return
        
        admins_col.insert_one({
            "admin_id": new_admin_id,
            "added_by": msg.from_user.id,
            "added_at": datetime.utcnow()
        })
        
        load_admins()
        
        try:
            bot.send_message(new_admin_id, "👑 You have been promoted to Admin!")
        except:
            pass
        
        bot.reply_to(msg, f"✅ Admin {new_admin_id} added!")
        log_admin_action(msg.from_user.id, "ADD_ADMIN", {"new_admin": new_admin_id})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_admin_state and is_admin(msg.from_user.id))
@set_user_context
def process_add_admin(msg):
    try:
        new_admin_id = int(msg.text.strip())
        
        if new_admin_id in ADMINS:
            bot.send_message(msg.from_user.id, "❌ Already an admin!")
        else:
            admins_col.insert_one({
                "admin_id": new_admin_id,
                "added_by": msg.from_user.id,
                "added_at": datetime.utcnow()
            })
            
            load_admins()
            
            try:
                bot.send_message(new_admin_id, "👑 You have been promoted to Admin!")
            except:
                pass
            
            bot.send_message(msg.from_user.id, f"✅ Admin {new_admin_id} added!")
            log_admin_action(msg.from_user.id, "ADD_ADMIN", {"new_admin": new_admin_id})
        
    except ValueError:
        bot.send_message(msg.from_user.id, "❌ Invalid ID!")
    
    admin_add_admin_state.pop(msg.from_user.id, None)

# -----------------------
# REMOVE ADMIN
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🗑 Remove Admin" and is_admin(msg.from_user.id))
@set_user_context
def remove_admin_start(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.send_message(msg.from_user.id, "❌ Only main admin can remove admins!")
        return
    
    other_admins = [a for a in ADMINS if a != ADMIN_ID]
    
    if not other_admins:
        bot.send_message(msg.from_user.id, "📭 No other admins to remove!")
        return
    
    text = "🗑 **Select Admin to Remove:**\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    
    for admin_id in other_admins:
        user = users_col.find_one({"user_id": admin_id}) or {}
        name = user.get('name', 'Unknown')
        markup.add(InlineKeyboardButton(
            f"{name} (ID: {admin_id})",
            callback_data=f"removeadmin_{admin_id}"
        ))
    
    bot.send_message(msg.from_user.id, text, reply_markup=markup)

@bot.message_handler(commands=['removeadmin'])
@set_user_context
def remove_admin_command(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.reply_to(msg, "❌ Only main admin can remove admins!")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            bot.reply_to(msg, "❌ Usage: /removeadmin [user_id]")
            return
        
        admin_id = int(parts[1])
        
        if admin_id == ADMIN_ID:
            bot.reply_to(msg, "❌ Cannot remove main admin!")
            return
        
        if admin_id not in ADMINS:
            bot.reply_to(msg, "❌ Not an admin!")
            return
        
        admins_col.delete_one({"admin_id": admin_id})
        load_admins()
        
        try:
            bot.send_message(admin_id, "⚠️ Your admin privileges have been removed!")
        except:
            pass
        
        bot.reply_to(msg, f"✅ Admin {admin_id} removed!")
        log_admin_action(msg.from_user.id, "REMOVE_ADMIN", {"removed_admin": admin_id})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("removeadmin_"))
def remove_admin_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    admin_id = int(call.data.replace("removeadmin_", ""))
    
    try:
        admins_col.delete_one({"admin_id": admin_id})
        load_admins()
        
        try:
            bot.send_message(admin_id, "⚠️ Your admin privileges have been removed!")
        except:
            pass
        
        bot.answer_callback_query(call.id, f"✅ Admin removed!")
        bot.edit_message_text(f"✅ Admin {admin_id} removed!", call.message.chat.id, call.message.message_id)
        log_admin_action(call.from_user.id, "REMOVE_ADMIN", {"removed_admin": admin_id})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error!", show_alert=True)

# -----------------------
# LIST ADMINS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📋 List Admins" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['admins'])
@set_user_context
def list_admins(msg):
    text = "👑 **Admin List**\n\n"
    
    for i, admin_id in enumerate(ADMINS, 1):
        user = users_col.find_one({"user_id": admin_id}) or {}
        name = user.get('name', 'Unknown')
        if admin_id == ADMIN_ID:
            text += f"{i}. **{name}** (ID: `{admin_id}`) - **Main**\n"
        else:
            text += f"{i}. {name} (ID: `{admin_id}`)\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# STATS
# -----------------------
@bot.message_handler(commands=['stats'])
@set_user_context
def stats_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    total = keys_col.count_documents({})
    available = keys_col.count_documents({"status": "available"})
    sold = keys_col.count_documents({"status": "sold"})
    users = users_col.count_documents({})
    pending = recharges_col.count_documents({"status": "pending"})
    
    text = f"📊 **Bot Statistics**\n\n"
    text += f"• Total Keys: {total}\n"
    text += f"• Available: {available}\n"
    text += f"• Sold: {sold}\n"
    text += f"• Users: {users}\n"
    text += f"• Pending Recharges: {pending}\n"
    
    bot.reply_to(msg, text, parse_mode="Markdown")

# -----------------------
# LOADER SETTINGS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "⚙️ Loader Settings" and is_admin(msg.from_user.id))
@set_user_context
def loader_settings(msg):
    bot.send_message(
        msg.from_user.id,
        "⚙️ **Loader Settings**\n\nManage loaders here.",
        parse_mode="Markdown",
        reply_markup=get_loader_settings_keyboard()
    )

# -----------------------
# ADD LOADER
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Loader" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['addloader'])
@set_user_context
def add_loader_start(msg):
    user_id = msg.from_user.id
    
    if msg.text.startswith('/addloader'):
        try:
            parts = msg.text.split(maxsplit=5)[1].split('|')
            if len(parts) < 4:
                bot.reply_to(msg, "❌ Usage: /addloader key|name|price|emoji|description")
                return
            
            key = parts[0].strip().lower()
            name = parts[1].strip()
            price = float(parts[2].strip())
            emoji = parts[3].strip()
            desc = parts[4].strip() if len(parts) > 4 else ""
            
            if key in KEY_CATEGORIES:
                bot.reply_to(msg, "❌ Key already exists!")
                return
            
            categories_col.insert_one({
                "key": key,
                "name": name,
                "price": price,
                "emoji": emoji,
                "description": desc,
                "buttons": [],
                "status": "active"
            })
            
            refresh_categories()
            bot.reply_to(msg, f"✅ Loader {emoji} {name} added!")
            log_admin_action(user_id, "ADD_LOADER", {"key": key, "name": name})
            
        except Exception as e:
            bot.reply_to(msg, f"❌ Error: {str(e)}")
        return
    
    text = "➕ **Add New Loader**\n\n"
    text += "Send: `key|name|price|emoji|description`\n\n"
    text += "Example:\n"
    text += "`brutal|Brutal Pass|49|🎮|Brutal keys`"
    
    bot.send_message(user_id, text, parse_mode="Markdown")
    add_loader_state[user_id] = {"step": "waiting_details"}

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_state and is_admin(msg.from_user.id))
@set_user_context
def process_add_loader(msg):
    user_id = msg.from_user.id
    
    try:
        parts = msg.text.strip().split('|')
        if len(parts) < 4:
            bot.send_message(user_id, "❌ Invalid format!")
            return
        
        key = parts[0].strip().lower()
        name = parts[1].strip()
        price = float(parts[2].strip())
        emoji = parts[3].strip()
        desc = parts[4].strip() if len(parts) > 4 else ""
        
        if key in KEY_CATEGORIES:
            bot.send_message(user_id, "❌ Key already exists!")
            return
        
        categories_col.insert_one({
            "key": key,
            "name": name,
            "price": price,
            "emoji": emoji,
            "description": desc,
            "buttons": [],
            "status": "active"
        })
        
        refresh_categories()
        
        bot.send_message(
            user_id,
            f"✅ **Loader Added!**\n\n{emoji} **{name}**\nKey: `{key}`\nPrice: {format_currency(price)}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "ADD_LOADER", {"key": key, "name": name})
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid price!")
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")
    
    add_loader_state.pop(user_id, None)

# -----------------------
# ADD PRICE BUTTON
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🔘 Add Price Button" and is_admin(msg.from_user.id))
@set_user_context
def add_price_button_start(msg):
    user_id = msg.from_user.id
    
    text = "🔘 **Add Price Button**\n\nSelect loader:\n\n"
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} (Key: `{key}`)\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_loader_edit_keyboard())
    add_loader_button_state[user_id] = {"step": "select"}

@bot.message_handler(commands=['addpricebtn'])
@set_user_context
def add_price_button_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 4:
            bot.reply_to(msg, "❌ Usage: /addpricebtn [key] [name] [price]")
            return
        
        key = parts[1].lower()
        btn_name = parts[2].strip()
        price = float(parts[3])
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Key '{key}' not found!")
            return
        
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        
        for btn in buttons:
            if btn['name'].lower() == btn_name.lower():
                bot.reply_to(msg, "❌ Button already exists!")
                return
        
        buttons.append({"name": btn_name, "price": price})
        categories_col.update_one({"key": key}, {"$set": {"buttons": buttons}})
        refresh_categories()
        
        bot.reply_to(msg, f"✅ Button '{btn_name}' ({format_currency(price)}) added!")
        log_admin_action(msg.from_user.id, "ADD_PRICE_BUTTON", {"key": key, "button": btn_name, "price": price})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_button_state and msg.text.startswith("📌") and is_admin(msg.from_user.id))
@set_user_context
def handle_button_loader_selection(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    selected_key = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == selected_name:
            selected_key = key
            break
    
    if not selected_key:
        bot.send_message(user_id, "❌ Loader not found!")
        return
    
    add_loader_button_state[user_id]["key"] = selected_key
    add_loader_button_state[user_id]["step"] = "waiting_name"
    bot.send_message(user_id, "🔘 Enter button name (e.g., '6 Months'):")

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_button_state and 
                    add_loader_button_state[msg.from_user.id].get("step") == "waiting_name" and is_admin(msg.from_user.id))
@set_user_context
def handle_button_name(msg):
    user_id = msg.from_user.id
    btn_name = msg.text.strip()
    
    if not btn_name:
        bot.send_message(user_id, "❌ Name cannot be empty!")
        return
    
    add_loader_button_state[user_id]["btn_name"] = btn_name
    add_loader_button_state[user_id]["step"] = "waiting_price"
    bot.send_message(user_id, "💰 Enter price:")

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_button_state and 
                    add_loader_button_state[msg.from_user.id].get("step") == "waiting_price" and is_admin(msg.from_user.id))
@set_user_context
def handle_button_price(msg):
    user_id = msg.from_user.id
    
    try:
        price = float(msg.text.strip())
        key = add_loader_button_state[user_id]["key"]
        btn_name = add_loader_button_state[user_id]["btn_name"]
        
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        
        for btn in buttons:
            if btn['name'].lower() == btn_name.lower():
                bot.send_message(user_id, "❌ Button already exists!")
                add_loader_button_state.pop(user_id, None)
                return
        
        buttons.append({"name": btn_name, "price": price})
        categories_col.update_one({"key": key}, {"$set": {"buttons": buttons}})
        refresh_categories()
        
        bot.send_message(user_id, f"✅ Button '{btn_name}' ({format_currency(price)}) added!")
        log_admin_action(user_id, "ADD_PRICE_BUTTON", {"key": key, "button": btn_name, "price": price})
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid price!")
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")
    
    add_loader_button_state.pop(user_id, None)

# -----------------------
# REMOVE PRICE BUTTON
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🗑 Remove Price Button" and is_admin(msg.from_user.id))
@set_user_context
def remove_price_button_start(msg):
    user_id = msg.from_user.id
    
    text = "🗑 **Remove Price Button**\n\nSelect loader:\n\n"
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} (Key: `{key}`)\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_loader_edit_keyboard())
    dynamic_price_state[user_id] = {"action": "remove", "step": "select"}

@bot.message_handler(commands=['removepricebtn'])
@set_user_context
def remove_price_button_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split(maxsplit=2)
        if len(parts) != 3:
            bot.reply_to(msg, "❌ Usage: /removepricebtn [key] [button_name]")
            return
        
        key = parts[1].lower()
        btn_name = parts[2].strip()
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Key '{key}' not found!")
            return
        
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        new_buttons = [btn for btn in buttons if btn['name'].lower() != btn_name.lower()]
        
        if len(new_buttons) == len(buttons):
            bot.reply_to(msg, f"❌ Button '{btn_name}' not found!")
            return
        
        categories_col.update_one({"key": key}, {"$set": {"buttons": new_buttons}})
        refresh_categories()
        
        bot.reply_to(msg, f"✅ Button '{btn_name}' removed!")
        log_admin_action(msg.from_user.id, "REMOVE_PRICE_BUTTON", {"key": key, "button": btn_name})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in dynamic_price_state and msg.text.startswith("📌") and is_admin(msg.from_user.id))
@set_user_context
def handle_remove_button_loader(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    selected_key = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == selected_name:
            selected_key = key
            break
    
    if not selected_key:
        bot.send_message(user_id, "❌ Loader not found!")
        return
    
    loader = categories_col.find_one({"key": selected_key})
    buttons = loader.get('buttons', [])
    
    if not buttons:
        bot.send_message(user_id, "❌ No buttons found!")
        dynamic_price_state.pop(user_id, None)
        return
    
    text = f"🗑 **Select button to remove:**\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    
    for btn in buttons:
        markup.add(InlineKeyboardButton(
            f"{btn['name']} - {format_currency(btn['price'])}",
            callback_data=f"rmbtn_{selected_key}_{btn['name']}"
        ))
    
    bot.send_message(user_id, text, reply_markup=markup)
    dynamic_price_state.pop(user_id, None)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rmbtn_"))
def remove_button_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    parts = call.data.split('_', 2)
    key = parts[1]
    btn_name = parts[2]
    
    try:
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        new_buttons = [btn for btn in buttons if btn['name'] != btn_name]
        
        categories_col.update_one({"key": key}, {"$set": {"buttons": new_buttons}})
        refresh_categories()
        
        bot.answer_callback_query(call.id, "✅ Removed!")
        bot.edit_message_text(f"✅ Button '{btn_name}' removed!", call.message.chat.id, call.message.message_id)
        log_admin_action(call.from_user.id, "REMOVE_PRICE_BUTTON", {"key": key, "button": btn_name})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error!", show_alert=True)

# -----------------------
# LIST PRICE BUTTONS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📋 List Price Buttons" and is_admin(msg.from_user.id))
@set_user_context
def list_price_buttons(msg):
    text = "📋 **Price Buttons**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['emoji']} **{data['name']}**\n"
        if data.get('buttons'):
            for btn in data['buttons']:
                text += f"  • {btn['name']}: {format_currency(btn['price'])}\n"
        else:
            text += "  No buttons\n"
        text += "\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# EDIT LOADER NAME
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "✏️ Edit Loader Name" and is_admin(msg.from_user.id))
@set_user_context
def edit_loader_name_start(msg):
    user_id = msg.from_user.id
    
    text = "✏️ **Edit Loader Name**\n\nSelect loader:\n\n"
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} (Key: `{key}`)\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_loader_edit_keyboard())
    edit_loader_state[user_id] = {"action": "name", "step": "select"}

@bot.message_handler(commands=['editname'])
@set_user_context
def edit_name_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /editname [key] [new_name]")
            return
        
        key = parts[1].lower()
        new_name = parts[2].strip()
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Key '{key}' not found!")
            return
        
        old_name = KEY_CATEGORIES[key]['name']
        categories_col.update_one({"key": key}, {"$set": {"name": new_name}})
        refresh_categories()
        
        bot.reply_to(msg, f"✅ Name updated!\n{old_name} → {new_name}")
        log_admin_action(msg.from_user.id, "EDIT_LOADER_NAME", {"key": key, "old": old_name, "new": new_name})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and msg.text.startswith("📌") and is_admin(msg.from_user.id))
@set_user_context
def handle_loader_name_selection(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    selected_key = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == selected_name:
            selected_key = key
            break
    
    if not selected_key:
        bot.send_message(user_id, "❌ Loader not found!")
        return
    
    edit_loader_state[user_id]["key"] = selected_key
    edit_loader_state[user_id]["step"] = "waiting_name"
    bot.send_message(user_id, f"📝 Enter new name for {KEY_CATEGORIES[selected_key]['name']}:")

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and 
                    edit_loader_state[msg.from_user.id].get("step") == "waiting_name" and is_admin(msg.from_user.id))
@set_user_context
def handle_new_name(msg):
    user_id = msg.from_user.id
    new_name = msg.text.strip()
    key = edit_loader_state[user_id]["key"]
    
    if not new_name:
        bot.send_message(user_id, "❌ Name cannot be empty!")
        return
    
    old_name = KEY_CATEGORIES[key]['name']
    categories_col.update_one({"key": key}, {"$set": {"name": new_name}})
    refresh_categories()
    
    bot.send_message(user_id, f"✅ Name updated!\n{old_name} → {new_name}")
    log_admin_action(user_id, "EDIT_LOADER_NAME", {"key": key, "old": old_name, "new": new_name})
    edit_loader_state.pop(user_id, None)

# -----------------------
# EDIT LOADER PRICE
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "💰 Edit Loader Price" and is_admin(msg.from_user.id))
@set_user_context
def edit_loader_price_start(msg):
    user_id = msg.from_user.id
    
    text = "💰 **Edit Loader Price**\n\nSelect loader:\n\n"
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} - {format_currency(data['price'])} (Key: `{key}`)\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_loader_edit_keyboard())
    edit_loader_state[user_id] = {"action": "price", "step": "select"}

@bot.message_handler(commands=['editprice'])
@set_user_context
def edit_price_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 3:
            bot.reply_to(msg, "❌ Usage: /editprice [key] [new_price]")
            return
        
        key = parts[1].lower()
        new_price = float(parts[2])
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Key '{key}' not found!")
            return
        
        old_price = KEY_CATEGORIES[key]['price']
        categories_col.update_one({"key": key}, {"$set": {"price": new_price}})
        keys_col.update_many({"category": key, "status": "available"}, {"$set": {"price": new_price}})
        refresh_categories()
        
        bot.reply_to(msg, f"✅ Price updated!\n{format_currency(old_price)} → {format_currency(new_price)}")
        log_admin_action(msg.from_user.id, "EDIT_LOADER_PRICE", {"key": key, "old": old_price, "new": new_price})
        
    except ValueError:
        bot.reply_to(msg, "❌ Invalid price!")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and msg.text.startswith("📌") and is_admin(msg.from_user.id))
@set_user_context
def handle_price_selection(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    selected_key = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == selected_name:
            selected_key = key
            break
    
    if not selected_key:
        bot.send_message(user_id, "❌ Loader not found!")
        return
    
    edit_loader_state[user_id]["key"] = selected_key
    edit_loader_state[user_id]["step"] = "waiting_price"
    current = format_currency(KEY_CATEGORIES[selected_key]['price'])
    bot.send_message(user_id, f"💰 Enter new price (Current: {current}):")

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and 
                    edit_loader_state[msg.from_user.id].get("step") == "waiting_price" and is_admin(msg.from_user.id))
@set_user_context
def handle_new_price(msg):
    user_id = msg.from_user.id
    
    try:
        new_price = float(msg.text.strip())
        key = edit_loader_state[user_id]["key"]
        
        old_price = KEY_CATEGORIES[key]['price']
        categories_col.update_one({"key": key}, {"$set": {"price": new_price}})
        keys_col.update_many({"category": key, "status": "available"}, {"$set": {"price": new_price}})
        refresh_categories()
        
        bot.send_message(user_id, f"✅ Price updated!\n{format_currency(old_price)} → {format_currency(new_price)}")
        log_admin_action(user_id, "EDIT_LOADER_PRICE", {"key": key, "old": old_price, "new": new_price})
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid price!")
    
    edit_loader_state.pop(user_id, None)

# -----------------------
# ADD KEY WITH APK
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Key" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['addkey'])
@set_user_context
def add_key_start(msg):
    user_id = msg.from_user.id
    
    if msg.text.startswith('/addkey'):
        bot.reply_to(msg, "Please use the Add Key button in Admin Panel.")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(f"{data['emoji']} {data['name']}", callback_data=f"addcat_{key}"))
    
    bot.send_message(user_id, "📝 **Select Loader:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("addcat_"))
def add_key_category(call):
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    category = call.data.replace("addcat_", "")
    
    admin_add_key_state[user_id] = {
        "category": category,
        "step": "waiting_key",
        "message_id": call.message.message_id,
        "chat_id": call.message.chat.id
    }
    
    bot.edit_message_text(
        f"📝 **Add Key for {KEY_CATEGORIES[category]['name']}**\n\n"
        f"**Step 1:** Send the KEY CODE\n\n"
        f"Example: `BRUTAL123456`",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_key" and is_admin(msg.from_user.id))
@set_user_context
def handle_key_code(msg):
    user_id = msg.from_user.id
    key_code = msg.text.strip()
    
    if not key_code:
        bot.send_message(user_id, "❌ Key code cannot be empty!")
        return
    
    admin_add_key_state[user_id]["key_code"] = key_code
    admin_add_key_state[user_id]["step"] = "waiting_details"
    
    try:
        bot.delete_message(admin_add_key_state[user_id]["chat_id"], admin_add_key_state[user_id]["message_id"])
    except:
        pass
    
    bot.send_message(
        user_id,
        f"✅ Key code saved: `{key_code}`\n\n"
        f"**Step 2:** Send DETAILS\n\n"
        f"Format:\n"
        f"`Email: example@gmail.com`\n"
        f"`Password: pass123`\n"
        f"`Server: Asia`"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_details" and is_admin(msg.from_user.id))
@set_user_context
def handle_details(msg):
    user_id = msg.from_user.id
    details = msg.text.strip()
    
    if not details:
        bot.send_message(user_id, "❌ Details cannot be empty!")
        return
    
    admin_add_key_state[user_id]["details"] = details
    admin_add_key_state[user_id]["step"] = "waiting_apk"
    
    bot.send_message(
        user_id,
        f"✅ Details saved!\n\n"
        f"**Step 3:** Send the APK file\n"
        f"(Send as file/document)"
    )

@bot.message_handler(content_types=['document'], func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_apk" and is_admin(msg.from_user.id))
@set_user_context
def handle_apk_file(msg):
    user_id = msg.from_user.id
    
    if msg.document:
        file_id = msg.document.file_id
        file_name = msg.document.file_name
        
        admin_add_key_state[user_id]["apk_file_id"] = file_id
        admin_add_key_state[user_id]["apk_file_name"] = file_name
        
        category = admin_add_key_state[user_id]['category']
        key_code = admin_add_key_state[user_id]['key_code']
        details = admin_add_key_state[user_id]['details']
        apk_file_id = admin_add_key_state[user_id]['apk_file_id']
        apk_file_name = admin_add_key_state[user_id]['apk_file_name']
        
        keys_col.insert_one({
            "key": key_code,
            "category": category,
            "price": KEY_CATEGORIES[category]['price'],
            "details": details,
            "apk_file_id": apk_file_id,
            "apk_file_name": apk_file_name,
            "status": "available",
            "added_by": user_id,
            "added_at": datetime.utcnow()
        })
        
        count = keys_col.count_documents({"category": category, "status": "available"})
        
        bot.send_message(
            user_id,
            f"✅ **Key Added with APK!**\n\n"
            f"📁 {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
            f"💰 Price: {format_currency(KEY_CATEGORIES[category]['price'])}\n"
            f"📊 Available: {count}\n"
            f"📁 APK: {apk_file_name}\n\n"
            f"🔑 Key: `{key_code}`\n"
            f"📝 Details:\n{details}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "ADD_KEY_WITH_APK", {"category": category})
        admin_add_key_state.pop(user_id, None)
    else:
        bot.send_message(user_id, "❌ Please send as document/file!")

# -----------------------
# KEY LIST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📋 Key List" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['keys'])
@set_user_context
def key_list(msg):
    if msg.text.startswith('/keys'):
        text = "📋 **All Keys (Last 20)**\n\n"
        all_keys = list(keys_col.find().sort("added_at", -1).limit(20))
        
        if not all_keys:
            bot.reply_to(msg, "📭 No keys found!")
            return
        
        for key in all_keys:
            cat_name = KEY_CATEGORIES.get(key['category'], {}).get('name', 'Unknown')[:10]
            status = "✅" if key['status'] == "available" else "💰"
            has_apk = "📁" if key.get('apk_file_id') else ""
            text += f"{status}{has_apk} {cat_name}: `{key['key'][:15]}...`\n"
        
        bot.reply_to(msg, text, parse_mode="Markdown")
        return
    
    text = "📋 **Key Inventory**\n\n"
    for key, data in KEY_CATEGORIES.items():
        avail = keys_col.count_documents({"category": key, "status": "available"})
        sold = keys_col.count_documents({"category": key, "status": "sold"})
        text += f"{data['emoji']} {data['name']}: {avail} avail, {sold} sold\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# MANAGE CATEGORIES
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📁 Manage Categories" and is_admin(msg.from_user.id))
@set_user_context
def manage_categories(msg):
    text = "📁 **Loader Management**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"Key: `{key}` | Price: {format_currency(data['price'])}\n\n"
    
    text += "Commands:\n"
    text += "/addcat key|name|price|emoji|desc - Add loader\n"
    text += "/editcat key|field|value - Edit loader\n"
    text += "/delcat key - Delete loader"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['addcat'])
@set_user_context
def add_category(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split(maxsplit=1)[1].split('|')
        if len(parts) < 4:
            raise ValueError("Invalid format")
        
        key = parts[0].strip().lower()
        name = parts[1].strip()
        price = float(parts[2].strip())
        emoji = parts[3].strip()
        desc = parts[4].strip() if len(parts) > 4 else ""
        
        if key in KEY_CATEGORIES:
            bot.reply_to(msg, "❌ Loader already exists!")
            return
        
        categories_col.insert_one({
            "key": key,
            "name": name,
            "price": price,
            "emoji": emoji,
            "description": desc,
            "buttons": [],
            "status": "active"
        })
        
        refresh_categories()
        bot.reply_to(msg, f"✅ Loader {emoji} {name} added!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['delcat'])
@set_user_context
def delete_category(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        key = msg.text.split()[1].lower()
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, "❌ Loader not found!")
            return
        
        keys_col.delete_many({"category": key})
        categories_col.delete_one({"key": key})
        refresh_categories()
        
        bot.reply_to(msg, f"✅ Loader deleted!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# REMOVE KEY
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🗑 Remove Key" and is_admin(msg.from_user.id))
@set_user_context
def remove_key_start(msg):
    user_id = msg.from_user.id
    
    all_keys = list(keys_col.find({"status": "available"}).sort("added_at", -1).limit(10))
    
    if not all_keys:
        bot.send_message(user_id, "📭 No keys available!")
        return
    
    text = "🗑 **Select Key to Remove**\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    
    for i, key in enumerate(all_keys, 1):
        cat_name = KEY_CATEGORIES.get(key['category'], {}).get('name', 'Unknown')[:10]
        has_apk = "📁" if key.get('apk_file_id') else ""
        markup.add(InlineKeyboardButton(
            f"{i}. {cat_name} {has_apk} - {key['key'][:15]}...",
            callback_data=f"rem_{key['_id']}"
        ))
    
    bot.send_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rem_"))
def confirm_remove(call):
    key_id = call.data.replace("rem_", "")
    
    try:
        key = keys_col.find_one({"_id": ObjectId(key_id)})
        if not key:
            bot.answer_callback_query(call.id, "❌ Not found!", show_alert=True)
            return
        
        cat_name = KEY_CATEGORIES.get(key['category'], {}).get('name', 'Unknown')
        
        text = f"🗑 **Remove Key?**\n\n"
        text += f"Loader: {cat_name}\n"
        text += f"Key: `{key['key']}`\n"
        if key.get('apk_file_name'):
            text += f"APK: {key['apk_file_name']}\n\n"
        text += "Are you sure?"
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Yes", callback_data=f"remove_yes_{key_id}"),
            InlineKeyboardButton("❌ No", callback_data="remove_no")
        )
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            reply_markup=markup, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_yes_"))
def process_remove(call):
    key_id = call.data.replace("remove_yes_", "")
    
    try:
        key = keys_col.find_one({"_id": ObjectId(key_id)})
        if key:
            keys_col.delete_one({"_id": ObjectId(key_id)})
            bot.edit_message_text(f"✅ Key removed!", call.message.chat.id, call.message.message_id)
            log_admin_action(call.from_user.id, "REMOVE_KEY", {"key": key['key'][:10]})
        else:
            bot.edit_message_text("❌ Key not found!", call.message.chat.id, call.message.message_id)
        
        bot.answer_callback_query(call.id, "✅ Removed!")
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "remove_no")
def cancel_remove(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Cancelled")

# -----------------------
# BULK ADD KEYS WITH APK
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📦 Bulk Add Keys" and is_admin(msg.from_user.id))
@set_user_context
def bulk_add_start(msg):
    text = "📦 **Bulk Add Keys**\n\n"
    text += "Send: `category:key1|details1|apk_file_id,key2|details2|apk_file_id`\n\n"
    text += "For keys without APK: `key|details`\n\n"
    text += "Example:\n"
    text += "`weekend:BRUTAL1|Email: a@b.com\\nPass: 123|file_id_123,BRUTAL2|Email: c@d.com\\nPass: 456`\n\n"
    text += "Loaders:\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"• `{key}` - {data['emoji']} {data['name']}\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")
    user_states[msg.from_user.id] = "admin_bulk"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_bulk" and is_admin(msg.from_user.id))
@set_user_context
def process_bulk(msg):
    try:
        text = msg.text.strip()
        if ':' not in text:
            raise ValueError("Invalid format")
        
        category, items_str = text.split(':', 1)
        category = category.strip().lower()
        
        if category not in KEY_CATEGORIES:
            bot.send_message(msg.from_user.id, f"❌ Invalid loader!")
            return
        
        items = [k.strip() for k in items_str.split(',') if k.strip()]
        added = 0
        errors = 0
        
        for item in items:
            try:
                parts = item.split('|')
                if len(parts) == 3:
                    key_code, details, apk_file_id = parts
                elif len(parts) == 2:
                    key_code, details = parts
                    apk_file_id = None
                else:
                    key_code = item
                    details = item
                    apk_file_id = None
                
                key_code = key_code.strip()
                details = details.strip()
                apk_file_id = apk_file_id.strip() if apk_file_id else None
                
                if keys_col.find_one({"key": key_code}):
                    errors += 1
                    continue
                
                keys_col.insert_one({
                    "key": key_code,
                    "category": category,
                    "price": KEY_CATEGORIES[category]['price'],
                    "details": details,
                    "apk_file_id": apk_file_id,
                    "apk_file_name": "APK File" if apk_file_id else None,
                    "status": "available",
                    "added_by": msg.from_user.id,
                    "added_at": datetime.utcnow()
                })
                added += 1
                
            except:
                errors += 1
        
        bot.send_message(msg.from_user.id, f"✅ Added: {added}\n❌ Errors: {errors}")
        log_admin_action(msg.from_user.id, "BULK_ADD", {"category": category, "added": added})
        
    except Exception as e:
        bot.send_message(msg.from_user.id, f"❌ Error: {str(e)}")
    
    user_states.pop(msg.from_user.id, None)

# -----------------------
# USERS LIST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👥 Users List" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['users'])
@set_user_context
def users_list(msg):
    total = users_col.count_documents({})
    recent = list(users_col.find().sort("joined_at", -1).limit(10))
    
    text = f"👥 **Total Users: {total}**\n\n**Recent:**\n"
    for user in recent:
        name = user.get('name', 'Unknown')[:15]
        bal = get_balance(user['user_id'])
        joined = user.get('joined_at', datetime.utcnow()).strftime('%d/%m')
        text += f"• {name} - {format_currency(bal)} (ID: `{user['user_id']}`) [{joined}]\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# PENDING RECHARGES
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "💸 Pending Recharges" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['pending'])
@set_user_context
def pending_recharges(msg):
    pending = list(recharges_col.find({"status": "pending"}).sort("created_at", -1).limit(5))
    
    if not pending:
        bot.send_message(msg.from_user.id, "✅ No pending recharges!")
        return
    
    for req in pending:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"app_req_{req['_id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"rej_req_{req['_id']}")
        )
        
        user = users_col.find_one({"user_id": req['user_id']}) or {}
        user_name = user.get('name', 'Unknown')
        
        text = f"💸 **Recharge Request**\n\n"
        text += f"User: {user_name} (ID: `{req['user_id']}`)\n"
        text += f"Amount: {format_currency(req['amount'])}\n"
        text += f"UTR: {req.get('utr', 'N/A')}\n"
        
        if req.get('screenshot'):
            bot.send_photo(
                msg.from_user.id,
                req['screenshot'],
                caption=text,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            bot.send_message(msg.from_user.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("app_req_") or call.data.startswith("rej_req_"))
def process_recharge_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    try:
        action = "approved" if call.data.startswith("app_req_") else "rejected"
        req_id = ObjectId(call.data.replace("app_req_", "").replace("rej_req_", ""))
        req = recharges_col.find_one({"_id": req_id, "status": "pending"})
        
        if not req:
            bot.answer_callback_query(call.id, "❌ Request not found!", show_alert=True)
            return
        
        if action == "approved":
            add_balance(req['user_id'], req['amount'])
            recharges_col.update_one({"_id": req_id}, {"$set": {
                "status": "approved",
                "approved_by": call.from_user.id,
                "approved_at": datetime.utcnow()
            }})
            
            try:
                bot.send_message(req['user_id'], f"✅ Recharge approved!\nAmount: {format_currency(req['amount'])}\nNew Balance: {format_currency(get_balance(req['user_id']))}")
            except:
                pass
            
            bot.answer_callback_query(call.id, "✅ Approved!")
            bot.edit_message_caption(caption=call.message.caption + "\n\n✅ APPROVED", chat_id=call.message.chat.id, message_id=call.message.message_id)
            log_admin_action(call.from_user.id, "APPROVE_RECHARGE", {"user": req['user_id'], "amount": req['amount']})
            
        else:
            recharges_col.update_one({"_id": req_id}, {"$set": {
                "status": "rejected",
                "rejected_by": call.from_user.id,
                "rejected_at": datetime.utcnow()
            }})
            
            try:
                bot.send_message(req['user_id'], f"❌ Recharge rejected!\nAmount: {format_currency(req['amount'])}")
            except:
                pass
            
            bot.answer_callback_query(call.id, "❌ Rejected!")
            bot.edit_message_caption(caption=call.message.caption + "\n\n❌ REJECTED", chat_id=call.message.chat.id, message_id=call.message.message_id)
            log_admin_action(call.from_user.id, "REJECT_RECHARGE", {"user": req['user_id'], "amount": req['amount']})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error!", show_alert=True)

# -----------------------
# BROADCAST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📢 Broadcast" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['broadcast'])
@set_user_context
def broadcast_start(msg):
    if msg.text.startswith('/broadcast'):
        bot.reply_to(msg, "Please use the Broadcast button in Admin Panel.")
        return
    
    bot.send_message(msg.from_user.id, "📢 Send message to broadcast:")
    user_states[msg.from_user.id] = "admin_broadcast"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_broadcast" and is_admin(msg.from_user.id),
                    content_types=['text', 'photo'])
@set_user_context
def process_broadcast(msg):
    users = list(users_col.find())
    sent = 0
    failed = 0
    
    status_msg = bot.send_message(msg.from_user.id, "📡 Broadcasting...")
    
    for user in users:
        uid = user.get('user_id')
        if not uid:
            continue
        
        try:
            if msg.content_type == 'text':
                bot.send_message(uid, f"📢 **Broadcast**\n\n{msg.text}", parse_mode="Markdown")
            elif msg.content_type == 'photo':
                bot.send_photo(uid, msg.photo[-1].file_id, caption=f"📢 **Broadcast**\n\n{msg.caption or ''}", parse_mode="Markdown")
            sent += 1
            if sent % 10 == 0:
                bot.edit_message_text(f"📡 Sent: {sent}", msg.from_user.id, status_msg.message_id)
            time.sleep(0.1)
        except:
            failed += 1
    
    bot.edit_message_text(f"✅ Complete\nSent: {sent}\nFailed: {failed}", msg.from_user.id, status_msg.message_id)
    log_admin_action(msg.from_user.id, "BROADCAST", {"sent": sent, "failed": failed})
    user_states.pop(msg.from_user.id, None)

# -----------------------
# BAN/UNBAN
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🚫 Ban User" and is_admin(msg.from_user.id))
@set_user_context
def ban_start(msg):
    bot.send_message(msg.from_user.id, "🚫 Enter user ID to ban:")
    user_states[msg.from_user.id] = "admin_ban"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_ban" and is_admin(msg.from_user.id))
@set_user_context
def process_ban(msg):
    try:
        target = int(msg.text.strip())
        
        if target in ADMINS:
            bot.send_message(msg.from_user.id, "❌ Cannot ban admin!")
        elif not users_col.find_one({"user_id": target}):
            bot.send_message(msg.from_user.id, "❌ User not found!")
        elif is_user_banned(target):
            bot.send_message(msg.from_user.id, "⚠️ Already banned!")
        else:
            banned_users_col.insert_one({
                "user_id": target,
                "banned_by": msg.from_user.id,
                "banned_at": datetime.utcnow(),
                "status": "active"
            })
            bot.send_message(msg.from_user.id, f"✅ User {target} banned!")
            try:
                bot.send_message(target, "🚫 You have been banned!")
            except:
                pass
            log_admin_action(msg.from_user.id, "BAN_USER", {"target": target})
    except:
        bot.send_message(msg.from_user.id, "❌ Invalid ID!")
    
    user_states.pop(msg.from_user.id, None)

@bot.message_handler(func=lambda msg: msg.text == "✅ Unban User" and is_admin(msg.from_user.id))
@set_user_context
def unban_start(msg):
    bot.send_message(msg.from_user.id, "✅ Enter user ID to unban:")
    user_states[msg.from_user.id] = "admin_unban"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_unban" and is_admin(msg.from_user.id))
@set_user_context
def process_unban(msg):
    try:
        target = int(msg.text.strip())
        result = banned_users_col.update_one(
            {"user_id": target, "status": "active"},
            {"$set": {"status": "inactive", "unbanned_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            bot.send_message(msg.from_user.id, f"✅ User {target} unbanned!")
            try:
                bot.send_message(target, "✅ You have been unbanned!")
            except:
                pass
            log_admin_action(msg.from_user.id, "UNBAN_USER", {"target": target})
        else:
            bot.send_message(msg.from_user.id, "❌ User not banned!")
    except:
        bot.send_message(msg.from_user.id, "❌ Invalid ID!")
    
    user_states.pop(msg.from_user.id, None)

@bot.message_handler(commands=['ban'])
@set_user_context
def ban_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 2:
            bot.reply_to(msg, "❌ Usage: /ban [user_id]")
            return
        
        target = int(parts[1])
        
        if target in ADMINS:
            bot.reply_to(msg, "❌ Cannot ban admin!")
            return
        
        if not users_col.find_one({"user_id": target}):
            bot.reply_to(msg, "❌ User not found!")
            return
        
        if is_user_banned(target):
            bot.reply_to(msg, "⚠️ Already banned!")
            return
        
        banned_users_col.insert_one({
            "user_id": target,
            "banned_by": msg.from_user.id,
            "banned_at": datetime.utcnow(),
            "status": "active"
        })
        
        try:
            bot.send_message(target, "🚫 You have been banned!")
        except:
            pass
        
        bot.reply_to(msg, f"✅ User {target} banned!")
        log_admin_action(msg.from_user.id, "BAN_USER", {"target": target})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['unban'])
@set_user_context
def unban_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 2:
            bot.reply_to(msg, "❌ Usage: /unban [user_id]")
            return
        
        target = int(parts[1])
        
        result = banned_users_col.update_one(
            {"user_id": target, "status": "active"},
            {"$set": {"status": "inactive", "unbanned_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            try:
                bot.send_message(target, "✅ You have been unbanned!")
            except:
                pass
            
            bot.reply_to(msg, f"✅ User {target} unbanned!")
            log_admin_action(msg.from_user.id, "UNBAN_USER", {"target": target})
        else:
            bot.reply_to(msg, "❌ User not found or not banned!")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# ADD/DEDUCT BALANCE
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Balance" and is_admin(msg.from_user.id))
@set_user_context
def add_balance_start(msg):
    bot.send_message(msg.from_user.id, "➕ Enter user ID:")
    admin_deduct_state[msg.from_user.id] = {"step": "user", "type": "add"}

@bot.message_handler(func=lambda msg: msg.text == "💳 Deduct Balance" and is_admin(msg.from_user.id))
@set_user_context
def deduct_start(msg):
    bot.send_message(msg.from_user.id, "💳 Enter user ID:")
    admin_deduct_state[msg.from_user.id] = {"step": "user", "type": "deduct"}

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_deduct_state)
@set_user_context
def process_deduct_flow(msg):
    user_id = msg.from_user.id
    state = admin_deduct_state[user_id]
    
    if state["step"] == "user":
        try:
            target = int(msg.text.strip())
            if not users_col.find_one({"user_id": target}):
                bot.send_message(user_id, "❌ User not found!")
                admin_deduct_state.pop(user_id, None)
                return
            
            state["target"] = target
            state["step"] = "amount"
            bot.send_message(user_id, f"💰 Enter amount:")
            
        except:
            bot.send_message(user_id, "❌ Invalid ID!")
            admin_deduct_state.pop(user_id, None)
    
    elif state["step"] == "amount":
        try:
            amount = float(msg.text.strip())
            if amount <= 0:
                bot.send_message(user_id, "❌ Invalid amount!")
                return
            
            if state["type"] == "deduct":
                current = get_balance(state["target"])
                if amount > current:
                    bot.send_message(user_id, f"❌ User has only {format_currency(current)}")
                    return
            
            state["amount"] = amount
            state["step"] = "reason"
            bot.send_message(user_id, "📝 Enter reason:")
            
        except:
            bot.send_message(user_id, "❌ Invalid amount!")
    
    elif state["step"] == "reason":
        reason = msg.text.strip()
        
        if state["type"] == "add":
            old = get_balance(state["target"])
            add_balance(state["target"], state["amount"])
            new = get_balance(state["target"])
            action = "ADDED"
        else:
            old = get_balance(state["target"])
            deduct_balance(state["target"], state["amount"])
            new = get_balance(state["target"])
            action = "DEDUCTED"
        
        transactions_col.insert_one({
            "user_id": state["target"],
            "amount": state["amount"],
            "type": f"admin_{action.lower()}",
            "reason": reason,
            "admin_id": user_id,
            "old_balance": old,
            "new_balance": new,
            "timestamp": datetime.utcnow()
        })
        
        bot.send_message(
            user_id,
            f"✅ {action} {format_currency(state['amount'])}\n"
            f"User: {state['target']}\n"
            f"Old: {format_currency(old)}\n"
            f"New: {format_currency(new)}\n"
            f"Reason: {reason}"
        )
        
        try:
            bot.send_message(
                state["target"],
                f"{'✅' if action=='ADDED' else '⚠️'} Balance {action}: {format_currency(state['amount'])}\n"
                f"Reason: {reason}\n"
                f"New Balance: {format_currency(new)}"
            )
        except:
            pass
        
        log_admin_action(user_id, f"{action}_BALANCE", {"target": state['target'], "amount": state['amount']})
        admin_deduct_state.pop(user_id, None)

@bot.message_handler(commands=['addbalance'])
@set_user_context
def add_balance_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /addbalance [user_id] [amount] [reason]")
            return
        
        target = int(parts[1])
        amount = float(parts[2])
        reason = " ".join(parts[3:]) if len(parts) > 3 else "Admin added"
        
        if not users_col.find_one({"user_id": target}):
            bot.reply_to(msg, "❌ User not found!")
            return
        
        old = get_balance(target)
        add_balance(target, amount)
        new = get_balance(target)
        
        transactions_col.insert_one({
            "user_id": target,
            "amount": amount,
            "type": "admin_add",
            "reason": reason,
            "admin_id": msg.from_user.id,
            "old_balance": old,
            "new_balance": new,
            "timestamp": datetime.utcnow()
        })
        
        try:
            bot.send_message(target, f"✅ {format_currency(amount)} added!\nReason: {reason}\nNew: {format_currency(new)}")
        except:
            pass
        
        bot.reply_to(msg, f"✅ Added {format_currency(amount)} to {target}")
        log_admin_action(msg.from_user.id, "ADD_BALANCE", {"target": target, "amount": amount})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['deduct'])
@set_user_context
def deduct_balance_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /deduct [user_id] [amount] [reason]")
            return
        
        target = int(parts[1])
        amount = float(parts[2])
        reason = " ".join(parts[3:]) if len(parts) > 3 else "Admin deducted"
        
        if not users_col.find_one({"user_id": target}):
            bot.reply_to(msg, "❌ User not found!")
            return
        
        current = get_balance(target)
        
        if amount > current:
            bot.reply_to(msg, f"❌ User has only {format_currency(current)}")
            return
        
        old = current
        deduct_balance(target, amount)
        new = get_balance(target)
        
        transactions_col.insert_one({
            "user_id": target,
            "amount": amount,
            "type": "admin_deduct",
            "reason": reason,
            "admin_id": msg.from_user.id,
            "old_balance": old,
            "new_balance": new,
            "timestamp": datetime.utcnow()
        })
        
        try:
            bot.send_message(target, f"⚠️ {format_currency(amount)} deducted!\nReason: {reason}\nNew: {format_currency(new)}")
        except:
            pass
        
        bot.reply_to(msg, f"✅ Deducted {format_currency(amount)} from {target}")
        log_admin_action(msg.from_user.id, "DEDUCT_BALANCE", {"target": target, "amount": amount})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# COUPONS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🎟 Coupons" and is_admin(msg.from_user.id))
@set_user_context
def coupon_menu(msg):
    text = "🎟 **Coupon Management**\n\n"
    text += "Commands:\n"
    text += "/createcoupon [code] [amount] [max_uses]\n"
    text += "/deletecoupon [code]\n"
    text += "/coupons - List coupons"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['createcoupon'])
@set_user_context
def create_coupon(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 4:
            bot.reply_to(msg, "❌ Usage: /createcoupon [code] [amount] [max_uses]")
            return
        
        code = parts[1].upper()
        amount = float(parts[2])
        max_uses = int(parts[3])
        
        if coupons_col.find_one({"code": code}):
            bot.reply_to(msg, f"❌ Coupon {code} already exists!")
            return
        
        coupons_col.insert_one({
            "code": code,
            "amount": amount,
            "max_uses": max_uses,
            "used_by": [],
            "used_count": 0,
            "status": "active",
            "created_by": msg.from_user.id,
            "created_at": datetime.utcnow()
        })
        
        bot.reply_to(msg, f"✅ Coupon {code} created!\nAmount: {format_currency(amount)}\nUses: {max_uses}")
        log_admin_action(msg.from_user.id, "CREATE_COUPON", {"code": code, "amount": amount})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['deletecoupon'])
@set_user_context
def delete_coupon(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        code = msg.text.split()[1].upper()
        result = coupons_col.delete_one({"code": code})
        
        if result.deleted_count > 0:
            bot.reply_to(msg, f"✅ Coupon {code} deleted!")
            log_admin_action(msg.from_user.id, "DELETE_COUPON", {"code": code})
        else:
            bot.reply_to(msg, f"❌ Coupon {code} not found!")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['coupons'])
@set_user_context
def coupon_list(msg):
    if not is_admin(msg.from_user.id):
        return
    
    coupons = list(coupons_col.find({"status": "active"}).sort("created_at", -1))
    
    if not coupons:
        bot.reply_to(msg, "📭 No active coupons!")
        return
    
    text = "🎟 **Active Coupons**\n\n"
    for c in coupons:
        used = c.get('used_count', len(c.get('used_by', [])))
        text += f"• `{c['code']}`\n"
        text += f"  Amount: {format_currency(c['amount'])}\n"
        text += f"  Used: {used}/{c['max_uses']}\n\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# SALES REPORT
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📈 Sales Report" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['sales'])
@set_user_context
def sales_report(msg):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = list(keys_col.find({"status": "sold", "sold_at": {"$gte": today}}))
    
    today_count = len(today_sales)
    today_revenue = sum(k.get('price', 0) for k in today_sales)
    
    week_ago = today - timedelta(days=7)
    week_count = keys_col.count_documents({"status": "sold", "sold_at": {"$gte": week_ago}})
    
    total_sold = keys_col.count_documents({"status": "sold"})
    total_revenue = sum(k.get('price', 0) for k in keys_col.find({"status": "sold"}))
    
    text = f"📈 **Sales Report**\n\n"
    text += f"**Today:** {today_count} keys | {format_currency(today_revenue)}\n"
    text += f"**This Week:** {week_count} keys\n"
    text += f"**All Time:** {total_sold} keys | {format_currency(total_revenue)}\n\n"
    text += f"**Loader Breakdown:**\n"
    
    for key, data in KEY_CATEGORIES.items():
        cat_sales = [k for k in today_sales if k['category'] == key]
        if cat_sales:
            rev = sum(k['price'] for k in cat_sales)
            text += f"{data['emoji']} {data['name']}: {len(cat_sales)} - {format_currency(rev)}\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# FALLBACK
# -----------------------
@bot.message_handler(func=lambda msg: True)
@set_user_context
def fallback(msg):
    if msg.from_user.id not in user_states and msg.from_user.id not in admin_deduct_state and msg.from_user.id not in admin_add_key_state and msg.from_user.id not in delete_loader_state:
        bot.send_message(msg.from_user.id, "❌ Use buttons below!", reply_markup=get_main_keyboard())

# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    logger.info("🚀 Bot Started!")
    logger.info(f"Main Admin: {ADMIN_ID}")
    logger.info(f"Total Admins: {len(ADMINS)}")
    logger.info(f"Loaders: {len(KEY_CATEGORIES)}")
    
    # Create indexes
    try:
        keys_col.create_index("key", unique=True)
        keys_col.create_index("status")
        coupons_col.create_index("code", unique=True)
        users_col.create_index("user_id", unique=True)
        wallets_col.create_index("user_id", unique=True)
        admins_col.create_index("admin_id", unique=True)
        logger.info("✅ Database indexes created")
    except Exception as e:
        logger.error(f"❌ Index creation error: {e}")
    
    # Start bot
    while True:
        try:
            logger.info("🤖 Bot is polling...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(5)