import os
import datetime
from datetime import timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom as minidom
import asyncio
import subprocess

# ====== Настройки ======
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

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

RSS_FILE = "rss.xml"

# ====== Функции ======
async def get_channel_posts():
    all_posts = []
    now = datetime.datetime.utcnow()
    cutoff = now - timedelta(hours=24)

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
        SubElement(item, "title").text = p["text"][:50] + "..."  # короткий заголовок
        SubElement(item, "description").text = p["text"]
        SubElement(item, "pubDate").text = p["date"].strftime("%a, %d %b %Y %H:%M:%S GMT")

    xml_str = xml.dom.minidom.parseString(tostring(rss)).toprettyxml(indent="  ")
    with open(RSS_FILE, "w", encoding="utf-8") as f:
        f.write(xml_str)

def push_changes():
    subprocess.run("git add rss.xml", shell=True, check=False)
    subprocess.run('git commit -m "Auto-update RSS" || echo "No changes"', shell=True, check=False)
    subprocess.run("git push", shell=True, check=False)

# ====== Основной запуск ======
if __name__ == "__main__":
    posts = asyncio.run(get_channel_posts())
    if not posts:
        print("Нет новых постов за 24 часа")
    else:
        create_rss(posts)
        push_changes()
        print("✅ RSS создан и отправлен в репозиторий")
