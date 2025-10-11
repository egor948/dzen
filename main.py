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
# Telegram (парсер)
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

if not API_ID or not API_HASH or not SESSION_STRING:
    raise ValueError("Один из секретов Telegram для парсинга не задан!")

client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)

CHANNELS_LIST = [
    "breakevens", "spurstg", "bluecityzens", "manutd_one", "lexusarsenal", "sixELCE", "astonvillago",
    "tg_barca", "ZZoneRM", "psgdot", "FcMilanItaly", "Vstakane", "LaligaOfficial_rus", "SportEPL", "tg_epl",
    "bundesliga_live", "wearethearsenal", "tg_calcio", "italianfootbol", "bundesligas1",
    "fcbarca_sports", "englishntvplus", "sportsrufootball", "real_sports", "atleticosmadrid",
    "amfans", "asmonacoRU", "NFFCCOYR", "fcBrightonHoveAlbion", "albionevening", "LeipzigFans", "BayerFanChannel",
    "BundesligaRuNET", "Herr_Baboba", "borussia_bundesliga", "Juventus2015", "bc_atalanta", "asromasiamonoi",
    "forzainter_ru", "internazionalemilanoo1908", "milanews_ru", "abibyllaev", "englandblog", "telingaterEPL", "tgprimera"
]
CHANNELS = sorted(list(set(CHANNELS_LIST)))

# ================== API Ключи ==================
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()

# ⬇️⬇️⬇️ НОВЫЕ КЛЮЧИ ДЛЯ TELEGRAM-ПОСТИНГА ⬇️⬇️⬇️
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL_USERNAME", "").strip()

if not all([CF_ACCOUNT_ID, CF_API_TOKEN, UNSPLASH_ACCESS_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_USERNAME]):
    raise ValueError("Один из обязательных API ключей или имен не задан!")

# ================== Модели AI и прочие настройки ==================
TEXT_MODEL = "@cf/mistral/mistral-7b-instruct-v0.1"
IMAGE_MODEL = "@cf/stabilityai/stable-diffusion-xl-base-1.0"
RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
IMAGE_DIR = os.path.join(os.getcwd(), "images")
MAX_RSS_ITEMS = 30
GITHUB_REPO_URL = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
# ===============================================

# ⬇️⬇️⬇️ НОВАЯ ФУНКЦИЯ ДЛЯ ПУБЛИКАЦИИ В TELEGRAM ⬇️⬇️⬇️
def post_to_telegram_channel(storyline):
    """Отправляет готовую статью с картинкой в Telegram-канал."""
    print(f"Публикация статьи '{storyline.get('title')}' в Telegram-канал...")
    
    article_text = storyline.get('article')
    image_url = storyline.get('image_url')

    if not article_text or not image_url:
        print("Недостаточно данных для публикации в Telegram (отсутствует текст или картинка).")
        return

    parts = article_text.strip().split('\n', 1)
    if len(parts) < 2: return
    
    title = parts[0].strip().replace("**", "").replace("Заголовок:", "").strip().replace('"', '')
    full_text = parts[1].strip()

    # Форматируем текст для Telegram (HTML) и обрезаем, если он слишком длинный
    caption = f"<b>{title}</b>\n\n{full_text}"
    if len(caption) > 1024: # Лимит Telegram для подписи к фото
        caption = caption[:1021] + "..."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        'chat_id': f"@{TELEGRAM_CHANNEL_USERNAME}",
        'photo': image_url,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        print("✅ Статья успешно опубликована в Telegram-канале.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка публикации в Telegram: {e}")
        if e.response is not None:
            print(f"Ответ сервера Telegram: {e.response.text}")


async def get_channel_posts():
    # ... (эта функция без изменений)
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
    # ... (эта функция без изменений)
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


def clean_ai_artifacts(text):
    # ... (эта функция без изменений)
    banned_phrases = [
        "заключение:", "вывод:", "примечание:", "содержание:", "анализ:", "история развития событий:", "раскрытие деталей:",
        "**заключение**", "**вывод**", "**примечание**", "**содержание**", "**анализ**",
        "статья:", "готовая статья:"
    ]
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if not any(line.lower().strip().startswith(phrase) for phrase in banned_phrases)]
    cleaned_text = '\n'.join(cleaned_lines).strip()
    for phrase in banned_phrases:
        cleaned_text = re.sub(r'(?i)' + re.escape(phrase), '', cleaned_text)
    return cleaned_text


def cluster_news_into_storylines(all_news_text):
    # ... (эта функция без изменений)
    print("Этап 1: Группировка новостей в сюжеты...")
    prompt = f"""[INST]Проанализируй новостной поток ниже. Твоя задача — найти МАКСИМАЛЬНОЕ количество независимых сюжетов, из которых можно сделать качественные журналистские статьи. Будь менее строгим: сюжет может быть основан даже на одной-двух очень содержательных новостях. Твоя цель — качество, но и количество. Отбрасывай только совсем короткие, несвязанные или рекламные упоминания.

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
    # ... (эта функция без изменений)
    print(f"Этап 2: Написание статьи на тему '{storyline['title']}'...")
    prompt = f"""[INST]Ты — первоклассный спортивный журналист и редактор, пишущий для ведущего русскоязычного издания. Твоя задача — написать захватывающую статью для Яндекс.Дзен на основе предоставленных новостей.

