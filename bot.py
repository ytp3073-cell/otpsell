import logging
import threading
import time
from datetime import datetime, timedelta
from bson import ObjectId
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import telebot.types

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
    from pymongo import MongoClient
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
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")

# Store temporary data
user_states = {}
upi_payment_states = {}
admin_deduct_state = {}
admin_add_key_state = {}
edit_category_state = {}
admin_remove_state = {}
edit_loader_state = {}

# Default Categories
DEFAULT_CATEGORIES = {
    "weekend": {"name": "🎮 Weekend Challenge", "price": 49, "emoji": "🎮", "description": "Weekend special challenge keys"},
    "royalty": {"name": "🏆 Royalty Pass", "price": 399, "emoji": "🏆", "description": "Premium royalty pass"},
    "uc": {"name": "⚡ UC", "price": 99, "emoji": "⚡", "description": "Unknown Cash for BGMI"},
    "event": {"name": "🎯 Event Pass", "price": 199, "emoji": "🎯", "description": "Special event passes"},
    "aqm": {"name": "💎 AQM Keys", "price": 299, "emoji": "💎", "description": "AQM premium keys"}
}

# Load categories from database
def load_categories():
    global KEY_CATEGORIES
    KEY_CATEGORIES = {}
    
    db_categories = list(categories_col.find())
    
    if db_categories:
        for cat in db_categories:
            KEY_CATEGORIES[cat['key']] = {
                "name": cat['name'],
                "price": cat['price'],
                "emoji": cat.get('emoji', '📌'),
                "description": cat.get('description', '')
            }
    else:
        KEY_CATEGORIES = DEFAULT_CATEGORIES.copy()
        for key, data in DEFAULT_CATEGORIES.items():
            categories_col.update_one(
                {"key": key},
                {"$set": {
                    "key": key,
                    "name": data['name'],
                    "price": data['price'],
                    "emoji": data['emoji'],
                    "description": data['description'],
                    "status": "active"
                }},
                upsert=True
            )
    
    return KEY_CATEGORIES

KEY_CATEGORIES = load_categories()

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
    keyboard.add(
        KeyboardButton("👑 Admin Panel")
    )
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
        KeyboardButton("✏️ Edit Loader Name"),
        KeyboardButton("💰 Edit Loader Price")
    )
    keyboard.add(
        KeyboardButton("📁 Manage Categories"),
        KeyboardButton("👥 Users List")
    )
    keyboard.add(
        KeyboardButton("💸 Pending Recharges"),
        KeyboardButton("📢 Broadcast")
    )
    keyboard.add(
        KeyboardButton("🚫 Ban User"),
        KeyboardButton("✅ Unban User")
    )
    keyboard.add(
        KeyboardButton("💳 Deduct Balance"),
        KeyboardButton("➕ Add Balance")
    )
    keyboard.add(
        KeyboardButton("🎟 Coupons"),
        KeyboardButton("📈 Sales Report")
    )
    keyboard.add(KeyboardButton("🔙 Main Menu"))
    return keyboard

def get_buy_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for key, data in KEY_CATEGORIES.items():
        keyboard.add(KeyboardButton(data['name']))
    keyboard.add(KeyboardButton("🔙 Main Menu"))
    return keyboard

def get_loader_edit_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for key, data in KEY_CATEGORIES.items():
        keyboard.add(KeyboardButton(f"📌 {data['name']}"))
    keyboard.add(KeyboardButton("🔙 Admin Panel"))
    return keyboard

# -----------------------
# UTILITY FUNCTIONS
# -----------------------
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
    return str(user_id) == str(ADMIN_ID)

def is_user_banned(user_id):
    return banned_users_col.find_one({"user_id": user_id, "status": "active"}) is not None

def log_admin_action(admin_id, action, details):
    admin_logs_col.insert_one({
        "admin_id": admin_id,
        "action": action,
        "details": details,
        "timestamp": datetime.utcnow()
    })

def refresh_categories():
    global KEY_CATEGORIES
    KEY_CATEGORIES = load_categories()
    return KEY_CATEGORIES

# -----------------------
# START HANDLER
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    
    if is_user_banned(user_id):
        bot.reply_to(msg, "🚫 **You are banned!** Contact admin.")
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
# HELP COMMAND
# -----------------------
@bot.message_handler(commands=['help'])
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
        text += "/addkey - Add a new key\n"
        text += "/removekey [keycode] - Remove a key\n"
        text += "/keys - List all keys\n"
        text += "/users - List users\n"
        text += "/pending - View pending recharges\n"
        text += "/approve [id] - Approve recharge\n"
        text += "/broadcast - Send broadcast\n"
        text += "/ban [user_id] - Ban a user\n"
        text += "/unban [user_id] - Unban a user\n"
        text += "/addbalance [user_id] [amount] - Add balance\n"
        text += "/deduct [user_id] [amount] [reason] - Deduct balance\n"
        text += "/createcoupon [code] [amount] [uses] - Create coupon\n"
        text += "/deletecoupon [code] - Delete coupon\n"
        text += "/coupons - List coupons\n"
        text += "/sales - View sales report\n"
        text += "/editname [loader_key] [new_name] - Edit loader name\n"
        text += "/editprice [loader_key] [new_price] - Edit loader price"
    
    bot.reply_to(msg, text, parse_mode="Markdown")

# -----------------------
# MAIN MENU
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🔙 Main Menu")
def main_menu(msg):
    bot.send_message(msg.from_user.id, "🏠 Main Menu", reply_markup=get_main_keyboard())

# -----------------------
# BUY KEYS - Category Selection
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🛒 Buy Keys")
@bot.message_handler(commands=['buy'])
def buy_keys(msg):
    user_id = msg.from_user.id
    text = "🎮 **Select Loader:**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        count = keys_col.count_documents({"category": key, "status": "available"})
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"💰 Price: {format_currency(data['price'])} | 📦 Available: {count}\n"
        if data['description']:
            text += f"📝 {data['description']}\n"
        text += "\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_buy_keyboard())

