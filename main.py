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
import google.generativeai as genai

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

# === ДОБАВЛЕНО/ОБНОВЛЕНО: Фразы для фильтрации рекламы/спама ===
SPAM_PHRASES = [
    "каппер", "прогноз на матч", "бесплатно", "заработок", "ставка на спорт", "налетай", "подписка", 
    "договорной матч", "слив инфы", "бот для ставок", "криптовалюта", "трейдинг", "платная инфа", 
    "подписаться", "подпишись", "подпишитесь", "экспресс", "ординар", "коэффициент", "коэф", 
    "проходимость", "железка", "аналитика", "раскрутка счета", "плюсовой аккаунт", "гарантии выигрыша", 
    "верификатор", "без вложений", "пассивный доход", "инвестиции", "быстрые деньги", "схема", 
    "миллионы", "вывод средств", "гарантированный доход", "финансовые гарантии", "окупаемость", 
    "с нуля", "легкие деньги", "халява", "розыгрыш", "подарок", "бонус", "приватный канал", 
    "закрытый клуб", "VIP-чат", "секретная стратегия", "инсайд", "доступ навсегда", "жми", 
    "переходи", "кликни", "заходи", "доступ ограничен", "успей", "пока не удалили", 
    "последние места", "жми на ссылку", "тг канал", "тг-канал", "телеграм канал", "телеграм-канал" ] 

# ================== API Ключи ==================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "").strip()
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL_USERNAME", "").strip()

# ================== Модели AI и прочие настройки ==================
TEXT_MODEL_NAME = "gemini-2.5-flash"
EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5"

RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
IMAGE_DIR = os.path.join(os.getcwd(), "images")
MEMORY_FILE_PATH = os.path.join(os.getcwd(), "memory.json")
DIGEST_MEMORY_PATH = os.path.join(os.getcwd(), "digest_memory.json")
NEWS_MEMORY_PATH = os.path.join(os.getcwd(), "news_memory.json")
MAX_RSS_ITEMS = 30
SIMILARITY_THRESHOLD = 0.88
GITHUB_REPO_URL = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
BANNED_PHRASES = [
    "вступление", "конец", "приложение:", "источники:", "из автора:", "дополнительные комментарии:", "заключение",
    "вывод:", "выводы:", "примечание:", "содержание:", "анализ:", "история:", "оценка:", "итог:", "перспективы:",
    "история развития событий:", "раскрытие деталей:", "резюме:", "призыв к действию:", "точная информация:",
    "голубая волна в милане", "право на выбор", "ставка на судзуки", "конclusion:", "продолжение:", "статья:", "готовая статья:"
]

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def cosine_similarity(v1, v2):
    if not v1 or not v2: return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = sum(a * a for a in v1) ** 0.5
    norm_v2 = sum(b * b for b in v2) ** 0.5
    if norm_v1 == 0 or norm_v2 == 0: return 0.0
    return dot_product / (norm_v1 * norm_v2)

def _call_cloudflare_ai(model, payload, timeout=240):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN: return None
    api_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"Ошибка HTTP-запроса к Cloudflare API: {e}")
        if e.response is not None: print(f"Ответ сервера ({e.response.status_code}): {e.response.text}")
        return None

def get_embedding(text):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        print("Ключи Cloudflare не найдены, 'умная память' отключена.")
        return None
    response = _call_cloudflare_ai(EMBEDDING_MODEL, {"text": [text]})
    if response:
        try:
            return response.json()["result"]["data"][0]
        except (KeyError, IndexError): return None
    return None

