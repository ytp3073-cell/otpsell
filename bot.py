import logging
import re
import threading
import time
import random
from datetime import datetime, timedelta
from bson import ObjectId
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import telebot.types

# -----------------------
# CONFIG
# -----------------------
BOT_TOKEN = '8477235690:AAGAjf1FJGxxJYG1I_229J_C-EBXphXAyzA'
ADMIN_ID = 8413263061  # Apna Telegram ID daalein
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
    categories_col = db['categories']  # New collection for categories
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")

# Store temporary data
user_states = {}
user_last_message = {}
upi_payment_states = {}
admin_deduct_state = {}
coupon_state = {}
broadcast_data = {}
edit_key_state = {}
admin_add_key_state = {}
edit_category_state = {}

# Default Categories (will be loaded from DB)
DEFAULT_CATEGORIES = {
    "weekend": {"name": "🎮 Weekend Challenge", "price": 49, "emoji": "🎮"},
    "royalty": {"name": "🏆 Royalty Pass", "price": 399, "emoji": "🏆"},
    "uc": {"name": "⚡ UC", "price": 99, "emoji": "⚡"},
    "event": {"name": "🎯 Event Pass", "price": 199, "emoji": "🎯"},
    "aqm": {"name": "💎 AQM Keys", "price": 299, "emoji": "💎"}
}

# Load categories from database
def load_categories():
    global KEY_CATEGORIES
    KEY_CATEGORIES = {}
    
    # Try to load from DB
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
        # Use defaults and save to DB
        KEY_CATEGORIES = DEFAULT_CATEGORIES.copy()
        for key, data in DEFAULT_CATEGORIES.items():
            categories_col.update_one(
                {"key": key},
                {"$set": {
                    "key": key,
                    "name": data['name'],
                    "price": data['price'],
                    "emoji": data['emoji'],
                    "description": "",
                    "status": "active"
                }},
                upsert=True
            )
    
    return KEY_CATEGORIES

# Load categories on startup
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
    
    # Key Management
    keyboard.add(
        KeyboardButton("➕ Add Key"),
        KeyboardButton("🗑 Remove Key")
    )
    keyboard.add(
        KeyboardButton("📋 Key List"),
        KeyboardButton("✏️ Edit Key Price")
    )
    keyboard.add(
        KeyboardButton("📦 Bulk Add Keys"),
        KeyboardButton("🔍 Search Key")
    )
    
    # Category Management (NEW)
    keyboard.add(
        KeyboardButton("📁 Manage Categories"),
        KeyboardButton("✏️ Edit Category Name")
    )
    
    # User Management
    keyboard.add(
        KeyboardButton("👥 Users List"),
        KeyboardButton("💰 User Balance")
    )
    keyboard.add(
        KeyboardButton("🚫 Ban User"),
        KeyboardButton("✅ Unban User")
    )
    keyboard.add(
        KeyboardButton("💬 Message User"),
        KeyboardButton("📊 User Stats")
    )
    
    # Financial
    keyboard.add(
        KeyboardButton("💸 Pending Recharges"),
        KeyboardButton("✅ Approve Recharge")
    )
    keyboard.add(
        KeyboardButton("💳 Deduct Balance"),
        KeyboardButton("➕ Add Balance")
    )
    keyboard.add(
        KeyboardButton("🎟 Coupons"),
        KeyboardButton("📈 Sales Report")
    )
    
    # Broadcast & Settings
    keyboard.add(
        KeyboardButton("📢 Broadcast"),
        KeyboardButton("📋 Admin Logs")
    )
    keyboard.add(
        KeyboardButton("⚙️ Settings"),
        KeyboardButton("🔄 Refresh Categories")  # NEW
    )
    keyboard.add(KeyboardButton("🔙 Main Menu"))
    
    return keyboard

def get_category_management_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📝 Edit Category Name"),
        KeyboardButton("💰 Edit Category Price")
    )
    keyboard.add(
        KeyboardButton("😊 Edit Category Emoji"),
        KeyboardButton("📄 Edit Description")
    )
    keyboard.add(
        KeyboardButton("➕ Add New Category"),
        KeyboardButton("🗑 Delete Category")
    )
    keyboard.add(KeyboardButton("🔙 Admin Panel"))
    return keyboard

def get_buy_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for key, data in KEY_CATEGORIES.items():
        keyboard.add(KeyboardButton(data['name']))
    keyboard.add(KeyboardButton("🔙 Main Menu"))
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

def get_user_info(user_id):
    user = users_col.find_one({"user_id": user_id}) or {}
    wallet = wallets_col.find_one({"user_id": user_id}) or {"balance": 0}
    orders = list(orders_col.find({"user_id": user_id}).sort("purchased_at", -1).limit(5))
    
    return {
        "user_id": user_id,
        "name": user.get("name", "Unknown"),
        "username": user.get("username", "No username"),
        "balance": wallet.get("balance", 0),
        "joined": user.get("joined_at", datetime.utcnow()),
        "total_purchases": user.get("total_purchases", 0),
        "total_spent": user.get("total_spent", 0),
        "recent_orders": orders
    }

def refresh_categories():
    """Reload categories from database"""
    global KEY_CATEGORIES
    KEY_CATEGORIES = load_categories()
    return KEY_CATEGORIES

# -----------------------
# MESSAGE HANDLERS
# -----------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_id = msg.from_user.id
    
    if is_user_banned(user_id):
        bot.reply_to(msg, "🚫 **You are banned from using this bot!**\nContact admin for support.")
        return
    
    ensure_user_exists(user_id, msg.from_user.first_name, msg.from_user.username)
    
    welcome_text = """
╔══════════════════╗
   🎮 **BGMI LODERS KEY SHOP** 🎮   
╚══════════════════╝

🔥 **Premium BGMI Keys Available:"""
    
    # Add dynamic categories
    for key, data in KEY_CATEGORIES.items():
        welcome_text += f"\n• {data['name']}"
    
    welcome_text += """
\n✨ **Features:**
• Instant Key Delivery
• Secure Payment
• 24/7 Support
• Best Prices

▰▰▰▰▰▰▰▰▰▰▰▰▰▰

📌 Use keyboard buttons below to navigate!
    """
    
    bot.send_message(
        user_id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "🔙 Main Menu")
def main_menu(msg):
    user_id = msg.from_user.id
    bot.send_message(
        user_id,
        "🏠 **Main Menu**\n\nChoose an option:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "🔙 Admin Panel" and is_admin(msg.from_user.id))
def back_to_admin(msg):
    show_admin_panel(msg)

# -----------------------
# USER HANDLERS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🛒 Buy Keys")
def buy_keys(msg):
    user_id = msg.from_user.id
    
    text = "🎮 **Select Key Category**\n\n"
    for key, data in KEY_CATEGORIES.items():
        count = keys_col.count_documents({"category": key, "status": "available"})
        desc = f" - {data['description']}" if data.get('description') else ""
        text += f"{data['emoji']} **{data['name']}**{desc}\n"
        text += f"   💰 Price: {format_currency(data['price'])}\n"
        text += f"   📦 Available: {count}\n\n"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_buy_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text in [data['name'] for data in KEY_CATEGORIES.values()])
def show_category_keys(msg):
    user_id = msg.from_user.id
    category_name = msg.text
    
    # Find category
    category = None
    cat_key = None
    price = 0
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == category_name:
            category = data
            cat_key = key
            price = data['price']
            break
    
    if not category:
        bot.send_message(user_id, "❌ Category not found!", reply_markup=get_buy_keyboard())
        return
    
    # Get available keys
    keys = list(keys_col.find({"category": cat_key, "status": "available"}).limit(10))
    
    if not keys:
        bot.send_message(
            user_id,
            f"❌ No {category['name']} keys available right now!\nCheck back later.",
            reply_markup=get_buy_keyboard()
        )
        return
    
    text = f"{category['emoji']} **{category['name']}**\n\n"
    if category.get('description'):
        text += f"📝 {category['description']}\n\n"
    text += f"💰 Price: {format_currency(price)} per key\n"
    text += f"📦 Available: {len(keys)}\n\n"
    text += "**Select key to purchase:**\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for i, key in enumerate(keys[:8], 1):
        markup.add(InlineKeyboardButton(
            f"Key #{i} - {format_currency(price)}",
            callback_data=f"buykey_{key['_id']}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "💰 Balance")
def show_balance(msg):
    user_id = msg.from_user.id
    balance = get_balance(user_id)
    user = users_col.find_one({"user_id": user_id}) or {}
    
    text = f"💰 **Your Wallet**\n\n"
    text += f"💳 Balance: {format_currency(balance)}\n"
    text += f"🛒 Total Purchases: {user.get('total_purchases', 0)}\n"
    text += f"📊 Total Spent: {format_currency(user.get('total_spent', 0))}\n\n"
    text += "💳 Recharge to buy more keys!"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "💳 Recharge")
def recharge(msg):
    user_id = msg.from_user.id
    
    text = "💳 **Recharge Wallet**\n\n"
    text += "Enter amount to recharge (minimum ₹10):\n"
    text += "Example: `100`"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    
    user_states[user_id] = "waiting_recharge_amount"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "waiting_recharge_amount")
