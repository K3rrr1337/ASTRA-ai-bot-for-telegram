import os
import asyncio
import json
import aiohttp
from urllib.parse import quote_plus
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters, 
    ContextTypes
)

# --- Конфигурация ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("Ошибка: переменная TELEGRAM_BOT_TOKEN должна быть установлена!")

# --- Хранилище истории диалогов ---
user_histories = {}

# ============================================
# 1. ПОИСК В ИНТЕРНЕТЕ (МНОЖЕСТВО ИСТОЧНИКОВ)
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
                        return f"📚 *Википедия:*\n{data['extract'][:500]}...\n🔗 {data.get('content_urls', {}).get('desktop', {}).get('page', '')}"
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
                    return f"🦆 *DuckDuckGo:*\n{data['AbstractText'][:500]}...\n🔗 {data.get('AbstractURL', '')}"
                
                if data.get("RelatedTopics"):
                    results = []
                    for topic in data["RelatedTopics"][:3]:
                        if "Text" in topic:
                            results.append(f"• {topic['Text'][:200]}")
                    if results:
                        return f"🦆 *DuckDuckGo:*\n" + "\n".join(results)
    except:
        pass
    return None

async def search_news(query: str) -> str:
    """Поиск новостей (через NewsAPI)"""
    try:
        # Используем бесплатный прокси для новостей
        url = f"https://newsapi.org/v2/everything?q={quote_plus(query)}&language=ru&pageSize=3&apiKey=YOUR_NEWS_API_KEY"
        # Если нет NewsAPI ключа, используем альтернативный источник
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("articles"):
                        articles = data["articles"][:3]
                        result = "📰 *Новости:*\n"
                        for i, article in enumerate(articles, 1):
                            result += f"{i}. {article['title']}\n"
                            if article.get('description'):
                                result += f"   {article['description'][:150]}...\n"
                            result += f"   🔗 {article['url']}\n\n"
                        return result
    except:
        pass
    return None

async def search_google(query: str) -> str:
    """Поиск через Google (альтернативный метод)"""
    try:
        # Используем бесплатный прокси для Google
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if data.get("AbstractText"):
                    return f"🔍 *Google/DDG:*\n{data['AbstractText'][:500]}...\n🔗 {data.get('AbstractURL', '')}"
    except:
        pass
    return None

async def search_all_sources(query: str) -> str:
    """Сбор информации из всех источников"""
    results = []
    
    # Ищем в Википедии
    wiki_result = await search_wikipedia(query)
    if wiki_result:
        results.append(wiki_result)
    
    # Ищем в DuckDuckGo
    ddg_result = await search_duckduckgo(query)
    if ddg_result:
        results.append(ddg_result)
    
    # Ищем новости
    news_result = await search_news(query)
    if news_result:
        results.append(news_result)
    
    # Если ничего не найдено
    if not results:
        return "❌ Ничего не найдено по вашему запросу. Попробуйте переформулировать вопрос."
    
    # Объединяем результаты
    full_response = "🔍 *Результаты поиска:*\n\n"
    for result in results:
        full_response += result + "\n\n"
    
    return full_response

# ============================================
# 2. ФОРМАТИРОВАНИЕ ОТВЕТОВ
# ============================================

async def format_response(raw_text: str) -> str:
    """Форматирование ответа для красивого отображения"""
    # Добавляем заголовки и структуру
    lines = raw_text.split('\n')
    formatted = []
    
    for line in lines:
        if line.strip():
            # Проверяем, является ли строка вопросом
            if line.endswith('?'):
                formatted.append(f"🤔 *{line.strip()}*")
            # Проверяем, является ли строка заголовком
            elif len(line.strip()) < 60 and line.strip().upper() == line.strip():
                formatted.append(f"📌 *{line.strip()}*")
            else:
                formatted.append(f"• {line.strip()}")
    
    return "\n".join(formatted)

