from typing import Union
from pathlib import Path
from datetime import datetime, timezone, timedelta

from PIL import Image

from gsuid_core.logger import logger
from gsuid_core.models import Event

from .period import get_slash_period_number
from ..utils.hint import error_reply
from ..utils.util import hide_uid, get_hide_uid_pref
from ..utils.waves_api import waves_api
from ..utils.error_reply import WAVES_CODE_102
from ..utils.api.model import (
    SlashDetail,
    RoleDetailData,
    AccountBaseInfo,
    RoleList,
)
from ..wutheringwaves_config import WutheringWavesConfig, PREFIX
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    render_html,
    get_image_b64_with_cache,
    get_footer_b64,
)
from ..utils.resource.RESOURCE_PATH import waves_templates, SLASH_PATH, PLAYER_PATH
from ..utils.image import (
    pil_to_b64,
    img_to_b64,
    get_waves_bg,
    get_event_avatar,
    get_square_avatar_path,
    CHAIN_COLOR,
)
from ..utils.ascension.char import get_char_model
from ..utils.char_info_utils import get_all_roleid_detail_info
from .draw_slash_card_pil import (
    draw_slash_img as draw_slash_img_pil,
    get_slash_data,
    save_slash_record,
    upload_slash_record,
    SLASH_ERROR_MESSAGE_NO_DATA,
    SLASH_ERROR_MESSAGE_NO_UNLOCK,
    COLOR_QUALITY,
)


