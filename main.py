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
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "").strip()
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL_USERNAME", "").strip()

# ================== Модели AI и прочие настройки ==================
# ⬇️⬇️⬇️ ВАШЕ НАЗВАНИЕ МОДЕЛИ ⬇️⬇️⬇️
TEXT_MODEL = "llama-3.1-70b-versatile"
EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5"

RSS_FILE_PATH = os.path.join(os.getcwd(), "rss.xml")
IMAGE_DIR = os.path.join(os.getcwd(), "images")
MEMORY_FILE_PATH = os.path.join(os.getcwd(), "memory.json")
MAX_RSS_ITEMS = 30
SIMILARITY_THRESHOLD = 0.92

GITHUB_REPO_URL = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}"
BANNED_PHRASES = [
    "вступление", "конец", "приложение:", "источники:", "из автора:", "дополнительные комментарии:",
    "заключение", "вывод:", "выводы:", "примечание:", "содержание:", "анализ:", "история:", "оценка:", "итог:", "перспективы:",
    "история развития событий:", "раскрытие деталей:", "резюме:", "призыв к действию:",
    "точная информация:", "голубая волна в милане", "право на выбор", "ставка на судзуки",
    "конclusion:", "продолжение:", "статья:", "готовая статья:"
]

def cosine_similarity(v1, v2):
    if not v1 or not v2: return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = sum(a * a for a in v1) ** 0.5
    norm_v2 = sum(b * b for b in v2) ** 0.5
    if norm_v1 == 0 or norm_v2 == 0: return 0.0
    return dot_product / (norm_v1 * norm_v2)

def get_embedding(text):
    """Получает векторное представление текста с помощью Cloudflare AI."""
    # ⬇️⬇️⬇️ ПРОВЕРКА НАЛИЧИЯ КЛЮЧЕЙ CLOUDFLARE ⬇️⬇️⬇️
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        print("Ключи Cloudflare не найдены, 'умная память' отключена.")
        return None
        
    response = _call_cloudflare_ai(EMBEDDING_MODEL, {"text": [text]})
    if response:
        try:
            return response.json()["result"]["data"][0]
        except (KeyError, IndexError):
            print("Ошибка: не удалось получить вектор из ответа Cloudflare.")
            return None
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

def _call_groq_ai(messages, max_tokens=2048):
    if not GROQ_API_KEY:
        print("Секрет GROQ_API_KEY не найден. Пропускаем вызов AI.")
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=messages, model=TEXT_MODEL, max_tokens=max_tokens, temperature=0.7,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Ошибка при обращении к Groq API: {e}")
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
    prompt = f"""[INST]... (ваш промпт на 2 статьи) ...[/INST]""" # Промпт остается тот же
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
                if last_brace_index != -1: json_string = json_string[:last_brace_index + 1] + ']'
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
                        is_duplicate = True
                        break
                if not is_duplicate: unique_storylines.append(storyline)
            print(f"Найдено {len(storylines)} сюжетов, из них {len(unique_storylines)} уникальных.")
            return unique_storylines
        else:
            print("Не удалось найти JSON-блок в ответе модели.")
            return []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Ошибка декодирования JSON ответа модели: {e}")
        return []
        
# ... (остальные функции остаются без изменений, просто убедитесь, что они на месте)

# (полный код остальных функций)

if __name__ == "__main__":
    # ... (этот блок без изменений)