# -----------------------
# SHOW AVAILABLE KEYS in Category
# -----------------------
@bot.message_handler(func=lambda msg: msg.text in [d['name'] for d in KEY_CATEGORIES.values()])
def show_keys(msg):
    user_id = msg.from_user.id
    category_name = msg.text
    
    # Find category
    cat_key = None
    cat_data = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == category_name:
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
    text += "**👇 Select a key to view details:**\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for i, key in enumerate(keys[:8], 1):
        if key.get('details'):
            btn_text = f"📝 Key #{i} (Has Details)"
        else:
            btn_text = f"🔑 Key #{i}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"view_{key['_id']}"))
    
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

# -----------------------
# VIEW KEY DETAILS (Before Purchase)
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
        
        cat_data = KEY_CATEGORIES[key['category']]
        
        text = f"{cat_data['emoji']} **{cat_data['name']}**\n"
        text += f"💰 **Price:** {format_currency(key['price'])}\n\n"
        
        if key.get('details'):
            text += f"📝 **Key Details:**\n```\n{key['details']}\n```\n"
        else:
            text += "ℹ️ No additional details available.\n\n"
        
        text += "🛒 **Do you want to purchase this key?**"
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Yes, Buy Now", callback_data=f"buy_{key_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_view")
        )
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"View error: {e}")
        bot.answer_callback_query(call.id, "❌ Error loading details!", show_alert=True)

# -----------------------
# PROCESS PURCHASE
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_purchase(call):
    user_id = call.from_user.id
    key_id = call.data.replace("buy_", "")
    
    try:
        key = keys_col.find_one({"_id": ObjectId(key_id), "status": "available"})
        if not key:
            bot.answer_callback_query(call.id, "❌ Key sold out!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
        balance = get_balance(user_id)
        price = key['price']
        
        if balance < price:
            bot.answer_callback_query(
                call.id, 
                f"❌ Insufficient balance! Need {format_currency(price)}", 
                show_alert=True
            )
            return
        
        # Process purchase
        deduct_balance(user_id, price)
        
        # Update key status
        keys_col.update_one(
            {"_id": ObjectId(key_id)},
            {"$set": {
                "status": "sold",
                "sold_to": user_id,
                "sold_at": datetime.utcnow()
            }}
        )
        
        # Update user stats
        users_col.update_one(
            {"user_id": user_id},
            {"$inc": {
                "total_purchases": 1,
                "total_spent": price
            }}
        )
        
        # Save order
        orders_col.insert_one({
            "user_id": user_id,
            "key_id": key_id,
            "key": key['key'],
            "category": key['category'],
            "price": price,
            "details": key.get('details', ''),
            "purchased_at": datetime.utcnow()
        })
        
        cat_data = KEY_CATEGORIES[key['category']]
        
        text = f"✅ **Purchase Successful!**\n\n"
        text += f"🎮 {cat_data['emoji']} {cat_data['name']}\n"
        text += f"💰 Paid: {format_currency(price)}\n"
        text += f"💳 Remaining: {format_currency(get_balance(user_id))}\n\n"
        
        if key.get('details'):
            text += f"📝 **Key Details:**\n```\n{key['details']}\n```\n\n"
        
        text += f"🔑 **Your Key Code:**\n`{key['key']}`\n\n"
        text += "✨ Save these details and use in game!"
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        bot.answer_callback_query(call.id, "✅ Key purchased!", show_alert=True)
        
    except Exception as e:
        logger.error(f"Purchase error: {e}")
        bot.answer_callback_query(call.id, "❌ Purchase failed!", show_alert=True)

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
def recharge(msg):
    user_id = msg.from_user.id
    bot.send_message(user_id, "💳 Enter amount (min ₹10):", reply_markup=get_back_keyboard())
    user_states[user_id] = "waiting_recharge"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "waiting_recharge")
def process_recharge(msg):
    user_id = msg.from_user.id
    
    try:
        amount = float(msg.text.strip())
        if amount < 10:
            bot.send_message(user_id, "❌ Minimum ₹10! Enter again:", reply_markup=get_back_keyboard())
            return
        
        upi_payment_states[user_id] = {"amount": amount}
        user_states.pop(user_id, None)
        
        caption = f"""💳 **UPI Payment**

Amount: {format_currency(amount)}
UPI ID: `anurag99999@fam`

📌 Send payment and click I HAVE PAID"""
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💰 I HAVE PAID", callback_data="upi_paid"))
        
        bot.send_photo(user_id, "https://files.catbox.moe/a310jr.jpg", caption=caption, 
                       parse_mode="Markdown", reply_markup=markup)
    except:
        bot.send_message(user_id, "❌ Invalid amount!", reply_markup=get_back_keyboard())

# -----------------------
# REDEEM COUPON
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🎁 Redeem Coupon")
@bot.message_handler(commands=['coupon'])
def redeem(msg):
    user_id = msg.from_user.id
    bot.send_message(user_id, "🎟 Enter coupon code:", reply_markup=get_back_keyboard())
    user_states[user_id] = "waiting_coupon"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "waiting_coupon")
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
    
    bot.send_message(user_id, f"✅ Added {format_currency(amount)} to your wallet!", 
                    reply_markup=get_main_keyboard())

