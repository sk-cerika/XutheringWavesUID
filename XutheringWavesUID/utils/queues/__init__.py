from typing import Any

import httpx

from gsuid_core.logger import logger

from .const import QUEUE_SCORE_RANK, QUEUE_ABYSS_RECORD, QUEUE_SLASH_RECORD, QUEUE_MATRIX_RECORD
from .queues import event_handler, start_dispatcher
from ..api.wwapi import (
    UPLOAD_URL,
    UPLOAD_ABYSS_RECORD_URL,
    UPLOAD_SLASH_RECORD_URL,
    UPLOAD_MATRIX_RECORD_URL,
)


# (queue_name, upload_url, log_label)
_UPLOAD_JOBS = [
    (QUEUE_SCORE_RANK, UPLOAD_URL, "面板"),
    (QUEUE_ABYSS_RECORD, UPLOAD_ABYSS_RECORD_URL, "深渊"),
    (QUEUE_SLASH_RECORD, UPLOAD_SLASH_RECORD_URL, "冥海"),
    (QUEUE_MATRIX_RECORD, UPLOAD_MATRIX_RECORD_URL, "矩阵"),
]


async def _post_upload(item: Any, url: str, label: str) -> None:
    if not item or not isinstance(item, dict):
        return

    from ...wutheringwaves_config import WutheringWavesConfig
    WavesToken = WutheringWavesConfig.get_config("WavesToken").data
    if not WavesToken:
        return

    res = None
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                url,
                json=item,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {WavesToken}",
                },
                timeout=httpx.Timeout(10),
            )
        logger.info(f"[鸣潮·队列] 上传{label}结果: {res.status_code} - {res.text}")
    except Exception as e:
        logger.exception(f"[鸣潮·队列] 上传{label}失败: {res.text if res else ''} {e}")


def _make_handler(queue: str, url: str, label: str):
    async def _handler(item: Any):
        await _post_upload(item, url, label)
    _handler.__name__ = f"send_{queue.removeprefix('waves_')}"
    return _handler


for _queue, _url, _label in _UPLOAD_JOBS:
    event_handler(_queue)(_make_handler(_queue, _url, _label))


def init_queues():
    # 启动任务分发器
    start_dispatcher(daemon=True)
