import os
import asyncio
import aiohttp
import feedparser
import re
import subprocess
from aiogram import Bot, types
from aiogram.enums import ParseMode

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@newstecnolojia"
MEMORY_FILE = "sent_links.txt"
MAX_HISTORY = 200

# СПИСОК ИСТОЧНИКОВ
# Примечание: Пробелы в конце строк теперь не страшны, код их обрежет автоматически.
RSS_FEEDS = [
    ("Habr", "https://habr.com/ru/rss/all/new/"),
    ("Hi-news.ru", "https://hi-news.ru/feed"),
    ("VC.ru", "https://vc.ru/rss"),
    ("TJournal", "https://tjournal.ru/feed"),
    ("CNews", "https://www.cnews.ru/inc/rss/news.xml"),
    ("iXBT", "https://www.ixbt.com/export/news.rss"), # Исправленная ссылка
    ("3DNews", "https://3dnews.ru/news/rss"),         # Новая ссылка по запросу
    ("Overclockers", "https://overclockers.ru/rss/news.xml"),
    ("OpenNET", "https://www.opennet.ru/opennews/opennews_all.rss"),
    ("Roem", "https://roem.ru/feed/"),
]

print(f"🇷🇺 ЗАПУСК БОТА (RU ONLY). Источников: {len(RSS_FEEDS)}")

# ==========================================
# ФИЛЬТР РУССКОГО ЯЗЫКА
# ==========================================
def has_cyrillic(text):
    return bool(re.search('[а-яА-ЯёЁ]', text))

def is_russian_news(title, summary):
    if not has_cyrillic(title):
        return False
    return True

# ==========================================
# РАБОТА С ПАМЯТЬЮ (GIT)
# ==========================================
def load_history():
    if not os.path.exists(MEMORY_FILE):
        return set()
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    except Exception:
        return set()

def save_history(history_set):
    history_list = list(history_set)[-MAX_HISTORY:]
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        for link in history_list:
            f.write(link + '\n')
    
    try:
        subprocess.run(["git", "config", "--global", "user.name", "NewsBot"], check=True, capture_output=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@github.actions"], check=True, capture_output=True)
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "add", MEMORY_FILE], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Update RU news history"], check=True, capture_output=True)
            
            repo_url = os.getenv("GITHUB_SERVER_URL") + "/" + os.getenv("GITHUB_REPOSITORY") + ".git"
            token = os.getenv("GITHUB_TOKEN")
            auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
            
            subprocess.run(["git", "push", auth_url, "HEAD:main"], check=True, capture_output=True)
            print("✅ История обновлена.")
    except Exception as e:
        print(f"⚠️ Git error: {e}")

# ==========================================
# ОСНОВНОЙ ЦИКЛ
# ==========================================
async def fetch_and_post():
    if not BOT_TOKEN:
        print("❌ Нет токена!")
        return

    bot = Bot(token=BOT_TOKEN)
    history = load_history()
    new_count = 0
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    async with aiohttp.ClientSession(headers=headers) as session:
        for source_name, url in RSS_FEEDS:
            # ВАЖНО: Удаляем пробелы в начале и конце ссылки
            clean_url = url.strip()
            
            try:
                async with session.get(clean_url, timeout=7) as response:
                    if response.status == 200:
                        text = await response.text(errors='ignore')
                        feed = feedparser.parse(text)
                        
                        # Берем топ-3 свежих с каждого источника
                        for entry in feed.entries[:3]:
                            link = entry.link
                            if link in history:
                                continue

                            title = entry.title
                            summary_raw = entry.get('summary', entry.get('description', ''))

                            # Фильтр языка
                            if not is_russian_news(title, summary_raw):
                                continue

                            # Чистка текста
                            clean_summary = re.sub(r'<[^>]+>', '', summary_raw)
                            clean_summary = re.sub(r'\s+', ' ', clean_summary).strip()
                            
                            if len(clean_summary) > 600:
                                clean_summary = clean_summary[:597] + "..."
                            
                            if not clean_summary:
                                clean_summary = "Подробности в источнике."

                            # Поиск картинки
                            photo_url = None
                            if 'media_content' in entry:
                                for m in entry['media_content']:
                                    if m.get('medium') == 'image' or m.get('type', '').startswith('image'):
                                        photo_url = m['url']
                                        break
                            if not photo_url and 'enclosures' in entry:
                                for e in entry['enclosures']:
                                    if e.get('type', '').startswith('image'):
                                        photo_url = e['href']
                                        break
                            if not photo_url:
                                match = re.search(r'src=["\'](https?://[^"\']+?\.(?:jpg|jpeg|png|webp))["\']', summary_raw, re.I)
                                if match:
                                    photo_url = match.group(1)

                            # ФОРМИРОВАНИЕ СООБЩЕНИЯ
                            # Убрали источник из начала, добавили ссылку в конец
                            # Используем MarkdownV2 для надежной работы ссылок, или HTML как раньше. 
                            # В HTML ссылка делается так: <a href='url'>текст</a>
                            
                            caption = f"🚀 <b>{title}</b>\n\n📝 {clean_summary}\n\n🔗 <a href='{link}'>Читать далее на сайте</a>"
                            
                            try:
                                if photo_url:
                                    await bot.send_photo(CHANNEL_ID, photo=photo_url, caption=caption, parse_mode=ParseMode.HTML)
                                    print(f"📸 [{source_name}] {title[:40]}...")
                                else:
                                    await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.HTML)
                                    print(f"📝 [{source_name}] {title[:40]}...")
                                
                                history.add(link)
                                new_count += 1
                            except Exception as e:
                                print(f"❌ Ошибка отправки: {e}")
                    else:
                        print(f"⚠️ [{source_name}] Ошибка доступа: {response.status} (URL: {clean_url})")
            except asyncio.TimeoutError:
                print(f"⏳ [{source_name}] Таймаут")
            except Exception as e:
                print(f"⚠️ [{source_name}] Критическая ошибка: {e}")

    if new_count > 0:
        save_history(history)
        print(f"✅ УСПЕХ! Отправлено новостей: {new_count}")
    else:
        print("ℹ️ Новых новостей нет.")

    await bot.session.close()

if __name__ == '__main__':
    asyncio.run(fetch_and_post())
