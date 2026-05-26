from gsuid_core.models import Event


def ruser_id(ev: Event) -> str:
    from ..wutheringwaves_config.wutheringwaves_config import (
        WutheringWavesConfig,
    )

    AtCheck = WutheringWavesConfig.get_config("AtCheck").data
    if AtCheck and ev.at and ev.at != ev.bot_self_id:
        return ev.at
    return ev.user_id


def is_valid_at(ev: Event) -> bool:
    return ev.user_id != ruser_id(ev)


# 国际服 uid 起始段(2/3/9 开头, >= 2e8); 与 utils.api.requests.WavesApi.is_net 对齐。
def is_intl_uid(uid) -> bool:
    if not uid:
        return False
    try:
        return int(uid) >= 200000000
    except (TypeError, ValueError):
        return False


def intl_unavailable_msg(uid) -> str:
    from .util import hide_uid

    return f"[鸣潮] UID {hide_uid(uid)} 暂不可用"
