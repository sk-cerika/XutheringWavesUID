import asyncio
import base64
from io import BytesIO
from typing import Dict, Any, Optional
from pathlib import Path
from collections import defaultdict

from PIL import Image

from ..wutheringwaves_config import WutheringWavesConfig
from ..utils.resource.RESOURCE_PATH import (
    waves_templates,
)
from ..utils.resource.constant import WEAPON_TYPE_ID_MAP
from ..utils.name_convert import alias_to_weapon_name, alias_to_echo_name, echo_name_to_echo_id
from ..utils.ascension.weapon import get_weapon_id, get_weapon_model, weapon_id_data, ensure_data_loaded as ensure_weapon_loaded
from ..utils.ascension.echo import get_echo_model
from ..utils.ascension.sonata import sonata_id_data, ensure_data_loaded as ensure_sonata_loaded
from ..utils.ascension.model import WeaponModel, EchoModel
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    image_to_base64,
    render_html,
)
from ..utils.resource.download_file import get_phantom_img, get_material_img
from ..utils.image import get_square_weapon, get_square_weapon_path, get_attribute_effect, pil_to_b64, img_to_b64

TEXTURE2D_PATH = Path(__file__).parents[1] / "utils" / "texture2d"
WIKI_TEXTURE_PATH = Path(__file__).parent / "texture2d"


def _load_bg_b64(bg_path) -> str:
    bg_img = Image.open(bg_path).transpose(Image.ROTATE_270)
    return pil_to_b64(bg_img, quality=75)



async def draw_weapon_wiki_render(weapon_name: str) -> Optional[bytes]:
    """渲染武器图鉴 (HTML)"""
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or render_html is None or not use_html_render:
        return None

    weapon_name = alias_to_weapon_name(weapon_name)
    weapon_id = get_weapon_id(weapon_name)
    if weapon_id is None:
        return None

    weapon_model: Optional[WeaponModel] = get_weapon_model(weapon_id)
    if not weapon_model:
        return None

    context = await _prepare_weapon_context(weapon_id, weapon_model)
    return await render_html(waves_templates, "wiki/item_wiki.html", context)


async def _prepare_weapon_context(weapon_id: str, weapon_model: WeaponModel) -> Dict[str, Any]:
    """准备武器渲染上下文"""
    # 获取武器图片
    weapon_pic_b64 = img_to_b64(get_square_weapon_path(weapon_id), quality=75, bake=True, cover_size=(128, 128))

    # 获取稀有度图标
    rarity_path = WIKI_TEXTURE_PATH / f"rarity_{weapon_model.starLevel}.png"
    rarity_icon = image_to_base64(rarity_path) if rarity_path.exists() else ""

    # 获取武器类型图标
    weapon_type_name = weapon_model.get_weapon_type()
    weapon_type_path = TEXTURE2D_PATH / "weapon_type" / f"weapon_type_{weapon_type_name}.png"
    weapon_type_icon = image_to_base64(weapon_type_path) if weapon_type_path.exists() else ""

    # 获取属性数据
    stats = []
    for stat_name, stat_value in weapon_model.get_max_level_stat_tuple():
        stats.append({"name": stat_name, "value": stat_value})

    # 获取突破材料
    materials = []
    for material_id in weapon_model.get_ascensions_max_list():
        material_img = await get_material_img(material_id)
        if material_img:
            materials.append(pil_to_b64(material_img, quality=75))

    # 背景
    bg_path = TEXTURE2D_PATH / "bg6.jpg"
    bg_b64 = await asyncio.to_thread(_load_bg_b64, bg_path)

    return {
        "item_type": "weapon",
        "name": weapon_model.name,
        "star": weapon_model.starLevel,
        "icon": weapon_pic_b64,
        "rarity_icon": rarity_icon,
        "type_icon": weapon_type_icon,
        "type_name": weapon_type_name,
        "stats": stats,
        "effect_name": weapon_model.effectName,
        "effect_desc": weapon_model.get_effect_detail(),
        "materials": materials,
        "bg_url": bg_b64,
        "footer_url": image_to_base64(TEXTURE2D_PATH / "footer_white.png"),
    }


async def draw_echo_wiki_render(echo_name: str) -> Optional[bytes]:
    """渲染声骸图鉴 (HTML)"""
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or render_html is None or not use_html_render:
        return None

    echo_name = alias_to_echo_name(echo_name)
    echo_id = echo_name_to_echo_id(echo_name)
    if echo_id is None:
        return None

    echo_model: Optional[EchoModel] = get_echo_model(echo_id)
    if not echo_model:
        return None

    context = await _prepare_echo_context(echo_id, echo_model)
    return await render_html(waves_templates, "wiki/item_wiki.html", context)


