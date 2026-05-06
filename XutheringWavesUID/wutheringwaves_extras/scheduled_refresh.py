"""功能 2：定时为所有有 cookie 的用户批量刷新角色面板。

设计：
- 配置项 ``WavesScheduledRefreshPanel`` (开关，默认关) +
  ``WavesScheduledRefreshTime`` ([时, 分]，默认 ["4","0"])，格式与 ``ResourceDownloadTime`` 对齐。
- 复用 ``utils.refresh_char_detail.refresh_char`` 作为单用户刷新核心；
  复用 ``utils.refresh_char_detail.semaphore_manager`` 作并发盖板（默认 ``RefreshCardConcurrency`` = 10）。
- ``refresh_char`` 仅依赖 ``ev.bot_id`` 与 ``ev.sender``；定时场景没有真 Event，
  用 ``SimpleNamespace`` 构造最小 mock。
- ``WavesUser.get_waves_all_user`` 已经是"status 正常 + cookie 非空"的全量入口，直接用。
- 模块导入即根据配置开关决定是否注册 cron 任务，**不**重启不生效（与 ``ResourceDownloadTime`` 一致）。
- 同时提供一个 ``pm=1`` 主人手动触发命令 ``ww刷新全部用户面板``，用于调试和手动补刷。
"""

import random
import asyncio
from types import SimpleNamespace
from typing import Tuple

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.aps import scheduler
from gsuid_core.models import Event
from gsuid_core.logger import logger

from ..utils.refresh_char_detail import refresh_char, semaphore_manager
from ..utils.database.models import WavesUser
from ..wutheringwaves_config import WutheringWavesConfig


def _make_mock_ev(bot_id: str):
    """构造最小可用 ev mock 喂给 ``refresh_char``。

    源代码仅访问 ``ev.bot_id``（``utils/refresh_char_detail.py:330``）和
    ``ev.sender``（同文件 462 行，``(ev.sender or {}).get("avatar")``）。
    给一个空 dict 即可，下游有 ``startswith("http")`` 兜底转空串。
    """
    return SimpleNamespace(bot_id=bot_id, sender={})


async def refresh_one_user(
    uid: str, user_id: str, bot_id: str, cookie: str
) -> Tuple[bool, str]:
    """刷新单个用户的全部角色面板。返回 (success, msg)。"""
    try:
        ev_mock = _make_mock_ev(bot_id)
        result = await refresh_char(
            ev_mock,  # type: ignore[arg-type]  仅访问 bot_id/sender
            uid,
            user_id,
            ck=cookie,
            is_self_ck=True,
            refresh_type="all",
        )
        # refresh_char 失败时返回错误字符串，成功返回 List[dict]
        if isinstance(result, str):
            return False, result
        return True, f"refreshed {len(result)} chars"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def refresh_all_users() -> Tuple[int, int, int]:
    """批量刷新所有 status 正常 + cookie 非空的用户。

    返回 (total, ok, fail)。
    """
    users = await WavesUser.get_waves_all_user()
    sem = await semaphore_manager.get_semaphore()

    async def _bounded(u):
        async with sem:
            return await refresh_one_user(u.uid, u.user_id, u.bot_id, u.cookie)

    results = await asyncio.gather(
        *[_bounded(u) for u in users], return_exceptions=True
    )
    ok = 0
    fail_msgs = []
    for r in results:
        if isinstance(r, tuple) and r[0]:
            ok += 1
        else:
            fail_msgs.append(str(r))
    fail = len(results) - ok
    logger.info(f"[鸣潮·定时刷面板] 完成 总数={len(results)} 成功={ok} 失败={fail}")
    if fail_msgs:
        # 失败原因可能很多重复（如全员同一接口故障），只打印前 5 条
        for msg in fail_msgs[:5]:
            logger.warning(f"[鸣潮·定时刷面板] 失败样本: {msg}")
    return len(results), ok, fail


# ===== Scheduler 注册 =====
# 仿 wutheringwaves_resource/__init__.py:107-114 的注册方式

_enabled = bool(WutheringWavesConfig.get_config("WavesScheduledRefreshPanel").data)
_sched_time = WutheringWavesConfig.get_config("WavesScheduledRefreshTime").data

if _enabled and _sched_time and len(_sched_time) == 2:
    try:
        _hour = int(_sched_time[0])
        _minute = int(_sched_time[1])
    except (TypeError, ValueError):
        _hour = -1
        _minute = -1

    if 0 <= _hour < 24 and 0 <= _minute < 60:

        async def auto_refresh_panel():
            # 0~1 小时随机抖动，避免多 bot 同 host 同时打 API
            delay = random.randint(0, 3600)
            if delay:
                await asyncio.sleep(delay)
            logger.info("[鸣潮·定时刷面板] 开始执行")
            await refresh_all_users()

        scheduler.add_job(
            auto_refresh_panel,
            "cron",
            id="ww_scheduled_refresh_panel",
            hour=_hour,
            minute=_minute,
        )
        logger.info(f"[鸣潮·定时刷面板] 已注册定时任务: {_hour:02d}:{_minute:02d}")
    else:
        logger.warning(
            f"[鸣潮·定时刷面板] 时间配置异常 hour={_sched_time[0]} minute={_sched_time[1]}，跳过注册"
        )
elif _enabled:
    logger.warning("[鸣潮·定时刷面板] 已开启但时间配置缺失或格式错误，跳过注册")


# ===== 主人手动触发命令 =====

sv_manual_refresh = SV("waves手动批量刷面板", pm=1)


@sv_manual_refresh.on_fullmatch(("刷新全部用户面板", "全部刷新面板"))
async def manual_refresh_handler(bot: Bot, ev: Event):
    await bot.send("[鸣潮] 开始批量刷新所有已登录用户面板，请稍候...")
    total, ok, fail = await refresh_all_users()
    await bot.send(
        f"[鸣潮] 批量刷新完成：总数={total} 成功={ok} 失败={fail}\n详细错误请查看日志"
    )
