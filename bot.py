import os
import asyncio
import aiohttp
import feedparser
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
import sqlite3

# ==========================================
# 1. ПОЛУЧЕНИЕ И ПРОВЕРКА ТОКЕНА (ДИАГНОСТИКА)
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")

print("🚀 ЗАПУСК ДИАГНОСТИКИ СИСТЕМЫ...")

if not BOT_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Переменная окружения BOT_TOKEN пуста!")
    print("   Проверьте: Settings -> Secrets and variables -> Actions.")
    print("   Убедитесь, что имя секрета точно: BOT_TOKEN")
    exit(1)

# Очищаем от возможных пробелов и переносов строк по краям
BOT_TOKEN = BOT_TOKEN.strip()

print(f"✅ Токен получен из среды.")
print(f"📏 Длина токена: {len(BOT_TOKEN)} символов.")
print(f"👁️  Первые 15 символов: {BOT_TOKEN[:15]}...")
print(f"👁️  Последние 10 символов: ...{BOT_TOKEN[-10:]}")

# Проверка структуры (должно быть ЧИСЛО:БУКВЫ)
parts = BOT_TOKEN.split(':')
if len(parts) != 2:
    print(f"❌ ОШИБКА ФОРМАТА: Ожидается формат 'ID:SECRET' (одно двоеточие).")
    print(f"   Найдено частей после разделения по ':': {len(parts)}")
    print(f"   Возможно, вы скопировали лишний текст или пробелы внутри токена.")
    print(f"   Полное содержимое переменной: [{BOT_TOKEN}]")
    exit(1)

bot_id, secret_part = parts
if not bot_id.isdigit():
    print(f"❌ ОШИБКА: Первая часть (ID) должна состоять только из цифр.")
    print(f"   Получено: '{bot_id}'")
    exit(1)

print("✅ Структура токена валидна. Попытка инициализации бота...")

# ==========================================
# 2. НАСТРОЙКИ КАНАЛА И ИСТОЧНИКОВ
# ==========================================
# Замените на ID вашего канала (например, '@my_tech_news' или '-100123456789')
CHANNEL_ID = "@newstecnolojia" # <-- ВПИШИТЕ СЮДА ВАШ КАНАЛ (с @ или числовой ID)

RSS_FEEDS = [
    "https://habr.com/ru/rss/all/new/",
    "https://www.techcrunch.com/feed/",
    "https://vc.ru/feed",
]

CHECK_INTERVAL = 600  # 10 минут

# ==========================================
# 3. РАБОТА С БАЗОЙ ДАННЫХ (SQLite)
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
# 4. ЛОГИКА ПАРСИНГА НОВОСТЕЙ
# ==========================================
async def fetch_news(session):
    new_posts = []
    # Для примера берем первый фид из списка. 
    # В продакшене можно сделать цикл по всем feeds.
    url = RSS_FEEDS[0] 
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                feed = feedparser.parse(text)
                
                # Берем последние 3 новости, чтобы не спамить при первом запуске
                for entry in feed.entries[:3]:
                    link = entry.link
                    if not is_posted(link):
                        title = entry.title
                        # Очищаем описание от HTML тегов для краткости
                        summary_raw = entry.get('summary', '')
                        # Простая очистка от тегов (можно усложнить при необходимости)
                        summary = "".join([s for s in summary_raw.split() if not s.startswith('<')])[:200]
                        if len(summary_raw) > 200: summary += "..."
                        
                        message = f"🚀 <b>{title}</b>\n\n📝 {summary}\n\n🔗 <a href='{link}'>Читать далее</a>"
                        new_posts.append(message)
                        save_news(link)
                        print(f"📰 Подготовлена новость: {title[:30]}...")
            else:
                print(f"⚠️ Ошибка доступа к ленте {url}: Статус {response.status}")
    except Exception as e:
        print(f"⚠️ Ошибка при парсинге ленты: {e}")
        
    return new_posts

# ==========================================
# 5. ОСНОВНОЙ ЦИКЛ
# ==========================================
async def main():
    # Инициализация бота (теперь мы уверены, что токен валиден по структуре)
    try:
        bot = Bot(token=BOT_TOKEN)
        # Проверка связи с Telegram (получаем инфо о боте)
        me = await bot.get_me()
        print(f"✅ УСПЕХ! Бот запущен: @{me.username} (ID: {me.id})")
    except Exception as e:
        print(f"❌ НЕУДАЧА ПРИ ПОДКЛЮЧЕНИИ К TELEGRAM: {e}")
        print("   Возможные причины:")
        print("   1. Токен отозван (сделайте /revoke и создайте новый).")
        print("   2. Токен содержит скрытые символы, которые не удалось отловить.")
        return

    init_db()
    
    async with aiohttp.ClientSession() as session:
        # Первый прогон сразу при старте
        print("🔄 Выполнение первого сканирования лент...")
        posts = await fetch_news(session)
        
        if posts:
            print(f"📤 Отправка {len(posts)} новостей в канал {CHANNEL_ID}...")
            for post in posts:
                try:
                    await bot.send_message(CHANNEL_ID, post, parse_mode=ParseMode.HTML)
                    print("   ✅ Новость отправлена.")
                except Exception as e:
                    print(f"   ❌ Ошибка отправки: {e}")
                    print("   Проверьте: добавлен ли бот в канал как АДМИНИСТРАТОР?")
        else:
            print("ℹ️ Новых новостей для публикации не найдено.")

        print("💤 Завершение работы (GitHub Actions остановит процесс).")
    
    await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Остановлено пользователем.")