async def _prepare_echo_context(echo_id: str, echo_model: EchoModel) -> Dict[str, Any]:
    """准备声骸渲染上下文"""
    # 获取声骸图片
    echo_pic = await get_phantom_img(int(echo_id), "")
    echo_pic_b64 = pil_to_b64(echo_pic, quality=75) if echo_pic else ""

    # 获取合鸣效果图标
    group_icons = []
    group_names = echo_model.get_group_name()
    for group_name in group_names:
        effect_img = await get_attribute_effect(group_name)
        if effect_img:
            group_icons.append({
                "name": group_name,
                "icon": pil_to_b64(effect_img, quality=75)
            })

    # 获取属性数据
    stats = []
    for stat_name, stat_value in echo_model.get_intensity():
        stats.append({"name": stat_name, "value": stat_value})

    # 背景
    bg_path = TEXTURE2D_PATH / "bg6.jpg"
    bg_b64 = await asyncio.to_thread(_load_bg_b64, bg_path)

    return {
        "item_type": "echo",
        "name": echo_model.name,
        "icon": echo_pic_b64,
        "group_icons": group_icons,
        "stats": stats,
        "skill_desc": echo_model.get_skill_detail(),
        "bg_url": bg_b64,
        "footer_url": image_to_base64(TEXTURE2D_PATH / "footer_white.png"),
    }


async def draw_weapon_list_render(weapon_type: str = "") -> Optional[bytes]:
    """渲染武器列表 (HTML)"""
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or render_html is None or not use_html_render:
        return None

    ensure_weapon_loaded()
    if not weapon_id_data:
        return None

    if weapon_type:
        weapon_type = weapon_type.replace("臂甲", "臂铠").replace("讯刀", "迅刀")

    # 创建反向映射
    reverse_type_map = {v: k for k, v in WEAPON_TYPE_ID_MAP.items()}
    target_type = reverse_type_map.get(weapon_type)

    # 按武器类型分组收集数据
    weapon_groups = defaultdict(list)
    for wid, data in weapon_id_data.items():
        name = data.get("name", "未知武器")
        star_level = data.get("starLevel", 0)
        w_type = data.get("type", 0)
        effect_name = data.get("effectName", "")

        if target_type is not None:
            if w_type == target_type:
                weapon_groups[w_type].append({
                    "id": wid, "name": name, "star_level": star_level, "effect_name": effect_name
                })
        else:
            weapon_groups[w_type].append({
                "id": wid, "name": name, "star_level": star_level, "effect_name": effect_name
            })

    groups_data = []
    for w_type in sorted(weapon_groups.keys()):
        weapons = weapon_groups[w_type]
        weapons.sort(key=lambda x: (-x["star_level"], x["name"]))

        type_name = WEAPON_TYPE_ID_MAP.get(w_type, f"未知类型{w_type}")
        weapons_render = []

        for weapon in weapons:
            weapons_render.append({
                "name": weapon["name"],
                "star": weapon["star_level"],
                "effect_name": weapon["effect_name"],
                "icon": img_to_b64(get_square_weapon_path(weapon["id"]), quality=75, bake=True, cover_size=(128, 128)),
            })

        groups_data.append({
            "type_name": type_name,
            "weapons": weapons_render,
        })

    # 背景
    bg_path = TEXTURE2D_PATH / "bg6.jpg"
    bg_b64 = await asyncio.to_thread(_load_bg_b64, bg_path)

    single_type = len(groups_data) == 1
    if single_type:
        title = f"{groups_data[0]['type_name']}武器一览"
    else:
        title = "武器一览"

    context = {
        "list_type": "weapon",
        "title": title,
        "single_type": single_type,
        "groups": groups_data,
        "bg_url": bg_b64,
        "footer_url": image_to_base64(TEXTURE2D_PATH / "footer_white.png"),
    }

    return await render_html(waves_templates, "wiki/list_wiki.html", context)


async def draw_sonata_list_render(version: str = "") -> Optional[bytes]:
    """渲染声骸套装列表 (HTML)"""
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or render_html is None or not use_html_render:
        return None

    ensure_sonata_loaded()
    if not sonata_id_data:
        return None

    if version:
        version = version.split(".")[0] + ".0"

    # 按版本分组
    sonata_groups = defaultdict(list)
    for data in sonata_id_data.values():
        name = data.get("name", "未知套装")
        set_list = data.get("set", {})
        from_version = data.get("version", "10.0")

        if version and from_version != version:
            continue

        sonata_groups[from_version].append({"name": name, "set": set_list})

    if version and not sonata_groups:
        return None

    # 准备渲染数据
    groups_data = []
    sorted_groups = sorted(sonata_groups.items(), key=lambda x: float(x[0]), reverse=True)

    for ver, sonatas in sorted_groups:
        sonatas.sort(key=lambda x: x["name"])
        sonatas_render = []

        for sonata in sonatas:
            effect_img = await get_attribute_effect(sonata["name"])
            effects = []
            for set_num, effect in sorted(sonata["set"].items(), key=lambda x: int(x[0])):
                effects.append({
                    "count": set_num,
                    "desc": effect.get("desc", "")
                })

            sonatas_render.append({
                "name": sonata["name"],
                "icon": pil_to_b64(effect_img, quality=75) if effect_img else "",
                "effects": effects,
            })

        groups_data.append({
            "version": ver,
            "sonatas": sonatas_render,
        })

    # 背景
    bg_path = TEXTURE2D_PATH / "bg6.jpg"
    bg_b64 = await asyncio.to_thread(_load_bg_b64, bg_path)

    title = f"声骸套装一览 - {version}版本" if version else "声骸套装一览"
    context = {
        "list_type": "sonata",
        "title": title,
        "groups": groups_data,
        "bg_url": bg_b64,
        "footer_url": image_to_base64(TEXTURE2D_PATH / "footer_white.png"),
    }

    return await render_html(waves_templates, "wiki/list_wiki.html", context)
