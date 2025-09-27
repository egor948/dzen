import os
import datetime
from datetime import timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom as minidom
import asyncio
import subprocess

# ================= НАСТРОЙКИ =================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")  # session string

if not API_ID or not API_HASH or not SESSION_STRING:
    raise ValueError("API_ID, API_HASH или SESSION_STRING не заданы!")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

CHANNELS = [
    "breakevens",
    "spurstg",
    "bluecityzens",
    "manutd_one",
    "lexusarsenal",
    "sixELCE",
    "astonvillago"
]

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
    cutoff = now - timedelta(hours=24)  # последние 24 часа

    async with client:
        for ch in CHANNELS:
            async for msg in client.iter_messages(ch, limit=500):
                if msg.text and msg.date.replace(tzinfo=None) > cutoff:
                    all_posts.append({
                        "text": msg.text,
                        "date": msg.date
                    })
    return all_posts

def create_rss(posts):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Новости из Telegram"
    SubElement(channel, "link").text = "https://github.com/egor948/dzen"
    SubElement(channel, "description").text = "Автоматические новости"

    for p in posts:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = p["text"][:50] + "..."
        SubElement(item, "description").text = p["text"]
        SubElement(item, "pubDate").text = p["date"].strftime("%a, %d %b %Y %H:%M:%S GMT")

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
        create_rss(posts)
        push_to_github()
        print("✅ Всё готово: RSS создан и выгружен в GitHub")