# -----------------------
# SUPPORT & ABOUT
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📞 Support")
@bot.message_handler(commands=['support'])
def support(msg):
    bot.send_message(msg.from_user.id, "📞 Contact: @UROGGY", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ About")
@bot.message_handler(commands=['about'])
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
    text += f"📊 **Statistics:**\n"
    text += f"• Total Keys: {total}\n"
    text += f"• Available: {available}\n"
    text += f"• Sold: {sold}\n"
    text += f"• Users: {users}\n"
    text += f"• Pending Recharges: {pending}\n\n"
    
    text += "📁 **Loaders:**\n"
    for key, data in KEY_CATEGORIES.items():
        loader_keys = keys_col.count_documents({"category": key})
        text += f"• {data['emoji']} {data['name']}: {loader_keys} keys\n"
    
    text += "\n🛠️ Use buttons below to manage:"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

# -----------------------
# STATS COMMAND
# -----------------------
@bot.message_handler(commands=['stats'])
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
# EDIT LOADER NAME
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "✏️ Edit Loader Name" and is_admin(msg.from_user.id))
def edit_loader_name_start(msg):
    user_id = msg.from_user.id
    
    text = "✏️ **Edit Loader Name**\n\n"
    text += "Select which loader's name you want to change:\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} (Key: `{key}`)\n"
    
    text += "\n**OR** use command: `/editname [loader_key] [new_name]`\n"
    text += "Example: `/editname weekend 🎮 New Weekend Loader`"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_loader_edit_keyboard())
    edit_loader_state[user_id] = {"action": "name", "step": "select"}

@bot.message_handler(commands=['editname'])
def edit_name_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /editname [loader_key] [new_name]\nExample: /editname weekend 🎮 New Weekend Loader")
            return
        
        key = parts[1].lower()
        new_name = parts[2].strip()
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Loader key '{key}' not found! Available keys: {', '.join(KEY_CATEGORIES.keys())}")
            return
        
        old_name = KEY_CATEGORIES[key]['name']
        
        # Update in database
        categories_col.update_one(
            {"key": key},
            {"$set": {"name": new_name}}
        )
        
        # Reload categories
        refresh_categories()
        
        bot.reply_to(
            msg,
            f"✅ **Loader Name Updated!**\n\n"
            f"Loader: {KEY_CATEGORIES[key]['emoji']}\n"
            f"Old Name: {old_name}\n"
            f"New Name: {new_name}",
            parse_mode="Markdown"
        )
        
        log_admin_action(msg.from_user.id, "EDIT_LOADER_NAME", {"key": key, "old": old_name, "new": new_name})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and 
                    msg.text.startswith("📌") and is_admin(msg.from_user.id))
def handle_loader_selection(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    # Find the key for this name
    selected_key = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == selected_name:
            selected_key = key
            break
    
    if not selected_key:
        bot.send_message(user_id, "❌ Loader not found! Please select from buttons.")
        return
    
    edit_loader_state[user_id]["key"] = selected_key
    edit_loader_state[user_id]["step"] = "waiting_name"
    
    current_name = KEY_CATEGORIES[selected_key]['name']
    
    bot.send_message(
        user_id,
        f"📝 Enter new name for {KEY_CATEGORIES[selected_key]['emoji']} {current_name}:\n\n"
        f"Example: `{current_name} 2024` or `New Loader Name`"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and 
                    edit_loader_state[msg.from_user.id].get("step") == "waiting_name" and 
                    is_admin(msg.from_user.id))
def handle_new_name(msg):
    user_id = msg.from_user.id
    new_name = msg.text.strip()
    key = edit_loader_state[user_id]["key"]
    
    if not new_name:
        bot.send_message(user_id, "❌ Name cannot be empty! Enter new name:")
        return
    
    old_name = KEY_CATEGORIES[key]['name']
    
    # Update in database
    categories_col.update_one(
        {"key": key},
        {"$set": {"name": new_name}}
    )
    
    # Reload categories
    refresh_categories()
    
    bot.send_message(
        user_id,
        f"✅ **Loader Name Updated!**\n\n"
        f"Loader: {KEY_CATEGORIES[key]['emoji']}\n"
        f"Old Name: {old_name}\n"
        f"New Name: {new_name}",
        parse_mode="Markdown"
    )
    
    log_admin_action(user_id, "EDIT_LOADER_NAME", {"key": key, "old": old_name, "new": new_name})
    edit_loader_state.pop(user_id, None)

# -----------------------
# EDIT LOADER PRICE
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "💰 Edit Loader Price" and is_admin(msg.from_user.id))
def edit_loader_price_start(msg):
    user_id = msg.from_user.id
    
    text = "💰 **Edit Loader Price**\n\n"
    text += "Select which loader's price you want to change:\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} - {format_currency(data['price'])} (Key: `{key}`)\n"
    
    text += "\n**OR** use command: `/editprice [loader_key] [new_price]`\n"
    text += "Example: `/editprice weekend 59`"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_loader_edit_keyboard())
    edit_loader_state[user_id] = {"action": "price", "step": "select"}

@bot.message_handler(commands=['editprice'])
def edit_price_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 3:
            bot.reply_to(msg, "❌ Usage: /editprice [loader_key] [new_price]\nExample: /editprice weekend 59")
            return
        
        key = parts[1].lower()
        new_price = float(parts[2])
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Loader key '{key}' not found! Available keys: {', '.join(KEY_CATEGORIES.keys())}")
            return
        
        if new_price <= 0:
            bot.reply_to(msg, "❌ Price must be positive!")
            return
        
        old_price = KEY_CATEGORIES[key]['price']
        
        # Update in database
        categories_col.update_one(
            {"key": key},
            {"$set": {"price": new_price}}
        )
        
        # Update all unsold keys in this category
        keys_col.update_many(
            {"category": key, "status": "available"},
            {"$set": {"price": new_price}}
        )
        
        # Reload categories
        refresh_categories()
        
        bot.reply_to(
            msg,
            f"✅ **Loader Price Updated!**\n\n"
            f"Loader: {KEY_CATEGORIES[key]['emoji']} {KEY_CATEGORIES[key]['name']}\n"
            f"Old Price: {format_currency(old_price)}\n"
            f"New Price: {format_currency(new_price)}",
            parse_mode="Markdown"
        )
        
        log_admin_action(msg.from_user.id, "EDIT_LOADER_PRICE", {"key": key, "old": old_price, "new": new_price})
        
    except ValueError:
        bot.reply_to(msg, "❌ Invalid price! Please enter a number.")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and 
                    edit_loader_state[msg.from_user.id].get("step") == "select" and 
                    msg.text.startswith("📌") and is_admin(msg.from_user.id))
