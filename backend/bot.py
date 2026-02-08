import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Hello! I am the Video Streaming Platform Bot. I help manage video uploads."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
     await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Check the admin dashboard for upload instructions."
    )

def main():
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        return

    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    help_handler = CommandHandler('help', help_command)
    
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    
    print("Bot is polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