def process_recharge_amount(msg):
    user_id = msg.from_user.id
    
    try:
        amount = float(msg.text.strip())
        if amount < 10:
            bot.send_message(
                user_id,
                "❌ Minimum recharge amount is ₹10!\nEnter amount again:",
                reply_markup=get_back_keyboard()
            )
            return
        
        upi_payment_states[user_id] = {
            "amount": amount,
            "step": "qr_shown"
        }
        
        user_states.pop(user_id, None)
        
        caption = f"""<blockquote>💳 <b>UPI Payment Details</b>

💰 Amount: {format_currency(amount)}
📱 UPI ID: <code>your_upi_id@okhdfcbank</code>
</blockquote>

<blockquote>📋 <b>Instructions:</b>
1. Send {format_currency(amount)} to above UPI ID
2. After payment, click **I HAVE PAID** button
3. Enter UTR number and send screenshot</blockquote>"""
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💰 I HAVE PAID", callback_data="upi_paid"))
        
        bot.send_photo(
            user_id,
            "https://files.catbox.moe/a310jr.jpg",
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
        
    except ValueError:
        bot.send_message(
            user_id,
            "❌ Invalid amount! Please enter numbers only:",
            reply_markup=get_back_keyboard()
        )

@bot.message_handler(func=lambda msg: msg.text == "🎁 Redeem Coupon")
def redeem_coupon(msg):
    user_id = msg.from_user.id
    
    text = "🎟 **Redeem Coupon**\n\nEnter your coupon code:"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    
    user_states[user_id] = "waiting_coupon"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "waiting_coupon")
def process_coupon(msg):
    user_id = msg.from_user.id
    code = msg.text.strip().upper()
    
    user_states.pop(user_id, None)
    
    coupon = coupons_col.find_one({"code": code, "status": "active"})
    
    if not coupon:
        bot.send_message(
            user_id,
            "❌ Invalid or expired coupon code!",
            reply_markup=get_main_keyboard()
        )
        return
    
    if user_id in coupon.get("used_by", []):
        bot.send_message(
            user_id,
            "❌ You have already used this coupon!",
            reply_markup=get_main_keyboard()
        )
        return
    
    if len(coupon.get("used_by", [])) >= coupon.get("max_uses", 1):
        bot.send_message(
            user_id,
            "❌ This coupon has reached maximum usage!",
            reply_markup=get_main_keyboard()
        )
        return
    
    amount = coupon.get("amount", 0)
    add_balance(user_id, amount)
    
    coupons_col.update_one(
        {"code": code},
        {
            "$push": {"used_by": user_id},
            "$inc": {"used_count": 1}
        }
    )
    
    transactions_col.insert_one({
        "user_id": user_id,
        "amount": amount,
        "type": "coupon",
        "coupon": code,
        "timestamp": datetime.utcnow()
    })
    
    new_balance = get_balance(user_id)
    
    bot.send_message(
        user_id,
        f"✅ **Coupon Redeemed Successfully!**\n\n"
        f"🎟 Code: `{code}`\n"
        f"💰 Amount Added: {format_currency(amount)}\n"
        f"💳 New Balance: {format_currency(new_balance)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "📞 Support")
def support(msg):
    user_id = msg.from_user.id
    
    text = "📞 **Support**\n\n"
    text += "👤 Admin: @YourAdminUsername\n"
    text += "📢 Channel: @YourChannel\n"
    text += "📧 Email: support@example.com\n\n"
    text += "For any issues, contact admin directly!"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ About")
def about(msg):
    user_id = msg.from_user.id
    
    total_keys = keys_col.count_documents({"status": "available"})
    total_users = users_col.count_documents({})
    total_sold = keys_col.count_documents({"status": "sold"})
    
    text = "ℹ️ **About Bot**\n\n"
    text += "🎮 **BGMI LODERS Key Shop**\n"
    text += "Version: 2.0\n\n"
    text += f"📊 **Stats:**\n"
    text += f"• Available Keys: {total_keys}\n"
    text += f"• Total Sold: {total_sold}\n"
    text += f"• Total Users: {total_users}\n"
    text += f"• Categories: {len(KEY_CATEGORIES)}\n\n"
    text += "🛡️ Secure | Fast | Reliable"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# -----------------------
# ADMIN HANDLERS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Panel")
def show_admin_panel(msg):
    user_id = msg.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Unauthorized access!")
        return
    
    # Get stats
    total_keys = keys_col.count_documents({})
    available_keys = keys_col.count_documents({"status": "available"})
    sold_keys = keys_col.count_documents({"status": "sold"})
    total_users = users_col.count_documents({})
    pending_recharges = recharges_col.count_documents({"status": "pending"})
    today_sales = keys_col.count_documents({
        "status": "sold",
        "sold_at": {"$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)}
    })
    
    # Calculate revenue
    pipeline = [
        {"$match": {"status": "sold"}},
        {"$group": {"_id": None, "total": {"$sum": "$price"}}}
    ]
    result = list(keys_col.aggregate(pipeline))
    total_revenue = result[0]['total'] if result else 0
    
    text = f"👑 **Admin Panel**\n\n"
    text += f"📊 **System Statistics:**\n"
    text += f"• Total Keys: {total_keys}\n"
    text += f"• Available: {available_keys}\n"
    text += f"• Sold: {sold_keys}\n"
    text += f"• Total Users: {total_users}\n"
    text += f"• Pending Recharges: {pending_recharges}\n"
    text += f"• Today's Sales: {today_sales}\n"
    text += f"• Total Revenue: {format_currency(total_revenue)}\n\n"
    text += f"📁 **Categories ({len(KEY_CATEGORIES)}):**\n"
    
    for key, data in KEY_CATEGORIES.items():
        cat_keys = keys_col.count_documents({"category": key})
        cat_available = keys_col.count_documents({"category": key, "status": "available"})
        text += f"• {data['emoji']} {data['name']}: {cat_available}/{cat_keys} keys\n"
    
    text += f"\n🛠️ **Management Tools:**\n"
    text += f"Use keyboard buttons below to manage the bot."
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )
    
    log_admin_action(user_id, "VIEW_ADMIN_PANEL", {})

# ======================
# CATEGORY MANAGEMENT (NEW)
# ======================
@bot.message_handler(func=lambda msg: msg.text == "📁 Manage Categories" and is_admin(msg.from_user.id))
def manage_categories(msg):
    user_id = msg.from_user.id
    
    text = "📁 **Category Management**\n\n"
    text += "**Current Categories:**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"   🔑 Key: `{key}`\n"
        text += f"   💰 Price: {format_currency(data['price'])}\n"
        if data.get('description'):
            text += f"   📝 Desc: {data['description']}\n"
        text += "\n"
    
    text += "**Options:**\n"
    text += "• Edit Category Name\n"
    text += "• Edit Category Price\n"
    text += "• Edit Category Emoji\n"
    text += "• Edit Description\n"
    text += "• Add New Category\n"
    text += "• Delete Category"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_category_management_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "✏️ Edit Category Name" and is_admin(msg.from_user.id))
def edit_category_name_start(msg):
    user_id = msg.from_user.id
    
    text = "✏️ **Edit Category Name**\n\n"
    text += "Select category to edit:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']}",
            callback_data=f"editcat_name_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "💰 Edit Category Price" and is_admin(msg.from_user.id))
def edit_category_price_start(msg):
    user_id = msg.from_user.id
    
    text = "💰 **Edit Category Price**\n\n"
    text += "Select category to edit price:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']} - {format_currency(data['price'])}",
            callback_data=f"editcat_price_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "😊 Edit Category Emoji" and is_admin(msg.from_user.id))
def edit_category_emoji_start(msg):
    user_id = msg.from_user.id
    
    text = "😊 **Edit Category Emoji**\n\n"
    text += "Select category to edit emoji:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']}",
            callback_data=f"editcat_emoji_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "📄 Edit Description" and is_admin(msg.from_user.id))
def edit_category_desc_start(msg):
    user_id = msg.from_user.id
    
    text = "📄 **Edit Category Description**\n\n"
    text += "Select category to edit description:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        desc = data.get('description', 'No description')[:20]
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']}",
            callback_data=f"editcat_desc_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "➕ Add New Category" and is_admin(msg.from_user.id))
def add_category_start(msg):
    user_id = msg.from_user.id
    
    text = "➕ **Add New Category**\n\n"
    text += "Please send the category details in this format:\n\n"
    text += "`key|name|price|emoji|description`\n\n"
    text += "**Example:**\n"
    text += "`uc|⚡ UC|99|⚡|Unknown Cash for BGMI`\n\n"
    text += "**Rules:**\n"
    text += "• Key: lowercase, no spaces (uc, weekend, etc.)\n"
    text += "• Name: Display name with emoji\n"
    text += "• Price: Number only\n"
    text += "• Emoji: Single emoji\n"
    text += "• Description: Optional"
    
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = "admin_add_category"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_add_category" and is_admin(msg.from_user.id))
def process_add_category(msg):
    user_id = msg.from_user.id
    text = msg.text.strip()
    
    try:
        parts = text.split('|')
        if len(parts) < 4:
            raise ValueError("Invalid format")
        
        key = parts[0].strip().lower()
        name = parts[1].strip()
        price = float(parts[2].strip())
        emoji = parts[3].strip()
        description = parts[4].strip() if len(parts) > 4 else ""
        
        if key in KEY_CATEGORIES:
            bot.send_message(user_id, f"❌ Category key '{key}' already exists!")
            return
        
        if price <= 0:
            bot.send_message(user_id, "❌ Price must be positive!")
            return
        
        # Save to database
        categories_col.insert_one({
            "key": key,
            "name": name,
            "price": price,
            "emoji": emoji,
            "description": description,
            "status": "active",
            "created_by": user_id,
            "created_at": datetime.utcnow()
        })
        
        # Refresh categories
        refresh_categories()
        
        bot.send_message(
            user_id,
            f"✅ **Category Added Successfully!**\n\n"
            f"Key: `{key}`\n"
            f"Name: {emoji} {name}\n"
            f"Price: {format_currency(price)}\n"
            f"Description: {description}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "ADD_CATEGORY", {
            "key": key,
            "name": name,
            "price": price
        })
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}\n\nPlease use correct format!")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "🗑 Delete Category" and is_admin(msg.from_user.id))
def delete_category_start(msg):
    user_id = msg.from_user.id
    
    text = "🗑 **Delete Category**\n\n"
    text += "⚠️ **Warning:** This will also delete all keys in this category!\n\n"
    text += "Select category to delete:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        key_count = keys_col.count_documents({"category": key})
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']} ({key_count} keys)",
            callback_data=f"delcat_confirm_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "🔄 Refresh Categories" and is_admin(msg.from_user.id))
