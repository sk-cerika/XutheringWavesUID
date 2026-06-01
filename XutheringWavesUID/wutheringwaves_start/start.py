from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

from ..wutheringwaves_resource import startup


@on_core_start
async def all_start():
    logger.info("[鸣潮·启动] 启动中...")
    try:
        await startup()
    except Exception as e:
        logger.exception(f"[鸣潮·启动] 启动失败: {e}")
        logger.error("[鸣潮·启动] 启动失败 ❌ 部分功能可能不可用，请查看日志排查")
        return

    logger.success("[鸣潮·启动] 启动完成 ✅")