def handle_price_selection(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    # Find the key for this name
    selected_key = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == selected_name:
            selected_key = key
            break
    
    if not selected_key:
        bot.send_message(user_id, "❌ Loader not found! Please select from buttons.")
        return
    
    edit_loader_state[user_id]["key"] = selected_key
    edit_loader_state[user_id]["step"] = "waiting_price"
    
    current_price = KEY_CATEGORIES[selected_key]['price']
    
    bot.send_message(
        user_id,
        f"💰 Enter new price for {KEY_CATEGORIES[selected_key]['emoji']} {KEY_CATEGORIES[selected_key]['name']}:\n"
        f"Current Price: {format_currency(current_price)}\n\n"
        f"Example: `59` or `399`"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_loader_state and 
                    edit_loader_state[msg.from_user.id].get("step") == "waiting_price" and 
                    is_admin(msg.from_user.id))
def handle_new_price(msg):
    user_id = msg.from_user.id
    
    try:
        new_price = float(msg.text.strip())
        key = edit_loader_state[user_id]["key"]
        
        if new_price <= 0:
            bot.send_message(user_id, "❌ Price must be positive! Enter again:")
            return
        
        old_price = KEY_CATEGORIES[key]['price']
        
        # Update in database
        categories_col.update_one(
            {"key": key},
            {"$set": {"price": new_price}}
        )
        
        # Update all unsold keys in this category
        keys_col.update_many(
            {"category": key, "status": "available"},
            {"$set": {"price": new_price}}
        )
        
        # Reload categories
        refresh_categories()
        
        bot.send_message(
            user_id,
            f"✅ **Loader Price Updated!**\n\n"
            f"Loader: {KEY_CATEGORIES[key]['emoji']} {KEY_CATEGORIES[key]['name']}\n"
            f"Old Price: {format_currency(old_price)}\n"
            f"New Price: {format_currency(new_price)}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "EDIT_LOADER_PRICE", {"key": key, "old": old_price, "new": new_price})
        edit_loader_state.pop(user_id, None)
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid price! Enter a number:")

# -----------------------
# ADD KEY
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Key" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['addkey'])
def add_key_start(msg):
    if isinstance(msg, telebot.types.Message) and msg.text.startswith('/addkey'):
        bot.reply_to(msg, "Please use the button to add key:\n👑 Admin Panel → ➕ Add Key")
        return
        
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(f"{data['emoji']} {data['name']}", callback_data=f"addcat_{key}"))
    
    bot.send_message(msg.from_user.id, "📝 Select loader category:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("addcat_"))
def add_key_category(call):
    category = call.data.replace("addcat_", "")
    admin_add_key_state[call.from_user.id] = {"category": category, "step": "waiting_key"}
    
    bot.edit_message_text(
        f"📝 **Add Key for {KEY_CATEGORIES[category]['name']}**\n\n"
        f"**Step 1:** Send the KEY CODE first\n"
        f"(Ye sirf buy ke baad dikhega)\n\n"
        f"Example: `BRUTAL123456`",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_key" and 
                    is_admin(msg.from_user.id))
def handle_key_code(msg):
    user_id = msg.from_user.id
    key_code = msg.text.strip()
    
    if not key_code:
        bot.send_message(user_id, "❌ Key code cannot be empty! Send key code:")
        return
    
    admin_add_key_state[user_id]["key_code"] = key_code
    admin_add_key_state[user_id]["step"] = "waiting_details"
    
    bot.send_message(
        user_id,
        f"✅ Key code saved: `{key_code}`\n\n"
        f"**Step 2:** Now send the DETAILS\n"
        f"(Ye preview mein aur buy ke baad dono jagah dikhega)\n\n"
        f"Example:\n"
        f"`🎮 Brutal Server - Asia`\n"
        f"`Email: brutal@gmail.com`\n"
        f"`Password: bgmi123`\n"
        f"`Server: Asia`"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_details" and 
                    is_admin(msg.from_user.id))
def handle_details(msg):
    user_id = msg.from_user.id
    details = msg.text.strip()
    category = admin_add_key_state[user_id]['category']
    key_code = admin_add_key_state[user_id]['key_code']
    
    if not details:
        bot.send_message(user_id, "❌ Details cannot be empty! Send details:")
        return
    
    keys_col.insert_one({
        "key": key_code,
        "category": category,
        "price": KEY_CATEGORIES[category]['price'],
        "details": details,
        "status": "available",
        "added_by": user_id,
        "added_at": datetime.utcnow()
    })
    
    count = keys_col.count_documents({"category": category, "status": "available"})
    
    bot.send_message(
        user_id,
        f"✅ **Key Added Successfully!**\n\n"
        f"Loader: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
        f"Price: {format_currency(KEY_CATEGORIES[category]['price'])}\n"
        f"Available in this loader: {count}\n\n"
        f"🔑 **Key Code (Sirf buy ke baad dikhega):**\n`{key_code}`\n\n"
        f"📝 **Details (Preview aur buy ke baad dono jagah dikhenge):**\n```\n{details}\n```"
    )
    
    log_admin_action(user_id, "ADD_KEY", {"category": category})
    admin_add_key_state.pop(user_id, None)

# -----------------------
# KEY LIST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📋 Key List" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['keys'])
def key_list(msg):
    if isinstance(msg, telebot.types.Message) and msg.text.startswith('/keys'):
        text = "📋 **All Keys**\n\n"
        all_keys = list(keys_col.find().sort("added_at", -1).limit(20))
        
        if not all_keys:
            bot.reply_to(msg, "📭 No keys found!")
            return
        
        for key in all_keys:
            cat_name = KEY_CATEGORIES[key['category']]['name'][:10]
            status_emoji = "✅" if key['status'] == "available" else "💰"
            text += f"{status_emoji} {cat_name}: `{key['key'][:15]}...`\n"
        
        bot.reply_to(msg, text, parse_mode="Markdown")
        return
    
    text = "📋 **Key Inventory**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        avail = keys_col.count_documents({"category": key, "status": "available"})
        sold = keys_col.count_documents({"category": key, "status": "sold"})
        text += f"{data['emoji']} {data['name']}: {avail} avail, {sold} sold\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# REMOVE KEY COMMAND
# -----------------------
@bot.message_handler(commands=['removekey'])
def remove_key_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            bot.reply_to(msg, "❌ Usage: /removekey [keycode]")
            return
        
        key_code = parts[1]
        result = keys_col.delete_one({"key": key_code})
        
        if result.deleted_count > 0:
            bot.reply_to(msg, f"✅ Key `{key_code}` removed!")
            log_admin_action(msg.from_user.id, "REMOVE_KEY", {"key": key_code})
        else:
            bot.reply_to(msg, f"❌ Key `{key_code}` not found!")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# REMOVE KEY - Sab keys show hongi
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🗑 Remove Key" and is_admin(msg.from_user.id))
def remove_key_start(msg):
    user_id = msg.from_user.id
    
    all_keys = []
    for cat_key, cat_data in KEY_CATEGORIES.items():
        keys = list(keys_col.find({"category": cat_key, "status": "available"}).limit(5))
        for k in keys:
            all_keys.append(k)
    
    if not all_keys:
        bot.send_message(user_id, "📭 No keys available to remove!")
        return
    
    text = "🗑 **Select Key to Remove**\n\n"
    text += f"Total Available: {len(all_keys)} keys\n\n"
    
    markup = InlineKeyboardMarkup(row_width=1)
    for i, key in enumerate(all_keys[:10], 1):
        cat_name = KEY_CATEGORIES[key['category']]['name'][:10]
        preview = key['details'][:30] + "..." if key.get('details') else "No details"
        btn_text = f"{i}. {cat_name} - {preview}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"rem_{key['_id']}"))
    
    if len(all_keys) > 10:
        markup.add(InlineKeyboardButton("📋 Next Page (Coming Soon)", callback_data="remove_next"))
    
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("rem_"))
def confirm_remove(call):
    key_id = call.data.replace("rem_", "")
    
    try:
        key = keys_col.find_one({"_id": ObjectId(key_id)})
        if not key:
            bot.answer_callback_query(call.id, "❌ Key not found!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
        cat_name = KEY_CATEGORIES[key['category']]['name']
        
        text = f"🗑 **Confirm Removal**\n\n"
        text += f"Loader: {cat_name}\n"
        text += f"Key Code: `{key['key']}`\n\n"
        
        if key.get('details'):
            text += f"📝 **Details:**\n```\n{key['details']}\n```\n\n"
        
        text += "Are you sure you want to remove this key?"
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Yes, Remove", callback_data=f"remove_yes_{key_id}"),
            InlineKeyboardButton("❌ No, Cancel", callback_data="remove_no")
        )
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_yes_"))
def process_remove(call):
    key_id = call.data.replace("remove_yes_", "")
    
    try:
        key = keys_col.find_one({"_id": ObjectId(key_id)})
        if not key:
            bot.answer_callback_query(call.id, "❌ Key not found!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
        keys_col.delete_one({"_id": ObjectId(key_id)})
        
        bot.edit_message_text(
            f"✅ **Key Removed Successfully!**\n\n"
            f"Loader: {KEY_CATEGORIES[key['category']]['name']}\n"
            f"Key Code: `{key['key']}`",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        log_admin_action(call.from_user.id, "REMOVE_KEY", {"category": key['category']})
        bot.answer_callback_query(call.id, "✅ Key removed!")
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "remove_no")
def cancel_remove(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Cancelled")

@bot.callback_query_handler(func=lambda call: call.data == "remove_next")
def remove_next(call):
    bot.answer_callback_query(call.id, "More keys coming in next update!", show_alert=True)

# -----------------------
# BULK ADD KEYS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📦 Bulk Add Keys" and is_admin(msg.from_user.id))
def bulk_add_start(msg):
    text = "📦 **Bulk Add Keys**\n\n"
    text += "Send keys in this format:\n\n"
    text += "`category:keycode|details,keycode|details,keycode|details`\n\n"
    text += "Examples:\n"
    text += "• `weekend:BRUTAL123|🎮 Brutal Asia,BRUTAL456|🎮 Brutal Europe`\n"
    text += "• `royalty:ROYAL30|🏆 30 Days Pass,ROYAL60|🏆 60 Days Pass`\n\n"
    text += "Available Loaders:\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"• `{key}` - {data['emoji']} {data['name']}\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")
    user_states[msg.from_user.id] = "admin_bulk"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_bulk" and is_admin(msg.from_user.id))
def process_bulk(msg):
    try:
        text = msg.text.strip()
        if ':' not in text:
            raise ValueError("Invalid format")
        
        category, items_str = text.split(':', 1)
        category = category.strip().lower()
        
        if category not in KEY_CATEGORIES:
            bot.send_message(msg.from_user.id, f"❌ Invalid loader! Available: {', '.join(KEY_CATEGORIES.keys())}")
            return
        
        items = [k.strip() for k in items_str.split(',') if k.strip()]
        added = 0
        errors = 0
        
        for item in items:
            try:
                if '|' in item:
                    key_code, details = item.split('|', 1)
                else:
                    key_code = item
                    details = item
                
                key_code = key_code.strip()
                details = details.strip()
                
                if keys_col.find_one({"key": key_code}):
                    errors += 1
                    continue
                
                keys_col.insert_one({
                    "key": key_code,
                    "category": category,
                    "price": KEY_CATEGORIES[category]['price'],
                    "details": details,
                    "status": "available",
                    "added_by": msg.from_user.id,
                    "added_at": datetime.utcnow()
                })
                added += 1
                
            except Exception as e:
                errors += 1
        
        bot.send_message(
            msg.from_user.id, 
            f"✅ Added: {added} keys\n❌ Errors/Skipped: {errors}\nLoader: {KEY_CATEGORIES[category]['name']}"
        )
        log_admin_action(msg.from_user.id, "BULK_ADD", {"category": category, "added": added, "errors": errors})
        
    except Exception as e:
        bot.send_message(msg.from_user.id, f"❌ Error: {str(e)}")
    
    user_states.pop(msg.from_user.id, None)

# -----------------------
# MANAGE CATEGORIES
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📁 Manage Categories" and is_admin(msg.from_user.id))
def manage_categories(msg):
    text = "📁 **Loader Management**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"Key: `{key}` | Price: {format_currency(data['price'])}\n"
        if data['description']:
            text += f"Desc: {data['description']}\n"
        text += "\n"
    
    text += "Commands:\n"
    text += "/addcat key|name|price|emoji|desc - Add loader\n"
    text += "/editcat key|field|value - Edit loader\n"
    text += "/delcat key - Delete loader\n\n"
    text += "Example: /addcat brutal|🎮 Brutal|30|🎮|Brutal server keys"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['addcat'])
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
            "status": "active"
        })
        
        refresh_categories()
        bot.reply_to(msg, f"✅ Loader {emoji} {name} added!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['editcat'])
def edit_category(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split(maxsplit=1)[1].split('|')
        if len(parts) < 3:
            raise ValueError("Invalid format")
        
        key = parts[0].strip().lower()
        field = parts[1].strip().lower()
        value = parts[2].strip()
        
        if field == "price":
            value = float(value)
        
        categories_col.update_one({"key": key}, {"$set": {field: value}})
        
        if field == "price":
            keys_col.update_many(
                {"category": key, "status": "available"},
                {"$set": {"price": value}}
            )
        
        refresh_categories()
        bot.reply_to(msg, f"✅ Loader {key} updated!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['delcat'])
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
        
        bot.reply_to(msg, f"✅ Loader deleted with all keys!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# USERS LIST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👥 Users List" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['users'])
def users_list(msg):
    total = users_col.count_documents({})
    recent = list(users_col.find().sort("joined_at", -1).limit(10))
    
    text = f"👥 **Total Users: {total}**\n\n**Recent Users:**\n"
    for user in recent:
        name = user.get('name', 'Unknown')[:15]
        uid = user['user_id']
        bal = get_balance(uid)
        joined = user['joined_at'].strftime('%d/%m')
        text += f"• {name} - {format_currency(bal)} (ID: `{uid}`) [{joined}]\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# PENDING RECHARGES
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "💸 Pending Recharges" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['pending'])
def pending_recharges(msg):
    pending = list(recharges_col.find({"status": "pending"}).sort("created_at", -1).limit(10))
    
    if not pending:
        bot.send_message(msg.from_user.id, "✅ No pending recharges!")
        return
    
    text = "💸 **Pending Recharges**\n\n"
    for p in pending:
        text += f"ID: `{p['_id']}`\n"
        text += f"User: {p['user_id']}\n"
        text += f"Amount: {format_currency(p['amount'])}\n"
        text += f"UTR: {p.get('utr', 'N/A')}\n"
        text += f"Time: {p['created_at'].strftime('%H:%M %d/%m')}\n\n"
    
    text += "Approve: /approve REQUEST_ID"
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['approve'])
def approve_recharge(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        req_id = ObjectId(msg.text.split()[1])
        req = recharges_col.find_one({"_id": req_id, "status": "pending"})
        
        if not req:
            bot.reply_to(msg, "❌ Request not found!")
            return
        
        add_balance(req['user_id'], req['amount'])
        recharges_col.update_one({"_id": req_id}, {"$set": {"status": "approved"}})
        
        try:
            bot.send_message(req['user_id'], f"✅ Recharge of {format_currency(req['amount'])} approved!")
        except:
            pass
        
        bot.reply_to(msg, f"✅ Approved for user {req['user_id']}")
        log_admin_action(msg.from_user.id, "APPROVE_RECHARGE", {"user": req['user_id'], "amount": req['amount']})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# BROADCAST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📢 Broadcast" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['broadcast'])
def broadcast_start(msg):
    if isinstance(msg, telebot.types.Message) and msg.text.startswith('/broadcast'):
        bot.reply_to(msg, "Please use the broadcast button:\n👑 Admin Panel → 📢 Broadcast")
        return
        
    bot.send_message(msg.from_user.id, "📢 Send message to broadcast (text/photo):")
    user_states[msg.from_user.id] = "admin_broadcast"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_broadcast" and is_admin(msg.from_user.id),
                    content_types=['text', 'photo'])
def process_broadcast(msg):
    users = list(users_col.find())
    sent = 0
    failed = 0
    
    bot.send_message(msg.from_user.id, "📡 Broadcasting started...")
    
    for user in users:
        uid = user.get('user_id')
        if not uid or uid == ADMIN_ID:
            continue
        
        try:
            if msg.content_type == 'text':
                bot.send_message(uid, f"📢 **Broadcast**\n\n{msg.text}")
            elif msg.content_type == 'photo':
                bot.send_photo(uid, msg.photo[-1].file_id, caption=f"📢 **Broadcast**\n\n{msg.caption or ''}")
            sent += 1
            time.sleep(0.1)
        except:
            failed += 1
    
    bot.send_message(msg.from_user.id, f"✅ Broadcast Complete\nSent: {sent}\nFailed: {failed}")
    log_admin_action(msg.from_user.id, "BROADCAST", {"sent": sent, "failed": failed})
    user_states.pop(msg.from_user.id, None)

# -----------------------
# BAN/UNBAN COMMANDS
# -----------------------
@bot.message_handler(commands=['ban'])
def ban_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 2:
            bot.reply_to(msg, "❌ Usage: /ban [user_id]")
            return
        
        target = int(parts[1])
        
        if target == ADMIN_ID:
            bot.reply_to(msg, "❌ Cannot ban admin!")
            return
        
        if not users_col.find_one({"user_id": target}):
            bot.reply_to(msg, "❌ User not found!")
            return
        
        if is_user_banned(target):
            bot.reply_to(msg, "⚠️ User is already banned!")
            return
        
        banned_users_col.insert_one({
            "user_id": target,
            "banned_by": msg.from_user.id,
            "banned_at": datetime.utcnow(),
            "status": "active"
        })
        
        try:
            bot.send_message(target, "🚫 You have been banned from using this bot!")
        except:
            pass
        
        bot.reply_to(msg, f"✅ User {target} banned!")
        log_admin_action(msg.from_user.id, "BAN_USER", {"target": target})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['unban'])
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
                bot.send_message(target, "✅ You have been unbanned! You can now use the bot.")
            except:
                pass
            
            bot.reply_to(msg, f"✅ User {target} unbanned!")
            log_admin_action(msg.from_user.id, "UNBAN_USER", {"target": target})
        else:
            bot.reply_to(msg, "❌ User not found or not banned!")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.text == "🚫 Ban User" and is_admin(msg.from_user.id))