def refresh_categories_handler(msg):
    user_id = msg.from_user.id
    
    old_count = len(KEY_CATEGORIES)
    refresh_categories()
    new_count = len(KEY_CATEGORIES)
    
    bot.send_message(
        user_id,
        f"✅ **Categories Refreshed!**\n\n"
        f"Previous: {old_count} categories\n"
        f"Current: {new_count} categories",
        parse_mode="Markdown"
    )
    
    log_admin_action(user_id, "REFRESH_CATEGORIES", {
        "old": old_count,
        "new": new_count
    })

# Key Management
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Key" and is_admin(msg.from_user.id))
def add_key_start(msg):
    user_id = msg.from_user.id
    
    text = "➕ **Add New Key**\n\n"
    text += "Select category:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']}",
            callback_data=f"addkey_cat_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "📦 Bulk Add Keys" and is_admin(msg.from_user.id))
def bulk_add_keys(msg):
    user_id = msg.from_user.id
    
    text = "📦 **Bulk Add Keys**\n\n"
    text += "Send keys in this format:\n"
    text += "`category:key1,key2,key3`\n\n"
    text += "Available Categories:\n"
    for key, data in KEY_CATEGORIES.items():
        text += f"• `{key}` - {data['emoji']} {data['name']}\n\n"
    text += "Example:\n"
    text += "`weekend:KEY123,KEY456,KEY789`\n"
    text += "`royalty:PASS1,PASS2`"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown"
    )
    
    user_states[user_id] = "admin_bulk_add"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_bulk_add" and is_admin(msg.from_user.id))
def process_bulk_add(msg):
    user_id = msg.from_user.id
    text = msg.text.strip()
    
    try:
        if ':' not in text:
            raise ValueError("Invalid format")
        
        category, keys_str = text.split(':', 1)
        category = category.strip().lower()
        
        if category not in KEY_CATEGORIES:
            bot.send_message(user_id, f"❌ Invalid category! Available: {', '.join(KEY_CATEGORIES.keys())}")
            return
        
        keys = [k.strip() for k in keys_str.split(',') if k.strip()]
        
        if not keys:
            bot.send_message(user_id, "❌ No keys provided!")
            return
        
        # Check for duplicates
        existing = keys_col.find({"key": {"$in": keys}})
        existing_keys = [k['key'] for k in existing]
        
        new_keys = [k for k in keys if k not in existing_keys]
        
        if new_keys:
            key_docs = []
            for key in new_keys:
                key_docs.append({
                    "key": key,
                    "category": category,
                    "price": KEY_CATEGORIES[category]['price'],
                    "status": "available",
                    "added_by": user_id,
                    "added_at": datetime.utcnow()
                })
            
            keys_col.insert_many(key_docs)
        
        text = f"✅ **Bulk Add Complete**\n\n"
        text += f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
        text += f"Total Provided: {len(keys)}\n"
        text += f"New Added: {len(new_keys)}\n"
        
        if existing_keys:
            text += f"\n⚠️ Duplicates skipped:\n"
            for k in existing_keys[:5]:
                text += f"• {k}\n"
            if len(existing_keys) > 5:
                text += f"• ... and {len(existing_keys)-5} more\n"
        
        bot.send_message(user_id, text)
        
        log_admin_action(user_id, "BULK_ADD_KEYS", {
            "category": category,
            "added": len(new_keys),
            "duplicates": len(existing_keys)
        })
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}\n\nPlease use correct format!")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "🗑 Remove Key" and is_admin(msg.from_user.id))
def remove_key_start(msg):
    user_id = msg.from_user.id
    
    text = "🗑 **Remove Key**\n\n"
    text += "Send the key code to remove:"
    
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = "admin_remove_key"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_remove_key" and is_admin(msg.from_user.id))
def process_key_removal(msg):
    user_id = msg.from_user.id
    key_code = msg.text.strip()
    
    key = keys_col.find_one({"key": key_code})
    
    if not key:
        bot.send_message(
            user_id,
            f"❌ Key `{key_code}` not found!",
            parse_mode="Markdown"
        )
    else:
        cat_name = KEY_CATEGORIES[key['category']]['name']
        keys_col.delete_one({"key": key_code})
        bot.send_message(
            user_id,
            f"✅ Key `{key_code}` removed successfully!\n"
            f"Category: {cat_name}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "REMOVE_KEY", {"key": key_code})
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "📋 Key List" and is_admin(msg.from_user.id))
def key_list(msg):
    user_id = msg.from_user.id
    
    text = "📋 **Key Inventory**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        available = keys_col.count_documents({"category": key, "status": "available"})
        sold = keys_col.count_documents({"category": key, "status": "sold"})
        total = available + sold
        
        # Get recent keys
        recent = list(keys_col.find(
            {"category": key, "status": "available"}
        ).sort("added_at", -1).limit(3))
        
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"   📦 Available: {available}\n"
        text += f"   ✅ Sold: {sold}\n"
        text += f"   📊 Total: {total}\n"
        
        if recent:
            text += f"   🔑 Recent Keys:\n"
            for k in recent:
                text += f"      • `{k['key'][:15]}...`\n"
        text += "\n"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "✏️ Edit Key Price" and is_admin(msg.from_user.id))
def edit_key_price(msg):
    user_id = msg.from_user.id
    
    text = "✏️ **Edit Key Price**\n\n"
    text += "Select category to edit price:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(
            f"{data['emoji']} {data['name']} - {format_currency(data['price'])}",
            callback_data=f"editprice_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "🔍 Search Key" and is_admin(msg.from_user.id))
def search_key(msg):
    user_id = msg.from_user.id
    
    text = "🔍 **Search Key**\n\n"
    text += "Enter key code to search:"
    
    bot.send_message(user_id, text)
    user_states[user_id] = "admin_search_key"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_search_key" and is_admin(msg.from_user.id))
def process_key_search(msg):
    user_id = msg.from_user.id
    key_code = msg.text.strip()
    
    key = keys_col.find_one({"key": key_code})
    
    if not key:
        bot.send_message(user_id, f"❌ Key `{key_code}` not found!")
    else:
        cat_name = KEY_CATEGORIES[key['category']]['name']
        status_emoji = "✅" if key['status'] == "available" else "💰" if key['status'] == "sold" else "❌"
        
        text = f"🔍 **Key Found**\n\n"
        text += f"Key: `{key['key']}`\n"
        text += f"Category: {cat_name}\n"
        text += f"Price: {format_currency(key['price'])}\n"
        text += f"Status: {status_emoji} {key['status'].upper()}\n"
        
        if key.get('sold_to'):
            user = users_col.find_one({"user_id": key['sold_to']}) or {}
            text += f"Sold To: {user.get('name', 'Unknown')} ({key['sold_to']})\n"
            text += f"Sold At: {key['sold_at'].strftime('%Y-%m-%d %H:%M')}\n"
        
        text += f"Added: {key['added_at'].strftime('%Y-%m-%d %H:%M')}"
        
        bot.send_message(user_id, text, parse_mode="Markdown")
    
    user_states.pop(user_id, None)

# User Management
@bot.message_handler(func=lambda msg: msg.text == "👥 Users List" and is_admin(msg.from_user.id))
def users_list(msg):
    user_id = msg.from_user.id
    
    total = users_col.count_documents({})
    active_today = users_col.count_documents({
        "joined_at": {"$gte": datetime.utcnow() - timedelta(days=1)}
    })
    
    text = f"👥 **Users List**\n\n"
    text += f"Total Users: {total}\n"
    text += f"New Today: {active_today}\n\n"
    
    # Recent users
    recent = list(users_col.find().sort("joined_at", -1).limit(10))
    
    if recent:
        text += "**Recent Users:**\n"
        for i, user in enumerate(recent, 1):
            wallet = wallets_col.find_one({"user_id": user['user_id']}) or {"balance": 0}
            name = user.get('name', 'Unknown')[:15]
            text += f"{i}. {name} - {format_currency(wallet['balance'])}\n"
            text += f"   ID: `{user['user_id']}`\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "💰 User Balance" and is_admin(msg.from_user.id))
def check_user_balance(msg):
    user_id = msg.from_user.id
    
    text = "💰 **Check User Balance**\n\nEnter User ID:"
    bot.send_message(user_id, text)
    user_states[user_id] = "admin_check_balance"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_check_balance" and is_admin(msg.from_user.id))
def process_balance_check(msg):
    user_id = msg.from_user.id
    
    try:
        target_id = int(msg.text.strip())
        user_info = get_user_info(target_id)
        
        text = f"👤 **User Information**\n\n"
        text += f"ID: `{target_id}`\n"
        text += f"Name: {user_info['name']}\n"
        text += f"Username: {user_info['username']}\n"
        text += f"Joined: {user_info['joined'].strftime('%Y-%m-%d')}\n\n"
        text += f"💰 Balance: {format_currency(user_info['balance'])}\n"
        text += f"🛒 Purchases: {user_info['total_purchases']}\n"
        text += f"📊 Total Spent: {format_currency(user_info['total_spent'])}\n\n"
        
        if user_info['recent_orders']:
            text += "**Recent Purchases:**\n"
            for order in user_info['recent_orders']:
                cat_name = KEY_CATEGORIES[order['category']]['name']
                text += f"• {cat_name} - {format_currency(order['price'])}\n"
                text += f"  {order['purchased_at'].strftime('%H:%M %d/%m')}\n"
        
        bot.send_message(user_id, text, parse_mode="Markdown")
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid User ID!")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "🚫 Ban User" and is_admin(msg.from_user.id))
def ban_user_start(msg):
    user_id = msg.from_user.id
    
    text = "🚫 **Ban User**\n\nEnter User ID to ban:"
    bot.send_message(user_id, text)
    user_states[user_id] = "admin_ban_user"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_ban_user" and is_admin(msg.from_user.id))
