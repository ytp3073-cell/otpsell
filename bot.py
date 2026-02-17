import logging
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
BOT_TOKEN = '8477235690:AAGAjf1FJGxxJYG1I_229J_C-EBXphXAyzA'  # Apna bot token yahan daalein
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

🔥 Available Categories:"""
    
    for data in KEY_CATEGORIES.values():
        welcome += f"\n• {data['emoji']} {data['name']}"
    
    welcome += """
\n✅ Instant Delivery
💳 Secure Payment
📞 24/7 Support

Use buttons below to navigate!"""
    
    bot.send_message(user_id, welcome, reply_markup=get_main_keyboard())

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
def buy_keys(msg):
    user_id = msg.from_user.id
    text = "🎮 **Select Category:**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        count = keys_col.count_documents({"category": key, "status": "available"})
        text += f"{data['emoji']} {data['name']}\n"
        text += f"💰 {format_currency(data['price'])} | 📦 {count} available\n"
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
        bot.send_message(user_id, "❌ Category not found!", reply_markup=get_buy_keyboard())
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
        # Show if key has details
        if key.get('details'):
            btn_text = f"📝 Key #{i} (Has Details)"
        else:
            btn_text = f"🔑 Key #{i}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"view_{key['_id']}"))
    
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

# -----------------------
# VIEW KEY DETAILS (Before Purchase) - Admin ki details yahan show hogi
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
        
        # 🎯 Admin ne jo details dali hain, wahi show karo
        text = f"{cat_data['emoji']} **{cat_data['name']}**\n"
        text += f"💰 **Price:** {format_currency(key['price'])}\n\n"
        
        if key.get('details'):
            # Admin ki exact details - bilkul waisi hi
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
# PROCESS PURCHASE - Key yahan show hogi
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
        
        # 🎯 AFTER PURCHASE - Key show karo
        text = f"✅ **Purchase Successful!**\n\n"
        text += f"🎮 {cat_data['emoji']} {cat_data['name']}\n"
        text += f"💰 Paid: {format_currency(price)}\n"
        text += f"💳 Remaining: {format_currency(get_balance(user_id))}\n\n"
        
        # Key show karo
        if key.get('details'):
            text += f"🔑 **Your Key Details:**\n```\n{key['details']}\n```\n"
        else:
            text += f"🔑 **Your Key:**\n`{key['key']}`\n"
        
        text += "\n✨ Save these details and use in game!"
        
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
UPI ID: `your_upi@okhdfcbank`

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
def support(msg):
    bot.send_message(msg.from_user.id, "📞 Contact: @YourAdmin", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ About")
def about(msg):
    total = keys_col.count_documents({"status": "available"})
    sold = keys_col.count_documents({"status": "sold"})
    users = users_col.count_documents({})
    
    text = f"ℹ️ **About Bot**\n\n"
    text += f"📦 Available: {total}\n"
    text += f"✅ Sold: {sold}\n"
    text += f"👥 Users: {users}\n"
    text += f"📁 Categories: {len(KEY_CATEGORIES)}"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# -----------------------
# ADMIN PANEL
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Panel")
def admin_panel(msg):
    if not is_admin(msg.from_user.id):
        return
    
    total = keys_col.count_documents({})
    available = keys_col.count_documents({"status": "available"})
    sold = keys_col.count_documents({"status": "sold"})
    users = users_col.count_documents({})
    pending = recharges_col.count_documents({"status": "pending"})
    
    text = f"👑 **Admin Panel**\n\n"
    text += f"📊 **Stats:**\n"
    text += f"• Total Keys: {total}\n"
    text += f"• Available: {available}\n"
    text += f"• Sold: {sold}\n"
    text += f"• Users: {users}\n"
    text += f"• Pending: {pending}\n\n"
    text += f"Use buttons below:"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

# -----------------------
# ADD KEY (Single with Details) - Admin yahan details dalega
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "➕ Add Key" and is_admin(msg.from_user.id))
def add_key_start(msg):
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(f"{data['emoji']} {data['name']}", callback_data=f"addcat_{key}"))
    
    bot.send_message(msg.from_user.id, "📝 Select category:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("addcat_"))
def add_key_category(call):
    category = call.data.replace("addcat_", "")
    admin_add_key_state[call.from_user.id] = {"category": category}
    
    bot.edit_message_text(
        f"📝 **Add Key for {KEY_CATEGORIES[category]['name']}**\n\n"
        f"Send the key details in this format:\n\n"
        f"`🎮 Brutal Server - Asia`\n"
        f"`Email: example@gmail.com`\n"
        f"`Password: bgmi123`\n"
        f"`Server: Asia`\n\n"
        f"**YEH DETAILS DONO JAGAH DIKHENGE:**\n"
        f"1. **Kharidne se pehle** - Preview mein\n"
        f"2. **Kharidne ke baad** - Final key mein\n\n"
        f"Jo bhi details aap daloge, wahi user ko milega!",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id in admin_add_key_state and is_admin(msg.from_user.id))
def handle_add_key(msg):
    user_id = msg.from_user.id
    category = admin_add_key_state[user_id]['category']
    details = msg.text.strip()
    
    if not details:
        bot.send_message(user_id, "❌ Details cannot be empty!")
        return
    
    # Generate a unique key ID for database
    key_id = f"KEY{int(time.time())}{user_id}"
    
    keys_col.insert_one({
        "key": key_id,
        "category": category,
        "price": KEY_CATEGORIES[category]['price'],
        "details": details,  # Yeh details dono jagah use hongi
        "status": "available",
        "added_by": user_id,
        "added_at": datetime.utcnow()
    })
    
    count = keys_col.count_documents({"category": category, "status": "available"})
    
    bot.send_message(
        user_id,
        f"✅ **Key Added Successfully!**\n\n"
        f"Category: {KEY_CATEGORIES[category]['emoji']} {KEY_CATEGORIES[category]['name']}\n"
        f"Price: {format_currency(KEY_CATEGORIES[category]['price'])}\n"
        f"Available in category: {count}\n\n"
        f"📝 **Details saved (yeh dikhenge user ko):**\n```\n{details}\n```"
    )
    
    log_admin_action(user_id, "ADD_KEY", {"category": category})
    admin_add_key_state.pop(user_id, None)

# -----------------------
# KEY LIST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📋 Key List" and is_admin(msg.from_user.id))
def key_list(msg):
    text = "📋 **Key Inventory**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        avail = keys_col.count_documents({"category": key, "status": "available"})
        sold = keys_col.count_documents({"category": key, "status": "sold"})
        text += f"{data['emoji']} {data['name']}: {avail} avail, {sold} sold\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# REMOVE KEY - Sab keys show hongi
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "🗑 Remove Key" and is_admin(msg.from_user.id))
def remove_key_start(msg):
    user_id = msg.from_user.id
    
    # Sab categories se keys collect karo
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
    for i, key in enumerate(all_keys[:10], 1):  # Max 10 keys show karo
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
        text += f"Category: {cat_name}\n"
        text += f"Key ID: `{key['key']}`\n\n"
        
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
            f"Category: {KEY_CATEGORIES[key['category']]['name']}\n"
            f"Key ID: `{key['key']}`",
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
    text += "`category:details1,details2,details3`\n\n"
    text += "Examples:\n"
    text += "• `weekend:🎮 Brutal Asia,🎮 Brutal Europe,🎮 Brutal India`\n"
    text += "• `royalty:🏆 30 Days Pass,🏆 60 Days Pass,🏆 90 Days Pass`\n\n"
    text += "Categories:\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"• {key}: {data['emoji']} {data['name']}\n"
    
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
            bot.send_message(msg.from_user.id, f"❌ Invalid category!")
            return
        
        items = [k.strip() for k in items_str.split(',') if k.strip()]
        added = 0
        
        for details in items:
            key_id = f"KEY{int(time.time())}{msg.from_user.id}{added}"
            
            keys_col.insert_one({
                "key": key_id,
                "category": category,
                "price": KEY_CATEGORIES[category]['price'],
                "details": details,
                "status": "available",
                "added_by": msg.from_user.id,
                "added_at": datetime.utcnow()
            })
            added += 1
            time.sleep(0.1)
        
        bot.send_message(msg.from_user.id, f"✅ Added {added} keys to {KEY_CATEGORIES[category]['name']}")
        log_admin_action(msg.from_user.id, "BULK_ADD", {"category": category, "added": added})
        
    except Exception as e:
        bot.send_message(msg.from_user.id, f"❌ Error: {str(e)}")
    
    user_states.pop(msg.from_user.id, None)

# -----------------------
# MANAGE CATEGORIES
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📁 Manage Categories" and is_admin(msg.from_user.id))
def manage_categories(msg):
    text = "📁 **Category Management**\n\n"
    
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['emoji']} **{data['name']}**\n"
        text += f"Key: `{key}` | Price: {format_currency(data['price'])}\n"
        if data['description']:
            text += f"Desc: {data['description']}\n"
        text += "\n"
    
    text += "Commands:\n"
    text += "/addcat key|name|price|emoji|desc\n"
    text += "/editcat key|field|value\n"
    text += "/delcat key\n\n"
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
            bot.reply_to(msg, "❌ Category already exists!")
            return
        
        categories_col.insert_one({
            "key": key,
            "name": name,
            "price": price,
            "emoji": emoji,
            "description": desc,
            "status": "active"
        })
        
        load_categories()
        bot.reply_to(msg, f"✅ Category {emoji} {name} added!")
        
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
        load_categories()
        
        bot.reply_to(msg, f"✅ Category {key} updated!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['delcat'])
def delete_category(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        key = msg.text.split()[1].lower()
        
        if key not in KEY_CATEGORIES:
            bot.reply_to(msg, "❌ Category not found!")
            return
        
        keys_col.delete_many({"category": key})
        categories_col.delete_one({"key": key})
        load_categories()
        
        bot.reply_to(msg, f"✅ Category deleted with all keys!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# USERS LIST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "👥 Users List" and is_admin(msg.from_user.id))
def users_list(msg):
    total = users_col.count_documents({})
    recent = list(users_col.find().sort("joined_at", -1).limit(5))
    
    text = f"👥 **Users: {total}**\n\n**Recent:**\n"
    for user in recent:
        name = user.get('name', 'Unknown')[:15]
        bal = get_balance(user['user_id'])
        text += f"• {name} - {format_currency(bal)}\n"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

# -----------------------
# PENDING RECHARGES
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "💸 Pending Recharges" and is_admin(msg.from_user.id))
def pending_recharges(msg):
    pending = list(recharges_col.find({"status": "pending"}).sort("created_at", -1).limit(5))
    
    if not pending:
        bot.send_message(msg.from_user.id, "✅ No pending recharges!")
        return
    
    text = "💸 **Pending Recharges**\n\n"
    for p in pending:
        text += f"ID: `{p['_id']}`\n"
        text += f"User: {p['user_id']}\n"
        text += f"Amount: {format_currency(p['amount'])}\n"
        text += f"UTR: {p.get('utr', 'N/A')}\n\n"
    
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
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# -----------------------
# BROADCAST
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📢 Broadcast" and is_admin(msg.from_user.id))
def broadcast_start(msg):
    bot.send_message(msg.from_user.id, "📢 Send message to broadcast:")
    user_states[msg.from_user.id] = "admin_broadcast"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_broadcast" and is_admin(msg.from_user.id),
                    content_types=['text', 'photo'])
def process_broadcast(msg):
    users = list(users_col.find())
    sent = 0
    
    bot.send_message(msg.from_user.id, "📡 Broadcasting...")
    
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
            pass
    
    bot.send_message(msg.from_user.id, f"✅ Sent to {sent} users")
    user_states.pop(msg.from_user.id, None)

# -----------------------
# BAN/UNBAN
# -----------------------
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
        else:
            banned_users_col.insert_one({"user_id": target, "status": "active", "banned_at": datetime.utcnow()})
            bot.send_message(msg.from_user.id, f"✅ User {target} banned!")
            try:
                bot.send_message(target, "🚫 You have been banned!")
            except:
                pass
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
            {"$set": {"status": "inactive"}}
        )
        
        if result.modified_count > 0:
            bot.send_message(msg.from_user.id, f"✅ User {target} unbanned!")
            try:
                bot.send_message(target, "✅ You have been unbanned!")
            except:
                pass
        else:
            bot.send_message(msg.from_user.id, "❌ User not banned!")
    except:
        bot.send_message(msg.from_user.id, "❌ Invalid ID!")
    
    user_states.pop(msg.from_user.id, None)

# -----------------------
# DEDUCT/ADD BALANCE
# -----------------------
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
                bot.send_message(user_id, f"❌ Insufficient balance!")
                admin_deduct_state.pop(user_id, None)
                return
            
            deduct_balance(state["target"], state["amount"])
            action = "DEDUCTED"
        else:
            add_balance(state["target"], state["amount"])
            action = "ADDED"
        
        new_balance = get_balance(state["target"])
        
        bot.send_message(
            user_id,
            f"✅ {action} {format_currency(state['amount'])}\n"
            f"User: {state['target']}\n"
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
    text = "🎟 **Coupon Commands:**\n\n"
    text += "/createcoupon CODE AMOUNT MAXUSES\n"
    text += "/deletecoupon CODE\n"
    text += "/couponlist\n\n"
    text += "Example: /createcoupon DIWALI50 50 100"
    
    bot.send_message(msg.from_user.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['createcoupon'])
def create_coupon(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        if len(parts) != 4:
            raise ValueError("Invalid format")
        
        code = parts[1].upper()
        amount = float(parts[2])
        max_uses = int(parts[3])
        
        if coupons_col.find_one({"code": code}):
            bot.reply_to(msg, "❌ Coupon exists!")
            return
        
        coupons_col.insert_one({
            "code": code,
            "amount": amount,
            "max_uses": max_uses,
            "used_by": [],
            "status": "active",
            "created_at": datetime.utcnow()
        })
        
        bot.reply_to(msg, f"✅ Coupon {code} created!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['deletecoupon'])
def delete_coupon(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        code = msg.text.split()[1].upper()
        coupons_col.delete_one({"code": code})
        bot.reply_to(msg, f"✅ Coupon deleted!")
    except:
        bot.reply_to(msg, "❌ Error!")

@bot.message_handler(commands=['couponlist'])
def coupon_list(msg):
    if not is_admin(msg.from_user.id):
        return
    
    coupons = list(coupons_col.find({"status": "active"}))
    
    if not coupons:
        bot.reply_to(msg, "📭 No coupons!")
        return
    
    text = "🎟 **Active Coupons**\n\n"
    for c in coupons:
        used = len(c.get('used_by', []))
        text += f"`{c['code']}` - {format_currency(c['amount'])} ({used}/{c['max_uses']})\n"
    
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# -----------------------
# SALES REPORT
# -----------------------
@bot.message_handler(func=lambda msg: msg.text == "📈 Sales Report" and is_admin(msg.from_user.id))
def sales_report(msg):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = list(keys_col.find({"status": "sold", "sold_at": {"$gte": today}}))
    
    today_count = len(today_sales)
    today_revenue = sum(k.get('price', 0) for k in today_sales)
    
    week_ago = today - timedelta(days=7)
    week_count = keys_col.count_documents({"status": "sold", "sold_at": {"$gte": week_ago}})
    
    text = f"📈 **Sales Report**\n\n"
    text += f"Today: {today_count} keys | {format_currency(today_revenue)}\n"
    text += f"This Week: {week_count} keys\n\n"
    text += f"**Category Breakdown:**\n"
    
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
    
    # Notify admin
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
    logger.info(f"Categories: {len(KEY_CATEGORIES)}")
    
    # Create indexes
    try:
        keys_col.create_index("key", unique=True)
        keys_col.create_index("status")
        coupons_col.create_index("code", unique=True)
    except:
        pass
    
    # Start bot
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(5)