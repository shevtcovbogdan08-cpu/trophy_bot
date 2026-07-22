import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BRAWL_API_KEY = os.getenv("BRAWL_API_KEY")
ROYALE_API_KEY = os.getenv("ROYALE_API_KEY")
CLAN_API_KEY = os.getenv("CLAN_API_KEY")

API_URLS = {
    "Brawl Stars": {
        "url": "https://api.brawlstars.com/v1/players/%23{}",
        "key": BRAWL_API_KEY
    },
    "Clash Royale": {
        "url": "https://api.clashroyale.com/v1/players/%23{}",
        "key": ROYALE_API_KEY
    },
    "Clash of Clans": {
        "url": "https://api.clashofclans.com/v1/players/%23{}",
        "key": CLAN_API_KEY
    }
}

if not all([BOT_TOKEN, BRAWL_API_KEY, ROYALE_API_KEY, CLAN_API_KEY]):
    raise ValueError("Не все переменные окружения заданы! Проверьте .env файл.")