def process_ban(msg):
    user_id = msg.from_user.id
    
    try:
        target_id = int(msg.text.strip())
        
        if target_id == ADMIN_ID:
            bot.send_message(user_id, "❌ Cannot ban admin!")
            user_states.pop(user_id, None)
            return
        
        if not users_col.find_one({"user_id": target_id}):
            bot.send_message(user_id, "❌ User not found!")
            user_states.pop(user_id, None)
            return
        
        if is_user_banned(target_id):
            bot.send_message(user_id, "⚠️ User is already banned!")
            user_states.pop(user_id, None)
            return
        
        banned_users_col.insert_one({
            "user_id": target_id,
            "banned_by": user_id,
            "banned_at": datetime.utcnow(),
            "status": "active"
        })
        
        try:
            bot.send_message(
                target_id,
                "🚫 **You have been banned from using this bot!**\nContact admin for more information."
            )
        except:
            pass
        
        bot.send_message(user_id, f"✅ User {target_id} has been banned!")
        
        log_admin_action(user_id, "BAN_USER", {"target": target_id})
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid User ID!")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "✅ Unban User" and is_admin(msg.from_user.id))
def unban_user_start(msg):
    user_id = msg.from_user.id
    
    text = "✅ **Unban User**\n\nEnter User ID to unban:"
    bot.send_message(user_id, text)
    user_states[user_id] = "admin_unban_user"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_unban_user" and is_admin(msg.from_user.id))
def process_unban(msg):
    user_id = msg.from_user.id
    
    try:
        target_id = int(msg.text.strip())
        
        result = banned_users_col.update_one(
            {"user_id": target_id, "status": "active"},
            {"$set": {"status": "inactive", "unbanned_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            bot.send_message(user_id, f"✅ User {target_id} has been unbanned!")
            
            try:
                bot.send_message(
                    target_id,
                    "✅ **You have been unbanned!**\nYou can now use the bot again."
                )
            except:
                pass
            
            log_admin_action(user_id, "UNBAN_USER", {"target": target_id})
        else:
            bot.send_message(user_id, "❌ User not found or not banned!")
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid User ID!")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "💬 Message User" and is_admin(msg.from_user.id))
def message_user_start(msg):
    user_id = msg.from_user.id
    
    text = "💬 **Message User**\n\nEnter User ID:"
    bot.send_message(user_id, text)
    user_states[user_id] = "admin_message_userid"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_message_userid" and is_admin(msg.from_user.id))
def process_message_userid(msg):
    user_id = msg.from_user.id
    
    try:
        target_id = int(msg.text.strip())
        
        if not users_col.find_one({"user_id": target_id}):
            bot.send_message(user_id, "❌ User not found!")
            user_states.pop(user_id, None)
            return
        
        user_states[user_id] = {
            "step": "admin_message_content",
            "target_id": target_id
        }
        
        bot.send_message(user_id, f"📝 Now send the message for user {target_id}:")
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid User ID!")
        user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: isinstance(user_states.get(msg.from_user.id), dict) and 
                    user_states[msg.from_user.id].get("step") == "admin_message_content" and 
                    is_admin(msg.from_user.id),
                    content_types=['text', 'photo', 'video', 'document'])
def process_message_content(msg):
    user_id = msg.from_user.id
    target_id = user_states[user_id]["target_id"]
    
    try:
        if msg.content_type == 'text':
            bot.send_message(target_id, f"📨 **Message from Admin:**\n\n{msg.text}")
        elif msg.content_type == 'photo':
            bot.send_photo(target_id, msg.photo[-1].file_id, caption=f"📨 **Message from Admin:**\n\n{msg.caption or ''}")
        elif msg.content_type == 'video':
            bot.send_video(target_id, msg.video.file_id, caption=f"📨 **Message from Admin:**\n\n{msg.caption or ''}")
        elif msg.content_type == 'document':
            bot.send_document(target_id, msg.document.file_id, caption=f"📨 **Message from Admin:**\n\n{msg.caption or ''}")
        
        bot.send_message(user_id, f"✅ Message sent to user {target_id}!")
        
        log_admin_action(user_id, "MESSAGE_USER", {"target": target_id, "type": msg.content_type})
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Failed to send message: {str(e)}")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "📊 User Stats" and is_admin(msg.from_user.id))
def user_stats(msg):
    user_id = msg.from_user.id
    
    # Overall stats
    total_users = users_col.count_documents({})
    users_with_balance = wallets_col.count_documents({"balance": {"$gt": 0}})
    
    # Users by join date
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    joined_today = users_col.count_documents({"joined_at": {"$gte": today}})
    joined_week = users_col.count_documents({"joined_at": {"$gte": today - timedelta(days=7)}})
    joined_month = users_col.count_documents({"joined_at": {"$gte": today - timedelta(days=30)}})
    
    # Top users
    top_users = list(wallets_col.find().sort("balance", -1).limit(5))
    
    text = f"📊 **User Statistics**\n\n"
    text += f"**Overview:**\n"
    text += f"• Total Users: {total_users}\n"
    text += f"• With Balance: {users_with_balance}\n\n"
    
    text += f"**New Users:**\n"
    text += f"• Today: {joined_today}\n"
    text += f"• This Week: {joined_week}\n"
    text += f"• This Month: {joined_month}\n\n"
    
    if top_users:
        text += f"**Top Users by Balance:**\n"
        for i, wallet in enumerate(top_users, 1):
            user = users_col.find_one({"user_id": wallet['user_id']}) or {}
            name = user.get('name', 'Unknown')[:15]
            text += f"{i}. {name} - {format_currency(wallet['balance'])}\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

# Financial Management
@bot.message_handler(func=lambda msg: msg.text == "💸 Pending Recharges" and is_admin(msg.from_user.id))
def pending_recharges(msg):
    user_id = msg.from_user.id
    
    pending = list(recharges_col.find({"status": "pending"}).sort("created_at", -1).limit(10))
    
    if not pending:
        bot.send_message(user_id, "✅ No pending recharge requests!")
        return
    
    text = "💸 **Pending Recharge Requests**\n\n"
    
    for req in pending:
        text += f"ID: `{req['_id']}`\n"
        text += f"User: {req['user_id']}\n"
        text += f"Amount: {format_currency(req['amount'])}\n"
        text += f"UTR: {req.get('utr', 'N/A')}\n"
        text += f"Time: {req['created_at'].strftime('%H:%M %d/%m')}\n"
        text += f"━━━━━━━━━━━━━━━━\n\n"
    
    text += "Use /approve [request_id] to approve\n"
    text += "Example: /approve 65f8a1b2c3d4e5f6a7b8c9d0"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "✅ Approve Recharge" and is_admin(msg.from_user.id))
def approve_recharge_prompt(msg):
    user_id = msg.from_user.id
    
    text = "✅ **Approve Recharge**\n\n"
    text += "Send the request ID to approve:\n"
    text += "Example: `65f8a1b2c3d4e5f6a7b8c9d0`"
    
    bot.send_message(user_id, text)
    user_states[user_id] = "admin_approve_recharge"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_approve_recharge" and is_admin(msg.from_user.id))
def process_recharge_approval(msg):
    user_id = msg.from_user.id
    
    try:
        req_id = ObjectId(msg.text.strip())
        req = recharges_col.find_one({"_id": req_id, "status": "pending"})
        
        if not req:
            bot.send_message(user_id, "❌ Request not found or already processed!")
            user_states.pop(user_id, None)
            return
        
        # Add balance
        add_balance(req['user_id'], req['amount'])
        
        # Update user stats
        users_col.update_one(
            {"user_id": req['user_id']},
            {"$inc": {"total_recharged": req['amount']}}
        )
        
        # Update request
        recharges_col.update_one(
            {"_id": req_id},
            {"$set": {
                "status": "approved",
                "approved_by": user_id,
                "approved_at": datetime.utcnow()
            }}
        )
        
        # Record transaction
        transactions_col.insert_one({
            "user_id": req['user_id'],
            "amount": req['amount'],
            "type": "recharge",
            "method": "upi",
            "utr": req.get('utr'),
            "approved_by": user_id,
            "timestamp": datetime.utcnow()
        })
        
        # Notify user
        try:
            bot.send_message(
                req['user_id'],
                f"✅ **Recharge Approved!**\n\n"
                f"💰 Amount: {format_currency(req['amount'])}\n"
                f"💳 New Balance: {format_currency(get_balance(req['user_id']))}\n\n"
                f"Thank you for your payment!",
                parse_mode="Markdown"
            )
        except:
            pass
        
        bot.send_message(user_id, f"✅ Recharge approved for user {req['user_id']}!")
        
        log_admin_action(user_id, "APPROVE_RECHARGE", {
            "user": req['user_id'],
            "amount": req['amount'],
            "utr": req.get('utr')
        })
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")
    
    user_states.pop(user_id, None)

@bot.message_handler(commands=['approve'])
def handle_approve_command(msg):
    if not is_admin(msg.from_user.id):
        return
    
    parts = msg.text.split()
    if len(parts) != 2:
        bot.reply_to(msg, "❌ Usage: /approve [request_id]")
        return
    
    try:
        req_id = ObjectId(parts[1])
        req = recharges_col.find_one({"_id": req_id, "status": "pending"})
        
        if not req:
            bot.reply_to(msg, "❌ Request not found or already processed!")
            return
        
        # Add balance
        add_balance(req['user_id'], req['amount'])
        
        # Update user stats
        users_col.update_one(
            {"user_id": req['user_id']},
            {"$inc": {"total_recharged": req['amount']}}
        )
        
        # Update request
        recharges_col.update_one(
            {"_id": req_id},
            {"$set": {
                "status": "approved",
                "approved_by": msg.from_user.id,
                "approved_at": datetime.utcnow()
            }}
        )
        
        # Record transaction
        transactions_col.insert_one({
            "user_id": req['user_id'],
            "amount": req['amount'],
            "type": "recharge",
            "method": "upi",
            "utr": req.get('utr'),
            "approved_by": msg.from_user.id,
            "timestamp": datetime.utcnow()
        })
        
        # Notify user
        try:
            bot.send_message(
                req['user_id'],
                f"✅ **Recharge Approved!**\n\n"
                f"💰 Amount: {format_currency(req['amount'])}\n"
                f"💳 New Balance: {format_currency(get_balance(req['user_id']))}",
                parse_mode="Markdown"
            )
        except:
            pass
        
        bot.reply_to(msg, f"✅ Recharge approved for user {req['user_id']}!")
        
        log_admin_action(msg.from_user.id, "APPROVE_RECHARGE", {
            "user": req['user_id'],
            "amount": req['amount']
        })
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.text == "💳 Deduct Balance" and is_admin(msg.from_user.id))
def deduct_balance_start(msg):
    user_id = msg.from_user.id
    
    text = "💳 **Deduct Balance**\n\nEnter User ID:"
    bot.send_message(user_id, text)
    admin_deduct_state[user_id] = {"step": "user_id"}

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_deduct_state)
def process_deduct_flow(msg):
    user_id = msg.from_user.id
    state = admin_deduct_state[user_id]
    
    if state["step"] == "user_id":
        try:
            target_id = int(msg.text.strip())
            user = users_col.find_one({"user_id": target_id})
            
            if not user:
                bot.send_message(user_id, "❌ User not found!")
                admin_deduct_state.pop(user_id, None)
                return
            
            current_balance = get_balance(target_id)
            
            state["target_id"] = target_id
            state["current_balance"] = current_balance
            state["step"] = "amount"
            
            bot.send_message(
                user_id,
                f"👤 User: {target_id}\n"
                f"💰 Current Balance: {format_currency(current_balance)}\n\n"
                f"Enter amount to deduct:"
            )
            
        except ValueError:
            bot.send_message(user_id, "❌ Invalid User ID!")
            admin_deduct_state.pop(user_id, None)
    
    elif state["step"] == "amount":
        try:
            amount = float(msg.text.strip())
            
            if amount <= 0:
                bot.send_message(user_id, "❌ Amount must be positive!")
                return
            
            if amount > state["current_balance"]:
                bot.send_message(
                    user_id,
                    f"❌ Amount exceeds balance ({format_currency(state['current_balance'])})!"
                )
                return
            
            state["amount"] = amount
            state["step"] = "reason"
            
            bot.send_message(user_id, "Enter reason for deduction:")
            
        except ValueError:
            bot.send_message(user_id, "❌ Invalid amount!")
    
    elif state["step"] == "reason":
        reason = msg.text.strip()
        
        if not reason:
            bot.send_message(user_id, "❌ Reason cannot be empty!")
            return
        
        # Process deduction
        deduct_balance(state["target_id"], state["amount"])
        new_balance = get_balance(state["target_id"])
        
        # Record transaction
        transactions_col.insert_one({
            "user_id": state["target_id"],
            "amount": state["amount"],
            "type": "deduction",
            "reason": reason,
            "admin_id": user_id,
            "old_balance": state["current_balance"],
            "new_balance": new_balance,
            "timestamp": datetime.utcnow()
        })
        
        # Notify user
        try:
            bot.send_message(
                state["target_id"],
                f"⚠️ **Balance Deducted**\n\n"
                f"💰 Amount: {format_currency(state['amount'])}\n"
                f"📝 Reason: {reason}\n"
                f"💳 New Balance: {format_currency(new_balance)}"
            )
        except:
            pass
        
        bot.send_message(
            user_id,
            f"✅ **Balance Deducted!**\n\n"
            f"User: {state['target_id']}\n"
            f"Amount: {format_currency(state['amount'])}\n"
            f"Reason: {reason}\n"
            f"Old Balance: {format_currency(state['current_balance'])}\n"
            f"New Balance: {format_currency(new_balance)}"
        )
        
        log_admin_action(user_id, "DEDUCT_BALANCE", {
            "target": state['target_id'],
            "amount": state['amount'],
            "reason": reason
        })
        
        admin_deduct_state.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "➕ Add Balance" and is_admin(msg.from_user.id))
