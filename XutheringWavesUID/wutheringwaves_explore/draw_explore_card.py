from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path

from ..utils.hint import error_reply
from ..utils.util import get_hide_uid_pref, hide_uid
from ..utils.waves_api import waves_api
from ..wutheringwaves_config import WutheringWavesConfig, PREFIX
from ..utils.error_reply import WAVES_CODE_102
from ..utils.api.model import (
    ExploreList,
    AccountBaseInfo,
)
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    render_html,
    get_image_b64_with_cache,
    get_footer_b64,
)
from ..utils.resource.RESOURCE_PATH import waves_templates
from ..utils.image import (
    YELLOW,
    WAVES_MOLTEN,
    WAVES_SIERRA,
    WAVES_MOONLIT,
    WAVES_FREEZING,
    WAVES_LINGERING,
    pil_to_b64,
    rgb_to_hex,
    get_custom_waves_bg,
    get_event_avatar,
)

from .draw_explore_card_pil import draw_explore_img as draw_explore_img_pil

EXPLORE_IMAGE_PATH = get_res_path("XutheringWavesUID") / "other" / "explore"

country_color_map = {
    "黑海岸": (28, 55, 118),
    "瑝珑": (140, 113, 58),
    "黎那汐塔": (95, 52, 39),
    "罗伊冰原": (141, 159, 77),
}

WAVES_OLIVE = (140, 178, 78)
WAVES_GOLD = (212, 177, 99)

progress_color = [
    (10, WAVES_MOONLIT),
    (20, WAVES_LINGERING),
    (35, WAVES_FREEZING),
    (50, WAVES_SIERRA),
    (70, WAVES_OLIVE),
    (80, WAVES_GOLD),
    (90, YELLOW),
    (100, WAVES_MOLTEN),
]


def get_progress_color_hex(progress: float) -> str:
    float_progress = float(progress)
    result = WAVES_MOONLIT
    for _p, color in progress_color:
        if float_progress >= _p:
            result = color
    return rgb_to_hex(result)

async def draw_explore_img(ev: Event, uid: str, user_id: str):
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await draw_explore_img_pil(ev, uid, user_id)

    try:
        is_self_ck, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
        if not ck:
            return error_reply(WAVES_CODE_102)
        user_pref = await get_hide_uid_pref(uid, user_id, ev.bot_id)

        account_info_res = await waves_api.get_base_info(uid, ck)
        if not account_info_res.success:
            return account_info_res.throw_msg()
        if not account_info_res.data:
            return f"用户未展示数据, 请尝试【{PREFIX}登录】"
        account_info = AccountBaseInfo.model_validate(account_info_res.data)

        explore_data_res = await waves_api.get_explore_data(uid, ck)
        if not explore_data_res.success:
            return explore_data_res.throw_msg()
        explore_data = ExploreList.model_validate(explore_data_res.data)
        
        if not is_self_ck and not explore_data.open:
            return "探索数据未开启"

        if not explore_data.exploreList:
            return "探索数据为空"

        avatar = await get_event_avatar(ev)
        avatar_url = pil_to_b64(avatar, quality=75)

        explore_list_data = []
        for _explore in reversed(explore_data.exploreList):
            # Country Info
            country_name = _explore.country.countryName
            country_color_rgb = country_color_map.get(country_name, YELLOW)
            country_color_hex = rgb_to_hex(country_color_rgb)
            country_color_rgba = "rgba({}, {}, {}, 0.45)".format(*country_color_rgb[:3])
            r, g, b = country_color_rgb[:3]
            bright = (min(255, int(r + (255 - r) * 0.45)),
                      min(255, int(g + (255 - g) * 0.45)),
                      min(255, int(b + (255 - b) * 0.45)))
            country_color_bright = "#{:02x}{:02x}{:02x}".format(*bright)
            
            # Country Icon
            icon_url = _explore.country.homePageIcon
            icon_b64 = await get_image_b64_with_cache(icon_url, EXPLORE_IMAGE_PATH) if icon_url else ""
            
            # Country Tag
            is_complete = float(_explore.countryProgress) >= 100
            tag_text = "已完成" if is_complete else "未完成"
            
            # Areas
            completed_sub_areas = []
            incomplete_sub_areas = []
            
            for _subArea in (_explore.areaInfoList or []):
                area_progress = float(_subArea.areaProgress)
                area_color_hex = get_progress_color_hex(area_progress)
                
                # Filter Items: Only items < 100%, max 5
                display_items = []
                for _item in _subArea.itemList:
                    item_progress = float(_item.progress)
                    if item_progress >= 100:
                        continue
                        
                    item_info = {
                        "name": _item.name,
                        "progress": item_progress,
                        "icon_url": await get_image_b64_with_cache(_item.icon, EXPLORE_IMAGE_PATH) if _item.icon else "",
                        "color": get_progress_color_hex(item_progress)
                    }
                    display_items.append(item_info)
                
                # Limit to top 5 unfinished items
                display_items = display_items[:5]
                
                area_data = {
                    "name": _subArea.areaName,
                    "progress": area_progress,
                    "progress_color": area_color_hex,
                    "item_list": display_items
                }
                
                if not display_items:
                    completed_sub_areas.append(area_data)
                else:
                    incomplete_sub_areas.append(area_data)

            explore_list_data.append({
                "name": country_name,
                "progress": _explore.countryProgress,
                "color": country_color_hex,
                "color_bright": country_color_bright,
                "color_tint": country_color_rgba,
                "is_complete": is_complete,
                "icon_url": icon_b64,
                "tag_text": tag_text,
                "completed_sub_areas": completed_sub_areas,
                "incomplete_sub_areas": incomplete_sub_areas
            })

        bg_img = get_custom_waves_bg(bg="bg3", crop=False)
        bg_url = pil_to_b64(bg_img, quality=75)

        context = {
            "user_name": account_info.name,
            "user_id": hide_uid(account_info.id, user_pref=user_pref),
            "level": account_info.level,
            "world_level": account_info.worldLevel,
            "show_stats": account_info.is_full,
            "avatar_url": avatar_url,
            "explore_list": explore_list_data,
            "footer_b64": get_footer_b64(footer_type="white") or "",
            "bg_url": bg_url,
        }

        logger.debug("[鸣潮] 准备通过HTML渲染探索卡片")
        img_bytes = await render_html(waves_templates, "explore_card.html", context)
        if img_bytes:
            return img_bytes
        else:
            logger.warning("[鸣潮] Playwright 渲染返回空, 正在回退到 PIL 渲染")
            return await draw_explore_img_pil(ev, uid, user_id)

    except Exception as e:
        logger.exception(f"[鸣潮] HTML渲染失败: {e}")
        return await draw_explore_img_pil(ev, uid, user_id)