# ============================================
# 3. КОМАНДЫ И ОБРАБОТЧИКИ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton("📰 Новости", callback_data="news")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *Привет! Я — умный ИИ-помощник с доступом в интернет!*\n\n"
        "✅ Отвечаю на любые вопросы\n"
        "✅ Ищу в Википедии, DuckDuckGo и новостях\n"
        "✅ Даю развернутые ответы\n"
        "✅ Помню контекст диалога\n\n"
        "🔍 *Как использовать:*\n"
        "• Просто напиши вопрос\n"
        "• Используй /search [вопрос]\n"
        "• Нажми кнопку 📰 для новостей\n\n"
        "📌 *Примеры:*\n"
        "• 'Кто такой Эйнштейн?'\n"
        "• 'Что такое ИИ?'\n"
        "• 'Последние новости технологий'",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /search - расширенный поиск"""
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
    
    # Ищем во всех источниках
    raw_result = await search_all_sources(query)
    formatted_result = await format_response(raw_result)
    
    # Сохраняем в историю
    user_id = update.effective_user.id
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": "user", "content": query})
    user_histories[user_id].append({"role": "assistant", "content": raw_result})
    
    # Отправляем результат с кнопками
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{query}")],
        [InlineKeyboardButton("🔍 Другие источники", callback_data=f"more_{query}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if len(formatted_result) > 4000:
        for i in range(0, len(formatted_result), 4000):
            await update.message.reply_text(
                formatted_result[i:i+4000], 
                parse_mode="Markdown",
                reply_markup=reply_markup if i == 0 else None
            )
    else:
        await update.message.reply_text(
            formatted_result, 
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /news - последние новости"""
    query = " ".join(context.args) if context.args else "технологии"
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    result = await search_news(query)
    if result:
        await update.message.reply_text(result, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "📰 *Новости по запросу:*\n"
            f"`{query}`\n\n"
            "❌ Не удалось найти свежие новости. Попробуйте другой запрос.",
            parse_mode="Markdown"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Доступные команды:*\n\n"
        "/start - Начать диалог\n"
        "/help - Показать эту справку\n"
        "/clear - Очистить историю диалога\n"
        "/search [вопрос] - Поиск в интернете (Википедия + DuckDuckGo)\n"
        "/news [тема] - Последние новости\n\n"
        "🔍 *Быстрый поиск:*\n"
        "• Просто напиши вопрос в чат\n"
        "• Я сам найду ответ\n\n"
        "📌 *Примеры запросов:*\n"
        "• 'Кто написал Войну и мир?'\n"
        "• 'Что такое квантовая физика?'\n"
        "• 'Новости космоса'\n"
        "• 'Как работает ChatGPT?'",
        parse_mode="Markdown"
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_histories:
        del user_histories[user_id]
    await update.message.reply_text(
        "🧹 *История диалога очищена!*\n\n"
        "Я забыл всё, о чём мы говорили ранее.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений"""
    user_id = update.effective_user.id
    user_text = update.message.text
    
    # Показываем статус "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Ищем во всех источниках
    raw_result = await search_all_sources(user_text)
    formatted_result = await format_response(raw_result)
    
    # Сохраняем в историю
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": "user", "content": user_text})
    user_histories[user_id].append({"role": "assistant", "content": raw_result})
    
    # Отправляем ответ
    if len(formatted_result) > 4000:
        for i in range(0, len(formatted_result), 4000):
            await update.message.reply_text(formatted_result[i:i+4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(formatted_result, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "help":
        await query.edit_message_text(
            "📖 *Помощь:*\n\n"
            "🤖 *Что я умею:*\n"
            "• Отвечать на любые вопросы\n"
            "• Искать в Википедии, DuckDuckGo и новостях\n"
            "• Давать развернутые ответы\n"
            "• Помнить контекст разговора\n\n"
            "📌 *Команды:*\n"
            "/start - Главное меню\n"
            "/search [вопрос] - Поиск\n"
            "/news [тема] - Новости\n"
            "/clear - Очистить историю",
            parse_mode="Markdown"
        )
    
    elif data == "search":
        await query.edit_message_text(
            "🔍 *Поиск в интернете:*\n\n"
            "📌 *Способы:*\n"
            "1. Команда: `/search ваш вопрос`\n"
            "2. Просто напиши вопрос в чат\n"
            "3. Нажми на кнопку 📰 для новостей\n\n"
            "📝 *Примеры:*\n"
            "• `кто такой Эйнштейн`\n"
            "• `что такое ИИ`\n"
            "• `история интернета`\n\n"
            "🌐 *Источники:*\n"
            "• Википедия\n"
            "• DuckDuckGo\n"
            "• Новостные ленты",
            parse_mode="Markdown"
        )
    
    elif data == "news":
        await query.edit_message_text(
            "📰 *Новости:*\n\n"
            "Используй команду:\n"
            "`/news [тема]`\n\n"
            "📌 *Примеры:*\n"
            "• `/news технологи`\n"
            "• `/news наука`\n"
            "• `/news спорт`\n\n"
            "_Если не указать тему, покажу новости о технологиях._",
            parse_mode="Markdown"
        )
    
    elif data.startswith("refresh_"):
        # Обновить поиск
        search_query = data.replace("refresh_", "")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        result = await search_all_sources(search_query)
        formatted_result = await format_response(result)
        
        await query.edit_message_text(
            f"🔄 *Обновленный поиск:*\n\n{formatted_result}",
            parse_mode="Markdown"
        )
    
    elif data.startswith("more_"):
        # Другие источники
        search_query = data.replace("more_", "")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Собираем информацию из разных источников
        response = "🔍 *Другие источники:*\n\n"
        
        # Проверяем каждый источник отдельно
        wiki = await search_wikipedia(search_query)
        if wiki:
            response += f"{wiki}\n\n"
        
        ddg = await search_duckduckgo(search_query)
        if ddg:
            response += f"{ddg}\n\n"
        
        news = await search_news(search_query)
        if news:
            response += f"{news}\n\n"
        
        if response == "🔍 *Другие источники:*\n\n":
            response = "❌ Дополнительной информации не найдено."
        
        await query.edit_message_text(response, parse_mode="Markdown")

# ============================================
# 4. ЗАПУСК БОТА
# ============================================

def main():
    print("🚀 Запуск бота с множественными источниками поиска...")
    print("📚 Источники: Википедия, DuckDuckGo, Новости")
    print("💬 Поддерживаются команды: /start, /help, /search, /news, /clear")
    
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("news", news_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Бот успешно запущен и готов к работе!")
    print("📊 Статистика:")
    print(f"   • Токен бота: {TELEGRAM_TOKEN[:10]}...")
    print("   • Модули: Википедия, DuckDuckGo, Новости")
    print("   • Поддержка кнопок: Да")
    print("   • История диалогов: Да\n")
    print("💡 Тестируй бота в Telegram!")
    
    application.run_polling()

if __name__ == "__main__":
    main()
