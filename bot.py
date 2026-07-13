import os
import asyncio
import aiohttp
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters, 
    ContextTypes
)
from aiohttp import web

# --- Конфигурация ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")

if not TELEGRAM_TOKEN:
    raise ValueError("Ошибка: переменная TELEGRAM_BOT_TOKEN должна быть установлена!")

if not WEBHOOK_URL:
    print("⚠️ Внимание: WEBHOOK_URL не установлен, использую polling")
    WEBHOOK_URL = None

# --- Хранилище истории диалогов ---
user_histories = {}

# ============================================
# 1. ПОИСК В ИНТЕРНЕТЕ
# ============================================

async def search_wikipedia(query: str) -> str:
    """Поиск в Википедии"""
    try:
        url = f"https://ru.wikipedia.org/api/rest_v1/page/summary/{quote_plus(query)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("extract"):
                        text = data['extract'][:500]
                        if len(data['extract']) > 500:
                            text += "..."
                        return f"📚 *Википедия:*\n{text}\n🔗 {data.get('content_urls', {}).get('desktop', {}).get('page', '')}"
    except:
        pass
    return None

async def search_duckduckgo(query: str) -> str:
    """Поиск через DuckDuckGo"""
    try:
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                
                if data.get("AbstractText"):
                    text = data['AbstractText'][:500]
                    if len(data['AbstractText']) > 500:
                        text += "..."
                    return f"🦆 *DuckDuckGo:*\n{text}\n🔗 {data.get('AbstractURL', '')}"
                
                if data.get("RelatedTopics"):
                    results = []
                    for topic in data["RelatedTopics"][:3]:
                        if "Text" in topic:
                            text = topic['Text'][:200]
                            if len(topic['Text']) > 200:
                                text += "..."
                            results.append(f"• {text}")
                    if results:
                        return f"🦆 *DuckDuckGo:*\n" + "\n".join(results)
    except:
        pass
    return None

async def search_all_sources(query: str) -> str:
    """Сбор информации из всех источников"""
    results = []
    
    wiki_result = await search_wikipedia(query)
    if wiki_result:
        results.append(wiki_result)
    
    ddg_result = await search_duckduckgo(query)
    if ddg_result:
        results.append(ddg_result)
    
    if not results:
        return "❌ Ничего не найдено по вашему запросу. Попробуйте переформулировать вопрос."
    
    full_response = "🔍 *Результаты поиска:*\n\n"
    for result in results:
        full_response += result + "\n\n"
    
    return full_response

# ============================================
# 2. ПРОВЕРКА: НУЖНО ЛИ ОТВЕЧАТЬ
# ============================================

def should_respond(update: Update) -> bool:
    """Проверяет, должен ли бот отвечать на сообщение"""
    
    if update.effective_chat.type == "private":
        return True
    
    if update.effective_chat.type in ["group", "supergroup"]:
        
        if update.message and update.message.text and update.message.text.startswith("/search"):
            return True
        
        if update.message and update.message.entities:
            for entity in update.message.entities:
                if entity.type == "mention":
                    mention_text = update.message.text[entity.offset:entity.offset + entity.length]
                    bot_username = update.get_bot().username
                    if mention_text.lower() == f"@{bot_username.lower()}":
                        return True
        
        if update.message and update.message.reply_to_message:
            if update.message.reply_to_message.from_user.id == update.get_bot().id:
                return True
        
        return False
    
    return False

def extract_query(update: Update) -> str:
    """Извлекает текст запроса из сообщения"""
    if not update.message or not update.message.text:
        return None
    
    text = update.message.text
    
    if text.startswith("/search"):
        query = text.replace("/search", "").strip()
        if query:
            return query
        return None
    
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == "mention":
                text = text[:entity.offset] + text[entity.offset + entity.length:]
                text = text.strip()
                break
    
    return text.strip() if text.strip() else None

