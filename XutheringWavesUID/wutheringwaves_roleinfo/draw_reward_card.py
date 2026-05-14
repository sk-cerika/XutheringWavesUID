from typing import Dict, Optional, Union

from gsuid_core.models import Event
from gsuid_core.logger import logger

from ..utils.at_help import ruser_id
from ..utils.util import get_hide_uid_pref, hide_uid
from ..utils.waves_api import waves_api
from ..wutheringwaves_config import WutheringWavesConfig
from ..utils.api.model import (
    RoleList,
    AccountBaseInfo,
)
from ..utils.char_info_utils import get_all_roleid_detail_info_int
from ..utils.resource.constant import SPECIAL_CHAR_INT_ALL
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    render_html,
    get_image_b64_with_cache,
    get_footer_b64,
)
from ..utils.resource.RESOURCE_PATH import waves_templates
from ..utils.image import (
    pil_to_b64,
    img_to_b64,
    get_custom_waves_bg,
    get_event_avatar,
    get_square_avatar_path,
    get_square_weapon_path,
)
from gsuid_core.data_store import get_res_path
from .draw_reward_card_pil import draw_reward_img_pil

SCORE_IMAGE_PATH = get_res_path("XutheringWavesUID") / "other" / "reward"
SCORE_IMAGE_PATH.mkdir(parents=True, exist_ok=True)


def _format_reward_text(display_uid: str, score_data: Dict) -> str:
    return (
        f"UID {display_uid} 伴行积分：{score_data['total_score']}，"
        f"{score_data['char_weapon_total_capped']}分"
        f"（角色{score_data['char_score_raw']}分 + "
        f"武器{score_data['weapon_score_raw']}分） + "
        f"成就{score_data['achievement_score']}分 + "
        f"活跃天数{score_data['active_days_score']}分"
    )


async def _draw_reward_pil_fallback(
    score_data: Dict,
    ev: Event,
    display_uid: str,
) -> Union[str, bytes]:
    try:
        return await draw_reward_img_pil(score_data, ev)
    except Exception as e:
        logger.exception(f"[鸣潮] 积分PIL渲染失败: {e}")
        return _format_reward_text(display_uid, score_data)


async def calculate_score(uid: str, ck: str) -> Optional[Dict]:
    """计算用户积分"""

    # 获取角色列表
    role_info_res = await waves_api.get_role_info(uid, ck)
    if not role_info_res.success:
        return None

    try:
        role_info = RoleList.model_validate(role_info_res.data)
    except Exception:
        return None

    # 获取基础信息
    account_info_res = await waves_api.get_base_info(uid, ck)
    if not account_info_res.success:
        return None
    if not account_info_res.data:
        return None
    account_info = AccountBaseInfo.model_validate(account_info_res.data)

    # 获取角色详细信息
    role_detail_map = await get_all_roleid_detail_info_int(uid)
    if not role_detail_map:
        return None

    # 计算角色积分
    character_items = []
    total_char_score = 0

    for role in role_info.roleList:
        # 只计算5星角色且不在特殊角色列表中
        if role.starLevel != 5 or role.roleId in SPECIAL_CHAR_INT_ALL:
            continue

        # 基础100分
        base_score = 100

        # 获取共鸣链数量
        chain_score = 0
        chain_num = 0
        if role.roleId in role_detail_map:
            detail_data = role_detail_map[role.roleId]
            chain_num = detail_data.get_chain_num()
            chain_score = chain_num * 100

        total_score = base_score + chain_score
        total_char_score += total_score

        # 从本地获取角色头像
        avatar_b64 = img_to_b64(get_square_avatar_path(role.roleId), quality=75, bake=True, cover_size=(128, 128))

        character_items.append({
            "name": role.roleName,
            "icon_url": avatar_b64,
            "score": total_score,
            "detail": f"100+{chain_num}链×100" if chain_num > 0 else "100",
            "chain_num": chain_num
        })

    # 按分数排序
    character_items.sort(key=lambda x: x["score"], reverse=True)

    # 计算武器积分
    weapon_items = []
    total_weapon_score = 0

    for detail_data in role_detail_map.values():
        weapon = detail_data.weaponData.weapon

        # 只计算5星武器
        if weapon.weaponStarLevel != 5 or weapon.weaponId == 21020046: # 血誓盟约
            continue

        # resonLevel至少是1，每个resonLevel算100分
        reson_level = detail_data.weaponData.resonLevel or 1
        weapon_score = reson_level * 100
        total_weapon_score += weapon_score

        # 获取武器图标 (优先使用本地资源)
        try:
            icon_b64 = img_to_b64(get_square_weapon_path(weapon.weaponId), quality=75, bake=True, cover_size=(128, 128))
        except Exception:
            # 回退到网络图片
            icon_url = weapon.weaponIcon or ""
            icon_b64 = await get_image_b64_with_cache(icon_url, SCORE_IMAGE_PATH) if icon_url else ""

        weapon_items.append({
            "name": weapon.weaponName,
            "icon_url": icon_b64,
            "score": weapon_score,
            "detail": f"{reson_level}阶×100",
            "reson_level": reson_level,
            "holder": detail_data.role.roleName
        })

    # 按分数排序
    weapon_items.sort(key=lambda x: x["score"], reverse=True)

    # 计算成就积分（上限1600分）
    achievement_count = account_info.achievementCount or 0
    achievement_star = account_info.achievementStar or 0
    achievement_score_raw = achievement_count * 2
    achievement_score = min(achievement_score_raw, 1600)

    # 计算活跃天数积分（上限10000分）
    active_days = account_info.activeDays or 0
    active_days_score_raw = active_days * 10
    active_days_score = min(active_days_score_raw, 10000)

    char_score_raw = total_char_score
    weapon_score_raw = total_weapon_score

    # 计算5星角色+武器积分总和（上限8000分）
    char_weapon_total_raw = total_char_score + total_weapon_score
    char_weapon_total_capped = min(char_weapon_total_raw, 8000)

    # 总分
    total_score = char_weapon_total_capped + achievement_score + active_days_score

    return {
        "character_items": character_items,
        "weapon_items": weapon_items,
        "char_score_raw": char_score_raw,
        "weapon_score_raw": weapon_score_raw,
        "char_weapon_total_raw": char_weapon_total_raw,
        "char_weapon_total_capped": char_weapon_total_capped,
        "achievement_count": achievement_count,
        "achievement_star": achievement_star,
        "achievement_score": achievement_score,
        "achievement_score_raw": achievement_score_raw,
        "active_days": active_days,
        "active_days_score": active_days_score,
        "active_days_score_raw": active_days_score_raw,
        "total_score": total_score,
        "account_info": account_info,
    }