def ban_start(msg):
    bot.send_message(msg.from_user.id, "🚫 Enter user ID to ban:")
    user_states[msg.from_user.id] = "admin_ban"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_ban" and is_admin(msg.from_user.id))
def process_ban(msg):
    try:
        target = int(msg.text.strip())
        if target == ADMIN_ID:
            bot.send_message(msg.from_user.id, "❌ Cannot ban admin!")
        elif not users_col.find_one({"user_id": target}):
            bot.send_message(msg.from_user.id, "❌ User not found!")
        elif is_user_banned(target):
            bot.send_message(msg.from_user.id, "⚠️ User is already banned!")
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
def unban_start(msg):
    bot.send_message(msg.from_user.id, "✅ Enter user ID to unban:")
    user_states[msg.from_user.id] = "admin_unban"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_unban" and is_admin(msg.from_user.id))
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

# -----------------------
# ADD/DEDUCT BALANCE COMMANDS
# -----------------------
@bot.message_handler(commands=['addbalance'])
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
        
        if amount <= 0:
            bot.reply_to(msg, "❌ Amount must be positive!")
            return
        
        old_balance = get_balance(target)
        add_balance(target, amount)
        new_balance = get_balance(target)
        
        transactions_col.insert_one({
            "user_id": target,
            "amount": amount,
            "type": "admin_add",
            "reason": reason,
            "admin_id": msg.from_user.id,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "timestamp": datetime.utcnow()
        })
        
        try:
            bot.send_message(target, f"✅ {format_currency(amount)} added to your wallet!\nReason: {reason}\nNew Balance: {format_currency(new_balance)}")
        except:
            pass
        
        bot.reply_to(msg, f"✅ Added {format_currency(amount)} to user {target}")
        log_admin_action(msg.from_user.id, "ADD_BALANCE", {"target": target, "amount": amount, "reason": reason})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['deduct'])
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
        
        if amount <= 0:
            bot.reply_to(msg, "❌ Amount must be positive!")
            return
        
        if amount > current:
            bot.reply_to(msg, f"❌ Insufficient balance! User has {format_currency(current)}")
            return
        
        old_balance = current
        deduct_balance(target, amount)
        new_balance = get_balance(target)
        
        transactions_col.insert_one({
            "user_id": target,
            "amount": amount,
            "type": "admin_deduct",
            "reason": reason,
            "admin_id": msg.from_user.id,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "timestamp": datetime.utcnow()
        })
        
        try:
            bot.send_message(target, f"⚠️ {format_currency(amount)} deducted from your wallet!\nReason: {reason}\nNew Balance: {format_currency(new_balance)}")
        except:
            pass
        
        bot.reply_to(msg, f"✅ Deducted {format_currency(amount)} from user {target}")
        log_admin_action(msg.from_user.id, "DEDUCT_BALANCE", {"target": target, "amount": amount, "reason": reason})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.text == "💳 Deduct Balance" and is_admin(msg.from_user.id))
