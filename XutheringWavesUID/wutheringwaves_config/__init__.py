from gsuid_core.sv import SV, get_plugin_available_prefix
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .set_config import set_waves_user_value
from .wutheringwaves_config import WutheringWavesConfig, ShowConfig
from ..utils.constants import WAVES_GAME_ID
from ..utils.database.models import WavesBind, WavesLangSettings, WavesUser
from ..utils.util import get_hide_uid_pref, hide_uid


sv_self_config = SV("waves配置", priority=3)


PREFIX = get_plugin_available_prefix("XutheringWavesUID")


async def _say(bot: Bot, at_sender: bool, msg: str):
    """统一处理 at_sender 时前导空格的小约定; 仅适用于纯字符串消息。"""
    return await bot.send((" " if at_sender else "") + msg, at_sender)


async def _ensure_waves_user_row(bot: Bot, ev: Event, uid: str, at_sender: bool) -> bool:
    """体力背景 / 面板图 共用前置: WavesUser 必须有该 uid 的行才允许写偏好。

    无行时已经把 102 提示发出去, 调用方拿到 False 直接 return 即可。
    error_reply 反向依赖 wutheringwaves_config.PREFIX, 顶层 import 会环回, 故 lazy。
    """
    waves_user = await WavesUser.select_waves_user(
        uid, ev.user_id, ev.bot_id, game_id=WAVES_GAME_ID
    )
    if waves_user:
        return True
    from ..utils.error_reply import ERROR_CODE, WAVES_CODE_102

    msg = f"当前特征码：{hide_uid(uid)}\n{ERROR_CODE[WAVES_CODE_102].rstrip(chr(10))}"
    await _say(bot, at_sender, msg)
    return False


async def _ensure_group_admin(bot: Bot, ev: Event, at_sender: bool, feature: str) -> bool:
    """群排行 / 排除攻略 / 抽卡条件 共用前置: 必须群聊 + 群管理。"""
    if ev.user_pm > 3:
        await _say(bot, at_sender, f"[鸣潮] {feature}设置需要群管理才可设置")
        return False
    if not ev.group_id:
        await _say(bot, at_sender, "[鸣潮] 请使用群聊进行设置")
        return False
    return True


