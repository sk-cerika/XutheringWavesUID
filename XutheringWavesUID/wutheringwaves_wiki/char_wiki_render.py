import asyncio
import re
import os
from typing import Dict, Optional, List, Any
from pathlib import Path

from msgspec import json as msgjson

from ..wutheringwaves_config import WutheringWavesConfig
from ..utils.resource.RESOURCE_PATH import (
    MAP_FORTE_PATH,
    ROLE_PILE_PATH,
    WIKI_CACHE_PATH,
    TEMP_PATH,
    waves_templates,
)
from ..utils.resource.constant import WEAPON_TYPE_ID_MAP
from ..utils.ascension.char import get_char_model
from ..utils.ascension.model import (
    Chain,
    Skill,
    Stats,
    CharacterModel,
)
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    image_to_base64,
    render_html,
)
from ..utils.image import ELEMENT_COLOR_MAP, pil_to_b64
from ..utils.resource.download_file import get_material_img


TEXTURE2D_PATH = Path(__file__).parents[1] / "utils" / "texture2d"
WIKI_TEXTURE_PATH = Path(__file__).parent / "texture2d"

WIKI_RENDER_CACHE: Dict[tuple[str, str], Path] = {}

def clear_wiki_cache():
    WIKI_RENDER_CACHE.clear()

def get_wiki_cache(char_id: str, render_type: str) -> Optional[bytes]:
    key = (char_id, render_type)
    if key in WIKI_RENDER_CACHE:
        file_path = WIKI_RENDER_CACHE[key]
        if file_path.exists():
            return file_path.read_bytes()
    return None

def save_wiki_cache(char_id: str, render_type: str, content: bytes) -> None:
    file_name = f"{char_id}_{render_type}.jpg"
    file_path = WIKI_CACHE_PATH / file_name
    
    if not WIKI_CACHE_PATH.exists():
        WIKI_CACHE_PATH.mkdir(parents=True, exist_ok=True)

    file_path.write_bytes(content)
    WIKI_RENDER_CACHE[(char_id, render_type)] = file_path

from PIL import Image
from io import BytesIO


async def _get_base_context(char_model: CharacterModel, char_id: str) -> Dict[str, Any]:
    max_stats: Stats = char_model.get_max_level_stat()
    
    stats = {
        "hp": f"{max_stats.life:.0f}",
        "atk": f"{max_stats.atk:.0f}",
        "def": f"{max_stats.def_:.0f}",
        "weakness_efficiency": "0",
        "break_ratio": "0%"
    }
    
    if char_model.statsWeakness:
        stats["weakness_efficiency"] = str(char_model.statsWeakness.weaknessMastery)
        ratio = char_model.statsWeakness.breakWeaknessRatio / 100
        stats["break_ratio"] = f"{ratio:.0f}%"
    
    element_name = char_model.get_attribute_name()
    weapon_name = WEAPON_TYPE_ID_MAP.get(char_model.weaponTypeId, "")
    
    element_icon_path = TEXTURE2D_PATH / "attribute" / f"attr_{element_name}.png"
    if not element_icon_path.exists():
        element_icon_path = TEXTURE2D_PATH / "attribute" / "attr_simple_default.png"
        
    weapon_icon_path = TEXTURE2D_PATH / "weapon_type" / f"weapon_type_{weapon_name}.png"
    
    rarity_path = WIKI_TEXTURE_PATH / f"rarity_{char_model.starLevel}.png"
    
    # Background - 顺时针旋转90度
    bg_path = TEXTURE2D_PATH / "bg6.jpg"
    bg_b64 = await asyncio.to_thread(_load_bg_b64, bg_path)

    # Role Pile
    role_pile_path = ROLE_PILE_PATH / f"role_pile_{char_id}.png"
    if not role_pile_path.exists():
        role_pile_path = ROLE_PILE_PATH / "role_pile_1503.png"

    char_data = {
        "name": char_model.name,
        "star": char_model.starLevel,
        "element": element_name,
        "weapon": weapon_name,
        "stats": stats,
    }
    
    theme_color = ELEMENT_COLOR_MAP.get(element_name, "#dcb268")

    # 突破材料
    materials = []
    for material_id in char_model.get_ascensions_max_list():
        try:
            material_img = await get_material_img(material_id)
            if material_img:
                materials.append(await asyncio.to_thread(pil_to_b64, material_img, 75))
        except Exception:
            pass

    return {
        "char_data": char_data,
        "theme_color": theme_color,
        "element_icon": image_to_base64(element_icon_path),
        "weapon_icon": image_to_base64(weapon_icon_path),
        "rarity_icon": image_to_base64(rarity_path),
        "bg_url": bg_b64,
        "portrait_url": image_to_base64(role_pile_path),
        "materials": materials,
        "footer_url": image_to_base64(TEXTURE2D_PATH / "footer_white.png"),
    }


