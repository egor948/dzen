# main.py
import os
import requests
import datetime
from datetime import timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom as minidom
import asyncio

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

# ================== Google Gemini через прокси ==================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не задан!")

# URL для прокси-сервера Gemini. 
# ВАЖНО: Этот URL - пример. Вам нужно найти реальный прокси-сервис
# и заменить его URL здесь. 
# Он должен вести к модели gemini-pro и методу generateContent.
GEMINI_PROXY_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"


# GitHub - Путь к файлу
RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
# ===============================================

async def get_channel_posts():
    all_posts = []
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - timedelta(hours=24)

    async with client:
        for channel_name in CHANNELS:
            print(f"Парсинг канала: {channel_name}...")
            try:
                async for msg in client.iter_messages(channel_name, limit=100):
                    if msg.date < cutoff: break
                    if msg.text: all_posts.append({"text": msg.text, "date": msg.date})
            except Exception as e:
                print(f"Не удалось получить посты из канала '{channel_name}': {e}")
    
    all_posts.sort(key=lambda p: p["date"])
    print(f"Найдено {len(all_posts)} новых постов.")
    return all_posts


def ask_gemini_to_write_article(text_digest):
    """Отправляет дайджест новостей в Gemini через прямой HTTP-запрос (прокси)."""
    print("Отправка запроса в Google Gemini через прокси...")
    
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
Ты — профессиональный спортивный журналист... (Ваш промпт без изменений)
...
Вот дайджест новостей для анализа:
---
{text_digest}
---
"""
    
    data = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }

    try:
        response = requests.post(GEMINI_PROXY_URL, headers=headers, json=data, timeout=120)
        response.raise_for_status()  # Вызовет ошибку, если код ответа не 2xx

        result = response.json()
        generated_text = result['candidates'][0]['content']['parts'][0]['text']
        
        print("Ответ от Gemini успешно получен.")
        return generated_text
    except requests.exceptions.RequestException as e:
        print(f"Ошибка HTTP-запроса к Gemini API: {e}")
        # Печатаем тело ответа, если он есть, для диагностики
        if e.response is not None:
            print(f"Ответ сервера: {e.response.text}")
        return None
    except (KeyError, IndexError) as e:
        print(f"Не удалось разобрать ответ от Gemini. Структура ответа изменилась? Ошибка: {e}")
        print(f"Полученный ответ: {result}")
        return None


def create_rss_feed(generated_content):
    if not generated_content:
        print("Контент не был сгенерирован, RSS-файл не будет создан.")
        return

    parts = generated_content.strip().split('\n', 1)
    title = parts[0].strip()
    description_text = parts[1].strip() if len(parts) > 1 else "Нет содержания."
    
    formatted_description = description_text.replace('\n', '<br/>')
    description_html = f"<![CDATA[{formatted_description}]]>"

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    # ... (остальная часть функции без изменений)
    SubElement(channel, "title").text = "Футбольные Новости от AI"
    SubElement(channel, "link").text = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
    SubElement(channel, "description").text = "Самые свежие футбольные новости, сгенерированные нейросетью"
    item = SubElement(channel, "item")
    SubElement(item, "title").text = title
    SubElement(item, "description").text = description_html
    SubElement(item, "pubDate").text = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    SubElement(item, "guid").text = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp()))
    xml_string = tostring(rss, 'utf-8')
    pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")
    with open(RSS_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print(f"✅ RSS-лента успешно сохранена в файл: {RSS_FILE_PATH}")


async def main():
    posts = await get_channel_posts()
    if not posts:
        print("Новых постов для обработки нет. Завершение работы.")
        return

    combined_text = "\n\n---\n\n".join([p["text"] for p in posts])
    
    max_length = 30000
    if len(combined_text) > max_length:
        print(f"Текст слишком длинный, обрезаем до {max_length} символов.")
        combined_text = combined_text[:max_length]
    
    generated_article = ask_gemini_to_write_article(combined_text)
    
    if generated_article:
        create_rss_feed(generated_article)

if __name__ == "__main__":
    asyncio.run(main())
