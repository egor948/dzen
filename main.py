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
import sys
from groq import Groq

# ================= НАСТРОЙКИ =================
# Telegram-парсер инициализируется по необходимости.
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
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "").strip()
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL_USERNAME", "").strip()

# ================== Модели AI и прочие настройки ==================
TEXT_MODEL = "llama-3.3-70b-versatile"

RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
IMAGE_DIR = os.path.join(os.getcwd(), "images")
MAX_RSS_ITEMS = 30
GITHUB_REPO_URL = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
BANNED_PHRASES = [
    "вступление", "конец", "приложение:", "источники:", "из автора:", "дополнительные комментарии:",
    "заключение", "вывод:", "выводы:", "примечание:", "содержание:", "анализ:", "история:", "оценка:", "итог:", "перспективы:",
    "история развития событий:", "раскрытие деталей:", "резюме:", "призыв к действию:",
    "точная информация:", "голубая волна в милане", "право на выбор", "ставка на судзуки",
    "конclusion:", "продолжение:", "статья:", "готовая статья:"
]

async def get_channel_posts():
    """Собирает новости за последний час."""
    API_ID = os.environ.get("API_ID")
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    if not API_ID or not API_HASH or not SESSION_STRING:
        raise ValueError("Секреты Telegram для парсинга не найдены!")
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
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

def _call_groq_ai(messages, max_tokens=2048):
    """Универсальная функция для вызова API Groq."""
    if not GROQ_API_KEY:
        print("Секрет GROQ_API_KEY не найден. Пропускаем вызов AI.")
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=messages,
            model=TEXT_MODEL,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Ошибка при обращении к Groq API: {e}")
        return None

def clean_ai_artifacts(text):
    """Программно удаляет распространенные 'артефакты' из текста ИИ."""
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        test_line = line.lower().strip().replace('*', '').replace(':', '')
        if not any(test_line.startswith(phrase) for phrase in BANNED_PHRASES):
            cleaned_lines.append(line)
    cleaned_text = '\n'.join(cleaned_lines).strip()
    return cleaned_text

def cluster_news_into_storylines(all_news_text, existing_titles):
    """Группирует новости в ДВА лучших сюжета для статей."""
    print("Этап 1: Группировка новостей в 2 лучших сюжета...")
    titles_to_exclude = "\n".join(f"- {title}" for title in existing_titles)
    prompt = f"""[INST]Твоя задача — выступить в роли главного редактора. Проанализируй весь новостной поток ниже и найди **ДВА САМЫХ ЛУЧШИХ, наиболее проработанных и независимых сюжета** для статей.

**ВАЖНОЕ ПРАВИЛО:** Не выбирай темы, заголовки которых похожи на те, что перечислены в списке "УЖЕ ОПУБЛИКОВАННЫЕ СТАТЬИ".

Для каждого из двух сюжетов верни JSON-объект с полями:
1. `title`: Краткое рабочее название сюжета НА РУССКОМ.
2. `category`: Категория для RSS НА РУССКОМ.
3. `search_queries`: JSON-массив из 2-3 приоритетных запросов на АНГЛИЙСКОМ для поиска фото (сначала конкретный, потом общий).
4. `priority`: Приоритет сюжета ('high' или 'normal').
5. `news_texts`: ПОЛНЫЙ текст всех новостей по этому сюжету.

Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате JSON-массива из ДВУХ объектов, заключенного в ```json ... ```. Никакого лишнего текста.
[/INST]

УЖЕ ОПУБЛИКОВАННЫЕ СТАТЬИ:
---
{titles_to_exclude}
---

НОВЫЙ ПОТОК НОВОСТЕЙ:
---
{all_news_text}
---
JSON:
"""
    # Здесь вы вызываете _call_cloudflare_ai, но у вас его нет. Заменяем на _call_groq_ai
    # И передаем правильный формат
    messages = [{"role": "user", "content": prompt}]
    raw_response = _call_groq_ai(messages)
    if not raw_response: return []
    try:
        match = re.search(r'```json(.*?)```', raw_response, re.DOTALL)
        if not match: match = re.search(r'(\[.*\])', raw_response, re.DOTALL)
        if match:
            json_string = match.group(1).strip() if len(match.groups()) > 0 else match.group(0).strip()
            if not json_string.endswith(']') and '}' in json_string:
                last_brace_index = json_string.rfind('}')
                if last_brace_index != -1:
                    json_string = json_string[:last_brace_index + 1] + ']'
            storylines = json.loads(json_string)
            print(f"Найдено {len(storylines)} сюжетов для статей.")
            return storylines
        else:
            print("Не удалось найти JSON-блок в ответе модели.")
            return []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка декодирования JSON ответа модели: {e}")
        return []

