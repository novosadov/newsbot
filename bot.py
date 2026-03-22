import os
import asyncio
import aiohttp
import feedparser
import re
import subprocess
import html  # Модуль для расшифровки &nbsp; &laquo; и т.д.
from aiogram import Bot, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@newstecnolojia"
MEMORY_FILE = "sent_links.txt"
MAX_HISTORY = 200

RSS_FEEDS = [
    ("Habr", "https://habr.com/ru/rss/all/new/"),
    ("Hi-news.ru", "https://hi-news.ru/feed"),
    ("Ferra.ru", "https://www.ferra.ru/exports/rss.xml"),
    ("VC.ru", "https://vc.ru/rss"),
    ("CNews", "https://www.cnews.ru/inc/rss/news.xml"),
    ("iXBT", "https://www.ixbt.com/export/news.rss"),
    ("3DNews", "https://3dnews.ru/news/rss"),
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
# РАБОТА С ПАМЯТЬЮ
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
            clean_url = url.strip()
            
            try:
                async with session.get(clean_url, timeout=7) as response:
                    if response.status == 200:
                        text = await response.text(errors='ignore')
                        feed = feedparser.parse(text)
                        
                        for entry in feed.entries[:3]:
                            link = entry.link
                            if link in history:
                                continue

                            title = entry.title
                            summary_raw = entry.get('summary', entry.get('description', ''))

                            if not is_russian_news(title, summary_raw):
                                continue

                            # --- ОБРАБОТКА ТЕКСТА ---
                            
                            # 1. Удаляем HTML теги (<b>, <p>, <img> и т.д.)
                            clean_text = re.sub(r'<[^>]+>', '', summary_raw)
                            
                            # 2. Расшифровываем HTML-сущности (&nbsp; -> пробел, &laquo; -> « и т.д.)
                            # Это ключевое исправление!
                            clean_text = html.unescape(clean_text)
                            
                            # 3. Убираем лишние пробелы (превращаем множественные пробелы в один)
                            clean_text = re.sub(r'\s+', ' ', clean_text)
                            
                            # 4. Обрезаем по краям и по длине
                            clean_text = clean_text.strip()
                            if len(clean_text) > 600:
                                clean_text = clean_text[:597] + "..."
                            
                            if not clean_text:
                                clean_text = "Подробности в источнике."

                            # Также чистим заголовок на всякий случай (там тоже могут быть сущности)
                            clean_title = html.unescape(re.sub(r'<[^>]+>', '', title)).strip()

                            # Поиск картинки
                            photo_url = None
                            
                            # 1. media_content
                            if 'media_content' in entry:
                                for m in entry['media_content']:
                                    if m.get('medium') == 'image' or m.get('type', '').startswith('image'):
                                        photo_url = m.get('url')
                                        break
                            
                            # 2. enclosures
                            if not photo_url and 'enclosures' in entry:
                                for e in entry['enclosures']:
                                    if e.get('type', '').startswith('image') and 'href' in e:
                                        photo_url = e['href']
                                        break
                            
                            # 3. Парсинг из HTML
                            if not photo_url:
                                match = re.search(r'src=["\'](https?://[^"\']+?\.(?:jpg|jpeg|png|webp))["\']', summary_raw, re.I)
                                if match:
                                    photo_url = match.group(1)

                            # Формирование сообщения
                            caption = f"🚀 <b>{clean_title}</b>\n\n📝 {clean_text}\n\n🔗 <a href='{link}'>Читать далее на сайте</a>"
                            
                            # ОТПРАВКА
                            sent = False
                            if photo_url:
                                try:
                                    await bot.send_photo(CHANNEL_ID, photo=photo_url, caption=caption, parse_mode=ParseMode.HTML)
                                    print(f"📸 [{source_name}] {clean_title[:40]}...")
                                    sent = True
                                except TelegramBadRequest as e:
                                    if "wrong type of the web page content" in str(e):
                                        print(f"⚠️ [{source_name}] Картинка битая, шлю текстом: {clean_title[:30]}...")
                                        try:
                                            await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.HTML)
                                            sent = True
                                        except Exception as inner_e:
                                            print(f"❌ Ошибка отправки текста: {inner_e}")
                                    else:
                                        print(f"❌ Ошибка фото: {e}")
                                except Exception as e:
                                    print(f"❌ Неизвестная ошибка фото: {e}")
                            
                            if not sent:
                                try:
                                    await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.HTML)
                                    print(f"📝 [{source_name}] {clean_title[:40]}...")
                                    sent = True
                                except Exception as e:
                                    print(f"❌ Ошибка текста: {e}")

                            if sent:
                                history.add(link)
                                new_count += 1

                    else:
                        print(f"⚠️ [{source_name}] Ошибка доступа: {response.status}")
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
