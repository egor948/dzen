# main.py
import os
import subprocess
import datetime
from datetime import timedelta
import google.generativeai as genai
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
    raise ValueError("Один из секретов Telegram (API_ID, API_HASH, SESSION_STRING) не задан!")

client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)

CHANNELS = [
    "breakevens", "spurstg", "bluecityzens", "manutd_one",
    "lexusarsenal", "sixELCE", "astonvillago"
]

# ================== Google Gemini ==================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не задан!")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest') # Используем быструю и дешевую модель

# GitHub - Путь к файлу
RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
# ===============================================

async def get_channel_posts():
    """Асинхронно собирает посты из указанных каналов за последние 24 часа."""
    all_posts = []
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - timedelta(hours=24)

    async with client:
        for channel_name in CHANNELS:
            print(f"Парсинг канала: {channel_name}...")
            try:
                async for msg in client.iter_messages(channel_name, limit=100):
                    if msg.date < cutoff:
                        break # Сообщения идут от новых к старым, можно прерваться
                    if msg.text:
                        all_posts.append({"text": msg.text, "date": msg.date})
            except Exception as e:
                print(f"Не удалось получить посты из канала '{channel_name}': {e}")
    
    # Сортируем посты по дате (от старых к новым) для лучшего понимания моделью
    all_posts.sort(key=lambda p: p["date"])
    print(f"Найдено {len(all_posts)} новых постов.")
    return all_posts


def ask_gemini_to_write_article(text_digest):
    """Отправляет дайджест новостей в Gemini и просит сгенерировать статью."""
    print("Отправка запроса в Google Gemini...")
    prompt = f"""
Ты — профессиональный спортивный журналист. Твоя задача — проанализировать сырой дайджест новостей из Telegram-каналов и написать на его основе одну цельную, интересную статью для Яндекс.Дзен.

Требования к статье:
1.  **Заголовок:** Придумай яркий, интригующий и кликабельный заголовок. Он должен быть на первой строке.
2.  **Структура:** Статья должна состоять из введения, основной части (2-4 абзаца) и заключения.
3.  **Содержание:** Объедини связанные новости в общие темы. Не перечисляй все подряд. Выбери самое важное и интересное.
4.  **Стиль:** Пиши живым, динамичным языком. Избегай канцеляризмов и прямого копирования. Сделай глубокий рерайт.
5.  **Фильтрация:** Полностью игнорируй любую рекламу, букмекерские конторы, личные мнения авторов каналов и повторяющуюся информацию.

ВАЖНО: Твой ответ должен начинаться с заголовка, а затем, с новой строки, идти основной текст статьи.

Вот дайджест новостей для анализа:
---
{text_digest}
---
"""
    try:
        response = model.generate_content(prompt)
        print("Ответ от Gemini успешно получен.")
        return response.text
    except Exception as e:
        print(f"Ошибка при обращении к Gemini API: {e}")
        return None


def create_rss_feed(generated_content):
    """Создает и сохраняет RSS-файл из сгенерированного контента."""
    if not generated_content:
        print("Контент не был сгенерирован, RSS-файл не будет создан.")
        return

    # Разделяем сгенерированный текст на заголовок (первая строка) и основной контент
    parts = generated_content.strip().split('\n', 1)
    title = parts[0].strip()
    description_text = parts[1].strip() if len(parts) > 1 else "Нет содержания."

    # Оборачиваем описание в CDATA для корректного отображения HTML в RSS
    description_html = f"<![CDATA[{description_text.replace('\n', '<br/>')}]]>"

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Футбольные Новости от AI"
    SubElement(channel, "link").text = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
    SubElement(channel, "description").text = "Самые свежие футбольные новости, сгенерированные нейросетью"
    
    item = SubElement(channel, "item")
    SubElement(item, "title").text = title
    SubElement(item, "description").text = description_html
    SubElement(item, "pubDate").text = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    # GUID важен, чтобы Дзен понимал, что это новый пост
    SubElement(item, "guid").text = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp()))

    xml_string = tostring(rss, 'utf-8')
    pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")

    with open(RSS_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print(f"✅ RSS-лента успешно сохранена в файл: {RSS_FILE_PATH}")


async def main():
    """Основная функция, запускающая весь процесс."""
    posts = await get_channel_posts()
    if not posts:
        print("Новых постов для обработки нет. Завершение работы.")
        return

    # Объединяем тексты постов в один большой дайджест
    combined_text = "\n\n---\n\n".join([p["text"] for p in posts])
    
    # Ограничиваем объем текста для экономии токенов и ускорения работы
    max_length = 25000
    if len(combined_text) > max_length:
        print(f"Текст слишком длинный, обрезаем до {max_length} символов.")
        combined_text = combined_text[:max_length]
    
    generated_article = ask_gemini_to_write_article(combined_text)
    
    if generated_article:
        create_rss_feed(generated_article)

if __name__ == "__main__":
    asyncio.run(main())
