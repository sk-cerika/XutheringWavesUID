from typing import Union
from datetime import datetime, timezone, timedelta

from gsuid_core.models import Event
from gsuid_core.logger import logger

from ..utils.hint import error_reply
from ..utils.util import hide_uid, get_hide_uid_pref
from ..utils.waves_api import waves_api
from ..utils.error_reply import WAVES_CODE_102
from ..utils.api.model import ChallengeArea, AccountBaseInfo
from ..wutheringwaves_config import WutheringWavesConfig, PREFIX
from ..utils.name_convert import char_name_to_char_id
from ..utils.ascension.char import get_char_detail
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    render_html,
    get_image_b64_with_cache,
    get_footer_b64,
)
from ..utils.resource.RESOURCE_PATH import waves_templates, CHALLENGE_PATH
from ..utils.image import (
    pil_to_b64,
    img_to_b64,
    get_waves_bg,
    get_event_avatar,
    get_square_avatar_path,
    CHAIN_COLOR,
)
from ..utils.char_info_utils import get_all_roleid_detail_info, lookup_chain
from .draw_challenge_card_pil import (
    draw_challenge_img as draw_challenge_img_pil,
    ERROR_UNLOCK,
    ERROR_OPEN,
)


async def draw_challenge_img(ev: Event, uid: str, user_id: str) -> Union[bytes, str]:
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await draw_challenge_img_pil(ev, uid, user_id)

    try:
        _, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
        if not ck:
            return error_reply(WAVES_CODE_102)
        user_pref = await get_hide_uid_pref(uid, user_id, ev.bot_id)

        # 全息数据
        challenge_data = await waves_api.get_challenge_data(uid, ck)
        if not challenge_data.success:
            return challenge_data.throw_msg()

        challenge_data = ChallengeArea.model_validate(challenge_data.data)
        if not challenge_data.isUnlock:
            return ERROR_UNLOCK

        if not challenge_data.open:
            return ERROR_OPEN

        # 账户数据
        account_info_res = await waves_api.get_base_info(uid, ck)
        if not account_info_res.success:
            return account_info_res.throw_msg()
        if not account_info_res.data:
            return f"用户未展示数据, 请尝试【{PREFIX}登录】"
        account_info = AccountBaseInfo.model_validate(account_info_res.data)

        # 准备渲染数据
        avatar = await get_event_avatar(ev)
        avatar_url = pil_to_b64(avatar, quality=75)

        # 获取角色详细信息（用于获取共鸣链）
        role_detail_info_map = await get_all_roleid_detail_info(uid)

        # 构建挑战数据
        challenges_list = []
        for _challenge in reversed(challenge_data.challengeInfo.values()):
            if not _challenge:
                continue

            # Boss 信息
            boss = _challenge[0]
            boss_icon_b64 = await get_image_b64_with_cache(boss.bossIconUrl, CHALLENGE_PATH, quality=75, cover_size=(130, 100)) if boss.bossIconUrl else ""

            # 通关记录（取最后一个有角色的记录）
            best_record = None
            for _temp in reversed(_challenge):
                if _temp.roles:
                    best_record = _temp
                    break

            roles_data = []
            pass_time = None
            boss_difficulty = 1
            boss_level = 60

            if best_record:
                pass_time = str(timedelta(seconds=best_record.passTime))
                boss_difficulty = best_record.difficulty
                boss_level = best_record.bossLevel

                for _role in best_record.roles:
                    # 通过角色名获取角色ID
                    role_id = char_name_to_char_id(_role.roleName)

                    # 获取角色星级（从本地数据）
                    star_level = 5  # 默认5星
                    if role_id:
                        try:
                            char_detail = get_char_detail(role_id, _role.roleLevel)
                            star_level = char_detail.starLevel
                        except Exception:
                            pass

                    chain_num, chain_name = lookup_chain(role_detail_info_map, role_id)

                    # 使用本地头像（和PIL版本一致）
                    role_icon_b64 = img_to_b64(get_square_avatar_path(role_id), quality=75, bake=True, cover_size=(128, 128))

                    roles_data.append({
                        "id": role_id or "",
                        "level": _role.roleLevel,
                        "star": star_level,
                        "chain_num": chain_num,
                        "chain_name": chain_name,
                        "icon_url": role_icon_b64,
                    })

            challenges_list.append({
                "boss_name": boss.bossName,
                "boss_level": boss_level,
                "boss_difficulty": boss_difficulty,
                "max_difficulty": len(_challenge),
                "boss_icon_url": boss_icon_b64,
                "pass_time": pass_time,
                "roles": roles_data,
            })

        bg_img = get_waves_bg(bg = "bg8", crop=False)
        bg_url = pil_to_b64(bg_img, quality=75)

        # 当前日期
        current_date = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

        # 将 CHAIN_COLOR 转换为 RGB 字符串格式
        chain_colors = {i: f"rgba({r}, {g}, {b}, 0.8)" for i, (r, g, b) in CHAIN_COLOR.items()}

        context = {
            "user_name": account_info.name,
            "user_id": hide_uid(account_info.id, user_pref=user_pref),
            "level": account_info.level,
            "world_level": account_info.worldLevel,
            "show_stats": account_info.is_full,
            "avatar_url": avatar_url,
            "current_date": current_date,
            "challenges": challenges_list,
            "chain_colors": chain_colors,
            "footer_b64": get_footer_b64(footer_type="white") or "",
            "bg_url": bg_url,
        }

        logger.debug("[鸣潮·全息渲染] 准备 HTML 渲染")
        img_bytes = await render_html(waves_templates, "abyss/challenge_card.html", context)
        if img_bytes:
            return img_bytes
        else:
            logger.warning("[鸣潮·全息渲染] Playwright 返回空, 回退到 PIL")
            return await draw_challenge_img_pil(ev, uid, user_id)

    except Exception as e:
        logger.exception(f"[鸣潮·全息渲染] HTML 失败: {e}")
        return await draw_challenge_img_pil(ev, uid, user_id)
