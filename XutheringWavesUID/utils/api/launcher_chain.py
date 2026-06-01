"""launcher SDK 高层调用链：从 DB 读凭据 → 走 SDK 拿 PlayerPanelData。

提供给 mr 体力 / ScoreEcho 等多处复用，统一处理凭据续期与回写。

失败路径分类：
- ``maintenance``: 服务端维护中, 直接 bubble up, 不试 auto_login (重试也是徒劳)
- ``expired``: SDK 鉴权环节 (make_oauth_code) 失败, 视为 access_token 失效,
  跑 auto_login + exchange_access_token 续一遍
- ``other``: oauth code 拿到但 launcher 数据查询失败, 不是鉴权问题, bubble up
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from gsuid_core.logger import logger

from ..constants import WAVES_GAME_ID
from ..database.models import WavesUser, WavesUserSdk
from .api_sdk import PlayerPanelData, launcher_sdk

# access_token 提前过期时间, 避免边界时戳擦边过期。
_TOKEN_EXPIRY_GUARD_SEC = 60


async def fetch_launcher_panel(
    user_id: str, bot_id: str, uid: str
) -> Optional[PlayerPanelData]:
    """对指定 launcher SDK uid 拉取 ``PlayerPanelData``。

    自动处理凭据续期：先用现有 ``access_token`` 试一次，过期再用 ``auto_token``
    跑 ``auto_login`` + ``exchange_access_token`` 续登并把新凭据回写。
    """
    waves_user = await WavesUser.select_waves_user(uid, user_id, bot_id, game_id=WAVES_GAME_ID)
    if not waves_user:
        logger.info(f"[鸣潮·启动链] 没有 WavesUser uid={uid} user_id={user_id}")
        return None
    if not waves_user.cookie:
        logger.info(f"[鸣潮·启动链] WavesUser.cookie 为空 uid={uid}")
        return None
    if waves_user.status == "无效":
        logger.info(f"[鸣潮·启动链] WavesUser 已被标记为无效 uid={uid}")
        return None

    sdk_record = await WavesUserSdk.select_record(user_id, bot_id, uid)
    if not sdk_record or not sdk_record.region:
        logger.info(f"[鸣潮·启动链] WavesUserSdk 没有 region 记录 uid={uid}")
        return None

    return await _fetch_with_refresh(
        uid=uid,
        region=sdk_record.region,
        auto_token=waves_user.cookie,
        access_token=waves_user.bat or "",
        bat_expires_at=sdk_record.bat_expires_at,
        device_no=waves_user.did or "",
        user_id=user_id,
        bot_id=bot_id,
    )


async def _query(
    access_token: str,
    *,
    uid: str,
    region: str,
    device_no: str,
) -> Tuple[Optional[PlayerPanelData], str]:
    """跑一遍 oauth code → query_player_panel。

    返回 ``(data, kind)``:
    - ``(panel, "")`` 成功
    - ``(None, "maintenance")`` 服务端维护
    - ``(None, "expired")`` SDK 鉴权失败 (access_token 多半失效)
    - ``(None, "other")`` 其它 (网络异常 / 玩家未展示数据 / launcher 端非鉴权错)
    """
    oc = await launcher_sdk.make_oauth_code(access_token, device_no=device_no)
    if not oc.success:
        if oc.is_server_maintenance:
            return None, "maintenance"
        # SDK 鉴权端点失败基本只可能是 access_token 失效, 走续登路径
        return None, "expired"
    if not oc.data:
        return None, "other"

    panel = await launcher_sdk.query_player_panel(oc.data, uid, region)
    if not panel.success:
        if panel.is_server_maintenance:
            return None, "maintenance"
        return None, "other"
    if not panel.data:
        return None, "other"
    return panel.data, ""


async def _fetch_with_refresh(
    *,
    uid: str,
    region: str,
    auto_token: str,
    access_token: str,
    bat_expires_at: Optional[int],
    device_no: str,
    user_id: str,
    bot_id: str,
) -> Optional[PlayerPanelData]:
    # 已知过期就别 speculative 试, 直接走续登
    now = int(time.time())
    token_known_expired = bool(
        bat_expires_at and now >= bat_expires_at - _TOKEN_EXPIRY_GUARD_SEC
    )

    if access_token and not token_known_expired:
        data, err = await _query(
            access_token, uid=uid, region=region, device_no=device_no
        )
        if data is not None:
            return data
        if err == "maintenance":
            logger.warning(f"[鸣潮·启动链] 服务器维护中, 跳过 uid={uid}")
            return None
        if err != "expired":
            # 非鉴权失败, 续登也救不了, bubble up
            logger.warning(
                f"[鸣潮·启动链] launcher 查询失败 (非鉴权) uid={uid}"
            )
            return None

    # access_token 缺失 / 已过期 / 鉴权拒绝 → 走 auto_login 续登
    login = await launcher_sdk.auto_login(auto_token, device_no=device_no)
    if not login.success or not login.data:
        if login.is_server_maintenance:
            logger.warning(f"[鸣潮·启动链] auto_login 命中维护 uid={uid}")
            return None
        logger.warning(f"[鸣潮·启动链] auto_login 失败 uid={uid} msg={login.msg!r}")
        return None

    tok = await launcher_sdk.exchange_access_token(login.data.code, device_no=device_no)
    if not tok.success or not tok.data:
        logger.warning(f"[鸣潮·启动链] exchange_token 失败 uid={uid} msg={tok.msg!r}")
        return None

    new_auto = login.data.auto_token
    new_access = tok.data.access_token
    new_expires_at = (
        int(time.time()) + tok.data.expires_in
        if tok.data.expires_in and tok.data.expires_in > 0
        else None
    )
    try:
        await WavesUser.update_data_by_data(
            select_data={
                "user_id": user_id,
                "bot_id": bot_id,
                "uid": uid,
                "game_id": WAVES_GAME_ID,
            },
            update_data={"cookie": new_auto, "bat": new_access, "status": ""},
        )
        await WavesUserSdk.update_bat_expires_at(user_id, bot_id, uid, new_expires_at)
    except Exception:
        logger.exception(f"[鸣潮·启动链] 凭据回写失败 uid={uid}")

    data, err = await _query(
        new_access, uid=uid, region=region, device_no=device_no
    )
    if data is None and err == "maintenance":
        logger.warning(f"[鸣潮·启动链] 续登后查询命中维护 uid={uid}")
    return data
