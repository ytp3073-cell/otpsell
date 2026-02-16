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
BOT_TOKEN = '8477235690:AAEUCputdxPMc3B_F3pXi6NR4WrbGb3t_h4'
ADMIN_ID = 8413263061  # Apna admin ID daalein
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

# Keyboard Buttons
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
    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🔙 Main Menu"))
    return keyboard

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("➕ Add Key"),
        KeyboardButton("🗑 Remove Key")
    )
    keyboard.add(
        KeyboardButton("📋 Key List"),
        KeyboardButton("💸 Approve Recharge")
    )
    keyboard.add(
        KeyboardButton("👥 Users"),
        KeyboardButton("📢 Broadcast")
    )
    keyboard.add(
        KeyboardButton("🚫 Ban User"),
        KeyboardButton("✅ Unban User")
    )
    keyboard.add(
        KeyboardButton("🎟 Coupons"),
        KeyboardButton("💳 Deduct Balance")
    )
    keyboard.add(KeyboardButton("🔙 Main Menu"))
    return keyboard

def get_buy_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("🎮 Weekend Challenge"),
        KeyboardButton("🏆 Royalty Pass")
    )
    keyboard.add(
        KeyboardButton("⚡ UC"),
        KeyboardButton("🎯 Event Pass")
    )
    keyboard.add(
        KeyboardButton("💎 AQM Keys"),
        KeyboardButton("🔙 Main Menu")
    )
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
            "created_at": datetime.utcnow()
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

# Key Categories and Prices
KEY_CATEGORIES = {
    "weekend": {"name": "🎮 Weekend Challenge", "price": 49},
    "royalty": {"name": "🏆 Royalty Pass", "price": 399},
    "uc": {"name": "⚡ UC", "price": 99},
    "event": {"name": "🎯 Event Pass", "price": 199},
    "aqm": {"name": "💎 AQM Keys", "price": 299}
}

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

🔥 **Premium BGMI Keys Available:**
• Weekend Challenge Keys
• Royalty Pass
• UC (Unknown Cash)
• Event Pass
• AQM Keys

✨ **Features:**
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

