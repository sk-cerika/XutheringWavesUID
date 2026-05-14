import json

import aiofiles

from .resource.RESOURCE_PATH import MAP_PATH, PLAYER_PATH

LIMIT_PATH = MAP_PATH / "1.json"


async def load_limit_user_card():
    if not LIMIT_PATH.exists():
        return []
    async with aiofiles.open(LIMIT_PATH, "r", encoding="UTF-8") as f:
        data = json.loads(await f.read())

    limit_user_path = PLAYER_PATH / "1"
    if not limit_user_path.exists():
        limit_user_path.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(
        limit_user_path / "rawData.json", "w", encoding="UTF-8"
    ) as f:
        await f.write(json.dumps(data, ensure_ascii=False))

    return data
