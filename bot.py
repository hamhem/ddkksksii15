import sys
import time
import os
import asyncio
import logging
import requests
import sqlite3
from contextlib import contextmanager
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.error import BadRequest

if sys.platform.startswith('win'):
    import nest_asyncio
    nest_asyncio.apply()
    
print("BOT DB EXISTS:", os.path.exists("/data/users.db"))

BOT_TOKEN = '7858846348:AAFJU4XdTtwU59jPEHXvd-1JFc8s9BIng2s'
NOWPAYMENTS_API_KEY = '30ZYG00-WCM4EGC-Q7Y4QSS-28GQ865'
OWNER_ID = 6746140279
CHANNEL_ID = '@PayToChat'

ASK_AMOUNT, ASK_CURRENCY, ASK_MESSAGE = range(3)
MIN_DEPOSIT = 0.5
MAX_DEPOSIT = 15000
PRICE_LIST = {
    "text": 0.35,
    "image": 4.0,
    "voice": 0.40,
    "video": 0.40
}
CURRENCIES = [
    ("Bitcoin", "btc"),
    ("Ethereum", "eth"),
    ("Litecoin", "ltc"),
    ("BNB", "bnb"),
    ("Solana", "sol"),
    ("Tron", "trx"),
    ("Toncoin", "ton"),
    ("Monero", "xmr"),
    ("USDC", "usdc"),
    ("DAI", "dai")
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Configuration
DB_PATH = "/data/users.db"

@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with db_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            user_id INTEGER PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0.0
        )
        """)
        conn.commit()

def get_balance(user_id: int) -> float:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0.0

def add_balance(user_id: int, amount: float):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO balances (user_id, balance)
        VALUES (?, COALESCE(
            (SELECT balance FROM balances WHERE user_id = ?), 0) + ?)
        """, (user_id, user_id, amount))
        conn.commit()

def deduct_balance(user_id: int, amount: float) -> bool:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if not result or result[0] < amount:
            return False
            
        cursor.execute("""
        UPDATE balances SET balance = balance - ? 
        WHERE user_id = ? AND balance >= ?
        """, (amount, user_id, amount))
        conn.commit()
        return cursor.rowcount > 0

def create_invoice(user_id: int, amount_usd: float, currency: str) -> dict:
    url = "https://api.nowpayments.io/v1/invoice"
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "price_amount": amount_usd,
        "price_currency": "usd",
        "pay_currency": currency.lower(),
        "order_id": f"c2s_{user_id}_{int(time.time())}",
        "order_description": f"Deposit ${amount_usd:.2f} to Crypto2Speak",
        "ipn_callback_url": "https://ddkksksii15.onrender.com/nowpayments_callback"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.info(f"NOWPayments response: {response.status_code} - {response.text}")
        response.raise_for_status()
        data = response.json()
        if "invoice_url" in data:
            return data
        elif "result" in data and "invoice_url" in data["result"]:
            return data["result"]
    except Exception as e:
        logger.error(f"NOWPayments API error: {e}")
    return None

async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only the owner can top up balances.")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        add_balance(user_id, amount)
        await update.message.reply_text(f"✅ Added ${amount:.2f} to user {user_id}.")
    except Exception as e:
        await update.message.reply_text("❌ Usage: /topup <user_id> <amount>")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗣️ Say Something", callback_data='say')],
        [InlineKeyboardButton("💰 Deposit", callback_data='deposit')],
        [InlineKeyboardButton("🤝 Referrals", callback_data='referrals')]
    ])

    text = (
        "\U0001f4ac <b>@PayToChat</b> — <i>Every message has a price. Make it count.</i>\n\n"
        "• Price Per Character: <b>$0.25</b>\n"
        "• Price Per Image/GIF: <b>$4.0</b>\n"
        "• Price Per Second (Voice): <b>$0.40</b>\n"
        "• Price Per Second (Video): <b>$0.40</b>\n\n"
        f"Your Balance: <b>${balance:.2f}</b>"
    )

    if update.message:
        await update.message.reply_html(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'deposit':
        await query.message.reply_text(
            f"💰 Enter amount to deposit (${MIN_DEPOSIT} - ${MAX_DEPOSIT}):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
            ])
        )
        return ASK_AMOUNT
    elif query.data == 'say':
        await query.message.reply_text(
            "What would you like to say? Your total will be calculated once sent.\n\n"
            "• Price Per Character: $0.25\n"
            "• Price Per Image/GIF: $4.0\n"
            "• Price Per Second (Voice Message): $0.40\n"
            "• Price Per Second (Video): $0.40",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Go Back", callback_data='cancel')]
            ])
        )
        return ASK_MESSAGE
    elif query.data == 'cancel':
        await start(update, context)
        return ConversationHandler.END

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        if MIN_DEPOSIT <= amount <= MAX_DEPOSIT:
            context.user_data['deposit_amount'] = amount
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(label, callback_data=f'currency_{code}') for label, code in CURRENCIES[i:i+2]]
                for i in range(0, len(CURRENCIES), 2)
            ])
            await update.message.reply_text("Select a currency:", reply_markup=keyboard)
            return ASK_CURRENCY
        else:
            await update.message.reply_text("Invalid amount. Try again.")
            return ASK_AMOUNT
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ASK_AMOUNT