def add_balance_start(msg):
    user_id = msg.from_user.id
    
    text = "➕ **Add Balance**\n\nEnter User ID:"
    bot.send_message(user_id, text)
    admin_deduct_state[user_id] = {"step": "add_user_id"}  # Reusing state dict

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_deduct_state and 
                    admin_deduct_state[msg.from_user.id].get("step") == "add_user_id")
def process_add_balance_user(msg):
    user_id = msg.from_user.id
    state = admin_deduct_state[user_id]
    
    try:
        target_id = int(msg.text.strip())
        user = users_col.find_one({"user_id": target_id})
        
        if not user:
            bot.send_message(user_id, "❌ User not found!")
            admin_deduct_state.pop(user_id, None)
            return
        
        current_balance = get_balance(target_id)
        
        state["target_id"] = target_id
        state["current_balance"] = current_balance
        state["step"] = "add_amount"
        
        bot.send_message(
            user_id,
            f"👤 User: {target_id}\n"
            f"💰 Current Balance: {format_currency(current_balance)}\n\n"
            f"Enter amount to add:"
        )
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid User ID!")
        admin_deduct_state.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_deduct_state and 
                    admin_deduct_state[msg.from_user.id].get("step") == "add_amount")
def process_add_amount(msg):
    user_id = msg.from_user.id
    state = admin_deduct_state[user_id]
    
    try:
        amount = float(msg.text.strip())
        
        if amount <= 0:
            bot.send_message(user_id, "❌ Amount must be positive!")
            return
        
        state["amount"] = amount
        state["step"] = "add_reason"
        
        bot.send_message(user_id, "Enter reason for adding balance:")
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid amount!")

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_deduct_state and 
                    admin_deduct_state[msg.from_user.id].get("step") == "add_reason")
def process_add_reason(msg):
    user_id = msg.from_user.id
    state = admin_deduct_state[user_id]
    
    reason = msg.text.strip()
    
    if not reason:
        bot.send_message(user_id, "❌ Reason cannot be empty!")
        return
    
    # Process addition
    add_balance(state["target_id"], state["amount"])
    new_balance = get_balance(state["target_id"])
    
    # Record transaction
    transactions_col.insert_one({
        "user_id": state["target_id"],
        "amount": state["amount"],
        "type": "admin_add",
        "reason": reason,
        "admin_id": user_id,
        "old_balance": state["current_balance"],
        "new_balance": new_balance,
        "timestamp": datetime.utcnow()
    })
    
    # Notify user
    try:
        bot.send_message(
            state["target_id"],
            f"✅ **Balance Added by Admin**\n\n"
            f"💰 Amount: {format_currency(state['amount'])}\n"
            f"📝 Reason: {reason}\n"
            f"💳 New Balance: {format_currency(new_balance)}"
        )
    except:
        pass
    
    bot.send_message(
        user_id,
        f"✅ **Balance Added!**\n\n"
        f"User: {state['target_id']}\n"
        f"Amount: {format_currency(state['amount'])}\n"
        f"Reason: {reason}\n"
        f"Old Balance: {format_currency(state['current_balance'])}\n"
        f"New Balance: {format_currency(new_balance)}"
    )
    
    log_admin_action(user_id, "ADD_BALANCE", {
        "target": state['target_id'],
        "amount": state['amount'],
        "reason": reason
    })
    
    admin_deduct_state.pop(user_id, None)

# Coupon Management
@bot.message_handler(func=lambda msg: msg.text == "🎟 Coupons" and is_admin(msg.from_user.id))
def coupon_management(msg):
    user_id = msg.from_user.id
    
    text = "🎟 **Coupon Management**\n\n"
    text += "**Commands:**\n"
    text += "• /createcoupon [code] [amount] [max_uses]\n"
    text += "• /deletecoupon [code]\n"
    text += "• /couponlist\n\n"
    text += "**Examples:**\n"
    text += "• `/createcoupon WELCOME10 10 50`\n"
    text += "• `/createcoupon DIWALI50 50 100`\n"
    text += "• `/deletecoupon WELCOME10`\n\n"
    
    # Show active coupons
    active = list(coupons_col.find({"status": "active"}).sort("created_at", -1).limit(5))
    
    if active:
        text += "**Recent Active Coupons:**\n"
        for c in active:
            used = len(c.get('used_by', []))
            text += f"• `{c['code']}` - {format_currency(c['amount'])} ({used}/{c['max_uses']})\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

@bot.message_handler(commands=['createcoupon'])
def create_coupon(msg):
    if not is_admin(msg.from_user.id):
        return
    
    parts = msg.text.split()
    if len(parts) != 4:
        bot.reply_to(msg, "❌ Usage: /createcoupon [code] [amount] [max_uses]")
        return
    
    code = parts[1].upper()
    
    try:
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
            "used_count": 0,
            "used_by": [],
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
        
        log_admin_action(msg.from_user.id, "CREATE_COUPON", {
            "code": code,
            "amount": amount,
            "max_uses": max_uses
        })
        
    except ValueError:
        bot.reply_to(msg, "❌ Invalid amount or max uses!")

