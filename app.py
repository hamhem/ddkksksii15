import os
import sqlite3
import asyncio
import logging
from flask import Flask, request, jsonify
from telegram import Bot

app = Flask(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '7858846348:AAFJU4XdTtwU59jPEHXvd-1JFc8s9BIng2s')
OWNER_ID = int(os.getenv('OWNER_ID', '6746140279'))
DB_PATH = os.getenv('DB_PATH', '/data/users.db')

# Initialize bot
bot = Bot(token=BOT_TOKEN)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection with WAL mode
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")  # 30 second timeout
    return conn

# Initialize database
def init_db():
    with get_db_connection() as conn:
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
        # Verify JSON content
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400

        data = request.get_json()
        logger.info(f"Received callback data: {data}")

        # Validate required fields
        required_fields = ['payment_status', 'order_id', 'price_amount']
        if not all(field in data for field in required_fields):
            return jsonify({"error": f"Missing required fields: {required_fields}"}), 400

        status = data['payment_status'].lower()
        order_id = data['order_id']
        amount = float(data['price_amount'])

        # Validate order ID format
        if not order_id.startswith('c2s_'):
            return jsonify({"error": "Invalid order ID format"}), 400

        try:
            user_id = int(order_id.split('_')[1])
        except (IndexError, ValueError) as e:
            return jsonify({"error": f"Invalid user ID in order ID: {str(e)}"}), 400

        if status == 'finished':
            # Update balance transaction
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO balances (user_id, balance)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?
                """, (user_id, amount, amount))
                conn.commit()

                # Verify update
                cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
                new_balance = cursor.fetchone()[0]

            logger.info(f"Updated balance for user {user_id}: {new_balance}")

            # Send notifications
            await notify_parties(user_id, amount, new_balance)
            
            return jsonify({
                "status": "success",
                "user_id": user_id,
                "amount": amount,
                "new_balance": new_balance
            })

        return jsonify({"status": "payment_not_completed"}), 200

    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

async def notify_parties(user_id, amount, new_balance):
    try:
        # Notify user
        await bot.send_message(
            chat_id=user_id,
            text=f"✅ Deposit of ${amount:.2f} received! New balance: ${new_balance:.2f}"
        )
        
        # Notify admin
        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"💸 New deposit: ${amount:.2f} from user {user_id}"
        )
    except Exception as e:
        logger.error(f"Notification failed: {str(e)}")

@app.route('/health', methods=['GET'])
def health_check():
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
        return jsonify({"status": "healthy"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start Flask app
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
