import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Local module imports
from bot.config import TELEGRAM_BOT_TOKEN
from bot.server.web_server import start_keep_alive
from bot.server.telegram_handlers import (
    start,
    send_logs_command,
    revoke_command,
    register_email_command,
    handle_message
)

def run_bot():
    """Sets up and runs the Telegram bot."""
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register handlers imported from telegram_handlers.py
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send", send_logs_command))
    app.add_handler(CommandHandler("revoke", revoke_command))
    app.add_handler(CommandHandler("register", register_email_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("Telegram bot is starting to poll...")
    app.run_polling()

if __name__ == "__main__":
    # Basic logging configuration
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # Start the web server in a background thread
    start_keep_alive()
    logging.info("Flask web server started in the background.")
    
    # Run the Telegram bot
    run_bot()