# ============================================
# 3. КОМАНДЫ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "🤖 *Привет! Я — умный ИИ-помощник с доступом в интернет!*\n\n"
            "✅ Отвечаю на любые вопросы\n"
            "✅ Ищу в Википедии и DuckDuckGo\n"
            "✅ Даю развернутые ответы\n"
            "✅ Помню контекст диалога\n\n"
            "🔍 *Как использовать:*\n"
            "• Просто напиши вопрос\n"
            "• Используй /search [вопрос]\n\n"
            "📌 *Примеры:*\n"
            "• 'Кто такой Эйнштейн?'\n"
            "• 'Что такое ИИ?'",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🤖 *Привет! Я — ИИ-помощник для групп!*\n\n"
            "🔍 *Как со мной общаться:*\n"
            "• Напиши `/search [вопрос]`\n"
            "• Или упомяни меня: `@имя_бота [вопрос]`\n"
            "• Или ответь на моё сообщение\n\n"
            "📌 *Примеры:*\n"
            "`/search кто такой Эйнштейн`\n"
            "`@имя_бота что такое ИИ?`",
            parse_mode="Markdown"
        )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "ℹ️ *Использование:*\n"
            "`/search [текст запроса]`\n\n"
            "📌 *Примеры:*\n"
            "`/search кто создал интернет`\n"
            "`/search последние новости науки`",
            parse_mode="Markdown"
        )
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    result = await search_all_sources(query)
    
    user_id = update.effective_user.id
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": "user", "content": query})
    user_histories[user_id].append({"role": "assistant", "content": result})
    
    if len(result) > 4000:
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i:i+4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(result, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Доступные команды:*\n\n"
        "/start - Начать диалог\n"
        "/help - Показать эту справку\n"
        "/clear - Очистить историю диалога\n"
        "/search [вопрос] - Поиск в интернете (Википедия + DuckDuckGo)\n\n"
        "🔍 *Быстрый поиск:*\n"
        "• В личных сообщениях: просто напиши вопрос\n"
        "• В группах: используй /search или упомяни меня\n\n"
        "📌 *Примеры запросов:*\n"
        "• 'Кто написал Войну и мир?'\n"
        "• 'Что такое квантовая физика?'\n"
        "• 'Как работает ChatGPT?'",
        parse_mode="Markdown"
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_histories:
        del user_histories[user_id]
    await update.message.reply_text(
        "🧹 *История диалога очищена!*",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not should_respond(update):
        return
    
    query = extract_query(update)
    if not query:
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "ℹ️ Напишите вопрос после команды или упоминания.\n"
                "Пример: `/search ваш вопрос`",
                parse_mode="Markdown"
            )
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    result = await search_all_sources(query)
    
    user_id = update.effective_user.id
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": "user", "content": query})
    user_histories[user_id].append({"role": "assistant", "content": result})
    
    if len(result) > 4000:
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i:i+4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(result, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await query.edit_message_text(
            "📖 *Помощь:*\n\n"
            "🤖 *Что я умею:*\n"
            "• Отвечать на любые вопросы\n"
            "• Искать в Википедии и DuckDuckGo\n"
            "• Давать развернутые ответы\n"
            "• Помнить контекст разговора\n\n"
            "📌 *Команды:*\n"
            "/start - Главное меню\n"
            "/search [вопрос] - Поиск\n"
            "/clear - Очистить историю\n"
            "/help - Справка\n\n"
            "👥 *В группах:*\n"
            "• Используй `/search [вопрос]`\n"
            "• Или упомяни меня: `@имя_бота [вопрос]`",
            parse_mode="Markdown"
        )
    
    elif query.data == "search":
        await query.edit_message_text(
            "🔍 *Поиск в интернете:*\n\n"
            "📌 *Способы:*\n\n"
            "🔹 *В личных сообщениях:*\n"
            "• Просто напиши вопрос\n"
            "• Или используй `/search [вопрос]`\n\n"
            "🔹 *В группах:*\n"
            "• `/search ваш вопрос`\n"
            "• `@имя_бота ваш вопрос`\n"
            "• Ответь на моё сообщение\n\n"
            "🌐 *Источники:*\n"
            "• Википедия\n"
            "• DuckDuckGo",
            parse_mode="Markdown"
        )

# ============================================
# 4. HTTP-СЕРВЕР
# ============================================

async def health_check(request):
    """Проверка здоровья для Railway"""
    return web.Response(text="Бот работает! ✅")

async def handle_webhook(request):
    """Обработка вебхука от Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, None)
        await application.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        print(f"Webhook error: {e}")
        return web.Response(text="Error", status=500)

# ============================================
# 5. ЗАПУСК
# ============================================

async def main():
    global application
    
    print("🚀 Запуск бота...")
    print("📚 Источники: Википедия, DuckDuckGo")
    print("👥 Режим групп: /search, @имя_бота, reply")
    
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Если есть WEBHOOK_URL - используем вебхук
    if WEBHOOK_URL:
        print(f"🔗 Настройка вебхука: {WEBHOOK_URL}/webhook")
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        
        # Запускаем HTTP сервер
        app = web.Application()
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        app.router.add_post('/webhook', handle_webhook)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
        await site.start()
        
        print(f"🌐 HTTP сервер запущен на порту {PORT}")
        print("✅ Бот работает через webhook!")
        
        # Держим сервер запущенным
        await asyncio.Event().wait()
    else:
        # Используем polling
        print("📡 Запуск через polling...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        print("✅ Бот готов к работе!")
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
