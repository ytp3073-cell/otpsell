import logging
import threading
import time
from datetime import datetime, timedelta
from bson import ObjectId
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import telebot.types
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
admin_add_key_state = {}  # For add key flow
edit_category_state = {}
admin_remove_state = {}
edit_loader_state = {}
add_loader_state = {}
add_loader_button_state = {}
dynamic_price_state = {}
admin_add_admin_state = {}  # For adding new admin

# Default Categories
DEFAULT_CATEGORIES = {
    "weekend": {"name": "🎮 Weekend Challenge", "price": 49, "emoji": "🎮", "description": "Weekend special challenge keys"},
    "royalty": {"name": "🏆 Royalty Pass", "price": 399, "emoji": "🏆", "description": "Premium royalty pass"},
    "uc": {"name": "⚡ UC", "price": 99, "emoji": "⚡", "description": "Unknown Cash for BGMI"},
    "event": {"name": "🎯 Event Pass", "price": 199, "emoji": "🎯", "description": "Special event passes"},
    "aqm": {"name": "💎 AQM Keys", "price": 299, "emoji": "💎", "description": "AQM premium keys"}
}

# Admin list - multiple admins support
ADMINS = [ADMIN_ID]  # Default admin

def load_admins():
    """Load all admin IDs from database"""
    global ADMINS
    admin_data = db['admins'].find()
    admins = [ADMIN_ID]  # Always include main admin
    for admin in admin_data:
        if admin['admin_id'] not in admins:
            admins.append(admin['admin_id'])
    ADMINS = admins
    return ADMINS

# Load admins on startup
load_admins()