async def get_channel_posts():
    API_ID = os.environ.get("API_ID")
    API_HASH = os.environ.get("API_HASH")
    SESSION_STRING = os.environ.get("SESSION_STRING")
    if not API_ID or not API_HASH or not SESSION_STRING:
        raise ValueError("Секреты Telegram для парсинга не найдены!")
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    candidate_posts = []
    unique_texts = set()
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - timedelta(hours=1)
    
    # === ДОБАВЛЕНО: Функция для проверки спама ===
    def is_spam(text):
        lower_text = text.lower()
        if len(text.split()) < 20: # Слишком короткие посты часто бывают рекламой
            return True
        for phrase in SPAM_PHRASES:
            if phrase in lower_text:
                return True
        return False
    # ============================================

    async with client:
        for channel_name in CHANNELS:
            print(f"Парсинг канала: {channel_name}...")
            try:
                async for msg in client.iter_messages(channel_name, limit=50):
                    if msg.date < cutoff: break
                    if msg.text and msg.text not in unique_texts:
                        
                        # === ИСПОЛЬЗОВАНИЕ ФИЛЬТРАЦИИ ===
                        if is_spam(msg.text):
                            continue
                        # ===============================

                        unique_texts.add(msg.text)
                        candidate_posts.append(msg.text.strip())
            except Exception as e:
                print(f"Не удалось получить посты из канала '{channel_name}': {e}")
    print(f"Найдено {len(candidate_posts)} постов-кандидатов.")
    return candidate_posts

async def filter_unique_posts(candidate_posts, news_memory):
    print("Начинаем фильтрацию смысловых дублей...")
    unique_posts = []
    old_embeddings = list(news_memory.values())
    for post_text in candidate_posts:
        if len(post_text) < 40: continue
        post_embedding = get_embedding(post_text)
        if not post_embedding:
            unique_posts.append(post_text)
            continue
        is_duplicate = False
        for old_embedding in old_embeddings:
            if cosine_similarity(post_embedding, old_embedding) > SIMILARITY_THRESHOLD:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_posts.append(post_text)
            news_memory[post_text] = post_embedding
            old_embeddings.append(post_embedding)
    print(f"После фильтрации осталось {len(unique_posts)} уникальных постов.")
    return unique_posts

def _call_gemini_ai(prompt, max_tokens=2048, use_json_mode=False):
    if not GEMINI_API_KEY:
        print("Секрет GEMINI_API_KEY не найден."); return None
    try:
        model = genai.GenerativeModel(TEXT_MODEL_NAME)
        safety_settings = {'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE', 'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'}
        generation_config = genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=0.7, response_mime_type="application/json" if use_json_mode else "text/plain")
        response = model.generate_content(prompt, generation_config=generation_config, safety_settings=safety_settings)
        if response.parts:
            return response.text
        else:
            print(f"Gemini вернул пустой ответ. Причина: {response.candidates[0].finish_reason.name if response.candidates else 'Неизвестно'}")
            return None
    except Exception as e:
        print(f"Ошибка при обращении к Gemini API: {e}"); return None

def clean_ai_artifacts(text):
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if not any(line.lower().strip().replace('*', '').replace(':', '') == phrase for phrase in BANNED_PHRASES)]
    cleaned_text = '\n'.join(cleaned_lines).strip()
    return cleaned_text

