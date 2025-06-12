import os
import sqlite3
import asyncio
from flask import Flask, request, jsonify
from telegram import Bot

app = Flask(__name__)

# Configuration
BOT_TOKEN = '7858846348:AAFJU4XdTtwU59jPEHXvd-1JFc8s9BIng2s'
OWNER_ID = 6746140279
DB_PATH = '/data/users.db'

# Initialize Telegram Bot
bot = Bot(token=BOT_TOKEN)

# Ensure database exists
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            user_id INTEGER PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

# Update balance
def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO balances (user_id, balance)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?
    """, (user_id, amount, amount))
    conn.commit()
    cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    conn.close()
    return balance

# Notify user and admin
def notify(user_id, amount, new_balance):
    try:
        asyncio.run(bot.send_message(chat_id=user_id, text=f"✅ Deposit of ${amount:.2f} received! New balance: ${new_balance:.2f}"))
    except Exception as e:
        print(f"User notify error: {e}")

    try:
        asyncio.run(bot.send_message(chat_id=OWNER_ID, text=f"💸 New deposit of ${amount:.2f} from user {user_id}"))
    except Exception as e:
        print(f"Admin notify error: {e}")

@app.route('/nowpayments_callback', methods=['POST'])
def nowpayments_callback():
    if not request.is_json:
        return jsonify({"error": "Expected JSON"}), 400

    data = request.get_json()
    print("Received callback:", data)

    status = data.get("payment_status")
    order_id = data.get("order_id")
    amount = float(data.get("price_amount", 0))

    if not order_id or not status:
        return jsonify({"error": "Missing order_id or status"}), 400

    if not order_id.startswith("c2s_"):
        return jsonify({"error": "Invalid order ID"}), 400

    try:
        user_id = int(order_id.split("_")[1])
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400

    if status.lower() == "finished":
        new_balance = update_balance(user_id, amount)
        notify(user_id, amount, new_balance)

        return jsonify({
            "status": "success",
            "user_id": user_id,
            "amount": amount,
            "new_balance": new_balance
        })

    return jsonify({"status": "ignored"}), 200

@app.route('/')
def home():
    return "Callback server is running."

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