**Рабочее название сюжета:** "{storyline['title']}"

**САМОЕ ГЛАВНОЕ ПРАВИЛО: Статья должна быть написана ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ.**

**СТРОГИЕ ТРЕБОВАНИЯ К СТАТЬЕ:**
1.  **ЗАГОЛОВОК:** Твой ответ должен начинаться с яркого, интригующего, но абсолютно правдивого заголовка на РУССКОМ ЯЗЫКЕ. Заголовок должен быть на первой строке. НЕ ИСПОЛЬЗУЙ markdown или слова "Заголовок:".
2.  **СТИЛЬ:** Пиши как эксперт. Текст должен быть грамотным, аналитичным и увлекательным, чтобы удерживать внимание читателя до самого конца.
3.  **СТРУКТУРА:** Создай цельное повествование с логичным началом, развитием и завершением. Текст должен течь естественно, как статья в качественном издании.
4.  **ЗАПРЕТЫ:**
    *   **НИКОГДА** не используй подзаголовки вроде "Введение", "Раскрытие деталей", "Заключение", "Вывод", "Примечание", "Содержание" и т.п.
    *   **НИКОГДА** не добавляй оговорки или дисклеймеры о том, что информация может быть неточной.
    *   **НИКОГДА** не начинай текст со слов "Статья:" или похожих маркеров.

Твоя цель — создать готовый журналистский продукт на безупречном РУССКОМ языке, который выглядит так, как будто его написал человек, а не ИИ.
[/INST]

НОВОСТИ ДЛЯ АНАЛИЗА:
---
{storyline['news_texts']}
---
ГОТОВАЯ СТАТЬЯ:
"""
    response = _call_cloudflare_ai(TEXT_MODEL, {"prompt": prompt, "max_tokens": 1500})
    if response:
        raw_article_text = response.json()["result"]["response"]
        cleaned_article_text = clean_ai_artifacts(raw_article_text)
        storyline['article'] = cleaned_article_text
        return storyline
    return None

def find_real_photo_on_unsplash(storyline):
    # ... (эта функция без изменений)
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
    # ... (эта функция без изменений)
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
    # ... (эта функция без изменений)
    ET.register_namespace('yandex', 'http://news.yandex.ru')
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    try:
        tree = ET.parse(RSS_FILE_PATH)
        root = tree.getroot()
        channel = root.find('channel')
    except (FileNotFoundError, ET.ParseError):
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = "НА БАНКЕ"
        ET.SubElement(channel, "link").text = GITHUB_REPO_URL
        ET.SubElement(channel, "description").text = "«НА БАНКЕ». Все главные футбольные новости и слухи в одном месте. Трансферы, инсайды и честное мнение. Говорим о футболе так, как будто сидим с тобой на скамейке запасных."
    for storyline in reversed(processed_storylines):
        article_text = storyline.get('article')
        if not article_text: continue
        parts = article_text.strip().split('\n', 1)
        if len(parts) < 2 or not parts[0].strip():
            print("Пропускаем статью: сгенерирован ответ без заголовка или основного текста.")
            continue
        title = parts[0].strip().replace("**", "").replace("Заголовок:", "").strip().replace('"', '')
        full_text = parts[1].strip()
        if not title:
            print("Пропускаем статью: заголовок пуст после очистки.")
            continue
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
        print(f"В RSS стало {len(items)} статей. Удаляем старые...")
        for old_item in items[MAX_RSS_ITEMS:]:
            enclosure = old_item.find('enclosure')
            if enclosure is not None:
                image_url = enclosure.get('url')
                if image_url:
                    try:
                        image_filename = os.path.basename(image_url)
                        image_path = os.path.join(IMAGE_DIR, image_filename)
                        if os.path.exists(image_path):
                            os.remove(image_path)
                            print(f"Удаляем старое изображение: {image_filename}")
                    except Exception as e:
                        print(f"Не удалось удалить изображение {image_filename}: {e}")
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
        
        # ⬇️⬇️⬇️ ВЫЗЫВАЕМ ФУНКЦИЮ ПУБЛИКАЦИИ В TELEGRAM ЗДЕСЬ ⬇️⬇️⬇️
        if final_storyline:
            post_to_telegram_channel(final_storyline)
            processed_storylines.append(final_storyline)
        elif storyline_with_article:
            # Постим даже если картинки нет
            post_to_telegram_channel(storyline_with_article)
            processed_storylines.append(storyline_with_article)

    update_rss_file(processed_storylines)

if __name__ == "__main__":
    asyncio.run(main())