@bot.message_handler(func=lambda msg: msg.text == "🛒 Buy Keys")
def buy_keys(msg):
    user_id = msg.from_user.id
    
    text = "🎮 **Select Key Category**\n\n"
    for key, data in KEY_CATEGORIES.items():
        text += f"{data['name']} - {format_currency(data['price'])}\n"
        count = keys_col.count_documents({"category": key, "status": "available"})
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
    
    # Find category key
    category = None
    for key, data in KEY_CATEGORIES.items():
        if data['name'] == category_name:
            category = key
            price = data['price']
            break
    
    if not category:
        bot.send_message(user_id, "❌ Category not found!", reply_markup=get_buy_keyboard())
        return
    
    # Get available keys
    keys = list(keys_col.find({"category": category, "status": "available"}).limit(10))
    
    if not keys:
        bot.send_message(
            user_id,
            f"❌ No {category_name} keys available right now!\nCheck back later.",
            reply_markup=get_buy_keyboard()
        )
        return
    
    text = f"{category_name}\n\n"
    text += f"💰 Price: {format_currency(price)} per key\n"
    text += f"📦 Available: {len(keys)}\n\n"
    text += "Select key to purchase:\n\n"
    
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
    
    text = f"💰 **Your Balance:** {format_currency(balance)}\n\n"
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
        
        # Store in payment state
        upi_payment_states[user_id] = {
            "amount": amount,
            "step": "qr_shown"
        }
        
        # Clear user state
        user_states.pop(user_id, None)
        
        # Show payment details
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
            "https://files.catbox.moe/a310jr.jpg",  # QR code image
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
    
    # Check coupon
    coupon = coupons_col.find_one({"code": code, "status": "active"})
    
    if not coupon:
        bot.send_message(
            user_id,
            "❌ Invalid or expired coupon code!",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Check if already used
    if user_id in coupon.get("used_by", []):
        bot.send_message(
            user_id,
            "❌ You have already used this coupon!",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Check usage limit
    if len(coupon.get("used_by", [])) >= coupon.get("max_uses", 1):
        bot.send_message(
            user_id,
            "❌ This coupon has reached maximum usage!",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Apply coupon
    amount = coupon.get("amount", 0)
    add_balance(user_id, amount)
    
    # Update coupon usage
    coupons_col.update_one(
        {"code": code},
        {
            "$push": {"used_by": user_id},
            "$inc": {"used_count": 1}
        }
    )
    
    # Record transaction
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
    
    text = "ℹ️ **About Bot**\n\n"
    text += "🎮 **BGMI LODERS Key Shop**\n"
    text += "Version: 2.0\n\n"
    text += f"📊 **Stats:**\n"
    text += f"• Available Keys: {total_keys}\n"
    text += f"• Total Users: {total_users}\n"
    text += f"• Categories: 5\n\n"
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
@bot.message_handler(func=lambda msg: msg.text == "👑 Admin Panel" and is_admin(msg.from_user.id))
def admin_panel(msg):
    user_id = msg.from_user.id
    
    total_keys = keys_col.count_documents({})
    available_keys = keys_col.count_documents({"status": "available"})
    sold_keys = keys_col.count_documents({"status": "sold"})
    total_users = users_col.count_documents({})
    pending_recharges = recharges_col.count_documents({"status": "pending"})
    
    text = f"👑 **Admin Panel**\n\n"
    text += f"📊 **Statistics:**\n"
    text += f"• Total Keys: {total_keys}\n"
    text += f"• Available: {available_keys}\n"
    text += f"• Sold: {sold_keys}\n"
    text += f"• Total Users: {total_users}\n"
    text += f"• Pending Recharges: {pending_recharges}\n\n"
    text += f"🛠️ Use keyboard buttons below:"
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "➕ Add Key" and is_admin(msg.from_user.id))
def add_key_start(msg):
    user_id = msg.from_user.id
    
    text = "➕ **Add New Key**\n\n"
    text += "Select key category:\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, data in KEY_CATEGORIES.items():
        markup.add(InlineKeyboardButton(
            data['name'],
            callback_data=f"addkey_cat_{key}"
        ))
    
    bot.send_message(
        user_id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "🗑 Remove Key" and is_admin(msg.from_user.id))
def remove_key_start(msg):
    user_id = msg.from_user.id
    
    text = "🗑 **Remove Key**\n\n"
    text += "Enter the key code to remove:"
    
    bot.send_message(user_id, text, parse_mode="Markdown")
    user_states[user_id] = "admin_remove_key"

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "admin_remove_key" and is_admin(msg.from_user.id))
def process_key_removal(msg):
    user_id = msg.from_user.id
    key_code = msg.text.strip()
    
    result = keys_col.delete_one({"key": key_code})
    
    if result.deleted_count > 0:
        bot.send_message(
            user_id,
            f"✅ Key `{key_code}` removed successfully!",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(
            user_id,
            f"❌ Key `{key_code}` not found!",
            parse_mode="Markdown"
        )
    
    user_states.pop(user_id, None)
    admin_panel(msg)

@bot.message_handler(func=lambda msg: msg.text == "📋 Key List" and is_admin(msg.from_user.id))
def key_list(msg):
    user_id = msg.from_user.id
    
    text = "📋 **Key List**\n\n"
    
    for category_key, category_data in KEY_CATEGORIES.items():
        available = keys_col.count_documents({"category": category_key, "status": "available"})
        sold = keys_col.count_documents({"category": category_key, "status": "sold"})
        total = available + sold
        
        text += f"{category_data['name']}\n"
        text += f"   📦 Available: {available}\n"
        text += f"   ✅ Sold: {sold}\n"
        text += f"   📊 Total: {total}\n\n"
    
    text += "Total Keys: " + str(keys_col.count_documents({}))
    
    bot.send_message(
        user_id,
        text,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "💸 Approve Recharge" and is_admin(msg.from_user.id))
def approve_recharge(msg):
    user_id = msg.from_user.id
    
    pending = list(recharges_col.find({"status": "pending"}).sort("created_at", -1).limit(10))
    
    if not pending:
        bot.send_message(user_id, "✅ No pending recharge requests!")
        return
    
    text = "💸 **Pending Recharge Requests**\n\n"
    
    for req in pending:
        text += f"User: {req['user_id']}\n"
        text += f"Amount: {format_currency(req['amount'])}\n"
        text += f"UTR: {req.get('utr', 'N/A')}\n"
        text += f"Time: {req['created_at'].strftime('%H:%M %d/%m')}\n"
        text += f"ID: `{req['_id']}`\n\n"
    
    text += "Reply with: /approve [request_id] to approve\n"
    text += "Example: /approve 65f8a1b2c3d4e5f6a7b8c9d0"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

@bot.message_handler(commands=['approve'])
def handle_approve(msg):
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
        
        # Update request
        recharges_col.update_one(
            {"_id": req_id},
            {"$set": {"status": "approved", "approved_at": datetime.utcnow()}}
        )
        
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
        
        bot.reply_to(msg, f"✅ Recharge approved for user {req['user_id']}")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda msg: msg.text == "👥 Users" and is_admin(msg.from_user.id))
def list_users(msg):
    user_id = msg.from_user.id
    
    total_users = users_col.count_documents({})
    active_today = users_col.count_documents({
        "created_at": {"$gte": datetime.utcnow() - timedelta(days=1)}
    })
    
    text = f"👥 **User Statistics**\n\n"
    text += f"Total Users: {total_users}\n"
    text += f"New Today: {active_today}\n\n"
    
    # Top 5 users by balance
    top_users = list(wallets_col.find().sort("balance", -1).limit(5))
    
    if top_users:
        text += "💰 **Top Users by Balance:**\n"
        for i, wallet in enumerate(top_users, 1):
            user = users_col.find_one({"user_id": wallet['user_id']}) or {}
            name = user.get('name', 'Unknown')[:15]
            text += f"{i}. {name} - {format_currency(wallet['balance'])}\n"
    
    bot.send_message(user_id, text, parse_mode="Markdown")

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
                time.sleep(1)  # Rate limit protection
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {uid}: {e}")
    
    bot.send_message(
        user_id,
        f"✅ **Broadcast Complete**\n\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}\n"
        f"Total: {len(users)}",
        parse_mode="Markdown"
    )
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "🚫 Ban User" and is_admin(msg.from_user.id))
def ban_user_start(msg):
    user_id = msg.from_user.id
    
    text = "🚫 **Ban User**\n\nEnter user ID to ban:"
    bot.send_message(user_id, text, parse_mode="Markdown")
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
        
        user = users_col.find_one({"user_id": target_id})
        if not user:
            bot.send_message(user_id, "❌ User not found!")
            user_states.pop(user_id, None)
            return
        
        # Check if already banned
        if is_user_banned(target_id):
            bot.send_message(user_id, "⚠️ User is already banned!")
            user_states.pop(user_id, None)
            return
        
        # Ban user
        banned_users_col.insert_one({
            "user_id": target_id,
            "banned_by": user_id,
            "banned_at": datetime.utcnow(),
            "status": "active"
        })
        
        # Notify user
        try:
            bot.send_message(
                target_id,
                "🚫 **You have been banned from using this bot!**\nContact admin for more information."
            )
        except:
            pass
        
        bot.send_message(user_id, f"✅ User {target_id} has been banned!")
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid user ID!")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "✅ Unban User" and is_admin(msg.from_user.id))
def unban_user_start(msg):
    user_id = msg.from_user.id
    
    text = "✅ **Unban User**\n\nEnter user ID to unban:"
    bot.send_message(user_id, text, parse_mode="Markdown")
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
            
            # Notify user
            try:
                bot.send_message(
                    target_id,
                    "✅ **You have been unbanned!**\nYou can now use the bot again."
                )
            except:
                pass
        else:
            bot.send_message(user_id, "❌ User not found or not banned!")
        
    except ValueError:
        bot.send_message(user_id, "❌ Invalid user ID!")
    
    user_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text == "🎟 Coupons" and is_admin(msg.from_user.id))
