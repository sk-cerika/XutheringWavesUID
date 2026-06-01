from typing import Any, List

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.button import WavesButton
from ..utils.database.models import WavesUser, WavesUserSdk
from ..utils.util import hide_uid
from ..wutheringwaves_config import PREFIX


async def _region_suffix(user_id: str, bot_id: str, uid: str) -> str:
    """SDK 登录的 UID 会在 ``WavesUserSdk`` 留区服信息，带括号显示。"""
    try:
        region = await WavesUserSdk.get_region(user_id, bot_id, uid)
    except Exception as e:
        logger.debug(f"[鸣潮·登录成功] 区服查询失败 uid={uid}: {e}")
        return ""
    return f"（{region} 服）" if region else ""


async def login_success_msg(
    bot: Bot,
    ev: Event,
    waves_user: WavesUser,
    role_name: str = "",
):
    buttons: List[Any] = [
        WavesButton("体力", "mr"),
        WavesButton("刷新面板", "刷新面板"),
        WavesButton("深塔", "深塔"),
        WavesButton("冥歌海墟", "冥海"),
    ]

    uid = str(waves_user.uid or "")
    is_sdk_uid = uid.isdigit() and int(uid) >= 200000000

    # 国际服 UID 不走 KuroBBS 面板渲染（auto_token 会被 KuroBBS 视作过期 token，
    # 触发 mark_cookie_invalid 把 launcher 凭据冲掉）。直接走文本 fallback。
    if not is_sdk_uid:
        from ..wutheringwaves_charinfo.draw_refresh_char_card import (
            draw_refresh_char_detail_img,
        )

        msg, _, _ = await draw_refresh_char_detail_img(
            bot, ev, waves_user.user_id, waves_user.uid, buttons
        )
        if isinstance(msg, bytes):
            return await bot.send_option(msg, buttons)

    at_sender = True if ev.group_id else False
    name_tag = f"【{role_name}】" if role_name else ""

    if uid.isdigit() and len(uid) == 9:
        suffix = await _region_suffix(ev.user_id, ev.bot_id, uid)
        masked_uid = hide_uid(uid)
        if suffix:
            text = (
                f"[鸣潮]{name_tag} 已绑定特征码【{masked_uid}】{suffix}\n"
                f"支持查看 {PREFIX}体力。面板相关请使用 {PREFIX}分析帮助"
            )
        else:
            text = (
                f"[鸣潮]{name_tag} 已绑定特征码【{masked_uid}】\n"
                f"发送【{PREFIX}切换】可切换到其他鸣潮特征码"
            )
    else:
        text = "[鸣潮] 登录失败，请稍后重试\n"

    return await bot.send((" " if at_sender else "") + text, at_sender=at_sender)