def write_article_for_storyline(storyline):
    """Пишет статью по конкретному сюжету."""
    print(f"Этап 2: Написание статьи на тему '{storyline['title']}'...")
    prompt = f"""Ты — первоклассный спортивный журналист. Напиши захватывающую, фактически точную и объемную статью на РУССКОМ ЯЗЫКЕ на основе новостей ниже.

**ТРЕБОВАНИЯ:**
1.  **Начинай сразу с заголовка.** Заголовок должен быть ярким, интригующим, но правдивым.
2.  **Никаких выдумок.** Не добавляй факты, которых нет в исходных новостях.
3.  **Пиши как эксперт:** глубокий анализ, увлекательный стиль, цельное повествование.
4.  **ЗАПРЕТЫ:** НИКОГДА не используй подзаголовки ("Введение", "Заключение"), дисклеймеры или маркеры ("Статья:").
"""
    messages = [
        {"role": "user", "content": prompt + "\n\nНОВОСТИ ДЛЯ АНАЛИЗА:\n---\n" + storyline['news_texts']}
    ]

    raw_article_text = _call_groq_ai(messages, max_tokens=1500)
    if raw_article_text:
        cleaned_article_text = clean_ai_artifacts(raw_article_text)
        storyline['article'] = cleaned_article_text
        return storyline
    return None