def coupon_management(msg):
    user_id = msg.from_user.id
    
    text = "🎟 **Coupon Management**\n\n"
    text += "1. /createcoupon [code] [amount] [max_uses]\n"
    text += "2. /deletecoupon [code]\n"
    text += "3. /couponlist\n\n"
    text += "Example: /createcoupon WELCOME50 50 10"
    
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
        
        # Check if exists
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
            f"✅ Coupon created!\n\n"
            f"Code: `{code}`\n"
            f"Amount: {format_currency(amount)}\n"
            f"Max Uses: {max_uses}",
            parse_mode="Markdown"
        )
        
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
    else:
        bot.reply_to(msg, f"❌ Coupon {code} not found!")

@bot.message_handler(commands=['couponlist'])
def coupon_list(msg):
    if not is_admin(msg.from_user.id):
        return
    
    coupons = list(coupons_col.find({"status": "active"}))
    
    if not coupons:
        bot.reply_to(msg, "📭 No active coupons!")
        return
    
    text = "🎟 **Active Coupons**\n\n"
    for coupon in coupons:
        text += f"Code: `{coupon['code']}`\n"
        text += f"Amount: {format_currency(coupon['amount'])}\n"
        text += f"Uses: {coupon['used_count']}/{coupon['max_uses']}\n"
        text += f"Created: {coupon['created_at'].strftime('%d/%m')}\n\n"
    
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "💳 Deduct Balance" and is_admin(msg.from_user.id))
def deduct_balance_start(msg):
    user_id = msg.from_user.id
    
    text = "💳 **Deduct Balance**\n\nEnter user ID:"
    bot.send_message(user_id, text, parse_mode="Markdown")
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
            bot.send_message(user_id, "❌ Invalid user ID!")
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
            f"✅ Balance deducted!\n\n"
            f"User: {state['target_id']}\n"
            f"Amount: {format_currency(state['amount'])}\n"
            f"Reason: {reason}\n"
            f"New Balance: {format_currency(new_balance)}"
        )
        
        admin_deduct_state.pop(user_id, None)

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
    
    if data.startswith("addkey_cat_"):
        category = data.replace("addkey_cat_", "")
        
        # Store category in state
        user_states[user_id] = f"addkey_{category}"
        
        bot.edit_message_text(
            f"📝 Enter key for {KEY_CATEGORIES[category]['name']}:\n\n"
            f"Send the key code/link:",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id)
    
    elif data.startswith("buykey_"):
        key_id = data.replace("buykey_", "")
        
        try:
            key = keys_col.find_one({"_id": ObjectId(key_id), "status": "available"})
            
            if not key:
                bot.answer_callback_query(call.id, "❌ Key not available!", show_alert=True)
                bot.delete_message(call.message.chat.id, call.message.message_id)
                return
            
            price = KEY_CATEGORIES[key['category']]['price']
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
            bot.edit_message_text(
                f"✅ **Purchase Successful!**\n\n"
                f"🎮 Category: {KEY_CATEGORIES[key['category']]['name']}\n"
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
    admin_text += f"User: {user_id}\n"
    admin_text += f"Amount: {format_currency(amount)}\n"
    admin_text += f"UTR: {utr}\n"
    admin_text += f"ID: `{recharge_id}`"
    
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
        f"Amount: {format_currency(amount)}\n"
        f"UTR: {utr}\n"
        f"Status: Pending Approval\n\n"
        f"Admin will verify and approve shortly.",
        reply_markup=get_main_keyboard()
    )
    
    upi_payment_states.pop(user_id, None)

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith('/'))
def handle_commands(msg):
    # Handle approve command (already handled above)
    if msg.text.startswith('/approve'):
        handle_approve(msg)
    elif msg.text.startswith('/createcoupon'):
        create_coupon(msg)
    elif msg.text.startswith('/deletecoupon'):
        delete_coupon(msg)
    elif msg.text.startswith('/couponlist'):
        coupon_list(msg)

@bot.message_handler(func=lambda msg: True)
def fallback_handler(msg):
    user_id = msg.from_user.id
    
    # If user is in any state, ignore (state handlers already handle it)
    if user_id in user_states or user_id in upi_payment_states or user_id in admin_deduct_state:
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
    
    # Create indexes
    try:
        keys_col.create_index("key", unique=True)
        keys_col.create_index("status")
        coupons_col.create_index("code", unique=True)
        logger.info("✅ Database indexes created")
    except Exception as e:
        logger.error(f"❌ Index creation failed: {e}")
    
    # Start bot
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        time.sleep(30)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)