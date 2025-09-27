import os
import subprocess
import datetime
from datetime import timedelta
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom as minidom
import asyncio

# ================= НАСТРОЙКИ =================
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")  # session string
GEMINI_KEY = os.environ.get("GEMINI_KEY", "").strip()
PAT = os.environ.get("PAT")  # GitHub Personal Access Token

if not API_ID or not API_HASH or not SESSION_STRING:
    raise ValueError("API_ID, API_HASH или SESSION_STRING не заданы!")

if not GEMINI_KEY:
    raise ValueError("GEMINI_KEY не задан!")

if not PAT:
    raise ValueError("PAT (GitHub token) не задан!")

client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)

CHANNELS = [
    "breakevens",
    "spurstg",
    "bluecityzens",
    "manutd_one",
    "lexusarsenal",
    "sixELCE",
    "astonvillago"
]

MODEL_NAME = "gemini-2.0-flash"

GIT_REPO_PATH = os.getcwd()
RSS_FILE_PATH = os.path.join(GIT_REPO_PATH, "rss.xml")
GITHUB_USER = "GitHub Actions"
GITHUB_EMAIL = "actions@github.com"
BRANCH = "main"
COMMIT_MESSAGE = "Автообновление RSS"
# ===============================================


def run_git_command(command, cwd=GIT_REPO_PATH):
    result = subprocess.run(command, cwd=cwd, text=True, shell=True, capture_output=True)
    if result.returncode != 0:
        print("Ошибка:", result.stderr)
    else:
        print(result.stdout)


async def get_channel_posts():
    all_posts = []
    now = datetime.datetime.utcnow()
    cutoff = now - timedelta(hours=4)

    try:
        async with client:
            for ch in CHANNELS:
                async for msg in client.iter_messages(ch, limit=500):
                    if msg.text and msg.date.replace(tzinfo=None) > cutoff:
                        all_posts.append({
                            "text": msg.text,
                            "date": msg.date
                        })
    except Exception as e:
        print("Ошибка при получении сообщений из Telegram:", e)
    return all_posts


def ask_gemini(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_KEY
    }
    data = {"contents": [{"parts": [{"text": text}]}]}

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
    except Exception as e:
        print("Ошибка при запросе к Gemini:", e)
        return None

    try:
        return response.json()["contents"][0]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        print("Не удалось разобрать ответ Gemini:", e)
        return None


def create_rss(content):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Новости из Telegram + Gemini"
    SubElement(channel, "link").text = "https://github.com/egor948/dzen"
    SubElement(channel, "description").text = "Автоматические новости"

    item = SubElement(channel, "item")
    SubElement(item, "title").text = "Главные события за 4 часа"
    SubElement(item, "description").text = content
    SubElement(item, "pubDate").text = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%
