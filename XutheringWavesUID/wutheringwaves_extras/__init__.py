"""XutheringWavesUID 非侵入式扩展模块。

把不属于核心查询/资源/配置的、可独立启停的"附加能力"集中放在这里，
避免侵入 ``wutheringwaves_gachalog`` / ``wutheringwaves_charinfo`` 等已有模块。

每个子模块在导入时自行注册 SV / scheduler，不再依赖外层显式调用。
"""

from . import at_view_gacha  # noqa: F401  功能1: @他人查看抽卡记录
from . import scheduled_refresh  # noqa: F401  功能2: 定时刷新所有有 cookie 用户的面板
from . import auto_refresh_on_view  # noqa: F401  功能3: ww<角色名>面板 自动先刷新再查看
