"""功能 3：发送 ``ww<角色名>面板`` 查询单角色面板时，自动先刷新该角色再渲染。

设计：
- 注册一个 priority=2 (小于 wutheringwaves_charinfo 默认 5) 的高优先级 SV，
  用与 ``send_char_detail_msg2`` (charinfo/__init__.py:572-684) **完全相同**的正则
  + ``block=True`` 抢占同名 trigger。
- handler 三分支：
  1. 边界场景（waves_id / damage / PK / 换装 / 极限 / lead_space / 角色解析失败 / 国际服
     / 未绑定）→ 完全不接管，直接调原 ``send_char_detail_msg2``。
  2. 开关 ``WavesAutoRefreshOnView`` 关闭 → 同上。
  3. 普通"查自己面板"且开关开 → 先尊重 ``RefreshSingleCharInterval`` 冷却，
     未冷却则调 ``refresh_char(refresh_type=[char_id])`` 静默刷新（异常和返回错误字符串
     都吞掉，**不**阻塞查询），刷新成功写冷却缓存避免抖动；最后转 ``send_char_detail_msg2`` 渲染。

完全复用 ``utils/refresh_char_detail.refresh_char``、``draw_refresh_char_card.can_refresh_card``
``set_cache_refresh_card``，以及原查询 handler 本身，不改任何已有业务文件。
"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger

from ..utils.at_help import ruser_id, is_intl_uid
from ..utils.name_resolve import resolve_char
from ..utils.name_convert import char_name_to_char_id
from ..utils.char_info_utils import PATTERN
from ..utils.refresh_char_detail import refresh_char
from ..utils.database.models import WavesBind
from ..utils.resource.constant import SPECIAL_CHAR
from ..wutheringwaves_config import WutheringWavesConfig
from ..wutheringwaves_charinfo import send_char_detail_msg2
from ..wutheringwaves_charinfo.draw_refresh_char_card import (
    can_refresh_card,
    set_cache_refresh_card,
)

# priority 数值小于 wutheringwaves_charinfo 的默认 5，确保抢占同名 trigger
sv_auto_refresh_on_view = SV("waves查面板自动刷新", priority=2)


# 正则必须与 send_char_detail_msg2 (charinfo/__init__.py:572-575) 字字相同，
# 否则会出现"原 handler 命中而新 handler 没命中"的不一致。
_TRIGGER_RE = (
    rf"^(?P<lead_space>\s+)?(?P<waves_id>\d{{9}})?(?P<char>{PATTERN})"
    rf"(?P<query_type>面板|面版|面包|🍞|mb|伤害(?P<damage>(\d+)?))"
    rf"(?P<is_pk>pk|对比|PK|比|比较)?(\s*)?"
    rf"(?P<change_list>((换[^换]*)*)?)"
)


@sv_auto_refresh_on_view.on_regex(_TRIGGER_RE, block=True)
async def auto_refresh_then_view(bot: Bot, ev: Event):
    # 开关关 → 透传给原 handler，0 行为差异
    enabled = WutheringWavesConfig.get_config("WavesAutoRefreshOnView").data
    if not enabled:
        return await send_char_detail_msg2(bot, ev)

    # 边界场景：含 lead_space / 查别人 uid / 伤害计算 / PK / 换装 / 极限
    # 这些场景刷新意义不大或行为复杂，全部跳过自动刷，直接走原 handler
    if ev.regex_dict.get("lead_space"):
        return await send_char_detail_msg2(bot, ev)
    if ev.regex_dict.get("waves_id"):
        return await send_char_detail_msg2(bot, ev)
    if ev.regex_dict.get("damage"):
        return await send_char_detail_msg2(bot, ev)
    if ev.regex_dict.get("is_pk") is not None:
        return await send_char_detail_msg2(bot, ev)
    if ev.regex_dict.get("change_list"):
        return await send_char_detail_msg2(bot, ev)

    char_raw = ev.regex_dict.get("char")
    if not char_raw or not isinstance(char_raw, str):
        return await send_char_detail_msg2(bot, ev)
    if "极限" in char_raw or "limit" in char_raw:
        return await send_char_detail_msg2(bot, ev)

    # 解析角色拿 char_id
    res = resolve_char(char_raw)
    if not res.ok:
        return await send_char_detail_msg2(bot, ev)
    char_id = char_name_to_char_id(res.matched)
    if not char_id or len(char_id) != 4:
        return await send_char_detail_msg2(bot, ev)

    # 解 uid（用 ruser_id 与原 handler 行为对齐）
    user_id = ruser_id(ev)
    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    if not uid or is_intl_uid(uid):
        return await send_char_detail_msg2(bot, ev)

    # 尊重 RefreshSingleCharInterval 冷却
    cd = can_refresh_card(user_id, uid, is_single_refresh=True)
    if cd > 0:
        logger.debug(
            f"[鸣潮·查面板自动刷新] 命中冷却 user={user_id} uid={uid} 剩余={cd}s, 跳过"
        )
        return await send_char_detail_msg2(bot, ev)

    # 漂泊者多形态映射
    refresh_types = SPECIAL_CHAR[char_id] if char_id in SPECIAL_CHAR else [char_id]

    # 静默刷新：异常或返回错误字符串都吞掉，不阻塞查询
    try:
        result = await refresh_char(ev, uid, user_id, refresh_type=refresh_types)
        if isinstance(result, str):
            logger.debug(
                f"[鸣潮·查面板自动刷新] 刷新返回错误 uid={uid} char={char_id}: {result}"
            )
        else:
            # 刷新成功才写冷却，避免短时间多次查询打 API
            set_cache_refresh_card(user_id, uid, is_single_refresh=True)
            logger.info(
                f"[鸣潮·查面板自动刷新] 已刷新 user={user_id} uid={uid} char_id={char_id}"
            )
    except Exception as e:
        logger.warning(
            f"[鸣潮·查面板自动刷新] 异常 uid={uid} char={char_id}: {type(e).__name__}: {e}"
        )

    # 走原查询渲染
    return await send_char_detail_msg2(bot, ev)
