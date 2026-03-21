import os
import asyncio
import aiohttp
import feedparser
import re  # Библиотека для регулярных выражений (очистка текста)
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
import sqlite3

# ==========================================
# 1. ПОЛУЧЕНИЕ И ПРОВЕРКА ТОКЕНА
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")

print("🚀 ЗАПУСК ДИАГНОСТИКИ СИСТЕМЫ...")

if not BOT_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Переменная окружения BOT_TOKEN пуста!")
    exit(1)

# Очищаем от пробелов
BOT_TOKEN = BOT_TOKEN.strip()

print(f"✅ Токен получен. Длина: {len(BOT_TOKEN)}")
print(f"👁️  Начало токена: {BOT_TOKEN[:10]}...")

# Проверка структуры
parts = BOT_TOKEN.split(':')
if len(parts) != 2 or not parts[0].isdigit():
    print(f"❌ ОШИБКА ФОРМАТА ТОКЕНА!")
    exit(1)

print("✅ Структура токена валидна.")

# ==========================================
# 2. НАСТРОЙКИ
# ==========================================
# ВПИШИТЕ СЮДА ИМЯ ВАШЕГО КАНАЛА (с @)
CHANNEL_ID = "@newstecnolojia" 

RSS_FEEDS = [
    "https://habr.com/ru/rss/all/new/",
    "https://www.techcrunch.com/feed/",
    "https://vc.ru/feed",
]

# ==========================================
# 3. БАЗА ДАННЫХ
# ==========================================
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

# ==========================================
# 4. ПАРСИНГ И ОЧИСТКА НОВОСТЕЙ
# ==========================================
async def fetch_news(session):
    new_posts = []
    url = RSS_FEEDS[0] # Берем первый источник (Хабр)
    
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                feed = feedparser.parse(text)
                
                for entry in feed.entries[:3]: # Берем 3 последние новости
                    link = entry.link
                    if not is_posted(link):
                        title = entry.title
                        summary_raw = entry.get('summary', 'Нет описания.')
                        
                        # === ОЧИСТКА ОТ HTML ТЕГОВ ===
                        # Удаляем все теги вида <...>
                        clean_summary = re.sub(r'<[^>]+>', '', summary_raw)
                        
                        # Заменяем переносы строк на пробелы, чтобы текст был сплошным
                        clean_summary = clean_summary.replace('\n', ' ').replace('\r', ' ')
                        
                        # Обрезаем длинный текст
                        if len(clean_summary) > 250:
                            clean_summary = clean_summary[:247] + "..."
                        
                        # Формируем сообщение. 
                        # Внимание: в заголовке и ссылке используем теги Telegram (<b>, <a>),
                        # а в тексте только чистый текст без тегов.
                        message = f"🚀 <b>{title}</b>\n\n📝 {clean_summary}\n\n🔗 <a href='{link}'>Читать далее</a>"
                        
                        new_posts.append(message)
                        save_news(link)
                        print(f"📰 Новость готова: {title[:40]}...")
            else:
                print(f"⚠️ Ошибка доступа к ленте: Статус {response.status}")
    except Exception as e:
        print(f"⚠️ Ошибка при парсинге: {e}")
        
    return new_posts

# ==========================================
# 5. ОСНОВНОЙ ЗАПУСК
# ==========================================
async def main():
    try:
        bot = Bot(token=BOT_TOKEN)
        me = await bot.get_me()
        print(f"✅ УСПЕХ! Бот запущен: @{me.username}")
    except Exception as e:
        print(f"❌ ОШИБКА ЗАПУСКА БОТА: {e}")
        return

    init_db()
    
    async with aiohttp.ClientSession() as session:
        print("🔄 Сканирование лент...")
        posts = await fetch_news(session)
        
        if posts:
            print(f"📤 Отправка {len(posts)} новостей в {CHANNEL_ID}...")
            for post in posts:
                try:
                    await bot.send_message(CHANNEL_ID, post, parse_mode=ParseMode.HTML)
                    print("   ✅ Отправлено успешно!")
                except Exception as e:
                    print(f"   ❌ Ошибка отправки: {e}")
        else:
            print("ℹ️ Новых новостей нет.")

    await bot.session.close()
    print("💤 Работа завершена.")

if __name__ == '__main__':
    asyncio.run(main())
