import os
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# --- Конфигурация из переменных окружения (Railway) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
    raise ValueError("Ошибка: переменные TELEGRAM_BOT_TOKEN и DEEPSEEK_API_KEY должны быть установлены!")

# --- Инициализация клиента DeepSeek (через Anthropic-совместимый endpoint для поиска) ---
deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/anthropic"  # Специальный endpoint для поиска
)

# --- Хранилище истории диалогов ---
user_histories = {}

# --- Функция запроса к DeepSeek с поиском ---
async def ask_deepseek(user_id: int, user_message: str, enable_search: bool = False) -> str:
    """Отправляет запрос к DeepSeek с опциональным поиском в интернете."""
    
    if user_id not in user_histories:
        user_histories[user_id] = [
            {"role": "system", "content": "Ты — полезный и дружелюбный ИИ-помощник. Отвечай кратко и по делу."}
        ]
    
    user_histories[user_id].append({"role": "user", "content": user_message})
    
    # Ограничиваем историю до 10 последних сообщений
    if len(user_histories[user_id]) > 11:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-10:]
    
    try:
        # Формируем запрос с поддержкой поиска
        messages = user_histories[user_id]
        
        # Если включён поиск, добавляем специальный флаг в system prompt
        if enable_search:
            # Добавляем инструкцию для поиска
            search_prompt = "Если для ответа нужна актуальная информация из интернета, используй поиск. ВСЕГДА указывай источники."
            if messages[0]["role"] == "system":
                messages[0]["content"] += f" {search_prompt}"
            else:
                messages.insert(0, {"role": "system", "content": search_prompt})
        
        # Отправляем запрос через Anthropic-совместимый API
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
            # Параметры для поиска (поддержка tool_use)
            extra_body={
                "tools": [{
                    "type": "web_search",
                    "name": "web_search",
                    "description": "Поиск информации в интернете"
                }],
                "tool_choice": "auto" if enable_search else "none"
            }
        )
        
        # Проверяем, есть ли результаты поиска
        if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
            # Извлекаем результаты поиска
            tool_call = response.choices[0].message.tool_calls[0]
            if tool_call.function.name == "web_search":
                search_results = json.loads(tool_call.function.arguments)
                # Отправляем второй запрос с результатами поиска
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call.id,
                        "type": "web_search",
                        "function": {
                            "name": "web_search",
                            "arguments": json.dumps(search_results)
                        }
                    }]
                })
                # Добавляем результаты в сообщение
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": f"Результаты поиска: {json.dumps(search_results)}"
                })
                
                # Получаем финальный ответ с учётом поиска
                final_response = deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000
                )
                answer = final_response.choices[0].message.content
            else:
                answer = response.choices[0].message.content
        else:
            answer = response.choices[0].message.content
        
        # Сохраняем ответ в историю
        user_histories[user_id].append({"role": "assistant", "content": answer})
        return answer
        
    except Exception as e:
        print(f"Ошибка DeepSeek API: {e}")
        return f"❌ Извините, произошла ошибка: {str(e)}"

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск в интернете", callback_data="search")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *Привет! Я — ИИ-помощник на базе DeepSeek с доступом в интернет!*\n\n"
        "✅ Отвечаю на любые вопросы\n"
        "✅ Ищу актуальную информацию в интернете\n"
        "✅ Помогаю решать проблемы\n"
        "✅ Помню контекст диалога\n\n"
        "Просто напиши мне что-нибудь!\n"
        "Используй /search [вопрос] для поиска в интернете",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /search - поиск в интернете."""
    user_id = update.effective_user.id
    
    # Получаем текст запроса
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("ℹ️ Использование: /search [текст запроса]\nПример: /search новости сегодня")
        return
    
    # Отправляем статус
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Отправляем запрос с включённым поиском
    reply = await ask_deepseek(user_id, query, enable_search=True)
    await update.message.reply_text(f"🔍 *Результаты поиска:*\n\n{reply}", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    await update.message.reply_text(
        "📖 *Доступные команды:*\n"
        "/start - Начать диалог\n"
        "/help - Показать эту справку\n"
        "/search [вопрос] - Найти информацию в интернете\n"
        "/clear - Очистить историю диалога\n\n"
        "_Просто напишите сообщение, и я отвечу._\n"
        "_Для поиска в интернете используйте /search_",
        parse_mode="Markdown"
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /clear для очистки истории."""
    user_id = update.effective_user.id
    if user_id in user_histories:
        del user_histories[user_id]
    await update.message.reply_text("🧹 История диалога для вас очищена!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений."""
    user_id = update.effective_user.id
    user_text = update.message.text
    
    # Проверяем, нужно ли включить поиск (если сообщение начинается с ?)
    enable_search = user_text.startswith("?")
    if enable_search:
        user_text = user_text[1:].strip()
    
    # Показываем статус "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Получаем ответ от DeepSeek
    reply = await ask_deepseek(user_id, user_text, enable_search=enable_search)
    
    # Отправляем ответ, разбивая, если он слишком длинный
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i:i+4000])
    else:
        await update.message.reply_text(reply)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await query.edit_message_text(
            "📖 *Помощь:*\n"
            "Просто отправьте мне любое текстовое сообщение.\n\n"
            "🔍 *Для поиска в интернете:*\n"
            "• Используйте команду /search [вопрос]\n"
            "• Или начните сообщение с '?' (например: '? новости сегодня')\n\n"
            "Команды:\n"
            "/start - Начать заново\n"
            "/clear - Очистить историю\n"
            "/search - Поиск в интернете\n"
            "/help - Эта справка",
            parse_mode="Markdown"
        )
    elif query.data == "search":
        await query.edit_message_text(
            "🔍 *Поиск в интернете*\n\n"
            "Отправьте вопрос через команду:\n"
            "`/search ваш вопрос`\n\n"
            "Или просто начните сообщение с '?'\n"
            "Например: `? погода в Москве`",
            parse_mode="Markdown"
        )

# --- Основная функция запуска ---
def main():
    """Запуск бота с использованием long polling."""
    print("🚀 Запуск бота с поддержкой интернет-поиска...")
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запуск поллинга
    print("✅ Бот запущен и слушает сообщения...")
    application.run_polling()

if __name__ == "__main__":
    main()
