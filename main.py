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
SESSION_STRING = os.environ.get("SESSION_STRING")  # session string для Telegram

if not API_ID or not API_HASH or not SESSION_STRING:
    raise ValueError("API_ID, API_HASH или SESSION_STRING не заданы!")

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

# ================== Яндекс GPT ==================
YANDEX_FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID")  # ID каталога Яндекс
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY")      # ключ API Яндекс GPT
YANDEX_MODEL = "yandexgpt"

if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
    raise ValueError("YANDEX_FOLDER_ID или YANDEX_API_KEY не заданы!")

# GitHub
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
    cutoff = now - timedelta(hours=24)  # берём посты за последние 24 часа

    async with client:
        for ch in CHANNELS:
            async for msg in client.iter_messages(ch, limit=500):
                if msg.text and msg.date.replace(tzinfo=None) > cutoff:
                    all_posts.append({
                        "text": msg.text,
                        "date": msg.date
                    })
    return all_posts


def ask_yandex_gpt(text):
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/{YANDEX_MODEL}",
        "completionOptions": {"stream": False, "temperature": 0.6},
        "messages": [
            {"role": "system", "text": "Ты умный редактор новостей."},
            {"role": "user", "text": f"""
Проанализируй новости и создай на их основе пост для Яндекс.Дзен. 
Фильтруй личные истории и повторяющиеся каналы. 
Сделай большой объем, интересные абзацы, триггерный заголовок. 

Текст:
{text}
            """}
        ]
    }
    response = requests.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers=headers,
        json=data
    )
    response.raise_for_status()
    return response.json()["result"]["alternatives"][0]["message"]["text"]


def create_rss(content):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Новости из Telegram + Yandex GPT"
    SubElement(channel, "link").text = "https://github.com/egor948/dzen"
    SubElement(channel, "description").text = "Автоматические новости"

    item = SubElement(channel, "item")
    SubElement(item, "title").text = "Главные события за 24 часа"
    SubElement(item, "description").text = content
    SubElement(item, "pubDate").text = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    xml_str = minidom.parseString(tostring(rss)).toprettyxml(indent="  ")
    with open(RSS_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(xml_str)


def push_to_github():
    run_git_command(f'git config user.name "{GITHUB_USER}"')
    run_git_command(f'git config user.email "{GITHUB_EMAIL}"')
    run_git_command(f'git add "{RSS_FILE_PATH}"')
    run_git_command(f'git commit -m "{COMMIT_MESSAGE}" || echo "No changes to commit"')
    run_git_command(f'git push origin {BRANCH}')


# ================= ОСНОВНОЙ ЗАПУСК =================
if __name__ == "__main__":
    posts = asyncio.run(get_channel_posts())
    if not posts:
        print("Нет новых постов за 24 часа")
    else:
        combined_text = "\n\n".join([p["text"] for p in posts])
        try:
            yandex_result = ask_yandex_gpt(combined_text)
            create_rss(yandex_result)
            push_to_github()
            print("✅ Всё готово: RSS создан и выгружен в GitHub")
        except Exception as e:
            print("Ошибка при работе с Yandex GPT:", e)