@bot.message_handler(commands=['deletecoupon'])
def delete_coupon(msg):
    if not is_admin(msg.from_user.id):
        return
    
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

@bot.message_handler(commands=['couponlist'])
def coupon_list(msg):
    if not is_admin(msg.from_user.id):
        return
    
    coupons = list(coupons_col.find({"status": "active"}).sort("created_at", -1))
    
    if not coupons:
        bot.reply_to(msg, "📭 No active coupons!")
        return
    
    text = "🎟 **Active Coupons**\n\n"
    for coupon in coupons:
        used = len(coupon.get('used_by', []))
        text += f"• `{coupon['code']}`\n"
        text += f"  Amount: {format_currency(coupon['amount'])}\n"
        text += f"  Used: {used}/{coupon['max_uses']}\n"
        text += f"  Created: {coupon['created_at'].strftime('%d/%m')}\n\n"
    
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# Sales Report
@bot.message_handler(func=lambda msg: msg.text == "📈 Sales Report" and is_admin(msg.from_user.id))
def sales_report(msg):
    user_id = msg.from_user.id
    
    # Today's sales
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = list(keys_col.find({
        "status": "sold",
        "sold_at": {"$gte": today_start}
    }))
    
    today_count = len(today_sales)
    today_revenue = sum(k.get('price', 0) for k in today_sales)
    
    # Week's sales
    week_start = today_start - timedelta(days=7)
    week_sales = keys_col.count_documents({
        "status": "sold",
        "sold_at": {"$gte": week_start}
    })
    
    # Month's sales
    month_start = today_start - timedelta(days=30)
    month_sales = keys_col.count_documents({
        "status": "sold",
        "sold_at": {"$gte": month_start}
    })
    
    # Category breakdown
    text = f"📈 **Sales Report**\n\n"
    text += f"**Today:**\n"
    text += f"• Keys Sold: {today_count}\n"
    text += f"• Revenue: {format_currency(today_revenue)}\n\n"
    
    text += f"**This Week:**\n"
    text += f"• Keys Sold: {week_sales}\n\n"
    
    text += f"**This Month:**\n"
    text += f"• Keys Sold: {month_sales}\n\n"
    
    text += f"**Category Breakdown (Today):**\n"
    for key, data in KEY_CATEGORIES.items():
        cat_sales = [k for k in today_sales if k['category'] == key]
        if cat_sales:
            cat_revenue = sum(k['price'] for k in cat_sales)
            text += f"• {data['emoji']} {data['name']}: {len(cat_sales)} keys - {format_currency(cat_revenue)}\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

# Broadcast
@bot.message_handler(func=lambda msg: msg.text == "📢 Broadcast" and is_admin(msg.from_user.id))
def broadcast_start(msg):
    user_id = msg.from_user.id
    
    text = "📢 **Broadcast Message**\n\n"
    text += "Send the message you want to broadcast to all users.\n"
    text += "You can send text, photo, video, or document."
    
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = "admin_broadcast"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_broadcast" and is_admin(msg.from_user.id),
                    content_types=['text', 'photo', 'video', 'document'])
def process_broadcast(msg):
    user_id = msg.from_user.id
    
    bot.send_message(user_id, "📡 Broadcasting started... Please wait.")
    
    users = list(users_col.find())
    sent = 0
    failed = 0
    
    for user in users:
        uid = user.get('user_id')
        if not uid or uid == ADMIN_ID:
            continue
        
        try:
            if msg.content_type == 'text':
                bot.send_message(uid, f"📢 **Broadcast**\n\n{msg.text}")
            elif msg.content_type == 'photo':
                bot.send_photo(uid, msg.photo[-1].file_id, caption=f"📢 **Broadcast**\n\n{msg.caption or ''}")
            elif msg.content_type == 'video':
                bot.send_video(uid, msg.video.file_id, caption=f"📢 **Broadcast**\n\n{msg.caption or ''}")
            elif msg.content_type == 'document':
                bot.send_document(uid, msg.document.file_id, caption=f"📢 **Broadcast**\n\n{msg.caption or ''}")
            
            sent += 1
            if sent % 25 == 0:
                time.sleep(1)
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {uid}: {e}")
    
    bot.send_message(
        user_id,
        f"✅ **Broadcast Complete**\n\n"
        f"📊 **Stats:**\n"
        f"• Sent: {sent}\n"
        f"• Failed: {failed}\n"
        f"• Total: {len(users)}",
        parse_mode="Markdown"
    )
    
    log_admin_action(user_id, "BROADCAST", {
        "type": msg.content_type,
        "sent": sent,
        "failed": failed
    })
    
    user_states.pop(user_id, None)

# Admin Logs
@bot.message_handler(func=lambda msg: msg.text == "📋 Admin Logs" and is_admin(msg.from_user.id))
def admin_logs(msg):
    user_id = msg.from_user.id
    
    logs = list(admin_logs_col.find().sort("timestamp", -1).limit(20))
    
    if not logs:
        bot.send_message(user_id, "📭 No admin logs found!")
        return
    
    text = "📋 **Recent Admin Actions**\n\n"
    for log in logs:
        action = log['action']
        time = log['timestamp'].strftime('%H:%M %d/%m')
        text += f"• {time} - {action}\n"
        if log.get('details'):
            details = str(log['details'])[:50]
            text += f"  {details}\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

# Settings
@bot.message_handler(func=lambda msg: msg.text == "⚙️ Settings" and is_admin(msg.from_user.id))
def settings(msg):
    user_id = msg.from_user.id
    
    text = "⚙️ **Bot Settings**\n\n"
    text += f"**Current Categories ({len(KEY_CATEGORIES)}):**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"   🔑 Key: `{key}`\n"
        text += f"   💰 Price: {format_currency(data['price'])}\n"
        text += f"   📝 Desc: {data.get('description', 'No description')}\n\n"
    
    text += "**Commands:**\n"
    text += "• /setprice [category] [amount] - Change price\n"
    text += "• /setname [category] [name] - Change name\n"
    text += "• /setemoji [category] [emoji] - Change emoji\n"
    text += "• /setdesc [category] [description] - Set description\n\n"
    
    text += "**Examples:**\n"
    text += "• /setprice weekend 59\n"
    text += "• /setname weekend Weekend Challenge 2024\n"
    text += "• /setemoji weekend 🎯\n"
    text += "• /setdesc weekend Weekend challenge keys for BGMI"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

# Category Edit Commands
@bot.message_handler(commands=['setprice'])
def set_price(msg):
    if not is_admin(msg.from_user.id):
        return
    
    parts = msg.text.split(maxsplit=2)
    if len(parts) != 3:
        bot.reply_to(msg, "❌ Usage: /setprice [category] [amount]")
        return
    
    category = parts[1].lower()
    
    try:
        amount = float(parts[2])
        
        if category not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Invalid category! Available: {', '.join(KEY_CATEGORIES.keys())}")
            return
        
        if amount <= 0:
            bot.reply_to(msg, "❌ Price must be positive!")
            return
        
        # Update in database
        old_price = KEY_CATEGORIES[category]['price']
        
        categories_col.update_one(
            {"key": category},
            {"$set": {"price": amount}}
        )
        
        # Update in memory
        KEY_CATEGORIES[category]['price'] = amount
        
        # Update all unsold keys
        keys_col.update_many(
            {"category": category, "status": "available"},
            {"$set": {"price": amount}}
        )
        
        bot.reply_to(
            msg,
            f"✅ **Price Updated!**\n\n"
            f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
            f"Old Price: {format_currency(old_price)}\n"
            f"New Price: {format_currency(amount)}",
            parse_mode="Markdown"
        )
        
        log_admin_action(msg.from_user.id, "SET_PRICE", {
            "category": category,
            "old": old_price,
            "new": amount
        })
        
    except ValueError:
        bot.reply_to(msg, "❌ Invalid amount!")

@bot.message_handler(commands=['setname'])
def set_name(msg):
    if not is_admin(msg.from_user.id):
        return
    
    parts = msg.text.split(maxsplit=2)
    if len(parts) != 3:
        bot.reply_to(msg, "❌ Usage: /setname [category] [new name]")
        return
    
    category = parts[1].lower()
    new_name = parts[2].strip()
    
    if category not in KEY_CATEGORIES:
        bot.reply_to(msg, f"❌ Invalid category! Available: {', '.join(KEY_CATEGORIES.keys())}")
        return
    
    if not new_name:
        bot.reply_to(msg, "❌ Name cannot be empty!")
        return
    
    # Update in database
    old_name = KEY_CATEGORIES[category]['name']
    
    categories_col.update_one(
        {"key": category},
        {"$set": {"name": new_name}}
    )
    
    # Update in memory
    KEY_CATEGORIES[category]['name'] = new_name
    
    bot.reply_to(
        msg,
        f"✅ **Name Updated!**\n\n"
        f"Category: {KEY_CATEGORIES[category]['emoji']}\n"
        f"Old Name: {old_name}\n"
        f"New Name: {new_name}",
        parse_mode="Markdown"
    )
    
    log_admin_action(msg.from_user.id, "SET_NAME", {
        "category": category,
        "old": old_name,
        "new": new_name
    })