async def draw_slash_img(ev: Event, uid: str, user_id: str) -> Union[bytes, str]:
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await draw_slash_img_pil(ev, uid, user_id)

    TEXT_PATH = Path(__file__).parent / "texture2d"

    try:
        is_self_ck, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
        if not ck:
            return error_reply(WAVES_CODE_102)
        user_pref = await get_hide_uid_pref(uid, user_id, ev.bot_id)

        command = ev.command
        text = ev.text.strip()
        challengeIds = [7, 8, 9, 10, 11, 12] if is_self_ck else [12]
        if "无尽" in text or "无尽" in command or "wj" in command or "wj" in text:
            challengeIds = [12]
        elif "禁忌" in text or "禁忌" in command:
            challengeIds = [1, 2, 3, 4, 5, 6]
        elif text.isdigit() and 1 <= int(text) <= 12:
            challengeIds = [int(text)]
        else:
            text = text.replace("层", "")
            if text.isdigit() and 1 <= int(text) <= 12:
                challengeIds = [int(text)]

        if not is_self_ck:
            challengeIds = [12]

        # 冥海数据
        slash_detail: Union[SlashDetail, str] = await get_slash_data(uid, ck, is_self_ck)
        if isinstance(slash_detail, str):
            return slash_detail

        # check 冥海数据
        if not is_self_ck and not slash_detail.isUnlock:
            return SLASH_ERROR_MESSAGE_NO_UNLOCK

        owned_challenge_ids = [
            challenge.challengeId
            for difficulty in slash_detail.difficultyList
            for challenge in difficulty.challengeList
            if len(challenge.halfList) > 0
        ]
        if len(owned_challenge_ids) == 0:
            return SLASH_ERROR_MESSAGE_NO_DATA

        query_challenge_ids = []
        for challenge_id in challengeIds:
            if challenge_id not in owned_challenge_ids:
                continue
            query_challenge_ids.append(challenge_id)

        if len(query_challenge_ids) == 0:
            return SLASH_ERROR_MESSAGE_NO_DATA

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

        # 根据面板数据获取详细信息
        role_detail_info_map = await get_all_roleid_detail_info(uid)
        role_detail_info_map = role_detail_info_map if role_detail_info_map else {}

        # 获取角色信息列表（用于获取角色等级）
        role_info_res = await waves_api.get_role_info(uid, ck)
        role_info_list = []
        if role_info_res.success and role_info_res.data:
            try:
                role_info = RoleList.model_validate(role_info_res.data)
                role_info_list = role_info.roleList
            except Exception:
                pass

        # 构建挑战数据
        challenges_data = []
        for difficulty in reversed(slash_detail.difficultyList):
            # 加载难度背景
            difficulty_bg = Image.open(TEXT_PATH / f"difficulty_{difficulty.difficulty}.png")
            difficulty_bg_url = pil_to_b64(difficulty_bg, quality=75)

            for challenge in difficulty.challengeList:
                if challenge.challengeId not in query_challenge_ids:
                    continue

                if not challenge.halfList:
                    continue

                # 加载分数背景
                rank = challenge.get_rank()
                score_bg = Image.open(TEXT_PATH / f"score_{rank}.png")
                score_bg_url = pil_to_b64(score_bg, quality=75)

                # 构建半场数据
                half_list = []
                for half_index, slash_half in enumerate(challenge.halfList):
                    team_name = "队伍一" if half_index == 0 else "队伍二"

                    # Buff 数据
                    buff_icon_b64 = await get_image_b64_with_cache(slash_half.buffIcon, SLASH_PATH, quality=75, cover_size=(100, 100)) if slash_half.buffIcon else ""
                    buff_quality = slash_half.buffQuality
                    buff_color_rgb = COLOR_QUALITY.get(buff_quality, (188, 188, 188))
                    buff_color_hex = f"rgb({buff_color_rgb[0]}, {buff_color_rgb[1]}, {buff_color_rgb[2]})"

                    # 角色数据
                    roles_data = []
                    for slash_role in slash_half.roleList:
                        char_model = get_char_model(slash_role.roleId)
                        if char_model is None:
                            continue

                        # 获取角色等级
                        role_level = 90
                        role = next(
                            (r for r in role_info_list if r.roleId == slash_role.roleId),
                            None,
                        )
                        if role:
                            role_level = role.level

                        chain_num = 0
                        chain_name = ""
                        if role_detail_info_map and str(slash_role.roleId) in role_detail_info_map:
                            temp: RoleDetailData = role_detail_info_map[str(slash_role.roleId)]
                            chain_num = temp.get_chain_num()
                            chain_name = temp.get_chain_name()

                        # 使用本地头像（和PIL版本一致）
                        role_icon_b64 = img_to_b64(get_square_avatar_path(slash_role.roleId), quality=75, bake=True, cover_size=(128, 128))

                        roles_data.append({
                            "id": slash_role.roleId,
                            "name": char_model.name,
                            "star": char_model.starLevel,
                            "level": role_level,
                            "chain": chain_num,
                            "chain_name": chain_name,
                            "icon_url": role_icon_b64,
                        })

                    half_list.append({
                        "team_name": team_name,
                        "score": slash_half.score,
                        "buff_icon_url": buff_icon_b64,
                        "buff_quality": buff_quality,
                        "buff_color": buff_color_hex,
                        "roles": roles_data,
                    })

                # 队伍图标
                team_icon_b64 = await get_image_b64_with_cache(difficulty.teamIcon, SLASH_PATH) if difficulty.teamIcon else ""

                challenges_data.append({
                    "challenge_id": challenge.challengeId,
                    "challenge_name": challenge.challengeName,
                    "period": get_slash_period_number() if challenge.challengeId == 12 else None,
                    "score": challenge.score,
                    "rank": rank,
                    "difficulty": difficulty.difficulty,
                    "difficulty_bg_url": difficulty_bg_url,
                    "score_bg_url": score_bg_url,
                    "team_icon_url": team_icon_b64,
                    "half_list": half_list,
                })

        bg_img = get_waves_bg(bg = "bg9", crop=False)
        bg_url = pil_to_b64(bg_img, quality=75)

        title_bar = Image.open(TEXT_PATH / "title_bar.png")
        title_bar_url = pil_to_b64(title_bar, quality=75)

        role_hang_bg = Image.open(TEXT_PATH / "role_hang_bg.png")
        role_hang_bg_url = pil_to_b64(role_hang_bg, quality=75)

        current_date = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

        chain_colors = {i: f"rgba({r}, {g}, {b}, 0.8)" for i, (r, g, b) in CHAIN_COLOR.items()}

        context = {
            "user_name": account_info.name,
            "user_id": hide_uid(account_info.id, user_pref=user_pref),
            "level": account_info.level,
            "world_level": account_info.worldLevel,
            "show_stats": account_info.is_full,
            "avatar_url": avatar_url,
            "current_date": current_date,
            "title_bar_url": title_bar_url,
            "role_hang_bg_url": role_hang_bg_url,
            "challenges": challenges_data,
            "footer_b64": get_footer_b64(footer_type="white") or "",
            "bg_url": bg_url,
            "chain_colors": chain_colors,
        }

        sender_avatar = (ev.sender or {}).get("avatar") or ""
        if not (isinstance(sender_avatar, str) and sender_avatar.startswith(("http://", "https://"))):
            sender_avatar = ""

        # 保存和上传记录
        await save_slash_record(uid, slash_detail)
        await upload_slash_record(is_self_ck, uid, slash_detail, sender_avatar)

        logger.debug("[鸣潮] 准备通过HTML渲染冥海卡片")
        img_bytes = await render_html(waves_templates, "abyss/slash_card.html", context)
        if img_bytes:
            return img_bytes
        else:
            logger.warning("[鸣潮] Playwright 渲染返回空, 正在回退到 PIL 渲染")
            return await draw_slash_img_pil(ev, uid, user_id)

    except Exception as e:
        logger.exception(f"[鸣潮] HTML渲染失败: {e}")
        return await draw_slash_img_pil(ev, uid, user_id)