@sv_self_config.on_prefix("设置", block=True)
async def send_config_ev(bot: Bot, ev: Event):
    at_sender = True if ev.group_id else False

    # 语言设置不需要绑定uid
    if "语言" in ev.text or "語言" in ev.text:
        if not WutheringWavesConfig.get_config("EnableLocalization").data:
            return await _say(bot, at_sender, "[鸣潮] 多语言本地化未启用，请先在配置中开启【启用多语言本地化】")
        VALID_LANGS = {"chs", "cht", "en", "jp", "kr"}
        lang = ev.text.replace("语言", "").replace("語言", "").strip().lower()
        if lang not in VALID_LANGS:
            return await _say(bot, at_sender, f"[鸣潮] 语言设置参数无效\n可选: {', '.join(sorted(VALID_LANGS))}")
        db_value = "" if lang == "chs" else lang
        await WavesLangSettings.set_lang(ev.user_id, db_value)
        return await _say(bot, at_sender, f"[鸣潮] 语言已设置为 {lang}")

    uid = await WavesBind.get_uid_by_game(ev.user_id, ev.bot_id)
    if uid is None:
        return await _say(bot, at_sender, f"您还未绑定鸣潮特征码, 请使用【{PREFIX}绑定uid】 完成绑定！")

    if "体力背景" in ev.text:
        if not await _ensure_waves_user_row(bot, ev, uid, at_sender):
            return
        func = "体力背景"
        value = ev.text.replace("体力背景", "").strip()
        # if not value:
        #     char_name = ""
        # char_name = alias_to_char_name(value)
        # im = await set_waves_user_value(ev, func, uid, char_name)
        im = await set_waves_user_value(ev, func, uid, value)
    elif "隐藏uid" in ev.text.lower():
        if not await _ensure_waves_user_row(bot, ev, uid, at_sender):
            return
        # 设置隐藏UID → on; 设置取消隐藏UID → off
        value = "off" if "取消" in ev.text else "on"
        im = await set_waves_user_value(ev, "隐藏UID", uid, value)
    elif "面板图" in ev.text:
        import re
        from ..utils import panel_card_pref
        from ..wutheringwaves_charinfo import card_hash_index
        from ..wutheringwaves_charinfo.card_utils import get_char_id_and_name

        m = re.match(r"^(.+?)面板图\s*(?P<hash_id>[a-zA-Z0-9]*)\s*$", ev.text)
        if not m:
            return await _say(bot, at_sender, "格式错误，正确格式: 设置{角色名}面板图{ID}")
        char_input = m.group(1).strip()
        hash_id = m.group("hash_id").strip()

        if not await _ensure_waves_user_row(bot, ev, uid, at_sender):
            return

        # 性别消歧 + alias 归一一次完成 (内部即过别名表 / i18n / 严格子串)。
        # 主角的 pin 走 element 长名 (1501/1502 共用"漂泊者·衍射"), pair 间不共享。
        resolved_char_id, resolved_char_name, char_err = get_char_id_and_name(char_input)
        if char_err or not resolved_char_id:
            return await _say(bot, at_sender, char_err or "未找到指定角色，请检查输入！")
        pin_key = panel_card_pref.pair_pin_key(resolved_char_id, resolved_char_name)

        if not hash_id:
            cleared = panel_card_pref.clear_pin(uid, pin_key)
            return await _say(
                bot, at_sender,
                f"已清除【{pin_key}】的面板图绑定" if cleared else f"角色【{pin_key}】未设置过面板图绑定",
            )

        if not card_hash_index.is_valid_hash(hash_id):
            return await _say(bot, at_sender, "面板图ID格式错误，ID 显示在面板图右上角")

        if card_hash_index.lookup_in_pair("card", str(resolved_char_id), hash_id) is None:
            return await _say(bot, at_sender, f"未找到角色【{pin_key}】id 为【{hash_id}】的面板图！")

        panel_card_pref.set_pin(uid, pin_key, hash_id)
        masked_uid = hide_uid(
            uid,
            user_pref=await get_hide_uid_pref(uid, ev.user_id, ev.bot_id),
        )
        return await _say(
            bot, at_sender,
            f"设置成功!\n特征码[{masked_uid}]\n角色【{pin_key}】面板图已绑定到 id【{hash_id}】",
        )
    elif "群排行" in ev.text:
        if not await _ensure_group_admin(bot, ev, at_sender, "群排行"):
            return

        WavesRankUseTokenGroup = set(WutheringWavesConfig.get_config("WavesRankUseTokenGroup").data)
        WavesRankNoLimitGroup = set(WutheringWavesConfig.get_config("WavesRankNoLimitGroup").data)

        if "1" in ev.text:
            # 设置为 无限制
            WavesRankNoLimitGroup.add(ev.group_id)
            # 删除token限制
            WavesRankUseTokenGroup.discard(ev.group_id)
            msg = f"[鸣潮] 【{ev.group_id}】群排行已设置为[无限制上榜]"
        elif "2" in ev.text:
            # 设置为 token限制
            WavesRankUseTokenGroup.add(ev.group_id)
            # 删除无限制
            WavesRankNoLimitGroup.discard(ev.group_id)
            msg = f"[鸣潮] 群【{ev.group_id}】群排行已设置为[登录后上榜]"
        else:
            return await _say(bot, at_sender, "[鸣潮] 群排行设置参数失效\n1.无限制上榜\n2.登录后上榜")

        WutheringWavesConfig.set_config("WavesRankUseTokenGroup", list(WavesRankUseTokenGroup))
        WutheringWavesConfig.set_config("WavesRankNoLimitGroup", list(WavesRankNoLimitGroup))
        return await _say(bot, at_sender, msg)

    elif "排除攻略" in ev.text:
        if not await _ensure_group_admin(bot, ev, at_sender, "排除攻略"):
            return

        from .guide_config import (
            load_guide_config,
            save_guide_config,
            parse_provider_names,
        )

        # 提取攻略提供方名称
        provider_text = ev.text.replace("排除攻略", "").strip()

        guide_config = load_guide_config()

        if not provider_text:
            # 清空当前群的排除设置
            if ev.group_id in guide_config:
                del guide_config[ev.group_id]
                save_guide_config(guide_config)
            return await _say(bot, at_sender, f"[鸣潮] 群【{ev.group_id}】已清空排除攻略设置")

        # 解析提供方名称
        providers = parse_provider_names(provider_text)
        if not providers:
            return await _say(bot, at_sender, "[鸣潮] 未识别到有效的攻略提供方名称")

        # 保存配置
        guide_config[ev.group_id] = providers
        save_guide_config(guide_config)

        return await _say(
            bot, at_sender,
            f"[鸣潮] 群【{ev.group_id}】已设置排除攻略提供方:\n"
            + "\n".join(f"  - {p}" for p in providers),
        )

    elif "抽卡条件" in ev.text:
        if not await _ensure_group_admin(bot, ev, at_sender, "抽卡条件"):
            return

        from .gacha_config import load_gacha_config, save_gacha_config, parse_gacha_min_value

        value_text = ev.text.replace("抽卡条件", "").strip()
        gacha_config = load_gacha_config()

        if not value_text:
            if str(ev.group_id) in gacha_config:
                del gacha_config[str(ev.group_id)]
                save_gacha_config(gacha_config)
            return await _say(bot, at_sender, f"[鸣潮] 群【{ev.group_id}】已清空抽卡条件设置")

        min_pull = parse_gacha_min_value(value_text)
        if min_pull is None:
            return await _say(bot, at_sender, "[鸣潮] 未识别到有效的抽卡阈值")

        gacha_config[str(ev.group_id)] = min_pull
        save_gacha_config(gacha_config)
        return await _say(bot, at_sender, f"[鸣潮] 群【{ev.group_id}】已设置抽卡条件阈值: {min_pull}")
    else:
        return await _say(bot, at_sender, "请输入正确的设置信息...")

    # 体力背景 / 隐藏UID 分支落到这里 (im 为字符串或非字符串响应); 其它分支早就 return 了。
    if isinstance(im, str):
        await _say(bot, at_sender, im.rstrip("\n"))
    else:
        await bot.send(im, at_sender)
