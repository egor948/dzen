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
import time

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

# ================== Hugging Face API ==================
HF_API_TOKEN = os.environ.get("HF_API_TOKEN")
if not HF_API_TOKEN:
    raise ValueError("HF_API_TOKEN не задан в секретах GitHub!")

# Выбираем мощную модель для генерации текста
MODEL_ID = "mistralai/Mixtral-8x7B-Instruct-v0.1"
API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"


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


def ask_hf_to_write_article(text_digest):
    """Отправляет дайджест новостей в Hugging Face и просит сгенерировать статью."""
    print(f"Отправка запроса в Hugging Face модель: {MODEL_ID}...")
    
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    
    prompt = f"""
Ты — профессиональный спортивный журналист. Проанализируй новости ниже и напиши на их основе одну цельную, интересную статью для Яндекс.Дзен. Придумай яркий заголовок (на первой строке), затем напиши саму статью. Игнорируй рекламу и личные мнения.

НОВОСТИ:
---
{text_digest}
---
СТАТЬЯ:
"""
    
    data = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 512,
            "temperature": 0.7,
            "repetition_penalty": 1.1,
        }
    }

    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers=headers, json=data, timeout=180)

            if response.status_code == 200:
                result = response.json()
                full_text = result[0]['generated_text']
                generated_article = full_text.replace(prompt, "").strip()
                print("Ответ от Hugging Face успешно получен.")
                return generated_article
            elif response.status_code == 503:
                wait_time = int(response.json().get("estimated_time", 20))
                print(f"Модель загружается. Повторная попытка через {wait_time} секунд...")
                time.sleep(wait_time)
                continue
            else:
                print(f"Ошибка от Hugging Face API ({response.status_code}): {response.text}")
                return None

        except reque
