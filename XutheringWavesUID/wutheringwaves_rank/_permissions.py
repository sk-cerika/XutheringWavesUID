"""rank 公共：token 限制配置 + 活跃用户过滤。

原本在 darw_rank_card / draw_rank_list_card / draw_gacha_rank_card 各复制一份。
"""
import time
import asyncio
from typing import Dict, List, Optional, Tuple

from ..utils.database.models import WavesBind, WavesUser, WavesUserActivity
from ..wutheringwaves_config import WutheringWavesConfig


async def get_rank_token_condition(ev) -> Tuple[bool, Dict[Tuple[str, str], str]]:
    """检查排行的 token 权限配置。

    返回 (flag, wavesTokenUsersMap):
    - flag=True 表示当前群/全局开启了"登录后排行"，需用 wavesTokenUsersMap 过滤
    - wavesTokenUsersMap: (user_id, uid) -> cookie
    """
    tokenLimitFlag = False
    wavesTokenUsersMap: Dict[Tuple[str, str], str] = {}

    WavesRankNoLimitGroup = WutheringWavesConfig.get_config("WavesRankNoLimitGroup").data
    if ev.group_id and WavesRankNoLimitGroup and ev.group_id in WavesRankNoLimitGroup:
        return tokenLimitFlag, wavesTokenUsersMap

    WavesRankUseTokenGroup = WutheringWavesConfig.get_config("WavesRankUseTokenGroup").data
    RankUseToken = WutheringWavesConfig.get_config("RankUseToken").data
    if (ev.group_id and WavesRankUseTokenGroup and ev.group_id in WavesRankUseTokenGroup) or RankUseToken:
        wavesTokenUsers = await WavesUser.get_waves_all_user()
        wavesTokenUsersMap = {(w.user_id, w.uid): w.cookie for w in wavesTokenUsers}
        tokenLimitFlag = True

    return tokenLimitFlag, wavesTokenUsersMap


async def filter_active_group_users(
    users: List[WavesBind],
    bot_id: str,
    bot_self_id: Optional[str] = None,
) -> List[WavesBind]:
    """筛掉超过 ActiveUserDays 天没有活动记录的用户。"""
    active_days = WutheringWavesConfig.get_config("ActiveUserDays").data
    if not users or not active_days:
        return users

    fallback_platform = bot_id
    fallback_bot_self_id = bot_self_id or ""
    user_pairs = {
        (user.user_id, user.bot_id or fallback_platform, fallback_bot_self_id)
        for user in users
        if user.user_id
    }
    if not user_pairs:
        return []

    semaphore = asyncio.Semaphore(50)

    async def check(user_id: str, platform: str, check_bot_self_id: str):
        async with semaphore:
            try:
                last_active_time = await WavesUserActivity.get_user_last_active_time(
                    user_id, platform, check_bot_self_id
                )
                current_time = int(time.time())
                threshold_time = current_time - (active_days * 24 * 60 * 60)
                is_active = last_active_time is not None and last_active_time >= threshold_time
            except Exception:
                is_active = False
            return user_id, is_active

    results = await asyncio.gather(
        *(check(uid, plat, sid) for uid, plat, sid in user_pairs)
    )
    active_user_ids = {uid for uid, is_active in results if is_active}
    return [user for user in users if user.user_id in active_user_ids]