def deduct_start(msg):
    bot.send_message(msg.from_user.id, "💳 Enter user ID:")
    admin_deduct_state[msg.from_user.id] = {"step": "user", "type": "deduct"}

@bot.message_handler(func=lambda msg: msg.text == "➕ Add Balance" and is_admin(msg.from_user.id))
def add_balance_start(msg):
    bot.send_message(msg.from_user.id, "➕ Enter user ID:")
    admin_deduct_state[msg.from_user.id] = {"step": "user", "type": "add"}

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_deduct_state)
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
            
            state["amount"] = amount
            state["step"] = "reason"
            bot.send_message(user_id, "📝 Enter reason:")
            
        except:
            bot.send_message(user_id, "❌ Invalid amount!")
    
    elif state["step"] == "reason":
        reason = msg.text.strip()
        
        if state["type"] == "deduct":
            current = get_balance(state["target"])
            if state["amount"] > current:
                bot.send_message(user_id, f"❌ Insufficient balance! User has {format_currency(current)}")
                admin_deduct_state.pop(user_id, None)
                return
            
            old_balance = current
            deduct_balance(state["target"], state["amount"])
            new_balance = get_balance(state["target"])
            action = "DEDUCTED"
        else:
            old_balance = get_balance(state["target"])
            add_balance(state["target"], state["amount"])
            new_balance = get_balance(state["target"])
            action = "ADDED"
        
        transactions_col.insert_one({
            "user_id": state["target"],
            "amount": state["amount"],
            "type": f"admin_{action.lower()}",
            "reason": reason,
            "admin_id": user_id,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "timestamp": datetime.utcnow()
        })
        
        bot.send_message(
            user_id,
            f"✅ {action} {format_currency(state['amount'])}\n"
            f"User: {state['target']}\n"
            f"Reason: {reason}\n"
            f"Old Balance: {format_currency(old_balance)}\n"
            f"New Balance: {format_currency(new_balance)}"
        )
        
        try:
            bot.send_message(
                state["target"],
                f"{'⚠️' if action=='DEDUCTED' else '✅'} Balance {action}: {format_currency(state['amount'])}\n"
                f"Reason: {reason}\n"
                f"New Balance: {format_currency(new_balance)}"
            )
        except:
            pass
        
        log_admin_action(user_id, f"{action}_BALANCE", {
            "target": state['target'],
            "amount": state['amount'],
            "reason": reason
        })
        
        admin_deduct_state.pop(user_id, None)