async def cluster_news_into_storylines(news_batch, memory):
    """Группирует пачку новостей в сюжеты."""
    print(f"Группируем {len(news_batch)} новостей в сюжеты...")
    numbered_news = "\n\n---\n\n".join([f"Новость #{i}:\n{news}" for i, news in enumerate(news_batch)])
    
    prompt = f"""Ты — главный редактор. Проанализируй пронумерованные новости ниже и выполни два действия:

1.  **Найди КАК МОЖНО БОЛЬШЕ** качественных сюжетов для статей (до 10 штук). Для каждого сюжета верни JSON-объект с полями: `title`, `category`, `search_queries` и `news_indices`.
2.  **Определи главную тему часа.** Проанализируй ВЕСЬ новостной поток и верни ОДНУ главную персону или событие в поле `main_event_query` (на английском).

Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате одного JSON-объекта с ключами `storylines` и `main_event_query`.

ПРОНУМЕРОВАННЫЕ НОВОСТИ:
---
{numbered_news}
---
"""
    raw_response = _call_gemini_ai(prompt, use_json_mode=True, max_tokens=8192)
    if not raw_response: return [], None
    
    try:
        # Gemini в JSON mode возвращает чистый JSON, парсим его напрямую
        data = json.loads(raw_response)
        
        storylines_with_indices = data.get("storylines", [])
        main_event_query = data.get("main_event_query")
        
        storylines = []
        for storyline in storylines_with_indices:
            indices = storyline.get("news_indices", [])
            news_texts = "\n\n---\n\n".join([news_batch[i] for i in indices if i < len(news_batch)])
            storyline['news_texts'] = news_texts
            storylines.append(storyline)
            
        unique_storylines = []
        for storyline in storylines:
            title = storyline.get("title")
            if not title: continue
            title_embedding = get_embedding(title)
            if not title_embedding:
                unique_storylines.append(storyline)
                continue
            is_duplicate = False
            for old_embedding in memory.values():
                if cosine_similarity(title_embedding, old_embedding) > SIMILARITY_THRESHOLD:
                    is_duplicate = True; break
            if not is_duplicate: unique_storylines.append(storyline)
            
        print(f"Найдено {len(storylines)} сюжетов, из них {len(unique_storylines)} уникальных.")
        return unique_storylines, main_event_query

    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка декодирования JSON: {e}")
        if 'raw_response' in locals():
            print("Сырой ответ от модели:", raw_response)
        return [], None

def write_article_for_storyline(storyline):
    print(f"Этап 2: Написание статьи на тему '{storyline['title']}'...")
    
    # === ИСПРАВЛЕНИЕ 1: Извлекаем новостные сводки ===
    news_content = storyline.get('news_texts', 'Нет новостных сводок.')
    
    prompt = f"""**Роль:**
Ты — опытный контент-маркетолог и редактор Дзен-канала "НА БАНКЕ". Твоя задача — взять сухие новостные сводки и превратить их в "воздушный", динамичный и вирусный текст, который читатели досмотрят до конца.

**Главные правила:**
1.  **Пиши только на безупречном РУССКОМ языке.**
2.  **Основывайся СТРОГО на фактах из предоставленных новостей.** Не выдумывай детали.

**ТРЕБОВАНИЯ К ТЕКСТУ:**

**1. Заголовок:**
*   Твой ответ должен начинаться СРАЗУ с заголовка.
*   Заголовок должен быть коротким (5-12 слов), интригующим и кликабельным.

**2. Структура и Форматирование (используй HTML-теги):**
*   **Короткие абзацы:** Каждый абзац — это 1-3 коротких, ударных предложения. Никаких "стен текста".
*   **Подзаголовки:** Используй 2-3 интригующих подзаголовка, чтобы разбить текст. Оберни их в теги `<b>` и `</b>`. **Пример:** `<b>Что теперь будет с тренером?</b>`
*   **Выделение:** Выделяй ключевые мысли, имена и цифры жирным шрифтом. Используй теги `<b>` и `</b>` (2-3 выделения на статью). **Пример:** `Контракт подписан на <b>5 лет</b>.`
*   **Списки:** Если есть перечисления, оформляй их как маркированный список, используя символ `•` в начале каждой строки.

**3. Стиль:**
*   **"Крючок" в начале:** Первый абзац должен быть самым мощным. Начни с самой шокирующей или интригующей детали.
*   **Без "воды":** Убирай все лишние слова и конструкции, которые замедляют чтение.
*   **Динамика:** Используй простой, разговорный язык и активный залог.

**ЗАПРЕТЫ:**
*   **НИКОГДА** не используй формальные подзаголовки ("Введение", "Заключение", "Анализ").
*   **НИКОГДА** не используй Markdown (`#`, `*`). Только HTML-теги `<b>` и `</b>` для жирного шрифта.
*   **НИКОГДА** не добавляй дисклеймеры или примечания.
*   **НИКОГДА** не пиши тексты рекламного, мошеннического, капперского или букмекерского характера. **Полный запрет** на любые призывы к ставкам, инвестициям или переходу по ссылкам.


**НОВОСТНЫЕ СВОДКИ ДЛЯ АНАЛИЗА И ПЕРЕРАБОТКИ:**
---
{news_content}
---
"""
    raw_article_text = _call_gemini_ai(prompt, max_tokens=3500)
    if not raw_article_text: return None
    
    cleaned_article_text = clean_ai_artifacts(raw_article_text)
    
    lines = cleaned_article_text.strip().split('\n')
    title, body_start_index = "", -1
    for i, line in enumerate(lines):
        if line.strip():
            title = line.strip()
            body_start_index = i + 1
            break
            
    is_bad_title = len(title) > 120 or (len(title.split()) > 1 and sum(1 for word in title.split() if word and word[0].isupper()) / len(title.split()) > 0.6)
    if is_bad_title:
        # Извлекаем только тело статьи
        body_lines = lines[body_start_index:] if body_start_index != -1 and body_start_index < len(lines) else []
        body = '\n'.join(body_lines).strip()
        
        print(f"Обнаружен плохой заголовок: '{title}'. Запрашиваем новый...")
        remake_prompt = f"Придумай короткий (5-10 слов), интригующий и понятный заголовок на русском языке для этой статьи:\n\n{body}" # <-- ИСПОЛЬЗУЕМ {body} вместо {cleaned_article_text}
        new_title_response = _call_gemini_ai(remake_prompt, max_tokens=150) 
        
        if new_title_response:
            new_title = new_title_response.strip().replace('"', '')
            print(f"Новый заголовок: '{new_title}'")
            # body уже определен выше
            storyline['article'] = f"{new_title}\n{body}"
        else:
            storyline['article'] = cleaned_article_text
   
    else:
        storyline['article'] = cleaned_article_text
        
    return storyline

