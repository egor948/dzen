# main.py
import os
import requests
import datetime
from datetime import timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import asyncio
import re

# ================= НАСТРОЙКИ =================
# Telegram
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

if not API_ID or not API_HASH or not SESSION_STRING:
    raise ValueError("Один из секретов Telegram не задан!")

client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)

CHANNELS = [
    "breakevens", "spurstg", "bluecityzens", "manutd_one",
    "lexusarsenal", "sixELCE", "astonvillago"
]

# ================== Cloudflare AI ==================
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()

if not CF_ACCOUNT_ID or not CF_API_TOKEN:
    raise ValueError("CF_ACCOUNT_ID или CF_API_TOKEN не заданы в секретах GitHub!")

MODEL_ID = "@cf/mistral/mistral-7b-instruct-v0.1"
API_URL = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{MODEL_ID}"

# ================== Прочие настройки ==================
RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
MAX_RSS_ITEMS = 20 # Максимальное количество статей в RSS-ленте
# ===============================================

async def get_channel_posts():
    all_posts = []
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - timedelta(hours=4)
    async with client:
        for channel_name in CHANNELS:
            print(f"Парсинг канала: {channel_name}...")
            try:
                async for msg in client.iter_messages(channel_name, limit=100):
                    if msg.date < cutoff: break
                    if msg.text: all_posts.append({"text": msg.text.strip(), "date": msg.date})
            except Exception as e:
                print(f"Не удалось получить посты из канала '{channel_name}': {e}")
    all_posts.sort(key=lambda p: p["date"])
    unique_posts = list(dict.fromkeys(p['text'] for p in all_posts))
    return "\n\n---\n\n".join(unique_posts)

def _call_cloudflare_ai(prompt, max_tokens=1024):
    """Внутренняя функция для вызова API Cloudflare."""
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    data = {"prompt": prompt, "max_tokens": max_tokens}
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=180)
        response.raise_for_status()
        result = response.json()
        if result.get("success") and result.get("result"):
            return result["result"]["response"].strip()
        else:
            print(f"Ответ от Cloudflare AI не содержит успешного результата: {result}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка HTTP-запроса к Cloudflare API: {e}")
        if e.response is not None:
            print(f"Ответ сервера ({e.response.status_code}): {e.response.text}")
        return None

def cluster_news_into_themes(all_news_text):
    """Группирует все новости по 2-4 основным темам с помощью ИИ."""
    print("Этап 1: Отправка запроса на группировку новостей по темам...")
    prompt = f"""[INST]Проанализируй все новости ниже. Выдели 2-4 самые главные и интересные темы. Для каждой темы верни ее название и ПОЛНЫЙ, НЕИЗМЕНЕННЫЙ текст всех новостей, которые к ней относятся. Не суммируй и не изменяй текст новостей.

Формат твоего ответа ДОЛЖЕН БЫТЬ СТРОГО ТАКИМ:
### THEME: Название темы 1
---
Полный текст новости 1...
---
Полный текст новости 2...
### THEME: Название темы 2
---
Полный текст новости 3...
---
Полный текст новости 4...
[/INST]

НОВОСТИ:
---
{all_news_text}
---
ТЕМЫ:
"""
    clustered_text = _call_cloudflare_ai(prompt, max_tokens=2048)
    if not clustered_text:
        return {}
    themes = {}
    theme_blocks = re.split(r'### THEME:', clustered_text)
    for block in theme_blocks:
        if not block.strip():
            continue
        parts = block.split('\n---\n', 1)
        if len(parts) == 2:
            title = parts[0].strip()
            news = parts[1].strip()
            if title and news:
                themes[title] = news
    
    print(f"Найдено {len(themes)} тем: {list(themes.keys())}")
    return themes

