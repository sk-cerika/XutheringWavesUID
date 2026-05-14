from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.hint import error_reply
from ..utils.at_help import ruser_id, is_intl_uid, intl_unavailable_msg
from .draw_role_info import draw_role_img
from .draw_reward_card import draw_reward_img
from ..utils.waves_api import waves_api
from ..utils.error_reply import WAVES_CODE_102, WAVES_CODE_103
from ..utils.database.models import WavesBind

waves_role_info = SV("waves查询信息")


@waves_role_info.on_fullmatch(
    ("查询", "卡片", "kp"),
    block=True,
    to_ai="""查询自己的鸣潮账号总览卡片（等级 / 活跃天数 / 已激活角色数 / 探索进度等基本信息）。

当用户问「我账号怎样 / 卡片 / 看下我的总览」时调用。需绑定 cookie。

Args:
    text: 无需参数，留空即可。
""",
)
async def send_role_info(bot: Bot, ev: Event):
    logger.info("[鸣潮]开始执行[查询信息]")
    user_id = ruser_id(ev)
    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    logger.info(f"[鸣潮][查询信息] user_id: {user_id} UID: {uid}")
    if not uid:
        await bot.send(error_reply(WAVES_CODE_102))
        return
    if is_intl_uid(uid):
        await bot.send(intl_unavailable_msg(uid))
        return

    _, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
    if not ck:
        await bot.send(error_reply(WAVES_CODE_102))
        return

    im = await draw_role_img(uid, ck, ev)
    await bot.send(im)  # type: ignore


@waves_role_info.on_fullmatch(("积分", "伴行", "伴行积分"), block=True)
async def send_score_info(bot: Bot, ev: Event):
    logger.info("[鸣潮]开始执行[伴行积分]")
    user_id = ruser_id(ev)
    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    logger.info(f"[鸣潮][伴行积分] user_id: {user_id} UID: {uid}")
    if not uid:
        await bot.send(error_reply(WAVES_CODE_102))
        return
    if is_intl_uid(uid):
        await bot.send(intl_unavailable_msg(uid))
        return

    is_self_ck, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
    if not ck or not is_self_ck:
        await bot.send(error_reply(WAVES_CODE_102))
        return

    im = await draw_reward_img(uid, ck, ev)
    if im:
        await bot.send(im)  # type: ignore
