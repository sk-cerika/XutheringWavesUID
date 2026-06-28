import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe

from ..utils.database.waves_subscribe import WavesSubscribe
from ..utils.resource.RESOURCE_PATH import PLAYER_PATH
from ..utils.player_store import compress_existing_sync

sv_master = SV("联系主人", pm=0)
master_name_ann = "联系主人"

sv_waves_compress = SV("waves压缩数据", pm=0)


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


@sv_waves_compress.on_fullmatch("压缩数据")
async def compress_player_data(bot: Bot, ev: Event):
    await bot.send("[鸣潮] 开始批量压缩存量逐用户数据")
    done, fail, before, after = await asyncio.to_thread(compress_existing_sync, PLAYER_PATH)
    fail_txt = f"（失败 {fail}）" if fail else ""
    if not done:
        return await bot.send(f"[鸣潮] 压缩数据完成，无需转换{fail_txt}")
    ratio = after / before * 100 if before else 0
    await bot.send(
        f"[鸣潮] 压缩数据完成{fail_txt}\n"
        f"压缩前 {_fmt_size(before)} → 压缩后 {_fmt_size(after)}\n"
        f"压缩率 {ratio:.1f}%（省 {100 - ratio:.1f}%）"
    )


@sv_master.on_regex(("^(联系|取消联系)主人$"))
async def rover_sign_result(bot: Bot, ev: Event):

    if "取消" in ev.raw_text:
        option = "关闭"
    else:
        option = "开启"

    if ev.group_id and option == "开启":
        await WavesSubscribe.check_and_update_bot(ev.group_id, ev.bot_id, ev.bot_self_id)

    if option == "关闭":
        await gs_subscribe.delete_subscribe("single", master_name_ann, ev)
    else:
        await gs_subscribe.add_subscribe("single", master_name_ann, ev)

    await bot.send(f"[联系主人] 已{option}订阅!")
