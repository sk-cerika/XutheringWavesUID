import json

import aiofiles

from .player_store import write_player_json
from .resource.RESOURCE_PATH import MAP_PATH, PLAYER_PATH

LIMIT_PATH = MAP_PATH / "1.json"


async def load_limit_user_card():
    if not LIMIT_PATH.exists():
        return []
    async with aiofiles.open(LIMIT_PATH, "r", encoding="UTF-8") as f:
        data = json.loads(await f.read())

    limit_user_path = PLAYER_PATH / "1"
    await write_player_json(limit_user_path / "rawData.json", data)

    return data
