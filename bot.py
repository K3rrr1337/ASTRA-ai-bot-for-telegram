import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters, 
    ContextTypes
)
from openai import OpenAI

# --- Конфигурация ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Ошибка: переменные TELEGRAM_BOT_TOKEN и OPENROUTER_API_KEY должны быть установлены!")

# --- Инициализация клиента OpenRouter ---
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# --- Хранилище истории диалогов ---
user_histories = {}

# --- Функция запроса к ИИ ---
async def ask_ai(user_id: int, user_message: str) -> str:
    if user_id not in user_histories:
        user_histories[user_id] = [
            {"role": "system", "content": "Ты — полезный и дружелюбный ИИ-помощник. Отвечай кратко и по делу."}
        ]
    
    user_histories[user_id].append({"role": "user", "content": user_message})
    
    if len(user_histories[user_id]) > 11:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-10:]
    
    try:
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",
            messages=user_histories[user_id],
            temperature=0.7,
            max_tokens=2000
        )
        answer = response.choices[0].message.content
        user_histories[user_id].append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        print(f"Ошибка API: {e}")
        return f"❌ Извините, произошла ошибка: {str(e)}"

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("❓ Помощь", callback_data="help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *Привет! Я — ИИ-помощник на базе OpenRouter!*\n\n"
        "✅ Отвечаю на любые вопросы\n"
        "✅ Помогаю решать проблемы\n"
        "✅ Помню контекст диалога\n\n"
        "Просто напиши мне что-нибудь!",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Доступные команды:*\n"
        "/start - Начать диалог\n"
        "/help - Показать эту справку\n"
        "/clear - Очистить историю диалога\n\n"
        "_Просто напишите сообщение, и я отвечу._",
        parse_mode="Markdown"
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_histories:
        del user_histories[user_id]
    await update.message.reply_text("🧹 История диалога для вас очищена!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await ask_ai(user_id, user_text)
    
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i:i+4000])
    else:
        await update.message.reply_text(reply)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "help":
        await query.edit_message_text(
            "📖 *Помощь:*\n"
            "Просто отправьте мне любое текстовое сообщение.\n\n"
            "Команды:\n"
            "/start - Начать заново\n"
            "/clear - Очистить историю\n"
            "/help - Эта справка",
            parse_mode="Markdown"
        )

# --- Основная функция ---
def main():
    print("🚀 Запуск бота на OpenRouter...")
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Бот запущен и слушает сообщения...")
    application.run_polling()

if __name__ == "__main__":
    main()