def _load_bg_b64(bg_path) -> str:
    bg_img = Image.open(bg_path).transpose(Image.ROTATE_270)
    return pil_to_b64(bg_img, quality=75)

async def draw_char_skill_render(char_id: str):
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or render_html is None or not use_html_render:
        return None
    
    cache_content = get_wiki_cache(char_id, "skill")
    if cache_content:
        return cache_content
    
    char_model: Optional[CharacterModel] = get_char_model(char_id)
    if char_model is None:
        return None

    context = await _get_base_context(char_model, char_id)
    context["section"] = "skill"
    context["skills"] = await prepare_char_skill_data(char_model.skillTree)

    if char_model.skillBranches:
        context["skill_branches"] = [
            {"name": b.name, "desc": b.desc, "isDefault": b.isDefault}
            for b in char_model.skillBranches
        ]

    res = await render_html(waves_templates, "wiki/char_wiki.html", context)
    if res:
        save_wiki_cache(char_id, "skill", res)
    return res

async def draw_char_chain_render(char_id: str):
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or render_html is None or not use_html_render:
        return None
    
    cache_content = get_wiki_cache(char_id, "chain")
    if cache_content:
        return cache_content
    
    char_model: Optional[CharacterModel] = get_char_model(char_id)
    if char_model is None:
        return None

    context = await _get_base_context(char_model, char_id)
    context["section"] = "chain"
    context["chains"] = await prepare_char_chain_data(char_model.chains)

    res = await render_html(waves_templates, "wiki/char_wiki.html", context)
    if res:
        save_wiki_cache(char_id, "chain", res)
    return res

async def draw_char_forte_render(char_id: str):
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or render_html is None or not use_html_render:
        return None
    
    cache_content = get_wiki_cache(char_id, "forte")
    if cache_content:
        return cache_content
    
    char_model: Optional[CharacterModel] = get_char_model(char_id)
    if char_model is None:
        return None

    forte_path = MAP_FORTE_PATH / str(char_id) / "forte.json"
    if not forte_path.exists():
        return None

    with open(forte_path, "rb") as f:
        data = msgjson.decode(f.read())

    context = await _get_base_context(char_model, char_id)
    context["section"] = "forte"
    context["forte"] = await prepare_char_forte_data_render(data, str(char_id))

    res = await render_html(waves_templates, "wiki/char_wiki.html", context)
    if res:
        save_wiki_cache(char_id, "forte", res)
    return res


