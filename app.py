from flask import Flask, request
import requests
import sqlite3
import os

app = Flask(__name__)

BOT_TOKEN = '7858846348:AAFJU4XdTtwU59jPEHXvd-1JFc8s9BIng2s'
OWNER_ID = 6746140279
DB_PATH = 'users.db'

def add_balance(user_id: int, amount: float):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE balances SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    else:
        cursor.execute("INSERT INTO balances (user_id, balance) VALUES (?, ?)", (user_id, amount))
    conn.commit()
    conn.close()

def send_admin_alert(user_id: int, amount: float, currency: str):
    message = f"💸 User {user_id} just deposited {amount:.2f} {currency.upper()}!"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": OWNER_ID,
        "text": message
    })

@app.route('/nowpayments_callback', methods=['POST'])
def nowpayments_callback():
    data = request.json
    if data.get("payment_status") == "confirmed":
        order_id = data.get("order_id")  # format: c2s_<user_id>_<timestamp>
        currency = data.get("pay_currency")
        amount = float(data.get("pay_amount", 0))
        user_id = int(order_id.split('_')[1])
        add_balance(user_id, amount)
        send_admin_alert(user_id, amount, currency)
    return '', 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  # Render sets PORT automatically
    app.run(host='0.0.0.0', port=port)
