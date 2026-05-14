import textwrap
import re
import os
from typing import Dict, Optional, List, Union
from pathlib import Path

from msgspec import json as msgjson
from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread
from gsuid_core.utils.image.convert import convert_img

from ..utils.image import (
    GREY,
    SPECIAL_GOLD,
    add_footer,
    get_waves_bg,
    get_role_pile,
)
from ..utils.resource.RESOURCE_PATH import MAP_FORTE_PATH
from ..utils.ascension.char import get_char_model
from ..utils.ascension.model import (
    Chain,
    Skill,
    Stats,
    SkillLevel,
    CharacterModel,
)
from ..utils.fonts.waves_fonts import (
    waves_font_12,
    waves_font_24,
    waves_font_70,
    waves_font_origin,
)

from .char_wiki_render import (
    draw_char_skill_render,
    draw_char_chain_render,
    draw_char_forte_render,
    PLAYWRIGHT_AVAILABLE,
)

from ..utils.util import clean_tags, wrap_text_with_manual_newlines
from ..utils.resource.download_file import get_material_img

TEXT_PATH = Path(__file__).parent / "texture2d"


def _clean_wiki_text(text: str) -> str:
    text = clean_tags(str(text or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("&nbsp;", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _font_width(text: str, font) -> int:
    return int(font.getlength(text)) if hasattr(font, "getlength") else int(font.getsize(text)[0])


def _wrap_pil_text(text: str, font, max_width: int) -> List[str]:
    lines: List[str] = []
    for part in _clean_wiki_text(text).split("\n"):
        if not part.strip():
            lines.append("")
            continue

        current = ""
        for char in part.strip():
            test = current + char
            if _font_width(test, font) <= max_width:
                current = test
                continue
            if current:
                lines.append(current)
                current = char
            else:
                lines.append(char)
                current = ""
        if current:
            lines.append(current)
    return lines


async def draw_char_materials(char_model: CharacterModel, char_bg: Image.Image, x: int, y: int):
    """在角色头部绘制突破材料图标"""
    material_list = char_model.get_ascensions_max_list()
    if not material_list:
        return
    index = 0
    for material_id in material_list:
        try:
            material = await get_material_img(material_id)
            if not material:
                continue
            material = material.resize((50, 50))
            char_bg.alpha_composite(material, (x + index * 55, y))
            index += 1
        except Exception:
            pass


async def draw_char_wiki(char_id: str, query_role_type: str):
    if query_role_type == "技能":
        return await draw_char_skill(char_id)
    elif query_role_type == "共鸣链":
        return await draw_char_chain(char_id)
    elif query_role_type == "机制":
        return await draw_char_forte(char_id)
    return ""


async def draw_char_skill(char_id: str):
    if PLAYWRIGHT_AVAILABLE:
        try:
            res = await draw_char_skill_render(char_id)
            if res:
                return res
        except Exception:
            pass
    return await draw_char_skill_pil(char_id)


async def draw_char_chain(char_id: str):
    if PLAYWRIGHT_AVAILABLE:
        try:
            res = await draw_char_chain_render(char_id)
            if res:
                return res
        except Exception:
            pass
    return await draw_char_chain_pil(char_id)


async def draw_char_forte(char_id: str):
    if PLAYWRIGHT_AVAILABLE:
        try:
            res = await draw_char_forte_render(char_id)
            if res:
                return res
        except Exception:
            pass
    return await draw_char_forte_pil(char_id)


async def draw_char_forte_pil(char_id: str):
    char_model: Optional[CharacterModel] = get_char_model(char_id)
    if char_model is None:
        return ""

    _, char_pile = await get_role_pile(char_id)

    char_pic = char_pile.resize((600, int(600 / char_pile.size[0] * char_pile.size[1])))

    char_bg = Image.open(TEXT_PATH / "title_bg.png")
    char_bg = char_bg.resize((1000, int(1000 / char_bg.size[0] * char_bg.size[1])))
    char_bg_draw = ImageDraw.Draw(char_bg)
    # 名字
    char_bg_draw.text((580, 120), f"{char_model.name}", "black", waves_font_70, "lm")
    # 稀有度
    rarity_pic = Image.open(TEXT_PATH / f"rarity_{char_model.starLevel}.png")
    rarity_pic = rarity_pic.resize((180, int(180 / rarity_pic.size[0] * rarity_pic.size[1])))

    # 90级别数据
    max_stats: Stats = char_model.get_max_level_stat()
    char_stats = await parse_char_stats(max_stats)

    # Forte Data
    forte_path = MAP_FORTE_PATH / str(char_id) / "forte.json"
    if not forte_path.exists():
        return f"Forte file not found at {forte_path}"

    with open(forte_path, "rb") as f:
        data = msgjson.decode(f.read())

    # Parse and draw forte
    forte_img = await parse_char_forte_data(data, str(char_id))

    card_img = get_waves_bg(1000, char_bg.size[1] + forte_img.size[1] + 50, "bg6")

    char_bg.alpha_composite(char_pic, (0, -100))
    char_bg.alpha_composite(char_stats, (580, 340))
    char_bg.alpha_composite(rarity_pic, (560, 160))
    await draw_char_materials(char_model, char_bg, 580, 210)
    card_img.paste(char_bg, (0, -5), char_bg)
    card_img.alpha_composite(forte_img, (0, 600))

    card_img = add_footer(card_img, 800, 20, color="white")
    card_img = await convert_img(card_img)
    return card_img


async def parse_char_forte_data(data: Dict, char_id: str):
    # Setup fonts and layout constants
    y_padding = 20
    x_padding = 20
    line_spacing = 10
    block_line_spacing = 30
    section_spacing = 40
    image_width = 1000
    shadow_radius = 20

    title_color = SPECIAL_GOLD
    title_font_size = 40
    title_font = waves_font_origin(title_font_size)

    subtitle_color = "white"
    subtitle_font_size = 32
    subtitle_font = waves_font_origin(subtitle_font_size)

    detail_color = "white"
    detail_color_size = 30
    detail_font = waves_font_origin(detail_color_size)

    images = []

    # 1. Features Section
    features = data.get("Features", [])
    if features:
        feature_img = await draw_text_block(
            "角色特点",
            [_clean_wiki_text(feature) for feature in features],
            image_width,
            title_font,
            detail_font,
            title_color,
            detail_color,
            x_padding,
            y_padding,
            shadow_radius,
            line_spacing,
        )
        images.append(feature_img)

    # 2. Instructions Section
    instructions = data.get("Instructions", {})
    sorted_keys = sorted(instructions.keys())

    for key in sorted_keys:
        instruction_group = instructions[key]
        group_name = _clean_wiki_text(instruction_group.get("Name", "未命名"))
        desc_map = instruction_group.get("Desc", {})
        
        # Sort desc items by key
        sorted_desc_keys = sorted(desc_map.keys())
        
        # Create image for this group
        group_images = []
        
        # Draw Group Title
        title_img = Image.new("RGBA", (image_width, title_font_size + y_padding * 2), (0,0,0,0))
        draw_title = ImageDraw.Draw(title_img)
        # Draw a small indicator or just text
        draw_title.text((x_padding + shadow_radius, y_padding), group_name, font=title_font, fill=title_color)
        group_images.append(title_img)
        
        group_image_paths_seen = set()
        group_image_blocks = []
        for desc_key in sorted_desc_keys:
            item = desc_map[desc_key]
            desc_text = _clean_wiki_text(item.get("Desc", ""))
            input_list = item.get("InputList", [])
            image_list = item.get("ImageList", [])

            # Draw Description Text with Icons
            text_block = await draw_mixed_text(
                desc_text, input_list, image_width, detail_font, detail_color, x_padding, y_padding, shadow_radius, line_spacing
            )
            group_images.append(text_block)

            # Collect images at group level (deduplicated)
            for img_path_str in image_list:
                if img_path_str in group_image_paths_seen:
                    continue
                group_image_paths_seen.add(img_path_str)
                img_name = os.path.basename(img_path_str)
                stem = os.path.splitext(img_name)[0]
                local_img_path = None
                for ext in (".png", ".webp", ".jpg"):
                    candidate = MAP_FORTE_PATH / char_id / (stem + ext)
                    if candidate.exists():
                        local_img_path = candidate
                        break
                if local_img_path:
                    try:
                        fg_img = Image.open(local_img_path).convert("RGBA")
                        content_width = image_width - 2 * (x_padding + shadow_radius)
                        ratio = content_width / fg_img.width
                        new_height = int(fg_img.height * ratio)
                        fg_img = fg_img.resize((content_width, new_height))
                        img_block = Image.new("RGBA", (image_width, new_height + 10), (0,0,0,0))
                        img_block.paste(fg_img, (x_padding + shadow_radius, 5))
                        group_image_blocks.append(img_block)
                    except Exception:
                        pass

        # Add images once at the end of the group
        group_images.extend(group_image_blocks)
        
        # Combine group images into one block with background
        if group_images:
            total_group_height = sum(img.height for img in group_images) + y_padding * 2 + shadow_radius * 2
            group_final_img = Image.new("RGBA", (image_width, total_group_height), (0,0,0,0))
            draw_group = ImageDraw.Draw(group_final_img)
             # Draw background for the whole group
            draw_group.rectangle(
                [shadow_radius, shadow_radius, image_width - shadow_radius, total_group_height - shadow_radius],
                fill=(0, 0, 0, int(0.3 * 255)),
            )
            
            y_curr = y_padding + shadow_radius
            for img in group_images:
                group_final_img.alpha_composite(img, (0, int(y_curr)))
                y_curr += img.height
            
            images.append(group_final_img)

    # Combine all blocks
    total_height = sum(img.height for img in images) + len(images) * section_spacing
    final_img = Image.new("RGBA", (image_width, total_height), color=(255, 255, 255, 0))

    y_offset = 0
    for img in images:
        final_img.paste(img, (0, y_offset))
        y_offset += img.height + section_spacing

    return final_img


@to_thread
def draw_text_block(title, lines, width, title_font, content_font, title_color, content_color, x_pad, y_pad, shadow_rad, line_sp):
    # Calculate height
    content_lines = []
    for line in lines:
        content_lines.extend(_wrap_pil_text(line, content_font, width - 2 * (x_pad + shadow_rad)))
    
    header_h = title_font.size + line_sp * 2
    content_h = len(content_lines) * (content_font.size + line_sp)
    total_h = header_h + content_h + y_pad * 2 + shadow_rad * 2

    img = Image.new("RGBA", (width, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [shadow_rad, shadow_rad, width - shadow_rad, total_h - shadow_rad],
        fill=(0, 0, 0, int(0.3 * 255)),
    )

    curr_y = y_pad + shadow_rad
    draw.text((x_pad + shadow_rad, curr_y), title, font=title_font, fill=title_color)
    curr_y += header_h

    for line in content_lines:
        draw.text((x_pad + shadow_rad, curr_y), line, font=content_font, fill=content_color)
        curr_y += content_font.size + line_sp
        
    return img


@to_thread
def draw_mixed_text(desc_text, input_list, width, font, color, x_pad, y_pad, shadow_rad, line_sp):
    # Prepare content segments
    segments = []
    parts = re.split(r"{(\d+)}", desc_text)

    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Text part
            if part:
                segments.append({"type": "text", "content": _clean_wiki_text(part)})
        else:
            # Index part
            if part.isdigit():
                idx = int(part)
                if idx < len(input_list):
                    input_name = input_list[idx]
                    icon_path = MAP_FORTE_PATH / f"{input_name}.webp"
                    if icon_path.exists():
                        segments.append({"type": "icon", "content": input_name, "path": icon_path})
                    else:
                        segments.append({"type": "text", "content": input_name})
                else:
                    segments.append({"type": "text", "content": f"{{{part}}}"})
            else:
                segments.append({"type": "text", "content": f"{{{part}}}"})

    # Draw to calculate height first? No, draw directly to a large canvas and crop.
    temp_h = 2000
    img = Image.new("RGBA", (width, temp_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    current_x = x_pad + shadow_rad
    current_y = 0 # Relative to block
    max_width = width - shadow_rad - x_pad - shadow_rad
    row_height = 0
    font_size = font.size

    for seg in segments:
        if seg["type"] == "text":
            text = seg["content"]
            for char in text:
                if char == '\\n':
                    current_y += (row_height if row_height > 0 else font_size) + line_sp
                    current_x = x_pad + shadow_rad
                    row_height = 0
                    continue

                bbox = draw.textbbox((0, 0), char, font=font)
                char_w = bbox[2] - bbox[0]
                char_h = bbox[3] - bbox[1]

                if current_x + char_w > max_width:
                    current_y += (row_height if row_height > 0 else font_size) + line_sp
                    current_x = x_pad + shadow_rad
                    row_height = 0

                draw.text((current_x, current_y), char, font=font, fill=color)
                current_x += char_w
                row_height = max(row_height, char_h)

        elif seg["type"] == "icon":
            icon_size = font_size + 4
            if current_x + icon_size > max_width:
                current_y += (row_height if row_height > 0 else font_size) + line_sp
                current_x = x_pad + shadow_rad
                row_height = 0

            icon = Image.open(seg["path"]).convert("RGBA")
            icon = icon.resize((icon_size, icon_size))
            img.alpha_composite(icon, (int(current_x), int(current_y)))
            current_x += icon_size + 2
            row_height = max(row_height, icon_size)

    final_h = current_y + row_height + line_sp
    return img.crop((0, 0, width, int(final_h)))


async def draw_char_skill_pil(char_id: str):
    char_model: Optional[CharacterModel] = get_char_model(char_id)
    if char_model is None:
        return ""

    _, char_pile = await get_role_pile(char_id)

    char_pic = char_pile.resize((600, int(600 / char_pile.size[0] * char_pile.size[1])))

    char_bg = Image.open(TEXT_PATH / "title_bg.png")
    char_bg = char_bg.resize((1000, int(1000 / char_bg.size[0] * char_bg.size[1])))
    char_bg_draw = ImageDraw.Draw(char_bg)
    # 名字
    char_bg_draw.text((580, 120), f"{char_model.name}", "black", waves_font_70, "lm")
    # 稀有度
    rarity_pic = Image.open(TEXT_PATH / f"rarity_{char_model.starLevel}.png")
    rarity_pic = rarity_pic.resize((180, int(180 / rarity_pic.size[0] * rarity_pic.size[1])))

    # 90级别数据
    max_stats: Stats = char_model.get_max_level_stat()
    char_stats = await parse_char_stats(max_stats)

    # 技能
    char_skill = await parse_char_skill(char_model.skillTree)

    card_img = get_waves_bg(1000, char_bg.size[1] + char_skill.size[1] + 50, "bg6")

    char_bg.alpha_composite(char_pic, (0, -100))
    char_bg.alpha_composite(char_stats, (580, 340))
    char_bg.alpha_composite(rarity_pic, (560, 160))
    await draw_char_materials(char_model, char_bg, 580, 210)
    card_img.paste(char_bg, (0, -5), char_bg)
    card_img.alpha_composite(char_skill, (0, 600))

    card_img = add_footer(card_img, 800, 20, color="white")
    card_img = await convert_img(card_img)
    return card_img


async def draw_char_chain_pil(char_id: str):
    char_model: Optional[CharacterModel] = get_char_model(char_id)
    if char_model is None:
        return ""

    _, char_pile = await get_role_pile(char_id)

    char_pic = char_pile.resize((600, int(600 / char_pile.size[0] * char_pile.size[1])))

    char_bg = Image.open(TEXT_PATH / "title_bg.png")
    char_bg = char_bg.resize((1000, int(1000 / char_bg.size[0] * char_bg.size[1])))
    char_bg_draw = ImageDraw.Draw(char_bg)
    # 名字
    char_bg_draw.text((580, 120), f"{char_model.name}", "black", waves_font_70, "lm")
    # 稀有度
    rarity_pic = Image.open(TEXT_PATH / f"rarity_{char_model.starLevel}.png")
    rarity_pic = rarity_pic.resize((180, int(180 / rarity_pic.size[0] * rarity_pic.size[1])))

    # 90级别数据
    max_stats: Stats = char_model.get_max_level_stat()
    char_stats = await parse_char_stats(max_stats)

    # 命座
    char_chain = await parse_char_chain(char_model.chains)

    card_img = get_waves_bg(1000, char_bg.size[1] + char_chain.size[1] + 50, "bg6")

    char_bg.alpha_composite(char_pic, (0, -100))
    char_bg.alpha_composite(char_stats, (580, 340))
    char_bg.alpha_composite(rarity_pic, (560, 160))
    card_img.paste(char_bg, (0, -5), char_bg)
    card_img.alpha_composite(char_chain, (0, 600))

    card_img = add_footer(card_img, 800, 20, color="white")
    card_img = await convert_img(card_img)
    return card_img


@to_thread
def parse_char_stats(max_stats: Stats):
    labels = ["基础生命", "基础攻击", "基础防御"]
    values = [f"{max_stats.life:.0f}", f"{max_stats.atk:.0f}", f"{max_stats.def_:.0f}"]
    rows = [(label, value) for label, value in zip(labels, values)]

    col_count = sum(len(row) for row in rows)
    cell_width = 400
    cell_height = 40
    table_width = cell_width
    table_height = col_count * cell_height

    image = Image.new("RGBA", (table_width, table_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    # 绘制表格
    for row_index, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            # 计算单元格位置
            x0 = col_index * cell_width / 2
            y0 = row_index * cell_height
            x1 = x0 + cell_width / 2
            y1 = y0 + cell_height

            # 绘制矩形边框
            _i = 0.8 if row_index % 2 == 0 else 1
            draw.rectangle([x0, y0, x1, y1], fill=(40, 40, 40, int(_i * 255)), outline=GREY)

            # 计算文本位置以居中
            bbox = draw.textbbox((0, 0), cell, font=waves_font_24)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x0 + (cell_width / 2 - text_width) / 2
            text_y = y0 + (cell_height - text_height) / 2

            # 绘制文本
            draw.text((text_x, text_y), cell, fill="white", font=waves_font_24)

    return image


@to_thread
def parse_char_chain(data: Dict[int, Chain]):
    y_padding = 20  # 初始位移
    x_padding = 20  # 初始位移
    line_spacing = 10  # 行间距
    block_line_spacing = 50  # 块行间距
    image_width = 1000  # 每个图像的宽度
    shadow_radius = 20  # 阴影半径

    title_color = SPECIAL_GOLD
    title_font_size = 40
    title_font = waves_font_origin(title_font_size)

    detail_color = "white"
    detail_color_size = 30
    detail_font = waves_font_origin(detail_color_size)

    images = []
    for chain_num in data:
        item = data[chain_num]
        # 拼接文本
        title = item.name
        desc = clean_tags(item.get_desc_detail())

        # 分行显示标题
        wrapped_title = textwrap.fill(title, width=20)
        wrapped_desc = textwrap.fill(desc, width=31)

        # 获取每行的宽度，确保不会超过设定的 image_width
        lines_title = wrapped_title.split("\n")
        lines_desc = wrapped_desc.split("\n")

        # 计算总的绘制高度
        total_text_height = y_padding + block_line_spacing + shadow_radius * 2
        total_text_height += len(lines_title) * (title_font_size + line_spacing)  # 标题部分的总高度
        total_text_height += len(lines_desc) * (detail_color_size + line_spacing)  # 描述部分的总高度

        img = Image.new(
            "RGBA",
            (image_width, total_text_height),
            color=(255, 255, 255, 0),
        )
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [
                shadow_radius,
                shadow_radius,
                image_width - shadow_radius,
                total_text_height - shadow_radius,
            ],
            fill=(0, 0, 0, int(0.3 * 255)),
        )

        # 绘制标题文本
        y_offset = y_padding + shadow_radius
        x_offset = x_padding + shadow_radius
        for line in lines_title:
            draw.text(
                (x_offset, y_offset),
                line,
                font=title_font,
                fill=title_color,
            )
            y_offset += title_font.size + line_spacing

        y_offset += block_line_spacing

        # 绘制描述文本
        for line in lines_desc:
            draw.text(
                (x_offset, y_offset),
                line,
                font=detail_font,
                fill=detail_color,
            )
            y_offset += detail_font.size + line_spacing

        images.append(img)

    # 拼接所有图像
    total_height = sum(img.height for img in images)
    final_img = Image.new("RGBA", (image_width, total_height), color=(255, 255, 255, 0))

    y_offset = 0
    for img in images:
        final_img.paste(img, (0, y_offset))
        y_offset += img.height

    return final_img


async def parse_char_skill(data: Dict[str, Dict[str, Skill]]):
    keys = [
        ("常态攻击", "1", ["12", "13"]),
        ("共鸣技能", "2", ["10", "14"]),
        ("共鸣回路", "7", ["4", "5"]),
        ("共鸣解放", "3", ["11", "15"]),
        ("变奏技能", "6", ["9", "16"]),
        ("延奏技能", "8", []),
        ("谐度破坏", "17", []),
    ]

    content_w = 900
    rate_imgs: Dict[str, Optional[Image.Image]] = {}
    for skill_type, skill_tree_id, _relate in keys:
        if skill_tree_id not in data:
            continue
        item = data[skill_tree_id]["skill"]
        rate_imgs[skill_tree_id] = await parse_char_skill_rate(item.level, content_w)

    return await _compose_char_skill(data, keys, rate_imgs)


@to_thread
def _compose_char_skill(data, keys, rate_imgs):
    image_width = 1000
    card_x = 30
    card_w = 940
    content_x = 50
    content_w = 900
    title_color = SPECIAL_GOLD
    title_font = waves_font_origin(30)
    subtitle_font = waves_font_origin(18)
    heading_font = waves_font_origin(18)
    detail_font = waves_font_origin(20)
    line_gap = 8

    images = []
    for skill_type, skill_tree_id, relate_skill_tree_ids in keys:
        if skill_tree_id not in data:
            continue
        item = data[skill_tree_id]["skill"]

        desc = _clean_wiki_text(item.get_desc_detail())
        if skill_type == "谐度破坏" and not desc.strip():
            desc = "目标【偏谐值】满时，可对其造成【谐度破坏】伤害。"

        line_items = [
            ("text", line)
            for line in _wrap_pil_text(desc, detail_font, content_w)
        ]

        for relate_id in relate_skill_tree_ids:
            if relate_id not in data:
                continue
            relate_item = data[relate_id]["skill"]
            _type = relate_item.type if relate_item.type else "属性加成"
            relate_title = f"{_type}: {relate_item.name}"
            relate_desc = _clean_wiki_text(relate_item.get_desc_detail())
            line_items.append(("space", ""))
            line_items.extend(("heading", line) for line in _wrap_pil_text(relate_title, heading_font, content_w))
            line_items.extend(("text", line) for line in _wrap_pil_text(relate_desc, detail_font, content_w))

        rate_img = rate_imgs.get(skill_tree_id)
        body_h = 0
        for kind, _line in line_items:
            if kind == "space":
                body_h += 10
            elif kind == "heading":
                body_h += heading_font.size + line_gap
            else:
                body_h += detail_font.size + line_gap
        if rate_img:
            body_h += 16 + rate_img.height

        total_text_height = 82 + body_h + 26

        img = Image.new(
            "RGBA",
            (image_width, total_text_height),
            color=(255, 255, 255, 0),
        )
        draw = ImageDraw.Draw(img, "RGBA")
        draw.rounded_rectangle(
            [card_x, 0, card_x + card_w, total_text_height - 16],
            radius=8,
            fill=(20, 20, 25, 220),
            outline=(255, 255, 255, 24),
            width=1,
        )
        draw.text((content_x, 35), skill_type, title_color, title_font, "lm")

        subtitle = item.name or ""
        if subtitle:
            sub_w = _font_width(subtitle, subtitle_font) + 22
            draw.rounded_rectangle(
                (content_x + content_w - sub_w, 20, content_x + content_w, 50),
                radius=15,
                fill=(255, 255, 255, 22),
                outline=(255, 255, 255, 35),
                width=1,
            )
            draw.text((content_x + content_w - sub_w + 11, 35), subtitle, (190, 190, 190), subtitle_font, "lm")
        draw.line((content_x, 64, content_x + content_w, 64), fill=(255, 255, 255, 28), width=1)

        y_offset = 84
        for kind, line in line_items:
            if kind == "space":
                y_offset += 10
                continue
            font = heading_font if kind == "heading" else detail_font
            fill = title_color if kind == "heading" else (220, 220, 220)
            draw.text((content_x, y_offset), line, font=font, fill=fill)
            y_offset += font.size + line_gap

        if rate_img:
            img.alpha_composite(rate_img, (content_x, y_offset + 8))

        images.append(img)

    # 拼接所有图像
    total_height = sum(img.height for img in images) + max(0, len(images) - 1) * 12
    final_img = Image.new("RGBA", (image_width, total_height), color=(255, 255, 255, 0))

    y_offset = 0
    for img in images:
        final_img.paste(img, (0, y_offset))
        y_offset += img.height + 12

    return final_img


@to_thread
def parse_char_skill_rate(skillLevels: Optional[Dict[str, SkillLevel]], table_width: int = 900):
    if not skillLevels:
        return
    rows = []
    labels = [
        "等级",
        "Lv 6",
        "Lv 7",
        "Lv 8",
        "Lv 9",
        "Lv 10",
    ]
    rows.append(labels)

    for _, skillLevel in skillLevels.items():
        row = [skillLevel.name]
        # 应用 format 格式化数值
        param_values = skillLevel.param[0][5:10]
        if skillLevel.format:
            # 使用 format 字符串格式化每个值
            formatted_values = [f"{v}{skillLevel.format}" for v in param_values]
            row.extend(formatted_values)
        else:
            row.extend(param_values)
        rows.append(row)

    font = waves_font_12
    offset = 0
    col_count = len(rows)
    first_col_width = 220
    cell_width = int((table_width - first_col_width) / 5)
    cell_height = 40
    table_height = col_count * cell_height

    image = Image.new("RGBA", (table_width, table_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    # 绘制表格
    for row_index, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            # 计算单元格位置
            if col_index == 0:
                x0 = offset
                x1 = first_col_width
            else:
                x0 = first_col_width + (col_index - 1) * cell_width
                x1 = x0 + cell_width

            y0 = row_index * cell_height
            y1 = y0 + cell_height

            # 绘制矩形边框
            fill = (255, 255, 255, 25) if row_index == 0 else (0, 0, 0, 72 if row_index % 2 == 0 else 105)
            draw.rectangle([x0, y0, x1, y1], fill=fill, outline=(255, 255, 255, 24))

            # 计算文本位置以居中
            bbox = draw.textbbox((0, 0), cell, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            if col_index == 0:
                text_x = (x0 + first_col_width - text_width) / 2
            else:
                text_x = x0 + (cell_width - text_width) / 2
            text_y = y0 + (cell_height - text_height) / 2

            # 绘制文本
            wrapped_cell = textwrap.wrap(cell, width=18)
            if len(wrapped_cell) > 1:
                text_y_temp = text_y - font.size
                for line in wrapped_cell:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_width = bbox[2] - bbox[0]
                    if col_index == 0:
                        text_x = (x0 + first_col_width - text_width) / 2
                    else:
                        text_x = x0 + (cell_width - text_width) / 2
                    draw.text(
                        (text_x, text_y_temp),
                        line,
                        fill="white",
                        font=font,
                    )
                    text_y_temp += font.size + 7
            else:
                draw.text(
                    (text_x, text_y),
                    cell,
                    fill="white",
                    font=font,
                )

    return image
