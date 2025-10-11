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
import json
import re

# ================= НАСТРОЙКИ =================
# Telegram
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

if not API_ID or not API_HASH or not SESSION_STRING:
    raise ValueError("Один из секретов Telegram не задан!")

client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)

CHANNELS_LIST = [
    "breakevens", "spurstg", "bluecityzens", "manutd_one", "lexusarsenal", "sixELCE", "astonvillago",
    "tg_barca", "ZZoneRM", "psgdot", "FcMilanItaly", "Vstakane", "LaligaOfficial_rus", "SportEPL", "tg_epl",
    "bundesliga_live", "wearethearsenal", "tg_calcio", "italianfootbol", "Match_TV", "bundesligas1",
    "fcbarca_sports", "englishntvplus", "sportsrufootball", "sportsru", "real_sports", "atleticosmadrid",
    "amfans", "asmonacoRU", "NFFCCOYR", "fcBrightonHoveAlbion", "albionevening", "LeipzigFans", "BayerFanChannel",
    "BundesligaRuNET", "Herr_Baboba", "borussia_bundesliga", "Juventus2015", "bc_atalanta", "asromasiamonoi",
    "forzainter_ru", "internazionalemilanoo1908", "milanews_ru", "abibyllaev", "englandblog", "telingaterEPL", "tgprimera"
]
CHANNELS = sorted(list(set(CHANNELS_LIST)))

# ================== API Ключи ==================
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()

if not CF_ACCOUNT_ID or not CF_API_TOKEN:
    raise ValueError("CF_ACCOUNT_ID или CF_API_TOKEN не заданы!")
if not UNSPLASH_ACCESS_KEY:
    raise ValueError("UNSPLASH_ACCESS_KEY не задан!")

# ================== Модели AI ==================
TEXT_MODEL = "@cf/mistral/mistral-7b-instruct-v0.1"
IMAGE_MODEL = "@cf/stabilityai/stable-diffusion-xl-base-1.0"

# ================== Прочие настройки ==================
RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
IMAGE_DIR = os.path.join(os.getcwd(), "images")
MAX_RSS_ITEMS = 30
GITHUB_REPO_URL = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
# ===============================================

async def get_channel_posts():
    """Собирает новости за последний час."""
    all_posts, unique_texts = [], set()
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - timedelta(hours=1)
    async with client:
        for channel_name in CHANNELS:
            print(f"Парсинг канала: {channel_name}...")
            try:
                async for msg in client.iter_messages(channel_name, limit=50):
                    if msg.date < cutoff: break
                    if msg.text and msg.text not in unique_texts:
                        unique_texts.add(msg.text)
                        all_posts.append({"text": msg.text.strip()})
            except Exception as e:
                print(f"Не удалось получить посты из канала '{channel_name}': {e}")
    print(f"Найдено {len(all_posts)} уникальных постов.")
    return "\n\n---\n\n".join(p['text'] for p in all_posts)

def _call_cloudflare_ai(model, payload, timeout=180):
    """Универсальная функция для вызова API Cloudflare."""
    api_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"Ошибка HTTP-запроса к Cloudflare API: {e}")
        if e.response is not None:
            print(f"Ответ сервера ({e.response.status_code}): {e.response.text}")
        return None

def cluster_news_into_storylines(all_news_text):
    """Группирует новости в потенциальные сюжеты для статей."""
    print("Этап 1: Группировка новостей в сюжеты...")
    
    # ⬇️⬇️⬇️ ОБНОВЛЕННЫЙ ПРОМПТ 1 ⬇️⬇️⬇️
    prompt = f"""[INST]Проанализируй новостной поток ниже. Твоя задача — найти МАКСИМАЛЬНОЕ количество независимых сюжетов, из которых можно сделать качественные журналистские статьи. Сюжет может быть основан даже на одной-двух очень содержательных новостях. Игнорируй только совсем короткие, несвязанные или рекламные упоминания.

Для каждого найденного сюжета верни следующую информацию:
1. `title`: Краткое рабочее название сюжета НА РУССКОМ ЯЗЫКЕ (например, "Трансферная сага Мбаппе", "Результаты матчей АПЛ", "Скандал в Итальянском футболе").
2. `category`: Одно-два слова, категория для RSS НА РУССКОМ ЯЗЫКЕ (например, "Трансферы", "АПЛ", "Серия А", "Скандалы").
3. `search_query`: Ключевые слова на АНГЛИЙСКОМ для поиска релевантной фотографии (например, "Kylian Mbappe PSG football", "Premier League match action", "Italian football referee scandal").
4. `news_texts`: ПОЛНЫЙ и НЕИЗМЕНЕННЫЙ текст всех новостей, относящихся к этому сюжету.

Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате JSON-массива.
[/INST]

НОВОСТИ:
---
{all_news_text}
---
JSON:
"""
    response = _call_cloudflare_ai(TEXT_MODEL, {"prompt": prompt, "max_tokens": 2048})
    if not response: return []
    try:
        raw_response = response.json()["result"]["response"]
        json_match = re.search(r'\[.*\]', raw_response, re.DOTALL)
        if json_match:
            storylines = json.loads(json_match.group(0))
            print(f"Найдено {len(storylines)} сюжетов для статей.")
            return storylines
        return []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка декодирования JSON ответа модели: {e}")
        return []

