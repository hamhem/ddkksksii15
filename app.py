from flask import Flask, request
import sqlite3
import logging
import requests

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = '7858846348:AAFJU4XdTtwU59jPEHXvd-1JFc8s9BIng2s'
OWNER_ID = 6746140279  # your Telegram user ID

# === LOGGING ===
logging.basicConfig(level=logging.INFO)

# === DATABASE INIT (optional safety) ===
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS balances (user_id INTEGER PRIMARY KEY, balance REAL)")
    conn.commit()
    conn.close()

init_db()

# === IPN CALLBACK ROUTE ===
@app.route('/ipn', methods=['POST'])
def nowpayments_ipn():
    data = request.json
    logging.info(f"Received IPN: {data}")

    status = data.get("payment_status")
    order_id = data.get("order_id")
    amount = data.get("price_amount")

    if not order_id or not amount or status != "finished":
        return "Ignored", 200

    try:
        # Extract user_id from order_id format: c2s_userid_timestamp
        user_id = int(order_id.split("_")[1])
        amount = float(amount)

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO balances (user_id, balance) VALUES (?, ?)", (user_id, 0))
        cursor.execute("UPDATE balances SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()

        # Telegram notify owner
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={
                "chat_id": OWNER_ID,
                "text": f"💸 Deposit of ${amount:.2f} received from user ID {user_id}!"
            }
        )

    except Exception as e:
        logging.error(f"Error processing IPN: {e}")
        return "Error", 500

    return "OK", 200

# === ROOT TEST ===
@app.route('/')
def index():
    return "NOWPayments IPN Listener is running!"

# === START FLASK ===
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