def write_article_for_theme(theme_title, news_for_theme):
    """Пишет статью на основе новостей для одной конкретной темы."""
    print(f"Этап 2: Написание статьи на тему '{theme_title}'...")
    prompt = f"""[INST]Ты — профессиональный спортивный журналист. Напиши одну цельную, интересную статью для Яндекс.Дзен на тему "{theme_title}". Используй ТОЛЬКО факты из новостей, представленных ниже.

Требования:
1.  **Заголовок:** Придумай яркий, интригующий и кликабельный заголовок. Он должен быть на первой строке.
2.  **Структура:** Статья должна состоять из введения, основной части (2-4 абзаца) и заключения.
3.  **Стиль:** Пиши живым языком, сделай глубокий рерайт. Не копируй исходный текст.
[/INST]

НОВОСТИ ДЛЯ АНАЛИЗА:
---
{news_for_theme}
---
ГОТОВАЯ СТАТЬЯ:
"""
    return _call_cloudflare_ai(prompt, max_tokens=1024)

def update_rss_file(generated_articles):
    """Читает существующий RSS, добавляет новые статьи и обрезает старые."""
    if not generated_articles:
        print("Нет сгенерированных статей для добавления в RSS.")
        return

    try:
        tree = ET.parse(RSS_FILE_PATH)
        root = tree.getroot()
        channel = root.find('channel')
    except (FileNotFoundError, ET.ParseError):
        print("RSS-файл не найден или поврежден. Создание нового файла.")
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = "Футбольные Новости от AI"
        ET.SubElement(channel, "link").text = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
        ET.SubElement(channel, "description").text = "Самые свежие футбольные новости, сгенерированные нейросетью"

    for article_text in reversed(generated_articles):
        parts = article_text.strip().split('\n', 1)
        if len(parts) < 2: continue

        title = parts[0].strip()
        description_text = parts[1].strip()

        item = ET.Element("item")
        ET.SubElement(item, "title").text = title
        
        # ⬇️⬇️⬇️ ВОТ ИСПРАВЛЕНИЕ: Безопасный способ добавления CDATA ⬇️⬇️⬇️
        description_element = ET.SubElement(item, "description")
        description_element.text = f"<![CDATA[{description_text.replace(chr(10), '<br/>')}]]>"
        
        ET.SubElement(item, "pubDate").text = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        ET.SubElement(item, "guid").text = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + hash(title))
        
        channel.insert(3, item)

    items = channel.findall('item')
    if len(items) > MAX_RSS_ITEMS:
        print(f"В RSS стало {len(items)} статей. Удаляем старые...")
        for old_item in items[MAX_RSS_ITEMS:]:
            channel.remove(old_item)

    xml_string = ET.tostring(root, 'utf-8', method='xml')
    # Используем minidom для красивого форматирования, но сначала исправляем баг с CDATA
    reparsed = minidom.parseString(xml_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    
    # Костыль для minidom, который кодирует CDATA. Мы его декодируем обратно.
    pretty_xml = pretty_xml.replace('&lt;![CDATA[', '<![CDATA[').replace(']]&gt;', ']]>')

    with open(RSS_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print(f"✅ RSS-лента успешно обновлена. Теперь в ней {len(channel.findall('item'))} статей.")


async def main():
    combined_text = await get_channel_posts()
    if not combined_text or len(combined_text) < 100:
        print("Новых постов для обработки недостаточно. Завершение работы.")
        return
    
    themes_with_news = cluster_news_into_themes(combined_text)
    
    if not themes_with_news:
        print("Не удалось сгруппировать новости по темам. Завершение работы.")
        return
        
    generated_articles = []
    for theme_title, news_text in themes_with_news.items():
        if len(news_text) > 25000:
            news_text = news_text[:25000]
            
        article = write_article_for_theme(theme_title, news_text)
        if article and len(article) > 50:
            print(f"--- Сгенерирована статья на тему: {theme_title} ---")
            generated_articles.append(article)
    
    update_rss_file(generated_articles)

if __name__ == "__main__":
    asyncio.run(main())