def write_article_for_storyline(storyline):
    """Пишет статью по конкретному сюжету."""
    print(f"Этап 2: Написание статьи на тему '{storyline['title']}'...")
    
    # ⬇️⬇️⬇️ ОБНОВЛЕННЫЙ ПРОМПТ 2 ⬇️⬇️⬇️
    prompt = f"""[INST]Ты — первоклассный спортивный журналист и редактор, пишущий для ведущего русскоязычного издания. Твоя задача — написать захватывающую статью для Яндекс.Дзен на основе предоставленных новостей.

**Рабочее название сюжета:** "{storyline['title']}"

**САМОЕ ГЛАВНОЕ ПРАВИЛО: Статья должна быть написана ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ.**

**СТРОГИЕ ТРЕБОВАНИЯ К СТАТЬЕ:**
1.  **ЗАГОЛОВОК:** Твой ответ должен начинаться с яркого, интригующего, но абсолютно правдивого заголовка на РУССКОМ ЯЗЫКЕ. Заголовок должен быть на первой строке. НЕ ИСПОЛЬЗУЙ markdown (символы `*` или `**`) или слова "Заголовок:" в начале.
2.  **СТИЛЬ:** Пиши как эксперт. Твой текст должен быть грамотным, аналитичным и увлекательным. Он должен удерживать внимание читателя до самого конца.
3.  **СТРУКТУРА:** Создай цельное повествование с логичным началом, развитием и завершением. Текст должен течь естественно, как статья в качественном издании.
4.  **ЗАПРЕТЫ:**
    *   **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО** использовать подзаголовки вроде "Введение", "Раскрытие деталей", "Заключение", "Вывод", "Примечание", "Содержание" и т.п.
    *   **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО** добавлять любые оговорки, дисклеймеры или примечания о том, что информация может быть неточной или неподтвержденной.
    *   **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО** начинать текст со слов "Статья:" или похожих маркеров.

Твоя цель — создать готовый журналистский продукт на безупречном РУССКОМ языке.
[/INST]

НОВОСТИ ДЛЯ АНАЛИЗА:
---
{storyline['news_texts']}
---
ГОТОВАЯ СТАТЬЯ:
"""
    response = _call_cloudflare_ai(TEXT_MODEL, {"prompt": prompt, "max_tokens": 1024})
    if response:
        article_text = response.json()["result"]["response"]
        storyline['article'] = article_text
        return storyline
    return None

def find_real_photo_on_unsplash(storyline):
    """Ищет реальное фото на Unsplash."""
    query = storyline.get("search_query")
    if not query: return None
    
    print(f"Этап 3 (Основной): Поиск реального фото на Unsplash по запросу: '{query}'...")
    url = "https://api.unsplash.com/search/photos"
    params = { "query": query, "orientation": "landscape", "per_page": 1, "client_id": UNSPLASH_ACCESS_KEY }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data["results"]:
            photo = data["results"][0]
            image_url = photo["urls"]["regular"]
            image_response = requests.get(image_url, timeout=60)
            image_response.raise_for_status()
            os.makedirs(IMAGE_DIR, exist_ok=True)
            timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            image_filename = f"{timestamp}.jpg"
            image_path = os.path.join(IMAGE_DIR, image_filename)
            with open(image_path, "wb") as f: f.write(image_response.content)
            print(f"Фото с Unsplash успешно сохранено: {image_path}")
            storyline['image_url'] = f"{GITHUB_REPO_URL.replace('github.com', 'raw.githubusercontent.com')}/main/images/{image_filename}"
            return storyline
        else:
            print("На Unsplash ничего не найдено.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при обращении к Unsplash API: {e}")
        return None

