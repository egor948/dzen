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

# ================== API Ключи ==================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "").strip()
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL_USERNAME", "").strip()

# ================== Модели AI и прочие настройки ==================
TEXT_MODEL_NAME = "gemini-1.5-flash"
EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5"

RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
IMAGE_DIR = os.path.join(os.getcwd(), "images")
MEMORY_FILE_PATH = os.path.join(os.getcwd(), "memory.json")
DIGEST_MEMORY_PATH = os.path.join(os.getcwd(), "digest_memory.json") # Память для дайджестов
MAX_RSS_ITEMS = 30
SIMILARITY_THRESHOLD = 0.85
GITHUB_REPO_URL = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
BANNED_PHRASES = [
    "вступление", "конец", "приложение:", "источники:", "из автора:", "дополнительные комментарии:",
    "заключение", "вывод:", "выводы:", "примечание:", "содержание:", "анализ:", "история:", "оценка:", "итог:", "перспективы:",
    "история развития событий:", "раскрытие деталей:", "резюме:", "призыв к действию:",
    "точная информация:", "голубая волна в милане", "право на выбор", "ставка на судзуки",
    "конclusion:", "продолжение:", "статья:", "готовая статья:"
]

# Инициализация клиента Gemini
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

def _call_gemini_ai(prompt, max_tokens=2048):
    if not GEMINI_API_KEY:
        print("Секрет GEMINI_API_KEY не найден. Пропускаем вызов AI.")
        return None
    try:
        model = genai.GenerativeModel(TEXT_MODEL_NAME)
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=0.7))
        return response.text
    except Exception as e:
        print(f"Ошибка при обращении к Gemini API: {e}")
        return None