@bot.message_handler(commands=['setemoji'])
def set_emoji(msg):
    if not is_admin(msg.from_user.id):
        return
    
    parts = msg.text.split(maxsplit=2)
    if len(parts) != 3:
        bot.reply_to(msg, "❌ Usage: /setemoji [category] [emoji]")
        return
    
    category = parts[1].lower()
    new_emoji = parts[2].strip()
    
    if category not in KEY_CATEGORIES:
        bot.reply_to(msg, f"❌ Invalid category! Available: {', '.join(KEY_CATEGORIES.keys())}")
        return
    
    if not new_emoji:
        bot.reply_to(msg, "❌ Emoji cannot be empty!")
        return
    
    # Update in database
    old_emoji = KEY_CATEGORIES[category]['emoji']
    
    categories_col.update_one(
        {"key": category},
        {"$set": {"emoji": new_emoji}}
    )
    
    # Update in memory
    KEY_CATEGORIES[category]['emoji'] = new_emoji
    
    bot.reply_to(
        msg,
        f"✅ **Emoji Updated!**\n\n"
        f"Category: {KEY_CATEGORIES[category]['name']}\n"
        f"Old Emoji: {old_emoji}\n"
        f"New Emoji: {new_emoji}",
        parse_mode="Markdown"
    )
    
    log_admin_action(msg.from_user.id, "SET_EMOJI", {
        "category": category,
        "old": old_emoji,
        "new": new_emoji
    })

@bot.message_handler(commands=['setdesc'])
def set_description(msg):
    if not is_admin(msg.from_user.id):
        return
    
    parts = msg.text.split(maxsplit=2)
    if len(parts) != 3:
        bot.reply_to(msg, "❌ Usage: /setdesc [category] [description]")
        return
    
    category = parts[1].lower()
    description = parts[2].strip()
    
    if category not in KEY_CATEGORIES:
        bot.reply_to(msg, f"❌ Invalid category! Available: {', '.join(KEY_CATEGORIES.keys())}")
        return
    
    # Update in database
    old_desc = KEY_CATEGORIES[category].get('description', '')
    
    categories_col.update_one(
        {"key": category},
        {"$set": {"description": description}}
    )
    
    # Update in memory
    KEY_CATEGORIES[category]['description'] = description
    
    bot.reply_to(
        msg,
        f"✅ **Description Updated!**\n\n"
        f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
        f"Old: {old_desc or 'None'}\n"
        f"New: {description}",
        parse_mode="Markdown"
    )
    
    log_admin_action(msg.from_user.id, "SET_DESCRIPTION", {
        "category": category,
        "old": old_desc,
        "new": description
    })

# -----------------------
# CALLBACK HANDLERS
# -----------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    if is_user_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 You are banned!", show_alert=True)
        return
    
    # Category Edit Callbacks
    if data.startswith("editcat_name_"):
        category = data.replace("editcat_name_", "")
        
        bot.edit_message_text(
            f"✏️ Enter new name for {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}:",
            call.message.chat.id,
            call.message.message_id
        )
        
        edit_category_state[user_id] = {
            "category": category,
            "type": "name",
            "step": "waiting_input"
        }
        bot.answer_callback_query(call.id)
    
    elif data.startswith("editcat_price_"):
        category = data.replace("editcat_price_", "")
        
        bot.edit_message_text(
            f"💰 Enter new price for {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}:\n"
            f"Current: {format_currency(KEY_CATEGORIES[category]['price'])}",
            call.message.chat.id,
            call.message.message_id
        )
        
        edit_category_state[user_id] = {
            "category": category,
            "type": "price",
            "step": "waiting_input"
        }
        bot.answer_callback_query(call.id)
    
    elif data.startswith("editcat_emoji_"):
        category = data.replace("editcat_emoji_", "")
        
        bot.edit_message_text(
            f"😊 Enter new emoji for {KEY_CATEGORIES[category]['name']}:\n"
            f"Current: {KEY_CATEGORIES[category]['emoji']}",
            call.message.chat.id,
            call.message.message_id
        )
        
        edit_category_state[user_id] = {
            "category": category,
            "type": "emoji",
            "step": "waiting_input"
        }
        bot.answer_callback_query(call.id)
    
    elif data.startswith("editcat_desc_"):
        category = data.replace("editcat_desc_", "")
        
        current_desc = KEY_CATEGORIES[category].get('description', 'No description')
        bot.edit_message_text(
            f"📄 Enter new description for {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}:\n\n"
            f"Current: {current_desc}",
            call.message.chat.id,
            call.message.message_id
        )
        
        edit_category_state[user_id] = {
            "category": category,
            "type": "description",
            "step": "waiting_input"
        }
        bot.answer_callback_query(call.id)
    
    elif data.startswith("delcat_confirm_"):
        category = data.replace("delcat_confirm_", "")
        
        # Ask for confirmation
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ Yes, Delete", callback_data=f"delcat_yes_{category}"),
            InlineKeyboardButton("❌ No, Cancel", callback_data="delcat_no")
        )
        
        key_count = keys_col.count_documents({"category": category})
        
        bot.edit_message_text(
            f"⚠️ **Confirm Delete**\n\n"
            f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
            f"Keys in this category: {key_count}\n\n"
            f"Are you sure you want to delete this category?\n"
            f"This will also delete all {key_count} keys in this category!",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)
    
    elif data.startswith("delcat_yes_"):
        category = data.replace("delcat_yes_", "")
        
        # Delete all keys in this category
        keys_deleted = keys_col.delete_many({"category": category}).deleted_count
        
        # Delete category from database
        categories_col.delete_one({"key": category})
        
        # Remove from memory
        category_name = KEY_CATEGORIES[category]['name']
        del KEY_CATEGORIES[category]
        
        bot.edit_message_text(
            f"✅ **Category Deleted!**\n\n"
            f"Category: {category_name}\n"
            f"Keys Deleted: {keys_deleted}\n\n"
            f"The category has been removed successfully.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "DELETE_CATEGORY", {
            "category": category,
            "name": category_name,
            "keys_deleted": keys_deleted
        })
        
        bot.answer_callback_query(call.id, "✅ Category deleted!")
    
    elif data == "delcat_no":
        bot.edit_message_text(
            "❌ Deletion cancelled.",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "Cancelled")
    
    # Add Key callback
    elif data.startswith("addkey_cat_"):
        category = data.replace("addkey_cat_", "")
        
        admin_add_key_state[user_id] = {
            "category": category,
            "step": "waiting_key"
        }
        
        bot.edit_message_text(
            f"📝 Enter key for {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}:\n\n"
            f"Send the key code/link:",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id)
    
    # Edit Price callback
    elif data.startswith("editprice_"):
        category = data.replace("editprice_", "")
        
        bot.edit_message_text(
            f"✏️ Enter new price for {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}:\n"
            f"Current: {format_currency(KEY_CATEGORIES[category]['price'])}",
            call.message.chat.id,
            call.message.message_id
        )
        
        edit_key_state[user_id] = {
            "category": category,
            "step": "waiting_price"
        }
        bot.answer_callback_query(call.id)
    
    # Buy Key callback
    elif data.startswith("buykey_"):
        key_id = data.replace("buykey_", "")
        
        try:
            key = keys_col.find_one({"_id": ObjectId(key_id), "status": "available"})
            
            if not key:
                bot.answer_callback_query(call.id, "❌ Key not available!", show_alert=True)
                bot.delete_message(call.message.chat.id, call.message.message_id)
                return
            
            price = key['price']
            balance = get_balance(user_id)
            
            if balance < price:
                bot.answer_callback_query(
                    call.id,
                    f"❌ Insufficient balance! Need {format_currency(price)}",
                    show_alert=True
                )
                return
            
            # Process purchase
            deduct_balance(user_id, price)
            
            # Update user stats
            users_col.update_one(
                {"user_id": user_id},
                {
                    "$inc": {
                        "total_purchases": 1,
                        "total_spent": price
                    }
                }
            )
            
            # Mark key as sold
            keys_col.update_one(
                {"_id": ObjectId(key_id)},
                {"$set": {
                    "status": "sold",
                    "sold_to": user_id,
                    "sold_at": datetime.utcnow()
                }}
            )
            
            # Record order
            orders_col.insert_one({
                "user_id": user_id,
                "key_id": key_id,
                "key": key['key'],
                "category": key['category'],
                "price": price,
                "purchased_at": datetime.utcnow()
            })
            
            # Send key to user
            cat_data = KEY_CATEGORIES[key['category']]
            bot.edit_message_text(
                f"✅ **Purchase Successful!**\n\n"
                f"🎮 Category: {cat_data['emoji']} {cat_data['name']}\n"
                f"💰 Price: {format_currency(price)}\n"
                f"💳 New Balance: {format_currency(get_balance(user_id))}\n\n"
                f"🔑 **Your Key:**\n`{key['key']}`\n\n"
                f"📌 Save this key and redeem in BGMI!",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown"
            )
            
            bot.answer_callback_query(call.id, "✅ Key purchased successfully!", show_alert=True)
            
        except Exception as e:
            logger.error(f"Purchase error: {e}")
            bot.answer_callback_query(call.id, "❌ Purchase failed!", show_alert=True)
    
    # UPI Paid callback
    elif data == "upi_paid":
        amount = upi_payment_states.get(user_id, {}).get("amount", 0)
        
        if amount <= 0:
            bot.answer_callback_query(call.id, "❌ Invalid amount!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "📝 Send your 12-digit UTR number")
        
        upi_payment_states[user_id] = {
            "amount": amount,
            "step": "waiting_utr"
        }
        
        bot.send_message(
            user_id,
            "📝 **Step 1: Enter UTR**\n\n"
            "Please send your 12-digit UTR number:\n"
            "(Sent by your bank after payment)"
        )

# -----------------------
# MESSAGE HANDLERS FOR STATES
# -----------------------
@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_key" and 
                    is_admin(msg.from_user.id))