async def draw_reward_img(uid: str, ck: str, ev: Event):
    """绘制积分卡片"""
    user_pref = await get_hide_uid_pref(uid, ruser_id(ev), ev.bot_id)
    display_uid = hide_uid(uid, user_pref=user_pref)

    score_data = await calculate_score(uid, ck)
    if not score_data:
        return "获取数据失败，请先登录，或尝试刷新面板！"
    score_data["display_uid"] = display_uid

    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await _draw_reward_pil_fallback(
            score_data,
            ev,
            display_uid,
        )

    account_info = score_data["account_info"]

    # 准备头像
    avatar = await get_event_avatar(ev)
    avatar_url = pil_to_b64(avatar, quality=75)

    # 准备背景
    bg_img = get_custom_waves_bg(bg="bg3", crop=False)
    bg_url = pil_to_b64(bg_img, quality=75)

    # 准备模板数据
    context = {
        "user_name": account_info.name,
        "user_id": hide_uid(account_info.id, user_pref=user_pref),
        "level": account_info.level or 0,
        "world_level": account_info.worldLevel or 0,
        "show_stats": account_info.is_full,
        "avatar_url": avatar_url,
        "bg_url": bg_url,
        "footer_b64": get_footer_b64(footer_type="white") or "",

        # 积分数据
        "character_items": score_data["character_items"],
        "weapon_items": score_data["weapon_items"],
        "char_score_raw": score_data["char_score_raw"],
        "weapon_score_raw": score_data["weapon_score_raw"],
        "char_weapon_total_raw": score_data["char_weapon_total_raw"],
        "char_weapon_total_capped": score_data["char_weapon_total_capped"],
        "achievement_count": score_data["achievement_count"],
        "achievement_star": score_data["achievement_star"],
        "achievement_score": score_data["achievement_score"],
        "achievement_score_raw": score_data["achievement_score_raw"],
        "active_days": score_data["active_days"],
        "active_days_score": score_data["active_days_score"],
        "active_days_score_raw": score_data["active_days_score_raw"],
        "total_score": score_data["total_score"],
    }

    logger.debug("[鸣潮] 准备通过HTML渲染积分卡片")
    try:
        img_bytes = await render_html(
            waves_templates,
            "roleinfo/reward_card.html",
            context,
        )
    except Exception as e:
        logger.exception(f"[鸣潮] 积分HTML渲染失败: {e}")
        img_bytes = None

    if img_bytes:
        return img_bytes
    else:
        logger.warning("[鸣潮] 积分HTML渲染失败，回退到PIL")
        return await _draw_reward_pil_fallback(
            score_data,
            ev,
            display_uid,
        )
