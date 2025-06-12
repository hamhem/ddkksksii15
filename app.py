import sys
import time
import asyncio
import logging
import requests
import sqlite3
import os
from flask import Flask, request, jsonify
from telegram import Bot

app = Flask(__name__)

BOT_TOKEN = '7858846348:AAFJU4XdTtwU59jPEHXvd-1JFc8s9BIng2s'
OWNER_ID = 6746140279  # Admin ID for notifications
bot = Bot(token=BOT_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# SQLite database path inside writable Render mount
DB_PATH = "/data/users.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS balances (user_id INTEGER PRIMARY KEY, balance REAL)")
conn.commit()

def add_balance(user_id: int, amount: float):
    cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result is None:
        cursor.execute("INSERT INTO balances (user_id, balance) VALUES (?, ?)", (user_id, amount))
    else:
        cursor.execute("UPDATE balances SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

@app.route('/nowpayments_callback', methods=['POST'])
def nowpayments_callback():
    data = request.json
    logger.info(f"Received callback: {data}")

    status = data.get("payment_status")
    order_id = data.get("order_id")
    amount = float(data.get("price_amount", 0))

    if not order_id or not status:
        return jsonify({"error": "Missing fields"}), 400

    if not order_id.startswith("c2s_"):
        return jsonify({"error": "Invalid order_id"}), 400

    try:
        user_id = int(order_id.split("_")[1])
    except ValueError:
        return jsonify({"error": "Invalid user_id in order_id"}), 400

    if status == "finished":
        add_balance(user_id, amount)

        # Notify admin
        try:
            asyncio.run(bot.send_message(
                chat_id=OWNER_ID,
                text=f"💸 Deposit of ${amount:.2f} received from user ID {user_id}!"
            ))
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

        # Notify user
        try:
            asyncio.run(bot.send_message(
                chat_id=user_id,
                text=f"✅ Your deposit of ${amount:.2f} was successful and has been added to your balance!"
            ))
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
