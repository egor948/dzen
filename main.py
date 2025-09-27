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

# =========  НАСТРОЙКИ =========
# Telegram через session string
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")  # <- сюда вставляешь строку сессии

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# список каналов
CHANNELS = [
    "breakevens",
    "spurstg",
    "bluecityzens",
    "manutd_one",
    "lexusarsenal",
    "sixELCE",
    "astonvillago"
]

# Gemini (Google AI)
GEMINI_KEY = os.environ.get("GEMINI_KEY")
MODEL_NAME = "gemini-2.0-flash"

# GitHub
GIT_REPO_PATH = r"D:\DISC G\dzen\github\dzen"
RSS_FILE_PATH = r"D:\DISC G\dzen\github\dzen\rss.xml"
GITHUB_USER = "egor948"
GITHUB_EMAIL = "Wifi6030@gmail.com"
BRANCH = "main"
COMMIT_MESSAGE = "Автообновление RSS"
# ===============================================

def run_git_command(command, cwd=GIT_REPO_PATH):
    """Выполняет git-команды"""
    result = subprocess.run(command, cwd=cwd, text=True, shell=True,
                            capture_output=True)
    if result.returncode != 0:
        print("Ошибка:", result.stderr)
    else:
        print(result.stdout)

async def get_channel_posts():
    all_posts = []
    now = datetime.datetime.utcnow()
    cutoff = now - timedelta(hours=4)  # последние 4 часа

    async with client:
        for ch in CHANNELS:
            async for msg in client.iter_messages(ch, limit=500):
                if msg.text and msg.date.replace(tzinfo=None) > cutoff:
                    all_posts.append({"text": msg.text, "date": msg.date})
    return all_posts

def ask_gemini(text):
    """Отправляем запрос в Gemini"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_KEY
    }
    data = {"contents": [{"parts": [{"text": text}]}]}

    try:
        r = requests.post(url, headers=headers, json=data)
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print("Ошибка при запросе к Gemini:", e)
        print("Ответ сервера:", r.text)
        return None

    return r.json()["contents"][0]["parts"][0]["text"]

def create_rss(content):
    """Создание rss.xml"""
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Новости из Telegram + Gemini"
    SubElement(channel, "link").text = "https://github.com/egor948/dzen"
    SubElement(channel, "description").text = "Автоматические новости"

    item = SubElement(channel, "item")
    SubElement(item, "title").text = "Главные события за 4 часа"
    SubElement(item, "description").text = content
    SubElement(item, "pubDate").text = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    xml_str = xml.dom.minidom.parseString(tostring(rss)).toprettyxml(indent="  ")
    with open(RSS_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(xml_str)

def push_to_github():
    """Загружаем в GitHub"""
    run_git_command(f'git config user.name "{GITHUB_USER}"')
    run_git_command(f'git config user.email "{GITHUB_EMAIL}"')
    run_git_command(f'git add "{RSS_FILE_PATH}"')
    run_git_command(f'git commit -m "{COMMIT_MESSAGE}"')
    run_git_command(f'git push origin {BRANCH}')

# ========= ОСНОВНОЙ ЗАПУСК =========
if __name__ == "__main__":
    posts = asyncio.run(get_channel_posts())
    if not posts:
        print("Нет новых постов за 4 часа")
    else:
        combined_text = "\n\n".join([p["text"] for p in posts])
        gpt_result = ask_gemini(combined_text)
        if gpt_result:
            create_rss(gpt_result)
            push_to_github()
            print("✅ Всё готово: RSS создан и выгружен в GitHub")
        else:
            print("Не удалось получить результат от Gemini")