def clean_ai_artifacts(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        test_line = line.lower().strip().replace('*', '').replace(':', '')
        if not any(test_line.startswith(phrase) for phrase in BANNED_PHRASES):
            cleaned_lines.append(line)
    cleaned_text = '\n'.join(cleaned_lines).strip()
    return cleaned_text

def cluster_news_into_storylines(all_news_text, memory):
    print("Этап 1: Группировка новостей в 2 лучших сюжета...")
    prompt = f"""Ты — главный редактор. Проанализируй новости и найди ДВА САМЫХ ЛУЧШИХ сюжета для статей.

Для каждого сюжета верни JSON-объект с полями: `title`, `category`, `search_queries` (массив запросов на английском для фото), `news_texts` (полный текст новостей).

Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате JSON-массива, заключенного в ```json ... ```.

НОВЫЙ ПОТОК НОВОСТЕЙ:
---
{all_news_text}
---
```json
"""
    raw_response = _call_gemini_ai(prompt)
    if not raw_response: return []
    try:
        match = re.search(r'```json(.*?)```', raw_response, re.DOTALL)
        if match:
            json_string = match.group(1).strip()
            storylines = json.loads(json_string)
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
            return unique_storylines
        else:
            print("Не удалось найти JSON-блок в ответе модели."); return []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка декодирования JSON ответа модели: {e}"); return []

def write_article_for_storyline(storyline):
    print(f"Этап 2: Написание статьи на тему '{storyline['title']}'...")
    prompt = f"""Ты — первоклассный спортивный журналист. Напиши захватывающую и объемную статью (3-5 абзацев) на РУССКОМ ЯЗЫКЕ на основе новостей ниже.

ТРЕБОВАНИЯ:
1.  Начинай сразу с яркого, интригующего заголовка.
2.  Придерживайся фактов из текста, не выдумывай информацию.
3.  Пиши как эксперт: глубокий анализ, увлекательный стиль, цельное повествование.
4.  ЗАПРЕТЫ: Не используй формальные подзаголовки ("Введение", "Заключение") и любые дисклеймеры.

НОВОСТИ ДЛЯ АНАЛИЗА:
---
{storyline['news_texts']}
---
"""
    raw_article_text = _call_gemini_ai(prompt, max_tokens=3500)
    if not raw_article_text: return None
    storyline['article'] = clean_ai_artifacts(raw_article_text)
    return storyline

def write_summary_article(remaining_news, main_event_query):
    print("План Б: Создание общей новостной сводки...")
    storyline = {"title": "Общая сводка новостей", "category": "Дайджест", "search_queries": [main_event_query] if main_event_query else ["latest football news"]}
    prompt = f"""Ты — первоклассный спортивный журналист. Твоя задача — проанализировать поток новостей ниже и написать на его основе одну общую статью-дайджест.

ТРЕБОВАНИЯ:
1.  Придумай яркий и интригующий заголовок, который отражает САМОЕ интересное событие из всего потока. Начинай ответ сразу с этого заголовка.
2.  В самой статье кратко, в 2-3 предложениях, расскажи о 3-4 самых заметных новостях.
3.  Статья должна быть на безупречном РУССКОМ языке и без формальных подзаголовков.

НОВЫЙ ПОТОК НОВОСТЕЙ:
---
{remaining_news}
---
"""
    raw_article_text = _call_gemini_ai(prompt, max_tokens=1500)
    if raw_article_text:
        storyline['article'] = clean_ai_artifacts(raw_article_text)
        return storyline
    return None

def find_real_photo_on_google(storyline):
    # ... (эта функция без изменений)

def update_rss_file(processed_storylines):
    # ... (эта функция без изменений)

def run_telegram_poster(storylines_json):
    # ... (эта функция без изменений)

async def run_rss_generator():
    """Основная логика генерации RSS и изображений."""
    memory = {}
    try:
        if os.path.exists(MEMORY_FILE_PATH):
            with open(MEMORY_FILE_PATH, 'r', encoding='utf-8') as f: memory = json.load(f)
            print(f"Загружено {len(memory)} заголовков из памяти.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("Файл памяти не найден или пуст.")
        
    digest_memory = []
    try:
        if os.path.exists(DIGEST_MEMORY_PATH):
            with open(DIGEST_MEMORY_PATH, 'r', encoding='utf-8') as f: digest_memory = json.load(f)
            print(f"Загружено {len(digest_memory)} новостей из памяти дайджестов.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("Файл памяти дайджестов не найден.")

    combined_text = await get_channel_posts()
    if not combined_text or len(combined_text) < 50:
        print("Новых постов для обработки недостаточно."); return
    if len(combined_text) > 40000:
        combined_text = combined_text[:40000]

    unique_storylines = cluster_news_into_storylines(combined_text, memory)
    
    processed_storylines = []
    used_news_for_digest = []
    if unique_storylines:
        print(f"Начинаем обработку {len(unique_storylines)} уникальных сюжетов...")
        for storyline in unique_storylines:
            if len(storyline.get("news_texts", "")) < 50:
                print(f"Пропускаем сюжет '{storyline.get('title')}' из-за недостатка материала."); continue
            
            storyline_with_article = write_article_for_storyline(storyline)
            if not storyline_with_article: continue
            
            used_news_for_digest.extend(storyline.get("news_texts", "").split("\n\n---\n\n"))
            final_storyline = find_real_photo_on_google(storyline_with_article)
            processed_storylines.append(final_storyline or storyline_with_article)
    
    # Логика "Плана Б"
    print("Подготовка к созданию дайджеста...")
    all_news_list = combined_text.split("\n\n---\n\n")
    remaining_news_list = [news for news in all_news_list if news not in used_news_for_digest and news not in digest_memory]
    
    if remaining_news_list and len("\n\n---\n\n".join(remaining_news_list)) > 100:
        remaining_news_text = "\n\n---\n\n".join(remaining_news_list)
        # Главную тему ищем по всем новостям, а не по остаткам
        main_event_query = _call_gemini_ai(f"Проанализируй эти новости и верни ОДНУ главную персону или событие на английском для поиска фото:\n\n{combined_text}", max_tokens=20)
        
        summary_storyline = write_summary_article(remaining_news_text, main_event_query)
        if summary_storyline:
            final_summary = find_real_photo_on_google(summary_storyline)
            processed_storylines.append(final_summary or summary_storyline)
            # Обновляем память дайджестов
            digest_memory.extend(remaining_news_list)
    else:
        print("Недостаточно новых новостей для создания дайджеста.")

    if not processed_storylines:
        print("Не удалось сгенерировать ни одной статьи."); return

    # Обновляем память заголовков
    new_memory_entries = {}
    for storyline in processed_storylines:
        if storyline and storyline.get('article'):
            title_for_memory = storyline['article'].split('\n', 1).strip()
            embedding = get_embedding(title_for_memory)
            if title_for_memory and embedding:
                new_memory_entries[title_for_memory] = embedding
    
    update_rss_file(processed_storylines)
    
    memory.update(new_memory_entries)
    if len(memory) > 200:
        oldest_titles = list(memory.keys())[:-150]
        for t in oldest_titles: del memory[t]
    with open(MEMORY_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    print(f"Память заголовков обновлена. Теперь в ней {len(memory)} записей.")

    # Обновляем память дайджестов
    if len(digest_memory) > 500: # Храним ~500 последних новостей из дайджестов
        digest_memory = digest_memory[-400:]
    with open(DIGEST_MEMORY_PATH, 'w', encoding='utf-8') as f:
        json.dump(digest_memory, f, ensure_ascii=False)
    print(f"Память дайджестов обновлена. Теперь в ней {len(digest_memory)} новостей.")
    
    storylines_json = json.dumps(processed_storylines)
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f'processed_storylines_json={storylines_json}\n')

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv == '--mode':
        mode = sys.argv
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
