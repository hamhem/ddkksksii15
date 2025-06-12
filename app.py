import os
import sqlite3
import asyncio
from flask import Flask, request, jsonify
from telegram import Bot

app = Flask(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN', '7858846348:AAFJU4XdTtwU59jPEHXvd-1JFc8s9BIng2s')
OWNER_ID = int(os.getenv('OWNER_ID', '6746140279'))
DB_PATH = os.getenv('DB_PATH', '/data/users.db')

# Initialize bot
bot = Bot(token=BOT_TOKEN)

# Database setup with connection pooling
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")  # 30 second timeout
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            user_id INTEGER PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0.0
        )
        """)
        conn.commit()

@app.route('/nowpayments_callback', methods=['POST'])
def payment_callback():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400

        logger.info(f"Received callback data: {data}")

        # Validate required fields
        required_fields = ['payment_status', 'order_id', 'price_amount']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        status = data['payment_status']
        order_id = data['order_id']
        amount = float(data['price_amount'])

        # Validate order ID format
        if not order_id.startswith('c2s_'):
            return jsonify({"error": "Invalid order ID format"}), 400

        try:
            user_id = int(order_id.split('_')[1])
        except (IndexError, ValueError):
            return jsonify({"error": "Invalid user ID in order ID"}), 400

        if status.lower() == 'finished':
            # Update balance in transaction
            with get_db() as conn:
                cursor = conn.cursor()
                # Use INSERT OR REPLACE to handle both new and existing users
                cursor.execute("""
                INSERT OR REPLACE INTO balances (user_id, balance)
                VALUES (?, COALESCE(
                    (SELECT balance FROM balances WHERE user_id = ?), 0) + ?)
                """, (user_id, user_id, amount))
                conn.commit()

                # Verify update
                cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
                updated_balance = cursor.fetchone()['balance']
                logger.info(f"Updated balance for user {user_id}: {updated_balance}")

            # Send notifications
            asyncio.run(notify_parties(user_id, amount))
            
            return jsonify({
                "status": "success",
                "user_id": user_id,
                "new_balance": updated_balance
            })

        return jsonify({"status": "payment_not_completed"})

    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

async def notify_parties(user_id, amount):
    try:
        # Notify admin
        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"💳 New deposit: ${amount:.2f} from user {user_id}"
        )
        
        # Notify user
        await bot.send_message(
            chat_id=user_id,
            text=f"✅ Your deposit of ${amount:.2f} was successful!"
        )
    except Exception as e:
        logger.error(f"Notification failed: {str(e)}")

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start Flask app
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