def write_summary_article(remaining_news, main_event_query):
    print("План Б: Создание общей новостной сводки...")
    storyline = {"title": "Общая сводка новостей", "category": "Дайджест", "search_queries": [main_event_query] if main_event_query else ["latest football news"]}
    prompt = f"""Ты — первоклассный спортивный журналист. Напиши одну общую статью-дайджест.

ТРЕБОВАНИЯ:
1.  Придумай яркий и интригующий заголовок, отражающий САМОЕ интересное событие.
2.  В статье кратко, в 2-3 предложениях, расскажи о 3-4 самых заметных новостях.
3.  Статья должна быть на безупречном РУССКОМ языке и без формальных подзаголовков.

НОВЫЙ ПОТОК НОВОСТЕЙ:
---
{remaining_news}
---
"""
    raw_article_text = _call_gemini_ai(prompt, max_tokens=3000)
    if raw_article_text:
        storyline['article'] = clean_ai_artifacts(raw_article_text)
        return storyline
    return None

async def find_real_photo_on_google(storyline):
    await asyncio.sleep(2)
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID: return None
    queries = storyline.get("search_queries", [])
    if not queries: return None
    for query in queries:
        print(f"Этап 3 (Основной): Поиск фото в Google по запросу: '{query}'...")
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
            print("Пропускаем статью: не удалось извлечь заголовок."); continue
            
        full_text = '\n'.join(lines[start_of_body_index:]).strip()
        if len(full_text.split()) < 30:
            print(f"Пропускаем статью '{title}': основной текст слишком короткий."); continue

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

