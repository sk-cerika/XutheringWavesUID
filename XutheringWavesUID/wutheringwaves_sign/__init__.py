from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.at_help import ruser_id, is_intl_uid, intl_unavailable_msg
from ..utils.error_reply import ERROR_CODE, WAVES_CODE_102
from ..utils.database.models import WavesBind
from .draw_sign_calendar import draw_sign_calendar

waves_sign_calendar = SV("waves签到日历")


@waves_sign_calendar.on_fullmatch(
    (
        "签到日历",
        "签到记录",
        "qdjl",
    ),
    block=True,
)
async def send_sign_calendar(bot: Bot, ev: Event):
    await bot.logger.info(f"[鸣潮·签到] 开始执行[签到日历]: {ruser_id(ev)}")
    uid = await WavesBind.get_uid_by_game(ruser_id(ev), ev.bot_id)
    if not uid:
        # 强需要登录的功能, uid 缺失直接报 102 (登录提示), 避免用户绑定 uid 后再被告知"还要登录"
        return await bot.send(ERROR_CODE[WAVES_CODE_102])
    if is_intl_uid(uid):
        return await bot.send(intl_unavailable_msg(uid))
    return await bot.send(await draw_sign_calendar(uid, ev))