async def handle_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    currency = query.data.split('_')[1].upper()
    amount = context.user_data['deposit_amount']
    user_id = query.from_user.id
    invoice = create_invoice(user_id, amount, currency)
    if not invoice:
        await query.message.reply_text("Failed to create payment. Try again later.")
        return ConversationHandler.END
    await query.message.reply_text(
        f"✅ Invoice created!\nAmount: ${amount:.2f} in {currency}\n\n{invoice['invoice_url']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open Payment Page", url=invoice['invoice_url'])]
        ])
    )
    return ConversationHandler.END

async def handle_say_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['original_message'] = update.message
    price = 0
    if update.message.text:
        price = len(update.message.text) * PRICE_LIST['text']
    elif update.message.voice:
        price = update.message.voice.duration * PRICE_LIST['voice']
    elif update.message.video:
        price = update.message.video.duration * PRICE_LIST['video']
    elif update.message.photo:
        price = PRICE_LIST['image']
    context.user_data['pending_price'] = price
    await update.message.reply_text(
        "How do you want to be shown?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Anonymous", callback_data='identity_anon'),
                InlineKeyboardButton("Full Name", callback_data='identity_fullname'),
                InlineKeyboardButton("@Username", callback_data='identity_username')
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
        ])
    )
    return ConversationHandler.END

async def handle_identity_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    identity = query.data.split('_')[1]
    user_id = query.from_user.id
    message = context.user_data.get('original_message')
    price = context.user_data.get('pending_price', 0)
    if price is None or message is None:
        await query.message.reply_text("Something went wrong. Try again.")
        return ConversationHandler.END
    if get_balance(user_id) < price:
        shortfall = price - get_balance(user_id)
        buttons = [InlineKeyboardButton(label, callback_data=f'currency_{code}') for label, code in CURRENCIES]
        currency_keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        currency_keyboard.append([InlineKeyboardButton("⬅️ Go Back", callback_data='cancel')])
        await query.message.reply_text(
            f"❌ Not enough balance. You need ${shortfall:.2f} more. Choose currency:",
            reply_markup=InlineKeyboardMarkup(currency_keyboard)
        )
        return ConversationHandler.END
    deduct_balance(user_id, price)
    sender = "Anonymous"
    if identity == 'fullname':
        sender = query.from_user.full_name
    elif identity == 'username':
        sender = f"@{query.from_user.username}" if query.from_user.username else query.from_user.full_name
    header = f"{sender} paid ${price:.2f} to say:"
    if message.text:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"{header}\n{message.text}")
    elif message.voice:
        await context.bot.send_voice(chat_id=CHANNEL_ID, voice=message.voice.file_id, caption=header)
    elif message.video:
        await context.bot.send_video(chat_id=CHANNEL_ID, video=message.video.file_id, caption=header)
    elif message.photo:
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=message.photo[-1].file_id, caption=header)
    await query.message.reply_text(f"✅ Sent! ${price:.2f} deducted. Balance: ${get_balance(user_id):.2f}")
    return ConversationHandler.END

async def main():
    # Initialize database (using the context manager version)
    init_db()
    
    # Verify database connection
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='balances'")
            if not cursor.fetchone():
                logger.error("Balances table not created!")
            else:
                logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    # Build application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Conversation handler setup
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('topup', topup),
            CallbackQueryHandler(button_handler, pattern='^say$'),
            CallbackQueryHandler(button_handler, pattern='^deposit$')
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)],
            ASK_CURRENCY: [CallbackQueryHandler(handle_currency, pattern='^currency_')],
            ASK_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, handle_say_message)]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern='^cancel$')]
    )
    
    # Add handlers
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_identity_choice, pattern='^identity_'))
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    logger.info("✅ Bot is running...")
    await app.run_polling()

def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update.effective_message:
        update.effective_message.reply_text("⚠️ An error occurred. Please try again.")

if __name__ == '__main__':
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
