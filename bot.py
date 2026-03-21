import os
import asyncio
import aiohttp
import feedparser
import re
from aiogram import Bot, types
from aiogram.enums import ParseMode
import subprocess # Для работы с Git

# ==========================================
# 1. НАСТРОЙКИ И ПАМЯТЬ (GIT)
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@newstecnolojia" # Ваш канал

# Файл для хранения истории ссылок (чтобы не было дублей)
MEMORY_FILE = "sent_links.txt"
MAX_HISTORY = 50 # Храним последние 50 ссылок

RSS_FEEDS = [
    "https://habr.com/ru/rss/all/new/",
]

print("🚀 ЗАПУСК БОТА С ФОТО-РЕЖИМОМ...")

# Функция загрузки истории из файла
def load_history():
    if not os.path.exists(MEMORY_FILE):
        return set()
    with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

# Функция сохранения истории и коммит в Git
def save_history(history_set):
    history_list = list(history_set)[-MAX_HISTORY:] # Оставляем только последние
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        for link in history_list:
            f.write(link + '\n')
    
    # Автоматический коммит изменений в репозиторий
    try:
        subprocess.run(["git", "config", "--global", "user.name", "NewsBot"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@github.actions"], check=True)
        subprocess.run(["git", "add", MEMORY_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update sent links history"], check=True)
        # Push выполняем только если есть токены для git, но в GitHub Actions это часто лишнее, 
        # так как файл нужен только для ТЕКУЩЕГО запуска? 
        # НЕТ! Файл должен сохраниться для СЛЕДУЮЩЕГО запуска.
        # В GitHub Actions файлы не сохраняются между запусками автоматически!
        # Нам нужно запушить изменения обратно.
        # Для этого нужен GITHUB_TOKEN. Он есть по умолчанию в env.
        
        repo_url = os.getenv("GITHUB_SERVER_URL") + "/" + os.getenv("GITHUB_REPOSITORY") + ".git"
        token = os.getenv("GITHUB_TOKEN")
        auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
        
        subprocess.run(["git", "push", auth_url, "HEAD:main"], check=True, capture_output=True)
        print("✅ История ссылок обновлена в репозитории.")
    except Exception as e:
        print(f"⚠️ Не удалось сохранить историю в Git: {e}. Возможны дубли при следующем запуске.")

# ==========================================
# 2. ОСНОВНАЯ ЛОГИКА
# ==========================================
async def fetch_and_post():
    if not BOT_TOKEN:
        print("❌ Токен не найден!")
        return

    bot = Bot(token=BOT_TOKEN)
    history = load_history()
    new_links = []

    async with aiohttp.ClientSession() as session:
        for url in RSS_FEEDS:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        text = await response.text()
                        feed = feedparser.parse(text)
                        
                        for entry in feed.entries[:5]: # Проверяем 5 последних
                            link = entry.link
                            if link in history:
                                continue # Уже отправлено

                            # --- Обработка контента ---
                            title = entry.title
                            summary_raw = entry.get('summary', '')
                            # Чистим HTML
                            clean_summary = re.sub(r'<[^>]+>', '', summary_raw)
                            clean_summary = clean_summary.replace('\n', ' ').replace('\r', ' ')
                            if len(clean_summary) > 400:
                                clean_summary = clean_summary[:397] + "..."

                            # --- Поиск картинки ---
                            photo_url = None
                            # Вариант 1: media_content
                            if 'media_content' in entry:
                                for media in entry['media_content']:
                                    if media.get('medium') == 'image' or media.get('type', '').startswith('image'):
                                        photo_url = media['url']
                                        break
                            # Вариант 2: enclosures
                            if not photo_url and 'enclosures' in entry:
                                for enc in entry['enclosures']:
                                    if enc.get('type', '').startswith('image'):
                                        photo_url = enc['href']
                                        break
                            # Вариант 3: картинка внутри summary (ищем первый img src)
                            if not photo_url:
                                match = re.search(r'src=["\']([^"\']+\.jpg[^"\']*)["\']', summary_raw)
                                if match:
                                    photo_url = match.group(1)
                                else:
                                    match = re.search(r'src=["\']([^"\']+\.png[^"\']*)["\']', summary_raw)
                                    if match:
                                        photo_url = match.group(1)
                            
                            # --- Отправка ---
                            caption = f"🚀 <b>{title}</b>\n\n📝 {clean_summary}"
                            
                            try:
                                if photo_url:
                                    await bot.send_photo(CHANNEL_ID, photo=photo_url, caption=caption, parse_mode=ParseMode.HTML)
                                    print(f"📸 Отправлено фото: {title[:30]}...")
                                else:
                                    # Если картинки нет, шлем просто текст
                                    await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.HTML)
                                    print(f"📝 Отправлен текст: {title[:30]}...")
                                
                                history.add(link)
                                new_links.append(link)
                            except Exception as e:
                                print(f"❌ Ошибка отправки: {e}")

            except Exception as e:
                print(f"⚠️ Ошибка чтения ленты {url}: {e}")

    # Сохраняем новые ссылки
    if new_links:
        save_history(history)
    else:
        print("ℹ️ Новых новостей нет.")

    await bot.session.close()

if __name__ == '__main__':
    asyncio.run(fetch_and_post())