def run_telegram_poster(storylines_json):
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

        if len(full_text.split()) < 30:
            print(f"Пропускаем отправку в Telegram статьи '{title}': основной текст слишком короткий.")
            continue
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        text = f"<b>{title}</b>\n\n{full_text}"
        if len(text) > 4096: text = text[:4093] + "..."
        payload = { 'chat_id': f"@{TELEGRAM_CHANNEL_USERNAME}", 'text': text, 'parse_mode': 'HTML' }
            
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            print(f"✅ Статья '{title}' успешно опубликована в Telegram.")
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка публикации статьи '{title}' в Telegram: {e}")
            if e.response is not None: print(f"Ответ сервера Telegram: {e.response.text}")

async def run_rss_generator():
    """Основная логика генерации RSS и изображений."""
    title_memory = {}
    try:
        if os.path.exists(MEMORY_FILE_PATH):
            with open(MEMORY_FILE_PATH, 'r', encoding='utf-8') as f: title_memory = json.load(f)
            print(f"Загружено {len(title_memory)} записей из памяти заголовков.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("Файл памяти заголовков не найден или пуст.")

    digest_memory = []
    try:
        if os.path.exists(DIGEST_MEMORY_PATH):
            with open(DIGEST_MEMORY_PATH, 'r', encoding='utf-8') as f: digest_memory = json.load(f)
            print(f"Загружено {len(digest_memory)} новостей из памяти дайджестов.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("Файл памяти дайджестов не найден.")

    news_memory = {}
    try:
        if os.path.exists(NEWS_MEMORY_PATH):
            with open(NEWS_MEMORY_PATH, 'r', encoding='utf-8') as f: news_memory = json.load(f)
            print(f"Загружено {len(news_memory)} новостей из памяти постов.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("Файл памяти новостей не найден.")

    candidate_posts = await get_channel_posts()
    unique_posts = await filter_unique_posts(candidate_posts, news_memory)
    
    if not unique_posts or len(unique_posts) < 3:
        print("Новых постов для обработки недостаточно."); return

    # "Разделяй и властвуй"
    mid_index = len(unique_posts) // 2
    news_batch_1 = unique_posts[:mid_index]
    news_batch_2 = unique_posts[mid_index:]
    
    print(f"Разделяем уникальные новости на две пачки: {len(news_batch_1)} и {len(news_batch_2)} постов.")
    
    # ⬇️⬇️⬇️ ИСПРАВЛЕНИЕ ЗДЕСЬ: Добавляем 'await' для асинхронных вызовов ⬇️⬇️⬇️
    # Выполняем запросы последовательно
    print("\n--- Обработка первой пачки новостей ---")
    storylines1, query1 = await cluster_news_into_storylines(news_batch_1, dict(list(title_memory.items())[-70:]))
    
    print("\n--- Обработка второй пачки новостей ---")
    storylines2, query2 = await cluster_news_into_storylines(news_batch_2, dict(list(title_memory.items())[-70:]))
    
    # Объединяем результаты
    all_storyline_candidates = (storylines1 or []) + (storylines2 or [])
    main_event_query = query1 or query2
    
    print(f"\nВсего найдено {len(all_storyline_candidates)} кандидатов в сюжеты.")
    
    processed_storylines = []
    used_news_for_digest = set()
    if all_storyline_candidates:
        print(f"Начинаем обработку {len(all_storyline_candidates)} уникальных сюжетов-кандидатов...")
        for storyline in all_storyline_candidates:
            if len(processed_storylines) >= 5:
                print("Уже набрано 5 статей, прекращаем обработку сюжетов."); break
            if len(storyline.get("news_texts", "")) < 50:
                continue
            storyline_with_article = write_article_for_storyline(storyline)
            if not storyline_with_article: continue
            
            # ⬇️⬇️⬇️ ИСПРАВЛЕНИЕ ЗДЕСЬ ⬇️⬇️⬇️
            article_parts = storyline_with_article['article'].split('\n', 1)
            title_part = article_parts[0] if article_parts else ""
            full_text_part = article_parts[1] if len(article_parts) > 1 else ""

            if len(full_text_part.split()) < 30:
                print(f"Пропускаем статью '{title_part}': сгенерированный текст слишком короткий.")
                continue

            used_news_for_digest.update(storyline.get("news_texts", "").split("\n\n---\n\n"))
            final_storyline = await find_real_photo_on_google(storyline_with_article)
            processed_storylines.append(final_storyline or storyline_with_article)
    if not processed_storylines:
        print("Ни один из сюжетов не прошел фильтры. Переходим к плану Б.")
        
        # 1. Сначала собираем все уникальные новости, которые еще не были в дайджесте
        all_news_for_digest = [news for news in unique_posts 
                               if news not in digest_memory[-150:]]
        
        # 2. Оставшиеся новости: те, что не были успешно использованы в индивидуальных статьях
        remaining_news_list = [news for news in all_news_for_digest if news not in used_news_for_digest]
        
        if remaining_news_list:
            remaining_news_text = "\n\n---\n\n".join(remaining_news_list)
            
            # Используем оставшиеся новости для определения главной темы
            news_sample_for_prompt = '\n'.join(remaining_news_list[:20])
            main_event_prompt = f"Проанализируй эти новости и верни ОДНУ главную персону или событие на английском для поиска фото:\n\n{news_sample_for_prompt}"
            main_event_query_response = _call_gemini_ai(main_event_prompt, max_tokens=100)
            main_event_query_final = main_event_query_response.strip() if main_event_query_response else "latest football news"

            summary_storyline = write_summary_article(remaining_news_text, main_event_query_final)
            if summary_storyline:
                final_summary = await find_real_photo_on_google(summary_storyline)
                processed_storylines.append(final_summary or summary_storyline)
                digest_memory.extend(remaining_news_list)
        else:
            print("Недостаточно новых новостей для дайджеста.")

    if not processed_storylines:
        print("Не удалось сгенерировать ни одной статьи."); return

    new_memory_entries = {}
    for storyline in processed_storylines:
        if storyline and storyline.get('article'):
            title_for_memory_match = storyline['article'].split('\n', 1)
            if title_for_memory_match:
                 title_for_memory = title_for_memory_match[0].strip()
                 embedding = get_embedding(title_for_memory)
                 if title_for_memory and embedding:
                     new_memory_entries[title_for_memory] = embedding
    
    update_rss_file(processed_storylines)
    
    title_memory.update(new_memory_entries)
    if len(title_memory) > 70:
        keys_to_keep = list(title_memory.keys())[-70:]
        title_memory = {k: title_memory[k] for k in keys_to_keep}
    with open(MEMORY_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(title_memory, f, ensure_ascii=False, indent=2)
    print(f"Память заголовков обновлена.")

    if len(digest_memory) > 150:
        digest_memory = digest_memory[-150:]
    with open(DIGEST_MEMORY_PATH, 'w', encoding='utf-8') as f:
        json.dump(digest_memory, f, ensure_ascii=False)
    print(f"Память дайджестов обновлена.")

    if len(news_memory) > 250:
        keys_to_keep = list(news_memory.keys())[-250:]
        news_memory = {k: news_memory[k] for k in keys_to_keep}
    with open(NEWS_MEMORY_PATH, 'w', encoding='utf-8') as f:
        json.dump(news_memory, f, ensure_ascii=False)
    print(f"Память новостей обновлена.")
    
    storylines_json = json.dumps(processed_storylines)
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f'processed_storylines_json={storylines_json}\n')

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == '--mode':
        mode = sys.argv[2]
        if mode == 'generate_rss':
            if not all(os.environ.get(key) for key in ["API_ID", "API_HASH", "SESSION_STRING"]):
                print("Пропускаем генерацию RSS.")
            else:
                asyncio.run(run_rss_generator())
        elif mode == 'post_to_telegram':
            storylines_json_env = os.environ.get("PROCESSED_STORYLINES_JSON")
            if storylines_json_env:
                run_telegram_poster(storylines_json_env)
    else:
        print("Режим работы не указан.")
