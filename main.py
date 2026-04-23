import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from ai_engine import get_ai_response

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Merhaba! Ben senin Erasmus dijital mentorunum. İspanya vizesi, "
        "konaklama güvenliği ve bürokratik süreçlerde hata yapmaman için buradayım. "
        "İlk olarak, sürecinin hangi aşamasındasın?"
    )
    await update.message.reply_text(message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text
    
    # Bot cevap verene kadar "Yazıyor..." animasyonu göster
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    # Gemini API'sine mesajı yolla ve cevabı al
    ai_reply = await get_ai_response(user_text)
    
    # Kullanıcıya AI cevabını dön
    await update.message.reply_text(ai_reply)

def main() -> None:
    if not TOKEN:
        print("Hata: TELEGRAM_BOT_TOKEN bulunamadı. Lütfen .env dosyanızı kontrol edin.")
        return

    application = Application.builder().token(TOKEN).build()
    
    # /start komutu için handler
    application.add_handler(CommandHandler("start", start))
    
    # Gelen tüm metin mesajlarını (komut olmayan) yakalamak için handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