async def prepare_char_skill_data(data: Dict[str, Dict[str, Skill]]) -> List[Dict[str, Any]]:
    keys = [
        ("常态攻击", "1", ["12", "13"]),
        ("共鸣技能", "2", ["10", "14"]),
        ("共鸣回路", "7", ["4", "5"]),
        ("共鸣解放", "3", ["11", "15"]),
        ("变奏技能", "6", ["9", "16"]),
        ("延奏技能", "8", []),
        ("谐度破坏", "17", []),
    ]
    
    skills_list = []
    
    for skill_type, skill_tree_id, relate_skill_tree_ids in keys:
        if skill_tree_id not in data:
            continue
            
        item = data[skill_tree_id]["skill"]
        desc = item.get_desc_detail().replace("\n", "<br>")
        if skill_type == "谐度破坏" and not desc.strip():
            desc = '目标<span style="color:#ffd12f;font-weight:bold">【偏谐值】</span>满时，可对其造成<span style="color:#ffd12f;font-weight:bold">【谐度破坏】</span>伤害。'

        for relate_id in relate_skill_tree_ids:
            if relate_id in data:
                relate_item = data[relate_id]["skill"]
                _type = relate_item.type if relate_item.type else "属性加成"
                relate_title = f"{_type}: {relate_item.name}"
                relate_desc = relate_item.get_desc_detail().replace("\n", "<br>")
                
                desc += f"<br><br><strong>{relate_title}</strong><br>{relate_desc}"
        
        # Rates
        rates = []
        if item.level:
            for _, skillLevel in item.level.items():
                row_values = []
                param_values = skillLevel.param[0][5:10]
                if skillLevel.format:
                    row_values = [f"{v}{skillLevel.format}" for v in param_values]
                else:
                    row_values = param_values
                
                rates.append({
                    "label": skillLevel.name,
                    "rate_values": row_values
                })

        skills_list.append({
            "name": skill_type,
            "type": item.name,
            "desc": desc,
            "rates": rates,
            "icon": ""
        })
        
    return skills_list

async def prepare_char_chain_data(data: Dict[int, Chain]) -> List[Dict[str, Any]]:
    chains_list = []
    for chain_num in sorted(data.keys()):
        item = data[chain_num]
        chains_list.append({
            "name": item.name,
            "desc": item.get_desc_detail().replace("\n", "<br>")
        })
    return chains_list

async def prepare_char_forte_data_render(data: Dict, char_id: str) -> Dict[str, Any]:
    features = data.get("Features", [])
    
    groups = []
    instructions = data.get("Instructions", {})
    sorted_keys = sorted(instructions.keys())
    
    for key in sorted_keys:
        instruction_group = instructions[key]
        group_name = instruction_group.get("Name", "未命名")
        desc_map = instruction_group.get("Desc", {})
        sorted_desc_keys = sorted(desc_map.keys())
        
        items = []
        for desc_key in sorted_desc_keys:
            item = desc_map[desc_key]
            desc_text = item.get("Desc", "")
            input_list = item.get("InputList", [])
            image_list = item.get("ImageList", [])

            parts = re.split(r"{(\d+)}", desc_text)
            final_desc = ""
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    final_desc += part.replace("\n", "<br>")
                else:
                    idx = int(part)
                    if idx < len(input_list):
                        input_name = input_list[idx]
                        icon_path = MAP_FORTE_PATH / f"{input_name}.webp"
                        if icon_path.exists():
                             b64 = image_to_base64(icon_path)
                             final_desc += f'<img src="{b64}" class="inline-icon" alt="{input_name}">'
                        else:
                            final_desc += f"<span class='key-input'>{input_name}</span>"
                    else:
                        final_desc += f"{{{part}}}"

            # Collect images per item
            item_imgs_b64 = []
            for img_path_str in image_list:
                if not img_path_str:
                    continue
                img_name = os.path.basename(img_path_str)
                stem = os.path.splitext(img_name)[0]
                local_img_path = None
                for ext in (".png", ".webp", ".jpg"):
                    candidate = MAP_FORTE_PATH / char_id / (stem + ext)
                    if candidate.exists():
                        local_img_path = candidate
                        break
                if local_img_path:
                    item_imgs_b64.append(image_to_base64(local_img_path))

            items.append({
                "desc": final_desc,
                "images": item_imgs_b64,
            })

        groups.append({
            "name": group_name,
            "forte_items": items,
        })
        
    return {
        "features": features,
        "groups": groups
    }
