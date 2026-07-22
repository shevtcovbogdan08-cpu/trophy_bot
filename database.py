import aiosqlite

DB_PATH = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER,
                game_name TEXT,
                player_tag TEXT,
                PRIMARY KEY (telegram_id, game_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trophy_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT,
                player_tag TEXT,
                trophies INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_or_update_user(telegram_id: int, game_name: str, player_tag: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (telegram_id, game_name, player_tag) VALUES (?, ?, ?)",
            (telegram_id, game_name, player_tag)
        )
        await db.commit()

async def save_trophy_snapshot(game_name: str, player_tag: str, trophies: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO trophy_history (game_name, player_tag, trophies) VALUES (?, ?, ?)",
            (game_name, player_tag, trophies)
        )
        await db.commit()

async def get_all_unique_players():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT game_name, player_tag FROM users")
        rows = await cursor.fetchall()
        return [(row[0], row[1]) for row in rows]

async def get_trophy_diff_since(game_name: str, player_tag: str, hours: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT trophies, timestamp FROM trophy_history "
            "WHERE game_name = ? AND player_tag = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (game_name, player_tag)
        )
        latest = await cursor.fetchone()
        if not latest:
            return None

        cursor = await db.execute(
            "SELECT trophies, timestamp FROM trophy_history "
            "WHERE game_name = ? AND player_tag = ? "
            "AND timestamp >= datetime('now', ?) "
            "ORDER BY timestamp DESC LIMIT 1",
            (game_name, player_tag, f'-{hours} hours')
        )
        old = await cursor.fetchone()
        if not old:
            return None

        latest_trophies, latest_ts = latest
        old_trophies, old_ts = old
        diff = latest_trophies - old_trophies
        return {
            "diff": diff,
            "latest_trophies": latest_trophies,
            "old_trophies": old_trophies,
            "latest_time": latest_ts,
            "old_time": old_ts
        }