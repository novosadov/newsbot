import asyncio
import aiohttp
import feedparser # Для работы с RSS (проще и надежнее парсинга)
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
import sqlite3
import os

# КОНФИГУРАЦИЯ
BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
CHANNEL_ID = "@ваш_канал_или_ID" # Например: -1001234567890
RSS_FEEDS = [
    "https://habr.com/ru/rss/all/new/",
    "https://www.techcrunch.com/feed/",
    # Добавьте другие источники
]
CHECK_INTERVAL = 600  # Проверка каждые 10 минут (в секундах)

# Инициализация БД
def init_db():
    conn = sqlite3.connect('news.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS posted_news (link TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

def is_posted(link):
    conn = sqlite3.connect('news.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM posted_news WHERE link=?", (link,))
    result = c.fetchone()
    conn.close()
    return result is not None

def save_news(link):
    conn = sqlite3.connect('news.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO posted_news VALUES (?)", (link,))
    conn.commit()
    conn.close()

async def fetch_news(session):
    new_posts = []
    async with session.get(RSS_FEEDS[0]) as response: # Для примера берем первый фид
        if response.status == 200:
            text = await response.text()
            feed = feedparser.parse(text)
            
            for entry in feed.entries[:5]: # Берем последние 5 записей
                link = entry.link
                if not is_posted(link):
                    title = entry.title
                    summary = entry.summary[:200] + "..." if len(entry.summary) > 200 else entry.summary
                    new_posts.append(f"🚀 <b>{title}</b>\n\n{summary}\n\n🔗 <a href='{link}'>Читать далее</a>")
                    save_news(link)
    return new_posts

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    init_db()
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                posts = await fetch_news(session)
                for post in posts:
                    try:
                        await bot.send_message(CHANNEL_ID, post, parse_mode=ParseMode.HTML)
                        print(f"Новость отправлена: {post[:50]}...")
                    except Exception as e:
                        print(f"Ошибка отправки: {e}")
                
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                print(f"Критическая ошибка цикла: {e}")
                await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())
