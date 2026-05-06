from typing import Optional
from datetime import datetime, timezone, timedelta

from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path

from ..utils.at_help import ruser_id
from ..utils.util import get_hide_uid_pref, hide_uid
from ..utils.waves_api import waves_api
from ..wutheringwaves_config import WutheringWavesConfig, PREFIX
from ..utils.api.model import (
    Role,
    RoleList,
    CalabashData,
    RoleDetailData,
    AccountBaseInfo,
)
from ..utils.char_info_utils import get_all_roleid_detail_info_int
from ..utils.resource.constant import NORMAL_LIST, SPECIAL_CHAR_INT
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    render_html,
    get_footer_b64,
    get_image_b64_with_cache,
)
from ..utils.resource.RESOURCE_PATH import waves_templates
from ..utils.image import (
    pil_to_b64,
    img_to_b64,
    get_custom_waves_bg,
    get_event_avatar,
    get_square_avatar,
    get_square_avatar_path,
    get_square_weapon,
    get_square_weapon_path,
    get_attribute,
    CHAIN_COLOR,
)

from .draw_role_info_pil import draw_role_img as draw_role_img_pil

SKIN_IMAGE_PATH = get_res_path("XutheringWavesUID") / "other" / "skin"


async def draw_role_img(uid: str, ck: str, ev: Event):
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await draw_role_img_pil(uid, ck, ev)
    user_pref = await get_hide_uid_pref(uid, ruser_id(ev), ev.bot_id)

    try:
        # 共鸣者信息
        role_info = await waves_api.get_role_info(uid, ck)
        if not role_info.success:
            return role_info.throw_msg()

        try:
            role_info = RoleList.model_validate(role_info.data)
        except Exception:
            return f"用户未展示角色数据, 请尝试【{PREFIX}登录】"

        role_info.roleList.sort(key=lambda i: (i.level, i.starLevel, i.roleId), reverse=True)

        # 账户数据
        account_info = await waves_api.get_base_info(uid, ck)
        if not account_info.success:
            return account_info.throw_msg()
        if not account_info.data:
            return f"用户未展示数据, 请尝试【{PREFIX}登录】"
        account_info = AccountBaseInfo.model_validate(account_info.data)

        # 数据坞
        calabash_data = await waves_api.get_calabash_data(uid, ck)
        if not calabash_data.success:
            return calabash_data.throw_msg()
        calabash_data = CalabashData.model_validate(calabash_data.data)

        # 计算UP角色数量
        up_num = sum(1 for i in role_info.roleList if i.starLevel == 5 and i.roleName not in NORMAL_LIST)

        # 基础信息数据
        base_info_list = []
        if account_info.is_full:
            base_info_list = [
                {"key": "活跃天数", "value": f"{account_info.activeDays}", "highlight": True},
                {"key": "解锁角色", "value": f"{account_info.roleNum}", "highlight": False},
                {"key": "UP角色", "value": f"{up_num}", "highlight": True},
                {"key": "数据坞等级", "value": f"{calabash_data.level if calabash_data.isUnlock else 0}", "highlight": False},
                {"key": "已达成成就", "value": f"{account_info.achievementCount}", "highlight": True},
                {"key": "成就星数", "value": f"{account_info.achievementStar}", "highlight": False},
                {"key": "小型信标", "value": f"{account_info.smallCount}", "highlight": False},
                {"key": "中型信标", "value": f"{account_info.bigCount}", "highlight": True},
            ]

            for bid, b in enumerate(account_info.treasureBoxList):
                base_info_list.append({"key": b.name, "value": f"{b.num}", "highlight": bid % 2})

        # 获取详细角色信息
        role_detail_info_map = await get_all_roleid_detail_info_int(uid)

        # 准备角色列表数据
        role_list_data = []
        for role in role_info.roleList:
            # 获取属性图标
            attribute_img = await get_attribute(role.attributeName)
            attribute_b64 = pil_to_b64(attribute_img) if attribute_img else ""

            role_avatar = None
            if role.roleSkin and role.roleSkin.quality and role.roleSkin.quality > 3:
                skin_icon_url = role.roleSkin.skinIcon
                if skin_icon_url:
                    role_avatar_b64 = await get_image_b64_with_cache(skin_icon_url, SKIN_IMAGE_PATH, quality=75, cover_size=(128, 128))
                    if not role_avatar_b64:
                        role_avatar_b64 = img_to_b64(get_square_avatar_path(role.roleId), quality=75, bake=True, cover_size=(128, 128))
            else:
                # 使用默认头像
                role_avatar_b64 = img_to_b64(get_square_avatar_path(role.roleId), quality=75, bake=True, cover_size=(128, 128))

            # 查找角色详细信息
            if role.roleId in SPECIAL_CHAR_INT:
                query_list = SPECIAL_CHAR_INT.copy()
            else:
                query_list = [role.roleId]

            temp: Optional[RoleDetailData] = None
            for char_id in query_list:
                if role_detail_info_map and char_id in role_detail_info_map:
                    temp = role_detail_info_map[char_id]
                    break

            weapon_icon_b64 = ""
            chain_num = 0
            chain_name = ""
            if temp:
                # 获取武器图标
                weapon_icon_b64 = img_to_b64(get_square_weapon_path(temp.weaponData.weapon.weaponId), quality=75, bake=True, cover_size=(128, 128))
                chain_num = temp.get_chain_num()
                chain_name = temp.get_chain_name()

            role_list_data.append({
                "name": role.roleName,
                "level": role.level,
                "star_level": role.starLevel,
                "rarity": role.starLevel,
                "attribute_icon": attribute_b64,
                "avatar_icon": role_avatar_b64,
                "weapon_icon": weapon_icon_b64,
                "chain_num": chain_num,
                "chain_name": chain_name,
            })

        # 准备头像
        avatar = await get_event_avatar(ev)
        avatar_url = pil_to_b64(avatar, quality=75)

        # 准备背景
        bg_img = get_custom_waves_bg(bg="bg3", crop=False)
        bg_url = pil_to_b64(bg_img, quality=75)

        # 将 CHAIN_COLOR 转换为 RGB 字符串格式
        chain_colors = {i: f"rgba({r}, {g}, {b}, 0.8)" for i, (r, g, b) in CHAIN_COLOR.items()}
        chain_border_colors = {i: f"rgba({r}, {g}, {b}, 1)" for i, (r, g, b) in CHAIN_COLOR.items()}

        # 当前日期
        current_date = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

        # 准备模板数据
        context = {
            "user_name": account_info.name[:10],
            "user_id": hide_uid(account_info.id, user_pref=user_pref),
            "level": account_info.level if account_info.is_full else 0,
            "world_level": account_info.worldLevel if account_info.is_full else 0,
            "show_stats": account_info.is_full,
            "avatar_url": avatar_url,
            "bg_url": bg_url,
            "current_date": current_date,
            "base_info_list": base_info_list,
            "role_list": role_list_data,
            "footer_b64": get_footer_b64(footer_type="white") or "",
            "chain_colors": chain_colors,
            "chain_border_colors": chain_border_colors,
        }

        logger.debug("[鸣潮] 准备通过HTML渲染角色卡片")
        img_bytes = await render_html(waves_templates, "roleinfo/role_card.html", context)
        if img_bytes:
            return img_bytes
        else:
            logger.warning("[鸣潮] Playwright 渲染返回空, 正在回退到 PIL 渲染")
            return await draw_role_img_pil(uid, ck, ev)

    except Exception as e:
        logger.exception(f"[鸣潮] HTML渲染失败: {e}")
        return await draw_role_img_pil(uid, ck, ev)