# -----------------------
# COUPONS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🎟 Coupons" and is_admin(msg.from_user.id))
def coupon_menu(msg):
    text = "🎟 **Coupon Management**\n\n"
    text += "**Commands:**\n"
    text += "• /createcoupon [code] [amount] [max_uses]\n"
    text += "• /deletecoupon [code]\n"
    text += "• /coupons\n\n"
    text += "**Examples:**\n"
    text += "• `/createcoupon DIWALI50 50 100`\n"
    text += "• `/deletecoupon DIWALI50`"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['createcoupon'])
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
        
        if amount <= 0 or max_uses <= 0:
            bot.reply_to(msg, "❌ Amount and max uses must be positive!")
            return
        
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
        
        bot.reply_to(
            msg,
            f"✅ **Coupon Created!**\n\n"
            f"Code: `{code}`\n"
            f"Amount: {format_currency(amount)}\n"
            f"Max Uses: {max_uses}",
            parse_mode="Markdown"
        )
        log_admin_action(msg.from_user.id, "CREATE_COUPON", {"code": code, "amount": amount, "max_uses": max_uses})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['deletecoupon'])
def delete_coupon(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            bot.reply_to(msg, "❌ Usage: /deletecoupon [code]")
            return
        
        code = parts[1].upper()
        result = coupons_col.delete_one({"code": code})
        
        if result.deleted_count > 0:
            bot.reply_to(msg, f"✅ Coupon {code} deleted!")
            log_admin_action(msg.from_user.id, "DELETE_COUPON", {"code": code})
        else:
            bot.reply_to(msg, f"❌ Coupon {code} not found!")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['coupons'])
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
        text += f"  Used: {used}/{c['max_uses']}\n"
        text += f"  Created: {c['created_at'].strftime('%d/%m')}\n\n"
    
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# -----------------------
# SALES REPORT
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📈 Sales Report" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['sales'])
def sales_report(msg):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = list(keys_col.find({"status": "sold", "sold_at": {"$gte": today}}))
    
    today_count = len(today_sales)
    today_revenue = sum(k.get('price', 0) for k in today_sales)
    
    week_ago = today - timedelta(days=7)
    week_count = keys_col.count_documents({"status": "sold", "sold_at": {"$gte": week_ago}})
    
    month_ago = today - timedelta(days=30)
    month_count = keys_col.count_documents({"status": "sold", "sold_at": {"$gte": month_ago}})
    
    total_sold = keys_col.count_documents({"status": "sold"})
    total_revenue = sum(k.get('price', 0) for k in keys_col.find({"status": "sold"}))
    
    text = f"📈 **Sales Report**\n\n"
    text += f"**Today:** {today_count} keys | {format_currency(today_revenue)}\n"
    text += f"**This Week:** {week_count} keys\n"
    text += f"**This Month:** {month_count} keys\n\n"
    text += f"**All Time:** {total_sold} keys | {format_currency(total_revenue)}\n\n"
    text += f"**Loader Breakdown (Today):**\n"
    
    for key, data in KEY_CATEGORIES.items():
        cat_sales = [k for k in today_sales if k['category'] == key]
        if cat_sales:
            rev = sum(k['price'] for k in cat_sales)
            text += f"{data['emoji']} {data['name']}: {len(cat_sales)} - {format_currency(rev)}\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

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
    
    bot.answer_callback_query(call.id, "📝 Send UTR number")
    upi_payment_states[user_id] = {"amount": amount, "step": "utr"}
    bot.send_message(user_id, "📝 Enter 12-digit UTR number:")

