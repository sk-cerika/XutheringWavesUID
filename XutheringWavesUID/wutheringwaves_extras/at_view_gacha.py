"""功能 1：在群聊中 @ 已绑定用户查看其抽卡记录。

设计：
- 注册一个 priority 比 ``wutheringwaves_gachalog`` 默认（5）小的高优先级 SV，
  用与原命令相同的 fullmatch 名集合 + ``block=True`` 抢占同名命令；从而
  原模块的 ``send_gacha_log_card_info`` 不再触发。
- handler 分三条路径：
  1. **自查**（``is_valid_at(ev) == False``）：行为完全等价原版（uid 校验 + ck 校验 + draw_card）。
  2. **@ 别人但 ``WavesAtViewGacha`` 关闭**：静默回退到自查（按 ``ev.user_id``），相当于功能未启用，不影响默认行为。
  3. **@ 别人且开关开启**：依次校验"群聊 → 被 @ 用户已绑定 → 同群 → 被 @ 用户有自有 cookie"，
     全部通过才用被 @ 用户的 uid 渲染抽卡卡片。

完全复用 ``wutheringwaves_gachalog`` 既有的 ``draw_card``、``waves_api`` 与 ``WavesBind``，
不改任何已有业务文件。
"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger

from ..utils.util import hide_uid
from ..utils.at_help import ruser_id, is_valid_at
from ..utils.waves_api import waves_api
from ..utils.error_reply import ERROR_CODE, WAVES_CODE_102, WAVES_CODE_103
from ..utils.database.models import WavesBind
from ..wutheringwaves_config import WutheringWavesConfig
from ..wutheringwaves_gachalog.draw_gachalogs import draw_card

# priority 数值小于 wutheringwaves_gachalog 默认的 5，确保抢占同名 trigger
sv_at_view_gacha = SV("waves@查抽卡记录", priority=2)


async def _self_view(bot: Bot, ev: Event, user_id: str) -> None:
    """自查路径：与原版 ``send_gacha_log_card_info`` 等价。"""
    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        await bot.send(ERROR_CODE[WAVES_CODE_103])
        return
    _, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
    if not ck:
        await bot.send(ERROR_CODE[WAVES_CODE_102])
        return
    im = await draw_card(uid, ev)
    await bot.send(im)


@sv_at_view_gacha.on_fullmatch(
    ("抽卡记录", "查看抽卡记录", "gacha", "ckjl"), block=True
)
async def at_view_gacha_handler(bot: Bot, ev: Event):
    inviter_id = ev.user_id
    target_id = ruser_id(ev)
    is_at = is_valid_at(ev)

    enabled = WutheringWavesConfig.get_config("WavesAtViewGacha").data

    # 自查 / 功能未启用 → 走原版等价路径
    if not is_at or not enabled:
        await _self_view(bot, ev, inviter_id)
        return

    # 以下: @ 别人 且 功能已启用
    if not ev.group_id:
        await bot.send("[鸣潮] @他人查抽卡记录仅支持群聊使用")
        return

    # 取被 @ 用户的绑定记录（含 group_id 字段，用于同群校验）
    target_bind = await WavesBind.select_data(target_id, ev.bot_id)
    if not target_bind or not target_bind.uid:
        await bot.send("[鸣潮] 被 @ 用户未绑定鸣潮特征码")
        return

    # 同群校验：WavesBind.group_id 是 "_" 分隔字符串，必须严格相等比较，
    # 不能用 substring 包含（"123" in "12345" 假阳性）
    bind_groups = [g for g in (target_bind.group_id or "").split("_") if g]
    if ev.group_id not in bind_groups:
        await bot.send("[鸣潮] 仅支持查询同群已绑定的用户")
        return

    # 取被 @ 用户当前主 uid（与该用户名下绑定的鸣潮 uid 一致）
    target_uid = await WavesBind.get_uid_by_game(target_id, ev.bot_id)
    if not target_uid:
        await bot.send("[鸣潮] 被 @ 用户未绑定鸣潮特征码")
        return

    # ck 校验：必须用被 @ 用户自己的 self ck（避免 get_ck_result 拿随机 ck 误判）
    target_ck = await waves_api.get_self_waves_ck(target_uid, target_id, ev.bot_id)
    if not target_ck:
        await bot.send(
            f"[鸣潮] 被 @ 用户 UID{hide_uid(target_uid)} 未登录或登录已失效，无法查看其抽卡记录"
        )
        return

    logger.info(
        f"[鸣潮·@查抽卡] inviter={inviter_id} target={target_id} uid={target_uid} group={ev.group_id}"
    )
    # 临时改写 ev 使 draw_card 内部按被 @ 用户取头像 / 隐藏偏好 / 自身 ck，
    # 调完 finally 还原避免污染外层 hook（user_activity / bot_send）。
    # 详见 utils/image.py:552 get_event_avatar 取头像优先级；ev.sender 清空后会
    # 走 onebot + ev.user_id 兜底分支拿被 @ 用户的 QQ 头像。
    _orig_user_id, _orig_sender, _orig_at = ev.user_id, ev.sender, ev.at
    try:
        ev.user_id = target_id
        ev.sender = {}
        ev.at = ""
        im = await draw_card(target_uid, ev)
    finally:
        ev.user_id, ev.sender, ev.at = _orig_user_id, _orig_sender, _orig_at
    await bot.send(im)
