from gsuid_core.status.plugin_status import register_status

from ..utils.image import get_ICON
from ..utils.database.models import WavesBind, WavesUser
from ..wutheringwaves_config import WutheringWavesConfig


async def get_user_num():
    datas = await WavesUser.get_waves_all_user()
    return len(datas)


async def get_add_num():
    datas = await WavesBind.get_all_data()
    # 仅统计鸣潮绑定行 (uid 非空); 战双 pgr 绑定不计入。
    return sum(1 for d in datas if getattr(d, "uid", None))


async def get_active_user_num():
    active_days = WutheringWavesConfig.get_config("ActiveUserDays").data
    count = await WavesUser.get_active_user_count(active_days)
    return count


register_status(
    get_ICON(),
    "XutheringWavesUID",
    {
        "绑定UID": get_add_num,
        "登录账号": get_user_num,
        "活跃账号数": get_active_user_num,
    },
)