@bot.message_handler(func=lambda msg: upi_payment_states.get(msg.from_user.id, {}).get("step") == "utr")
def handle_utr(msg):
    user_id = msg.from_user.id
    utr = msg.text.strip()
    
    if not utr.isdigit() or len(utr) != 12:
        bot.send_message(user_id, "❌ Invalid UTR! Enter 12 digits:")
        return
    
    upi_payment_states[user_id]["utr"] = utr
    upi_payment_states[user_id]["step"] = "screenshot"
    bot.send_message(user_id, "📸 Now send payment screenshot:")

@bot.message_handler(content_types=['photo'], func=lambda msg: upi_payment_states.get(msg.from_user.id, {}).get("step") == "screenshot")
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
    
    bot.send_photo(
        ADMIN_ID,
        msg.photo[-1].file_id,
        caption=f"💰 New Recharge\nUser: {user_id}\nAmount: {format_currency(data['amount'])}\nUTR: {data['utr']}\nID: {recharge_id}"
    )
    
    bot.send_message(user_id, "✅ Payment submitted! Admin will approve soon.", reply_markup=get_main_keyboard())
    upi_payment_states.pop(user_id, None)

# -----------------------
# FALLBACK HANDLER
# -----------------------
@bot.message_handler(func=lambda msg: True)
def fallback(msg):
    if msg.from_user.id not in user_states and msg.from_user.id not in admin_deduct_state:
        bot.send_message(msg.from_user.id, "❌ Use buttons below!", reply_markup=get_main_keyboard())

# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    logger.info("🚀 Bot Started!")
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info(f"Loaders: {len(KEY_CATEGORIES)}")
    
    # Create indexes
    try:
        keys_col.create_index("key", unique=True)
        keys_col.create_index("status")
        coupons_col.create_index("code", unique=True)
        users_col.create_index("user_id", unique=True)
        wallets_col.create_index("user_id", unique=True)
        logger.info("✅ Database indexes created")
    except Exception as e:
        logger.error(f"❌ Index creation failed: {e}")
    
    # Start bot
    while True:
        try:
            logger.info("🤖 Bot is polling...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(5)