def handle_add_key_input(msg):
    user_id = msg.from_user.id
    state = admin_add_key_state[user_id]
    
    key_code = msg.text.strip()
    category = state['category']
    
    # Check if key already exists
    if keys_col.find_one({"key": key_code}):
        bot.send_message(user_id, f"❌ Key `{key_code}` already exists!\nTry another key:")
        return
    
    # Add key
    keys_col.insert_one({
        "key": key_code,
        "category": category,
        "price": KEY_CATEGORIES[category]['price'],
        "status": "available",
        "added_by": user_id,
        "added_at": datetime.utcnow()
    })
    
    # Get updated count
    count = keys_col.count_documents({"category": category, "status": "available"})
    
    bot.send_message(
        user_id,
        f"✅ **Key Added Successfully!**\n\n"
        f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
        f"Key: `{key_code}`\n"
        f"Price: {format_currency(KEY_CATEGORIES[category]['price'])}\n"
        f"Total Available in this category: {count}",
        parse_mode="Markdown"
    )
    
    log_admin_action(user_id, "ADD_KEY", {
        "category": category,
        "key": key_code[:20] + "..."
    })
    
    admin_add_key_state.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_key_state and 
                    edit_key_state[msg.from_user.id].get("step") == "waiting_price" and 
                    is_admin(msg.from_user.id))
def handle_edit_price_input(msg):
    user_id = msg.from_user.id
    state = edit_key_state[user_id]
    
    try:
        new_price = float(msg.text.strip())
        
        if new_price <= 0:
            bot.send_message(user_id, "❌ Price must be positive! Enter again:")
            return
        
        category = state['category']
        old_price = KEY_CATEGORIES[category]['price']
        
        # Update in database
        categories_col.update_one(
            {"key": category},
            {"$set": {"price": new_price}}
        )
        
        # Update in memory
        KEY_CATEGORIES[category]['price'] = new_price
        
        # Update all unsold keys
        result = keys_col.update_many(
            {"category": category, "status": "available"},
            {"$set": {"price": new_price}}
        )
        
        bot.send_message(
            user_id,
            f"✅ **Price Updated!**\n\n"
            f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
            f"Old Price: {format_currency(old_price)}\n"
            f"New Price: {format_currency(new_price)}\n"
            f"Keys Updated: {result.modified_count}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "EDIT_PRICE", {
            "category": category,
            "old": old_price,
            "new": new_price
        })
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid price! Enter numbers only:")
        return
    
    edit_key_state.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.from_user.id in edit_category_state and 
                    edit_category_state[msg.from_user.id].get("step") == "waiting_input" and 
                    is_admin(msg.from_user.id))
def handle_category_edit_input(msg):
    user_id = msg.from_user.id
    state = edit_category_state[user_id]
    
    category = state['category']
    edit_type = state['type']
    new_value = msg.text.strip()
    
    if edit_type == "name":
        if not new_value:
            bot.send_message(user_id, "❌ Name cannot be empty!")
            return
        
        old_value = KEY_CATEGORIES[category]['name']
        
        # Update database
        categories_col.update_one(
            {"key": category},
            {"$set": {"name": new_value}}
        )
        
        # Update memory
        KEY_CATEGORIES[category]['name'] = new_value
        
        bot.send_message(
            user_id,
            f"✅ **Category Name Updated!**\n\n"
            f"Category: {KEY_CATEGORIES[category]['emoji']}\n"
            f"Old Name: {old_value}\n"
            f"New Name: {new_value}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "EDIT_CATEGORY_NAME", {
            "category": category,
            "old": old_value,
            "new": new_value
        })
    
    elif edit_type == "price":
        try:
            new_price = float(new_value)
            if new_price <= 0:
                bot.send_message(user_id, "❌ Price must be positive!")
                return
            
            old_price = KEY_CATEGORIES[category]['price']
            
            # Update database
            categories_col.update_one(
                {"key": category},
                {"$set": {"price": new_price}}
            )
            
            # Update memory
            KEY_CATEGORIES[category]['price'] = new_price
            
            # Update unsold keys
            keys_col.update_many(
                {"category": category, "status": "available"},
                {"$set": {"price": new_price}}
            )
            
            bot.send_message(
                user_id,
                f"✅ **Category Price Updated!**\n\n"
                f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
                f"Old Price: {format_currency(old_price)}\n"
                f"New Price: {format_currency(new_price)}",
                parse_mode="Markdown"
            )
            
            log_admin_action(user_id, "EDIT_CATEGORY_PRICE", {
                "category": category,
                "old": old_price,
                "new": new_price
            })
            
        except ValueError:
            bot.send_message(user_id, "❌ Invalid price!")
            return
    
    elif edit_type == "emoji":
        if not new_value:
            bot.send_message(user_id, "❌ Emoji cannot be empty!")
            return
        
        old_value = KEY_CATEGORIES[category]['emoji']
        
        # Update database
        categories_col.update_one(
            {"key": category},
            {"$set": {"emoji": new_value}}
        )
        
        # Update memory
        KEY_CATEGORIES[category]['emoji'] = new_value
        
        bot.send_message(
            user_id,
            f"✅ **Category Emoji Updated!**\n\n"
            f"Category: {KEY_CATEGORIES[category]['name']}\n"
            f"Old Emoji: {old_value}\n"
            f"New Emoji: {new_value}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "EDIT_CATEGORY_EMOJI", {
            "category": category,
            "old": old_value,
            "new": new_value
        })
    
    elif edit_type == "description":
        old_value = KEY_CATEGORIES[category].get('description', '')
        
        # Update database
        categories_col.update_one(
            {"key": category},
            {"$set": {"description": new_value}}
        )
        
        # Update memory
        KEY_CATEGORIES[category]['description'] = new_value
        
        bot.send_message(
            user_id,
            f"✅ **Category Description Updated!**\n\n"
            f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
            f"Old: {old_value or 'None'}\n"
            f"New: {new_value}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "EDIT_CATEGORY_DESCRIPTION", {
            "category": category,
            "old": old_value,
            "new": new_value
        })
    
    edit_category_state.pop(user_id, None)

@bot.message_handler(func=lambda msg: upi_payment_states.get(msg.from_user.id, {}).get("step") == "waiting_utr")
def handle_utr_input(msg):
    user_id = msg.from_user.id
    utr = msg.text.strip()
    
    if not utr.isdigit() or len(utr) != 12:
        bot.send_message(user_id, "❌ Invalid UTR! Please enter a valid 12-digit UTR number:")
        return
    
    upi_payment_states[user_id]["utr"] = utr
    upi_payment_states[user_id]["step"] = "waiting_screenshot"
    
    bot.send_message(
        user_id,
        "✅ **UTR Received!**\n\n"
        "📸 **Step 2: Send Screenshot**\n\n"
        "Now please send the payment screenshot from your bank app."
    )

@bot.message_handler(content_types=['photo'], func=lambda msg: upi_payment_states.get(msg.from_user.id, {}).get("step") == "waiting_screenshot")
def handle_screenshot(msg):
    user_id = msg.from_user.id
    
    amount = upi_payment_states[user_id]["amount"]
    utr = upi_payment_states[user_id]["utr"]
    screenshot = msg.photo[-1].file_id
    
    # Save recharge request
    recharge_id = recharges_col.insert_one({
        "user_id": user_id,
        "amount": amount,
        "utr": utr,
        "screenshot": screenshot,
        "status": "pending",
        "created_at": datetime.utcnow()
    }).inserted_id
    
    # Notify admin
    admin_text = f"💰 **New Recharge Request**\n\n"
    admin_text += f"👤 User: {user_id}\n"
    admin_text += f"💰 Amount: {format_currency(amount)}\n"
    admin_text += f"🔢 UTR: {utr}\n"
    admin_text += f"🆔 ID: `{recharge_id}`\n\n"
    admin_text += f"Use /approve {recharge_id} to approve"
    
    bot.send_photo(
        ADMIN_ID,
        screenshot,
        caption=admin_text,
        parse_mode="Markdown"
    )
    
    # Confirm to user
    bot.send_message(
        user_id,
        f"✅ **Payment Proof Submitted!**\n\n"
        f"💰 Amount: {format_currency(amount)}\n"
        f"🔢 UTR: {utr}\n"
        f"📊 Status: Pending Approval\n\n"
        f"Admin will verify and approve shortly.\n"
        f"Your request ID: `{recharge_id}`",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    
    upi_payment_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith('/'))
def handle_commands(msg):
    # Handle commands
    if msg.text.startswith('/approve'):
        handle_approve_command(msg)
    elif msg.text.startswith('/createcoupon'):
        create_coupon(msg)
    elif msg.text.startswith('/deletecoupon'):
        delete_coupon(msg)
    elif msg.text.startswith('/couponlist'):
        coupon_list(msg)
    elif msg.text.startswith('/setprice'):
        set_price(msg)
    elif msg.text.startswith('/setname'):
        set_name(msg)
    elif msg.text.startswith('/setemoji'):
        set_emoji(msg)
    elif msg.text.startswith('/setdesc'):
        set_description(msg)

@bot.message_handler(func=lambda msg: True)
def fallback_handler(msg):
    user_id = msg.from_user.id
    
    # If user is in any state, ignore
    if (user_id in user_states or 
        user_id in upi_payment_states or 
        user_id in admin_deduct_state or
        user_id in admin_add_key_state or
        user_id in edit_key_state or
        user_id in edit_category_state):
        return
    
    bot.send_message(
        user_id,
        "❌ Please use the keyboard buttons below!",
        reply_markup=get_main_keyboard()
    )

# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    logger.info("🎮 BGMI LODERS Key Selling Bot Starting...")
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info(f"Loaded Categories: {len(KEY_CATEGORIES)}")
    
    # Create indexes
    try:
        keys_col.create_index("key", unique=True)
        keys_col.create_index("status")
        keys_col.create_index("category")
        coupons_col.create_index("code", unique=True)
        users_col.create_index("user_id", unique=True)
        wallets_col.create_index("user_id", unique=True)
        categories_col.create_index("key", unique=True)
        logger.info("✅ Database indexes created")
    except Exception as e:
        logger.error(f"❌ Index creation failed: {e}")
    
    # Start bot
    while True:
        try:
            logger.info("🤖 Bot is running...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(30)