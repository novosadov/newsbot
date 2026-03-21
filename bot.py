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
CHANNEL_ID = "@newstecnolojia" # Ваш канал
MEMORY_FILE = "sent_links.txt"
MAX_HISTORY = 100 # Храним последние 100 ссылок для памяти

# СПИСОК ИСТОЧНИКОВ (МАКСИМАЛЬНО ПОЛНЫЙ)
RSS_FEEDS = [
    # --- РОССИЯ ---
    ("Habr (Все)", "https://habr.com/ru/rss/all/new/"),
    ("VC.ru (Технологии)", "https://vc.ru/feed"),
    ("TJournal", "https://tjournal.ru/feed"),
    ("CNews", "https://www.cnews.ru/news/index.rss"),
    ("iXBT.com", "https://www.ixbt.com/news/all/index.xml"),
    ("3DNews", "https://www.3dnews.ru/news.rdf"),
    ("Overclockers.ru", "https://overclockers.ru/rss/news.xml"),
    ("OpenNET", "https://www.opennet.ru/opennews/opennews_all.rss"),
    
    # --- МИР (ENGLISH) ---
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Wired", "https://www.wired.com/feed/rss"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Hacker News (Top)", "https://hnrss.org/frontpage"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
    ("ZDNet", "https://www.zdnet.com/topic/technology/rss.xml"),
    ("The Next Web", "https://thenextweb.com/feed/"),
]

print(f"🚀 ЗАПУСК БОТА. Источников: {len(RSS_FEEDS)}")

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
        # Настройка Git пользователя
        subprocess.run(["git", "config", "--global", "user.name", "NewsBot"], check=True, capture_output=True)
        subprocess.run(["git", "config", "--global", "user.email", "bot@github.actions"], check=True, capture_output=True)
        
        # Проверка, есть ли изменения
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "add", MEMORY_FILE], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Update news history"], check=True, capture_output=True)
            
            repo_url = os.getenv("GITHUB_SERVER_URL") + "/" + os.getenv("GITHUB_REPOSITORY") + ".git"
            token = os.getenv("GITHUB_TOKEN")
            auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
            
            subprocess.run(["git", "push", auth_url, "HEAD:main"], check=True, capture_output=True)
            print("✅ История обновлена в репозитории.")
        else:
            print("ℹ️ Изменений в истории нет.")
    except Exception as e:
        print(f"⚠️ Ошибка сохранения в Git: {e}")

# ==========================================
# ПАРСИНГ И ОТПРАВКА
# ==========================================
async def fetch_and_post():
    if not BOT_TOKEN:
        print("❌ Токен не найден!")
        return

    bot = Bot(token=BOT_TOKEN)
    history = load_history()
    new_links_count = 0

    # Создаем сессию с заголовками, чтобы сайты не блокировали бота
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    async with aiohttp.ClientSession(headers=headers) as session:
        for source_name, url in RSS_FEEDS:
            try:
                # Таймаут уменьшен для скорости, если один сайт висит - идем дальше
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        text = await response.text()
                        feed = feedparser.parse(text)
                        
                        # Берем по 2 новости с каждого источника, чтобы не спамить одним сайтом
                        for entry in feed.entries[:2]: 
                            link = entry.link
                            if link in history:
                                continue

                            # Обработка текста
                            title = entry.title
                            summary_raw = entry.get('summary', entry.get('description', ''))
                            
                            # Чистка HTML
                            clean_summary = re.sub(r'<[^>]+>', '', summary_raw)
                            clean_summary = re.sub(r'\s+', ' ', clean_summary) # Убираем лишние пробелы
                            clean_summary = clean_summary.strip()
                            
                            if len(clean_summary) > 500:
                                clean_summary = clean_summary[:497] + "..."
                            
                            if not clean_summary or clean_summary == "Нет описания.":
                                clean_summary = "Подробности по ссылке в источнике."

                            # Поиск картинки
                            photo_url = None
                            # 1. media_content
                            if 'media_content' in entry:
                                for media in entry['media_content']:
                                    if media.get('medium') == 'image' or media.get('type', '').startswith('image'):
                                        photo_url = media['url']
                                        break
                            # 2. enclosures
                            if not photo_url and 'enclosures' in entry:
                                for enc in entry['enclosures']:
                                    if enc.get('type', '').startswith('image'):
                                        photo_url = enc['href']
                                        break
                            # 3. image в корне entry
                            if not photo_url and 'image' in entry:
                                photo_url = entry['image'].get('href')
                            
                            # 4. Парсинг из HTML summary (fallback)
                            if not photo_url:
                                img_match = re.search(r'src=["\'](https?://[^"\']+?\.(?:jpg|jpeg|png|webp|gif))["\']', summary_raw, re.I)
                                if img_match:
                                    photo_url = img_match.group(1)

                            caption = f"🏷 <b>{source_name}</b>\n\n🚀 <b>{title}</b>\n\n📝 {clean_summary}"
                            
                            try:
                                if photo_url:
                                    await bot.send_photo(CHANNEL_ID, photo=photo_url, caption=caption, parse_mode=ParseMode.HTML)
                                    print(f"📸 [{source_name}] {title[:30]}...")
                                else:
                                    await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.HTML)
                                    print(f"📝 [{source_name}] {title[:30]}...")
                                
                                history.add(link)
                                new_links_count += 1
                            except Exception as e:
                                print(f"❌ Ошибка отправки в Telegram: {e}")
                    else:
                        print(f"⚠️ {source_name}: Статус {response.status}")
            except asyncio.TimeoutError:
                print(f"⏳ {source_name}: Превышено время ожидания, пропускаем.")
            except Exception as e:
                print(f"⚠️ {source_name}: Ошибка чтения ({e})")

    if new_links_count > 0:
        save_history(history)
        print(f"✅ Готово! Отправлено новостей: {new_links_count}")
    else:
        print("ℹ️ Новых новостей не найдено.")

    await bot.session.close()

if __name__ == '__main__':
    asyncio.run(fetch_and_post())