def find_real_photo_on_google(storyline):
    """Ищет реальное фото с лицензией Creative Commons."""
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID: return None
    queries = storyline.get("search_queries", [])
    if not queries: return None
    for query in queries:
        print(f"Этап 3 (Основной): Поиск легального фото в Google по запросу: '{query}'...")
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "searchType": "image", "num": 1, "imgSize": "large"}
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if "items" in data and data["items"]:
                image_url = data["items"][0]["link"]
                if not image_url.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    continue
                image_response = requests.get(image_url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
                image_response.raise_for_status()
                os.makedirs(IMAGE_DIR, exist_ok=True)
                timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                image_filename = f"{timestamp}.jpg"
                image_path = os.path.join(IMAGE_DIR, image_filename)
                with open(image_path, "wb") as f: f.write(image_response.content)
                print(f"Фото из Google успешно сохранено: {image_path}")
                storyline['image_url'] = f"{GITHUB_REPO_URL.replace('github.com', 'raw.githubusercontent.com')}/main/images/{image_filename}"
                return storyline
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при обращении к Google Search API с запросом '{query}': {e}")
            continue
    print("В Google Images ничего не найдено.")
    return None

def update_rss_file(processed_storylines):
    """Обновляет RSS и возвращает список всех текущих заголовков."""
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
        
        lines = article_text.strip().split('\n')
        title, start_of_body_index = "", 0
        for i, line in enumerate(lines):
            if line.strip():
                title = line.strip().replace("**", "").replace('"', '')
                start_of_body_index = i + 1
                break
        
        if not title:
            print("Пропускаем статью: не удалось извлечь заголовок.")
            continue
            
        full_text = '\n'.join(lines[start_of_body_index:]).strip()
        if not full_text:
            print(f"Пропускаем статью '{title}': отсутствует основной текст после заголовка.")
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
            if enclosure is not None and enclosure.get('url'):
                try:
                    image_filename = os.path.basename(enclosure.get('url'))
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
    
    current_items = channel.findall('item')
    print(f"✅ RSS-лента успешно обновлена. Теперь в ней {len(current_items)} статей.")
    
    current_titles = [item.find('title').text for item in current_items if item.find('title') is not None]
    return current_titles

def run_telegram_poster(storylines_json):
    """Читает JSON и отправляет посты в Telegram."""
    print("Запуск публикации в Telegram...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_USERNAME: return
    try:
        storylines = json.loads(storylines_json)
    except json.JSONDecodeError: return
    for storyline in storylines:
        article_text = storyline.get('article')
        if not article_text: continue
        lines = article_text.strip().split('\n')
        title, start_of_body_index = "", 0
        for i, line in enumerate(lines):
            if line.strip():
                title = line.strip().replace("**", "").replace('"', '')
                start_of_body_index = i + 1
                break
        if not title: continue
        full_text = '\n'.join(lines[start_of_body_index:]).strip()
        if not storyline.get('image_url'):
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            text = f"<b>{title}</b>\n\n{full_text}"
            if len(text) > 4096: text = text[:4093] + "..."
            payload = { 'chat_id': f"@{TELEGRAM_CHANNEL_USERNAME}", 'text': text, 'parse_mode': 'HTML' }
        else:
            image_url = storyline['image_url']
            caption = f"<b>{title}</b>\n\n{full_text}"
            if len(caption) > 1024: caption = caption[:1021] + "..."
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            payload = { 'chat_id': f"@{TELEGRAM_CHANNEL_USERNAME}", 'photo': image_url, 'caption': caption, 'parse_mode': 'HTML' }
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            print(f"✅ Статья '{title}' успешно опубликована в Telegram.")
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка публикации статьи '{title}' в Telegram: {e}")
            if e.response is not None: print(f"Ответ сервера Telegram: {e.response.text}")

async def run_rss_generator():
    """Основная логика генерации RSS и изображений."""
    existing_titles = []
    try:
        tree = ET.parse(RSS_FILE_PATH)
        root = tree.getroot()
        # ⬇️⬇️⬇️ ИСПРАВЛЕНИЕ ЗДЕСЬ ⬇️⬇️⬇️
        existing_titles = [title_element.text for title_element in root.findall('.//item/title') if title_element.text is not None]
        print(f"Найдено {len(existing_titles)} существующих заголовков в RSS.")
    except (FileNotFoundError, ET.ParseError):
        print("RSS-файл не найден, будет создан новый.")

    combined_text = await get_channel_posts()
    if not combined_text or len(combined_text) < 100:
        print("Новых постов для обработки недостаточно.")
        return

    if len(combined_text) > 30000:
        combined_text = combined_text[:30000]
    storylines = cluster_news_into_storylines(combined_text, existing_titles)
    if not storylines:
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write('processed_storylines_json=[]\n')
        return
    processed_storylines = []
    for storyline in storylines:
        if len(storyline.get("news_texts", "")) < 100:
            print(f"Пропускаем сюжет '{storyline.get('title')}' из-за недостатка материала.")
            continue
        storyline_with_article = write_article_for_storyline(storyline)
        if not storyline_with_article: continue
        final_storyline = find_real_photo_on_google(storyline_with_article)
        processed_storylines.append(final_storyline or storyline_with_article)
    
    update_rss_file(processed_storylines)
    storylines_json = json.dumps(processed_storylines)
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f'processed_storylines_json={storylines_json}\n')

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == '--mode':
        mode = sys.argv[2]
        if mode == 'generate_rss':
            if not all(os.environ.get(key) for key in ["API_ID", "API_HASH", "SESSION_STRING"]):
                print("Пропускаем генерацию RSS: не все секреты Telegram для парсинга доступны.")
            else:
                asyncio.run(run_rss_generator())
        elif mode == 'post_to_telegram':
            storylines_json_env = os.environ.get("PROCESSED_STORYLINES_JSON")
            if storylines_json_env:
                run_telegram_poster(storylines_json_env)
    else:
        print("Режим работы не указан. Запустите с --mode generate_rss или --mode post_to_telegram.")