# Load categories from database
def load_categories():
    global KEY_CATEGORIES
    KEY_CATEGORIES = {}
    
    db_categories = list(categories_col.find())
    
    if db_categories:
        for cat in db_categories:
            KEY_CATEGORIES[cat['key']] = {
                "name": cat['name'],
                "price": cat.get('price', 0),
                "emoji": cat.get('emoji', '📌'),
                "description": cat.get('description', ''),
                "buttons": cat.get('buttons', [])  # Multiple price buttons for loader
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
                    "buttons": [],
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
    # Admin panel sirf admin ko dikhe
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
        KeyboardButton("👥 Users List"),
        KeyboardButton("💸 Pending Recharges")
    )
    keyboard.add(
        KeyboardButton("📢 Broadcast"),
        KeyboardButton("📈 Sales Report")
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
        KeyboardButton("⚙️ Loader Settings")
    )
    keyboard.add(
        KeyboardButton("👑 Admin Management"),  # New button for admin management
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

# Global variable to store current user for keyboard
_current_user_id = None

def set_current_user_id(user_id):
    global _current_user_id
    _current_user_id = user_id

def get_current_user_id():
    return _current_user_id

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
    """Check if user is admin"""
    # Load latest admins
    load_admins()
    return user_id in ADMINS

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

def generate_dynamic_qr(amount, upi_id="anurag99999@fam"):
    """Generate QR code for specific amount"""
    try:
        # UPI QR format: upi://pay?pa=UPI_ID&pn=Receiver&am=AMOUNT&cu=INR
        upi_url = f"upi://pay?pa={upi_id}&pn=BGMI%20Keys&am={amount}&cu=INR"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(upi_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        bio.name = 'qr.png'
        img.save(bio)
        bio.seek(0)
        return bio
    except Exception as e:
        logger.error(f"QR generation error: {e}")
        return None

# -----------------------
# DECORATOR TO SET USER ID
# -----------------------
def set_user_context(func):
    def wrapper(message):
        set_current_user_id(message.from_user.id)
        return func(message)
    return wrapper

# -----------------------
# START HANDLER
# -----------------------
@bot.message_handler(commands=['start'])
@set_user_context
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
        text += "/addkey - Add a new key\n"
        text += "/removekey [keycode] - Remove a key\n"
        text += "/keys - List all keys\n"
        text += "/users - List users\n"
        text += "/pending - View pending recharges\n"
        text += "/broadcast - Send broadcast\n"
        text += "/ban [user_id] - Ban a user\n"
        text += "/unban [user_id] - Unban a user\n"
        text += "/addbalance [user_id] [amount] [reason] - Add balance\n"
        text += "/deduct [user_id] [amount] [reason] - Deduct balance\n"
        text += "/createcoupon [code] [amount] [uses] - Create coupon\n"
        text += "/deletecoupon [code] - Delete coupon\n"
        text += "/coupons - List coupons\n"
        text += "/sales - View sales report\n"
        text += "/addloader [key] [name] [price] [emoji] [desc] - Add new loader\n"
        text += "/addadmin [user_id] - Add new admin\n"
        text += "/removeadmin [user_id] - Remove admin\n"
        text += "/admins - List all admins"
    
    bot.reply_to(msg, text, parse_mode="Markdown")

# -----------------------
# MAIN MENU
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🔙 Main Menu")
@set_user_context
def main_menu(msg):
    bot.send_message(msg.from_user.id, "🏠 Main Menu", reply_markup=get_main_keyboard())

# -----------------------
# BUY KEYS - Category Selection
# -----------------------
@bot.message_handler(func=lambda msg: msg.text.startswith("🛒") or msg.text == "🛒 Buy Keys")
@bot.message_handler(commands=['buy'])
@set_user_context
def buy_keys(msg):
    user_id = msg.from_user.id
    text = "🎮 **Select Loader:**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        count = keys_col.count_documents({"category": key, "status": "available"})
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"💰 Base Price: {format_currency(data['price'])} | 📦 Available: {count}\n"
        if data['description']:
            text += f"📝 {data['description']}\n"
        
        # Show price buttons if available
        if data.get('buttons'):
            text += f"   **Price Options:** "
            price_options = [f"{format_currency(b['price'])}" for b in data['buttons']]
            text += f"{', '.join(price_options)}\n"
        text += "\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=get_buy_keyboard())

# -----------------------
# SHOW AVAILABLE KEYS in Category
# -----------------------
@bot.message_handler(func=lambda msg: any(msg.text.startswith(data['emoji']) for data in KEY_CATEGORIES.values()))
@set_user_context
def show_keys(msg):
    user_id = msg.from_user.id
    category_name = msg.text.replace("🎮 ", "").replace("🏆 ", "").replace("⚡ ", "").replace("🎯 ", "").replace("💎 ", "")
    
    # Find category
    cat_key = None
    cat_data = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == category_name or msg.text.startswith(data['emoji']):
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
    text += f"💰 Base Price: {format_currency(cat_data['price'])} per key\n"
    text += f"📦 Available: {len(keys)}\n\n"
    
    # Show price buttons if available
    if cat_data.get('buttons'):
        text += "**💵 Price Options Available:**\n"
        for btn in cat_data['buttons']:
            text += f"• {btn['name']}: {format_currency(btn['price'])}\n"
        text += "\n"
    
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
            # Make details bold - split by lines and format
            details_lines = key['details'].split('\n')
            formatted_details = []
            for line in details_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    formatted_details.append(f"**{parts[0]}:**{parts[1]}")
                else:
                    formatted_details.append(f"**{line}**")
            
            text += f"📝 **Key Details:**\n"
            for line in formatted_details:
                text += f"{line}\n"
        else:
            text += "ℹ️ No additional details available.\n\n"
        
        # Check if category has price buttons
        if cat_data.get('buttons'):
            text += "\n**💵 Select Price Option:**\n"
            
            markup = InlineKeyboardMarkup(row_width=2)
            # Add price buttons
            for btn in cat_data['buttons']:
                markup.add(InlineKeyboardButton(
                    f"{btn['name']} - {format_currency(btn['price'])}", 
                    callback_data=f"buyprice_{key_id}_{btn['price']}"
                ))
            # Add base price option
            markup.add(InlineKeyboardButton(
                f"Base Price - {format_currency(key['price'])}", 
                callback_data=f"buy_{key_id}"
            ))
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_view"))
        else:
            text += "\n🛒 **Do you want to purchase this key?**"
            
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
# PROCESS PURCHASE WITH DYNAMIC PRICE
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("buyprice_"))
def process_purchase_with_price(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    key_id = parts[1]
    price = float(parts[2])
    
    try:
        key = keys_col.find_one({"_id": ObjectId(key_id), "status": "available"})
        if not key:
            bot.answer_callback_query(call.id, "❌ Key sold out!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
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
        
        # Update key status
        keys_col.update_one(
            {"_id": ObjectId(key_id)},
            {"$set": {
                "status": "sold",
                "sold_to": user_id,
                "sold_at": datetime.utcnow(),
                "sold_price": price  # Store actual sold price
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
            # Make details bold
            details_lines = key['details'].split('\n')
            text += f"📝 **Key Details:**\n"
            for line in details_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    text += f"**{parts[0]}:**{parts[1]}\n"
                else:
                    text += f"**{line}**\n"
            text += "\n"
        
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
# PROCESS PURCHASE (Original)
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
            # Make details bold
            details_lines = key['details'].split('\n')
            text += f"📝 **Key Details:**\n"
            for line in details_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    text += f"**{parts[0]}:**{parts[1]}\n"
                else:
                    text += f"**{line}**\n"
            text += "\n"
        
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
# RECHARGE - WITH DYNAMIC QR
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
        if amount < 1:  # Changed from 10 to 1
            bot.send_message(user_id, "❌ Minimum ₹1! Enter again:", reply_markup=get_back_keyboard())
            return
        
        upi_payment_states[user_id] = {"amount": amount}
        user_states.pop(user_id, None)
        
        # Generate dynamic QR code
        qr_image = generate_dynamic_qr(amount)
        
        if qr_image:
            caption = f"""💳 **UPI Payment**

Amount: {format_currency(amount)}
UPI ID: `anurag99999@fam`

📌 **QR Code Generated for {format_currency(amount)}**
Scan this QR code or use UPI ID to pay.

After payment, click I HAVE PAID"""
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💰 I HAVE PAID", callback_data="upi_paid"))
            
            bot.send_photo(user_id, qr_image, caption=caption, 
                          parse_mode="Markdown", reply_markup=markup)
        else:
            # Fallback to static QR if generation fails
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
    
    bot.send_message(user_id, f"✅ Added {format_currency(amount)} to your wallet!", 
                    reply_markup=get_main_keyboard())

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
# ADMIN MANAGEMENT
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Management" and is_admin(msg.from_user.id))
@set_user_context
def admin_management(msg):
    if msg.from_user.id != ADMIN_ID:  # Only main admin can manage admins
        bot.send_message(msg.from_user.id, "❌ Only main admin can manage other admins!")
        return
    
    text = "👑 **Admin Management**\n\n"
    text += "Manage bot administrators here.\n\n"
    text += "**Commands:**\n"
    text += "• /addadmin [user_id] - Add new admin\n"
    text += "• /removeadmin [user_id] - Remove admin\n"
    text += "• /admins - List all admins"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown", reply_markup=get_admin_management_keyboard())

# -----------------------
# ADD ADMIN
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Admin" and is_admin(msg.from_user.id))
@set_user_context
def add_admin_start(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.send_message(msg.from_user.id, "❌ Only main admin can add new admins!")
        return
    
    bot.send_message(msg.from_user.id, "➕ Enter Telegram User ID of new admin:")
    admin_add_admin_state[msg.from_user.id] = {"action": "add"}

@bot.message_handler(commands=['addadmin'])
@set_user_context
def add_admin_command(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.reply_to(msg, "❌ Only main admin can add new admins!")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            bot.reply_to(msg, "❌ Usage: /addadmin [user_id]")
            return
        
        new_admin_id = int(parts[1])
        
        if new_admin_id in ADMINS:
            bot.reply_to(msg, "❌ User is already an admin!")
            return
        
        # Add to database
        db['admins'].insert_one({
            "admin_id": new_admin_id,
            "added_by": msg.from_user.id,
            "added_at": datetime.utcnow()
        })
        
        # Reload admins
        load_admins()
        
        # Notify new admin
        try:
            bot.send_message(new_admin_id, "👑 You have been promoted to Admin!")
        except:
            pass
        
        bot.reply_to(msg, f"✅ User {new_admin_id} added as admin!")
        log_admin_action(msg.from_user.id, "ADD_ADMIN", {"new_admin": new_admin_id})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_admin_state and 
                    admin_add_admin_state[msg.from_user.id].get("action") == "add" and 
                    is_admin(msg.from_user.id))
@set_user_context
def process_add_admin(msg):
    try:
        new_admin_id = int(msg.text.strip())
        
        if new_admin_id in ADMINS:
            bot.send_message(msg.from_user.id, "❌ User is already an admin!")
        else:
            # Add to database
            db['admins'].insert_one({
                "admin_id": new_admin_id,
                "added_by": msg.from_user.id,
                "added_at": datetime.utcnow()
            })
            
            # Reload admins
            load_admins()
            
            # Notify new admin
            try:
                bot.send_message(new_admin_id, "👑 You have been promoted to Admin!")
            except:
                pass
            
            bot.send_message(msg.from_user.id, f"✅ User {new_admin_id} added as admin!")
            log_admin_action(msg.from_user.id, "ADD_ADMIN", {"new_admin": new_admin_id})
        
    except ValueError:
        bot.send_message(msg.from_user.id, "❌ Invalid User ID!")
    
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
    
    # List all admins except main
    other_admins = [admin_id for admin_id in ADMINS if admin_id != ADMIN_ID]
    
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
            bot.reply_to(msg, "❌ User is not an admin!")
            return
        
        # Remove from database
        db['admins'].delete_one({"admin_id": admin_id})
        
        # Reload admins
        load_admins()
        
        # Notify removed admin
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
        # Remove from database
        db['admins'].delete_one({"admin_id": admin_id})
        
        # Reload admins
        load_admins()
        
        # Notify removed admin
        try:
            bot.send_message(admin_id, "⚠️ Your admin privileges have been removed!")
        except:
            pass
        
        bot.answer_callback_query(call.id, f"✅ Admin removed!")
        bot.edit_message_text(
            f"✅ Admin {admin_id} removed successfully!",
            call.message.chat.id,
            call.message.message_id
        )
        
        log_admin_action(call.from_user.id, "REMOVE_ADMIN", {"removed_admin": admin_id})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

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
            text += f"{i}. **{name}** (ID: `{admin_id}`) - **Main Admin**\n"
        else:
            text += f"{i}. {name} (ID: `{admin_id}`)\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# STATS COMMAND
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
# LOADER SETTINGS MENU
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "⚙️ Loader Settings" and is_admin(msg.from_user.id))
@set_user_context
def loader_settings(msg):
    bot.send_message(
        msg.from_user.id,
        "⚙️ **Loader Settings**\n\nManage loader names, prices, and price buttons.",
        parse_mode="Markdown",
        reply_markup=get_loader_settings_keyboard()
    )

# -----------------------
# ADD LOADER BUTTON
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Loader" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['addloader'])
@set_user_context
def add_loader_start(msg):
    user_id = msg.from_user.id
    
    # If command
    if msg.text.startswith('/addloader'):
        try:
            parts = msg.text.split(maxsplit=5)[1].split('|')
            if len(parts) < 4:
                bot.reply_to(msg, "❌ Usage: /addloader [key]|[name]|[price]|[emoji]|[description]")
                return
            
            key = parts[0].strip().lower()
            name = parts[1].strip()
            price = float(parts[2].strip())
            emoji = parts[3].strip()
            desc = parts[4].strip() if len(parts) > 4 else ""
            
            if key in KEY_CATEGORIES:
                bot.reply_to(msg, "❌ Loader key already exists!")
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
            bot.reply_to(msg, f"✅ Loader {emoji} {name} added successfully!")
            log_admin_action(user_id, "ADD_LOADER", {"key": key, "name": name})
            
        except Exception as e:
            bot.reply_to(msg, f"❌ Error: {str(e)}")
        return
    
    # Button flow
    text = "➕ **Add New Loader**\n\n"
    text += "Send loader details in format:\n"
    text += "`key|name|price|emoji|description`\n\n"
    text += "**Example:**\n"
    text += "`brutal|🎮 Brutal Pass|49|🎮|Brutal server keys`\n\n"
    text += "Available keys must be unique!"
    
    bot.send_message(user_id, text, parse_mode="Markdown")
    add_loader_state[user_id] = {"step": "waiting_details"}

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_state and 
                    add_loader_state[msg.from_user.id].get("step") == "waiting_details" and 
                    is_admin(msg.from_user.id))
@set_user_context
def process_add_loader(msg):
    user_id = msg.from_user.id
    
    try:
        parts = msg.text.strip().split('|')
        if len(parts) < 4:
            bot.send_message(user_id, "❌ Invalid format! Use: key|name|price|emoji|description")
            return
        
        key = parts[0].strip().lower()
        name = parts[1].strip()
        price = float(parts[2].strip())
        emoji = parts[3].strip()
        desc = parts[4].strip() if len(parts) > 4 else ""
        
        if key in KEY_CATEGORIES:
            bot.send_message(user_id, "❌ Loader key already exists! Choose another key.")
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
            f"✅ **Loader Added Successfully!**\n\n"
            f"{emoji} **{name}**\n"
            f"Key: `{key}`\n"
            f"Price: {format_currency(price)}\n"
            f"Description: {desc}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "ADD_LOADER", {"key": key, "name": name})
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid price! Must be a number.")
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")
    
    add_loader_state.pop(user_id, None)

# -----------------------
# ADD PRICE BUTTON TO LOADER
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🔘 Add Price Button" and is_admin(msg.from_user.id))
@set_user_context
def add_price_button_start(msg):
    user_id = msg.from_user.id
    
    text = "🔘 **Add Price Button**\n\n"
    text += "Select which loader to add price button to:\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} (Key: `{key}`)\n"
    
    text += "\nOr use command: `/addpricebtn [loader_key] [button_name] [price]`"
    
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
            bot.reply_to(msg, "❌ Usage: /addpricebtn [loader_key] [button_name] [price]\nExample: /addpricebtn weekend '6 Months' 299")
            return
        
        key = parts[1].lower()
        btn_name = parts[2].strip()
        price = float(parts[3])
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Loader key '{key}' not found!")
            return
        
        if price <= 0:
            bot.reply_to(msg, "❌ Price must be positive!")
            return
        
        # Get current loader
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        
        # Check if button with same name exists
        for btn in buttons:
            if btn['name'].lower() == btn_name.lower():
                bot.reply_to(msg, "❌ Button with this name already exists!")
                return
        
        # Add new button
        buttons.append({
            "name": btn_name,
            "price": price
        })
        
        categories_col.update_one(
            {"key": key},
            {"$set": {"buttons": buttons}}
        )
        
        refresh_categories()
        
        bot.reply_to(
            msg,
            f"✅ **Price Button Added!**\n\n"
            f"Loader: {KEY_CATEGORIES[key]['emoji']} {KEY_CATEGORIES[key]['name']}\n"
            f"Button: {btn_name}\n"
            f"Price: {format_currency(price)}",
            parse_mode="Markdown"
        )
        
        log_admin_action(msg.from_user.id, "ADD_PRICE_BUTTON", {"key": key, "button": btn_name, "price": price})
        
    except ValueError:
        bot.reply_to(msg, "❌ Invalid price! Must be a number.")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_button_state and 
                    add_loader_button_state[msg.from_user.id].get("step") == "select" and 
                    msg.text.startswith("📌") and is_admin(msg.from_user.id))
@set_user_context
def handle_button_loader_selection(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    # Find the key for this name
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
    
    bot.send_message(
        user_id,
        f"🔘 Enter button name for {KEY_CATEGORIES[selected_key]['emoji']} {KEY_CATEGORIES[selected_key]['name']}:\n\n"
        f"Example: `6 Months Pass` or `Premium Access`"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_button_state and 
                    add_loader_button_state[msg.from_user.id].get("step") == "waiting_name" and 
                    is_admin(msg.from_user.id))
@set_user_context
def handle_button_name(msg):
    user_id = msg.from_user.id
    btn_name = msg.text.strip()
    
    if not btn_name:
        bot.send_message(user_id, "❌ Button name cannot be empty!")
        return
    
    add_loader_button_state[user_id]["btn_name"] = btn_name
    add_loader_button_state[user_id]["step"] = "waiting_price"
    
    bot.send_message(
        user_id,
        f"💰 Enter price for '{btn_name}' button:"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in add_loader_button_state and 
                    add_loader_button_state[msg.from_user.id].get("step") == "waiting_price" and 
                    is_admin(msg.from_user.id))
@set_user_context
def handle_button_price(msg):
    user_id = msg.from_user.id
    
    try:
        price = float(msg.text.strip())
        key = add_loader_button_state[user_id]["key"]
        btn_name = add_loader_button_state[user_id]["btn_name"]
        
        if price <= 0:
            bot.send_message(user_id, "❌ Price must be positive!")
            return
        
        # Get current loader
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        
        # Check if button with same name exists
        for btn in buttons:
            if btn['name'].lower() == btn_name.lower():
                bot.send_message(user_id, "❌ Button with this name already exists!")
                add_loader_button_state.pop(user_id, None)
                return
        
        # Add new button
        buttons.append({
            "name": btn_name,
            "price": price
        })
        
        categories_col.update_one(
            {"key": key},
            {"$set": {"buttons": buttons}}
        )
        
        refresh_categories()
        
        bot.send_message(
            user_id,
            f"✅ **Price Button Added!**\n\n"
            f"Loader: {KEY_CATEGORIES[key]['emoji']} {KEY_CATEGORIES[key]['name']}\n"
            f"Button: {btn_name}\n"
            f"Price: {format_currency(price)}",
            parse_mode="Markdown"
        )
        
        log_admin_action(user_id, "ADD_PRICE_BUTTON", {"key": key, "button": btn_name, "price": price})
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid price! Enter a number.")
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
    
    text = "🗑 **Remove Price Button**\n\n"
    text += "Select loader to remove button from:\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"• {data['emoji']} {data['name']} (Key: `{key}`)\n"
    
    text += "\nOr use command: `/removepricebtn [loader_key] [button_name]`"
    
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
            bot.reply_to(msg, "❌ Usage: /removepricebtn [loader_key] [button_name]")
            return
        
        key = parts[1].lower()
        btn_name = parts[2].strip()
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, f"❌ Loader key '{key}' not found!")
            return
        
        # Get current loader
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        
        # Find and remove button
        new_buttons = [btn for btn in buttons if btn['name'].lower() != btn_name.lower()]
        
        if len(new_buttons) == len(buttons):
            bot.reply_to(msg, f"❌ Button '{btn_name}' not found!")
            return
        
        categories_col.update_one(
            {"key": key},
            {"$set": {"buttons": new_buttons}}
        )
        
        refresh_categories()
        
        bot.reply_to(
            msg,
            f"✅ **Price Button Removed!**\n\n"
            f"Loader: {KEY_CATEGORIES[key]['emoji']} {KEY_CATEGORIES[key]['name']}\n"
            f"Button Removed: {btn_name}",
            parse_mode="Markdown"
        )
        
        log_admin_action(msg.from_user.id, "REMOVE_PRICE_BUTTON", {"key": key, "button": btn_name})
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.from_user.id in dynamic_price_state and 
                    dynamic_price_state[msg.from_user.id].get("step") == "select" and 
                    msg.text.startswith("📌") and is_admin(msg.from_user.id))
@set_user_context
def handle_remove_button_loader(msg):
    user_id = msg.from_user.id
    selected_name = msg.text.replace("📌", "").strip()
    
    # Find the key for this name
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
        bot.send_message(user_id, f"❌ No price buttons found for this loader!")
        dynamic_price_state.pop(user_id, None)
        return
    
    text = f"🗑 **Select button to remove from {KEY_CATEGORIES[selected_key]['name']}:**\n\n"
    
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
    
    parts = call.data.split('_')
    key = parts[1]
    btn_name = '_'.join(parts[2:])  # In case button name has underscores
    
    try:
        # Get current loader
        loader = categories_col.find_one({"key": key})
        buttons = loader.get('buttons', [])
        
        # Remove button
        new_buttons = [btn for btn in buttons if btn['name'] != btn_name]
        
        categories_col.update_one(
            {"key": key},
            {"$set": {"buttons": new_buttons}}
        )
        
        refresh_categories()
        
        bot.answer_callback_query(call.id, "✅ Button removed!")
        bot.edit_message_text(
            f"✅ **Price Button Removed!**\n\n"
            f"Loader: {KEY_CATEGORIES[key]['emoji']} {KEY_CATEGORIES[key]['name']}\n"
            f"Button Removed: {btn_name}",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        log_admin_action(call.from_user.id, "REMOVE_PRICE_BUTTON", {"key": key, "button": btn_name})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

# -----------------------
# LIST PRICE BUTTONS
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📋 List Price Buttons" and is_admin(msg.from_user.id))
@set_user_context
def list_price_buttons(msg):
    text = "📋 **Price Buttons by Loader**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['emoji']} **{data['name']}**\n"
        
        if data.get('buttons'):
            for btn in data['buttons']:
                text += f"  • {btn['name']}: {format_currency(btn['price'])}\n"
        else:
            text += "  No price buttons\n"
        text += "\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# EDIT LOADER NAME
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "✏️ Edit Loader Name" and is_admin(msg.from_user.id))
@set_user_context
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
@set_user_context
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
@set_user_context
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
@set_user_context
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
@set_user_context
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
@set_user_context
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
@set_user_context
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
@set_user_context
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
# ADD KEY - COMPLETE FLOW
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Key" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['addkey'])
@set_user_context
def add_key_start(msg):
    user_id = msg.from_user.id
    
    # Agar command se aaya hai
    if msg.text.startswith('/addkey'):
        bot.reply_to(msg, "Please use the Add Key button:\n👑 Admin Panel → ➕ Add Key")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(f"{data['emoji']} {data['name']}", callback_data=f"addcat_{key}"))
    
    bot.send_message(user_id, "📝 **Select Loader Category:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("addcat_"))
def add_key_category(call):
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    category = call.data.replace("addcat_", "")
    
    # Store in state
    admin_add_key_state[user_id] = {
        "category": category,
        "step": "waiting_key",
        "message_id": call.message.message_id,
        "chat_id": call.message.chat.id
    }
    
    bot.edit_message_text(
        f"📝 **Add Key for {KEY_CATEGORIES[category]['name']}**\n\n"
        f"**Step 1 of 2:**\n"
        f"Send the **KEY CODE** now\n\n"
        f"🔑 This code will be shown to user AFTER purchase\n\n"
        f"Example: `BRUTAL123456`",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_key" and 
                    is_admin(msg.from_user.id))
@set_user_context
def handle_key_code(msg):
    user_id = msg.from_user.id
    key_code = msg.text.strip()
    
    if not key_code:
        bot.send_message(user_id, "❌ Key code cannot be empty! Send key code again:")
        return
    
    # Save key code
    admin_add_key_state[user_id]["key_code"] = key_code
    admin_add_key_state[user_id]["step"] = "waiting_details"
    
    # Delete previous instruction message if exists
    try:
        bot.delete_message(
            admin_add_key_state[user_id]["chat_id"],
            admin_add_key_state[user_id]["message_id"]
        )
    except:
        pass
    
    bot.send_message(
        user_id,
        f"✅ Key code saved: `{key_code}`\n\n"
        f"**Step 2 of 2:**\n"
        f"Now send the **DETAILS** for this key\n\n"
        f"📝 These details will be shown in **BOLD** format\n\n"
        f"**Recommended Format:**\n"
        f"`Email: brutal@gmail.com`\n"
        f"`Password: bgmi123`\n"
        f"`Server: Asia`\n"
        f"`Expiry: 30 Days`\n\n"
        f"Ya jo bhi details chahte ho send karo - ye automatically bold ho jayegi"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and 
                    admin_add_key_state[msg.from_user.id].get("step") == "waiting_details" and 
                    is_admin(msg.from_user.id))
@set_user_context
def handle_details(msg):
    user_id = msg.from_user.id
    details = msg.text.strip()
    
    if not details:
        bot.send_message(user_id, "❌ Details cannot be empty! Send details again:")
        return
    
    # Get data from state
    category = admin_add_key_state[user_id]['category']
    key_code = admin_add_key_state[user_id]['key_code']
    
    # Insert into database
    keys_col.insert_one({
        "key": key_code,
        "category": category,
        "price": KEY_CATEGORIES[category]['price'],
        "details": details,
        "status": "available",
        "added_by": user_id,
        "added_at": datetime.utcnow()
    })
    
    # Count available keys in this category
    count = keys_col.count_documents({"category": category, "status": "available"})
    
    # Format preview with bold
    details_lines = details.split('\n')
    formatted_details = []
    for line in details_lines:
        if ':' in line:
            parts = line.split(':', 1)
            formatted_details.append(f"**{parts[0]}:**{parts[1]}")
        else:
            formatted_details.append(f"**{line}**")
    
    preview_details = "\n".join(formatted_details)
    
    bot.send_message(
        user_id,
        f"✅ **Key Added Successfully!**\n\n"
        f"📁 **Loader:** {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
        f"💰 **Price:** {format_currency(KEY_CATEGORIES[category]['price'])}\n"
        f"📊 **Available in this loader:** {count}\n\n"
        f"🔑 **Key Code (After Purchase):**\n`{key_code}`\n\n"
        f"📝 **Details (BOLD Format):**\n{preview_details}",
        parse_mode="Markdown"
    )
    
    # Log admin action
    log_admin_action(user_id, "ADD_KEY", {
        "category": category,
        "key_code": key_code[:10] + "..."
    })
    
    # Clear state
    admin_add_key_state.pop(user_id, None)

# -----------------------
# KEY LIST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📋 Key List" and is_admin(msg.from_user.id))
@bot.message_handler(commands=['keys'])
@set_user_context
def key_list(msg):
    # Agar command se aaya hai to alag response
    if msg.text.startswith('/keys'):
        text = "📋 **All Keys (Last 20)**\n\n"
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
    
    # Button se aaya hai to category wise count dikhao
    text = "📋 **Key Inventory**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        avail = keys_col.count_documents({"category": key, "status": "available"})
        sold = keys_col.count_documents({"category": key, "status": "sold"})
        text += f"{data['emoji']} {data['name']}: {avail} avail, {sold} sold\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# REST OF THE CODE (Remove Key, Bulk Add, Pending Recharges, etc.) remains the same
# ...
# (Aage ka code same rahega - maine important changes upar kar diye hain)
# ...

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
@set_user_context
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
    
    # Notify all admins with buttons
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"app_req_{recharge_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"rej_req_{recharge_id}")
    )
    
    # Send to all admins
    for admin_id in ADMINS:
        try:
            bot.send_photo(
                admin_id,
                msg.photo[-1].file_id,
                caption=f"💰 New Recharge\nUser: {user_id}\nAmount: {format_currency(data['amount'])}\nUTR: {data['utr']}\nID: {recharge_id}",
                reply_markup=markup
            )
        except:
            pass
    
    bot.send_message(user_id, "✅ Payment submitted! Admin will approve soon.", reply_markup=get_main_keyboard())
    upi_payment_states.pop(user_id, None)

# -----------------------
# APPROVE RECHARGE BUTTON HANDLER
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("app_req_"))
def approve_recharge_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    try:
        req_id = ObjectId(call.data.replace("app_req_", ""))
        req = recharges_col.find_one({"_id": req_id, "status": "pending"})
        
        if not req:
            bot.answer_callback_query(call.id, "❌ Request not found or already processed!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
        # Add balance to user
        add_balance(req['user_id'], req['amount'])
        
        # Update request status
        recharges_col.update_one(
            {"_id": req_id},
            {"$set": {
                "status": "approved",
                "approved_by": call.from_user.id,
                "approved_at": datetime.utcnow()
            }}
        )
        
        # Notify user
        try:
            bot.send_message(
                req['user_id'],
                f"✅ **Recharge Approved!**\n\n"
                f"💰 Amount: {format_currency(req['amount'])}\n"
                f"💳 New Balance: {format_currency(get_balance(req['user_id']))}\n\n"
                f"Thank you for your payment!"
            )
        except:
            pass
        
        # Update message
        bot.edit_message_caption(
            caption=call.message.caption + "\n\n✅ **APPROVED**",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        bot.answer_callback_query(call.id, "✅ Recharge approved!")
        log_admin_action(call.from_user.id, "APPROVE_RECHARGE", {"user": req['user_id'], "amount": req['amount']})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

# -----------------------
# REJECT RECHARGE BUTTON HANDLER
# -----------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("rej_req_"))
def reject_recharge_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return
    
    try:
        req_id = ObjectId(call.data.replace("rej_req_", ""))
        req = recharges_col.find_one({"_id": req_id, "status": "pending"})
        
        if not req:
            bot.answer_callback_query(call.id, "❌ Request not found or already processed!", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return
        
        # Update request status
        recharges_col.update_one(
            {"_id": req_id},
            {"$set": {
                "status": "rejected",
                "rejected_by": call.from_user.id,
                "rejected_at": datetime.utcnow()
            }}
        )
        
        # Notify user
        try:
            bot.send_message(
                req['user_id'],
                f"❌ **Recharge Rejected**\n\n"
                f"💰 Amount: {format_currency(req['amount'])}\n"
                f"UTR: {req.get('utr', 'N/A')}\n\n"
                f"Your payment could not be verified. Please contact support if you think this is a mistake."
            )
        except:
            pass
        
        # Update message
        bot.edit_message_caption(
            caption=call.message.caption + "\n\n❌ **REJECTED**",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        bot.answer_callback_query(call.id, "❌ Recharge rejected!")
        log_admin_action(call.from_user.id, "REJECT_RECHARGE", {"user": req['user_id'], "amount": req['amount']})
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

# -----------------------
# FALLBACK HANDLER
# -----------------------
@bot.message_handler(func=lambda msg: True)
@set_user_context
def fallback(msg):
    if msg.from_user.id not in user_states and msg.from_user.id not in admin_deduct_state and msg.from_user.id not in admin_add_key_state:
        bot.send_message(msg.from_user.id, "❌ Use buttons below!", reply_markup=get_main_keyboard())

# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    logger.info("🚀 Bot Started!")
    logger.info(f"Main Admin ID: {ADMIN_ID}")
    logger.info(f"Total Admins: {len(ADMINS)}")
    logger.info(f"Loaders: {len(KEY_CATEGORIES)}")
    
    # Create indexes
    try:
        keys_col.create_index("key", unique=True)
        keys_col.create_index("status")
        coupons_col.create_index("code", unique=True)
        users_col.create_index("user_id", unique=True)
        wallets_col.create_index("user_id", unique=True)
        db['admins'].create_index("admin_id", unique=True)
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