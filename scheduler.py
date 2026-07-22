import logging
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import API_URLS
from database import get_all_unique_players, save_trophy_snapshot

logger = logging.getLogger(__name__)

async def collect_trophies():
    players = await get_all_unique_players()
    if not players:
        logger.info("Нет игроков для сбора данных.")
        return

    async with httpx.AsyncClient(timeout=30.0) as client:
        for game_name, player_tag in players:
            api_info = API_URLS.get(game_name)
            if not api_info:
                logger.warning(f"Нет конфигурации для игры {game_name}, пропускаем.")
                continue

            url = api_info["url"].format(player_tag.replace("#", ""))
            headers = {"Authorization": f"Bearer {api_info['key']}"}

            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                trophies = data.get("trophies")
                if trophies is not None:
                    await save_trophy_snapshot(game_name, player_tag, trophies)
                    logger.info(f"[{game_name}] {player_tag} -> {trophies} трофеев сохранено.")
                else:
                    logger.warning(f"[{game_name}] {player_tag} – поле 'trophies' не найдено в ответе.")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.error(f"API ключ для {game_name} недействителен или истёк.")
                elif e.response.status_code == 404:
                    logger.warning(f"[{game_name}] Игрок с тегом {player_tag} не найден.")
                elif e.response.status_code == 429:
                    logger.warning(f"[{game_name}] Превышен лимит запросов, пропускаем игрока.")
                else:
                    logger.error(f"[{game_name}] Ошибка HTTP {e.response.status_code}: {e}")
            except Exception as e:
                logger.exception(f"[{game_name}] Непредвиденная ошибка при запросе для {player_tag}: {e}")

def setup_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        collect_trophies,
        trigger=IntervalTrigger(minutes=60),
        id="collect_trophies",
        replace_existing=True
    )
    return scheduler