def generate_ai_image(storyline):
    """Генерирует AI изображение как запасной вариант."""
    title = storyline['article'].split('\n', 1)[0]
    print(f"Этап 3 (Запасной): Генерация AI изображения для статьи '{title}'...")
    prompt = f"dramatic, ultra-realistic, 4k photo of: {title}. Professional sports photography, cinematic lighting"
    
    response = _call_cloudflare_ai(IMAGE_MODEL, {"prompt": prompt})
    if not response or response.status_code != 200: return None

    os.makedirs(IMAGE_DIR, exist_ok=True)
    timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    image_filename = f"{timestamp}.png"
    image_path = os.path.join(IMAGE_DIR, image_filename)
    with open(image_path, "wb") as f: f.write(response.content)
    print(f"AI изображение успешно сохранено: {image_path}")
    storyline['image_url'] = f"{GITHUB_REPO_URL.replace('github.com', 'raw.githubusercontent.com')}/main/images/{image_filename}"
    return storyline

def update_rss_file(processed_storylines):
    """Обновляет RSS-файл, добавляя новые статьи и изображения."""
    ET.register_namespace('yandex', 'http://news.yandex.ru')
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    try:
        tree = ET.parse(RSS_FILE_PATH)
        root = tree.getroot()
        channel = root.find('channel')
    except (FileNotFoundError, ET.ParseError):
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = "Футбольные Новости от AI"
        ET.SubElement(channel, "link").text = GITHUB_REPO_URL
        ET.SubElement(channel, "description").text = "Самые свежие футбольные новости, сгенерированные нейросетью"

    for storyline in reversed(processed_storylines):
        article_text = storyline.get('article')
        if not article_text: continue
        parts = article_text.strip().split('\n', 1)
        if len(parts) < 2: continue
        
        title = parts[0].strip().replace("**", "").replace("Заголовок:", "").strip()
        full_text = parts[1].strip()
        
        item = ET.Element("item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = GITHUB_REPO_URL
        ET.SubElement(item, "category").text = storyline.get('category', 'Общее')
        yandex_full_text = ET.SubElement(item, "{http://news.yandex.ru}full-text")
        yandex_full_text.text = full_text
        if storyline.get('image_url'):
            image_type = 'image/jpeg' if '.jpg' in storyline['image_url'] else 'image/png'
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set('url', storyline['image_url'])
            enclosure.set('type', image_type)
        ET.SubElement(item, "pubDate").text = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        ET.SubElement(item, "guid", isPermaLink="false").text = str(hash(title))
        channel.insert(3, item)

    items = channel.findall('item')
    if len(items) > MAX_RSS_ITEMS:
        for old_item in items[MAX_RSS_ITEMS:]:
            channel.remove(old_item)

    xml_string = ET.tostring(root, 'utf-8')
    pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")
    with open(RSS_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print(f"✅ RSS-лента успешно обновлена. Теперь в ней {len(channel.findall('item'))} статей.")


async def main():
    combined_text = await get_channel_posts()
    if not combined_text or len(combined_text) < 200:
        print("Новых постов для обработки недостаточно.")
        return
    if len(combined_text) > 30000:
        combined_text = combined_text[:30000]

    storylines = cluster_news_into_storylines(combined_text)
    if not storylines: return
        
    processed_storylines = []
    for storyline in storylines:
        if len(storyline.get("news_texts", "")) < 150:
            print(f"Пропускаем сюжет '{storyline.get('title')}' из-за недостатка материала.")
            continue
        storyline_with_article = write_article_for_storyline(storyline)
        if not storyline_with_article: continue
        final_storyline = find_real_photo_on_unsplash(storyline_with_article)
        if not final_storyline:
            final_storyline = generate_ai_image(storyline_with_article)
        processed_storylines.append(final_storyline or storyline_with_article)
    
    update_rss_file(processed_storylines)

if __name__ == "__main__":
    asyncio.run(main())```
