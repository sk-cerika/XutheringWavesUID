import asyncio
import copy
import textwrap
from pathlib import Path
from collections import defaultdict

from PIL import Image, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.pool import to_thread
from gsuid_core.utils.image.convert import convert_img

from ..utils.image import (
    SPECIAL_GOLD,
    add_footer,
    get_waves_bg,
    get_square_weapon,
    get_attribute_effect,
)
from ..utils.resource.constant import WEAPON_TYPE_ID_MAP
from ..wutheringwaves_config import PREFIX
from ..utils.ascension.sonata import sonata_id_data
from ..utils.ascension.weapon import weapon_id_data
from ..utils.fonts.waves_fonts import waves_font_16, waves_font_18, waves_font_24
from .other_wiki_render import draw_weapon_list_render, draw_sonata_list_render

TEXT_PATH = Path(__file__).parent.parent / "wutheringwaves_develop" / "texture2d"
star_1 = Image.open(TEXT_PATH / "star-1.png")
star_2 = Image.open(TEXT_PATH / "star-2.png")
star_3 = Image.open(TEXT_PATH / "star-3.png")
star_4 = Image.open(TEXT_PATH / "star-4.png")
star_5 = Image.open(TEXT_PATH / "star-5.png")
star_img_map = {
    1: star_1,
    2: star_2,
    3: star_3,
    4: star_4,
    5: star_5,
}

SONATA_DESC_WIDTH = 18
SONATA_DESC_LINE_HEIGHT = 25
UTILS_TEXTURE_PATH = Path(__file__).parent.parent / "utils" / "texture2d"


def _get_cover_waves_bg(width: int, height: int, bg: str = "bg6") -> Image.Image:
    source = Image.open(UTILS_TEXTURE_PATH / f"{bg}.jpg").convert("RGBA")
    scale = max(width / source.width, height / source.height)
    resized_size = (
        max(width, int(source.width * scale) + 1),
        max(height, int(source.height * scale) + 1),
    )
    source = source.resize(resized_size, Image.Resampling.LANCZOS)
    left = (source.width - width) // 2
    top = (source.height - height) // 2
    return source.crop((left, top, left + width, top + height))


def _wrap_sonata_desc(desc: str) -> list[str]:
    return textwrap.wrap(desc or "", width=SONATA_DESC_WIDTH) or [""]


def _calc_sonata_card_height(sonata: dict) -> int:
    height = 30
    for _, effect in sorted(sonata["set"].items(), key=lambda x: int(x[0])):
        height += len(_wrap_sonata_desc(effect.get("desc", ""))) * SONATA_DESC_LINE_HEIGHT + 5
    return max(height, 60)


def _calc_sonata_canvas_height(sorted_groups: list[tuple[str, list[dict]]]) -> int:
    y_offset = 100
    for _, sonatas in sorted_groups:
        for i in range(0, len(sonatas), 2):
            row_height = _calc_sonata_card_height(sonatas[i])
            if i + 1 < len(sonatas):
                row_height = max(row_height, _calc_sonata_card_height(sonatas[i + 1]))
            y_offset += row_height + 20
        y_offset += 20
    return max(y_offset + 90, 320)


def _draw_sonata_card_sync(img: Image.Image, draw: ImageDraw.ImageDraw, sonata: dict, fetter_icon: Image.Image, x: int, y: int) -> int:
    fetter_icon = fetter_icon.resize((50, 50))
    img.paste(fetter_icon, (x, y), fetter_icon)

    text_x = x + 60
    draw.text((text_x, y), sonata["name"], font=waves_font_24, fill=SPECIAL_GOLD)

    current_y = y + 30
    for set_num, effect in sorted(sonata["set"].items(), key=lambda x: int(x[0])):
        draw.text((text_x, current_y), f"{set_num}件:", font=waves_font_16, fill="white")
        wrapped_desc = _wrap_sonata_desc(effect.get("desc", ""))
        for j, line in enumerate(wrapped_desc):
            draw.text(
                (text_x + 40, current_y + j * SONATA_DESC_LINE_HEIGHT),
                line,
                font=waves_font_16,
                fill="#AAAAAA",
            )
        current_y += len(wrapped_desc) * SONATA_DESC_LINE_HEIGHT + 5

    return current_y - y


async def draw_weapon_list(weapon_type: str):
    """武器列表 - 优先使用HTML渲染，失败则回退到PIL"""
    # 尝试HTML渲染
    try:
        result = await draw_weapon_list_render(weapon_type)
        if result:
            return result
    except Exception as e:
        logger.warning(f"[鸣潮] 武器列表HTML渲染失败，回退到PIL: {e}")

    # 回退到PIL绘制
    return await _draw_weapon_list_pil(weapon_type)


async def _draw_weapon_list_pil(weapon_type: str):
    """武器列表 - PIL绘制"""
    # 确保数据已加载
    if not weapon_id_data:
        return "[鸣潮][武器列表]暂无数据"

    if weapon_type:
        weapon_type = weapon_type.replace("臂甲", "臂铠").replace("讯刀", "迅刀")

    # 创建反向映射（中文类型 → 数字类型）
    reverse_type_map = {v: k for k, v in WEAPON_TYPE_ID_MAP.items()}
    logger.debug(f"正在处理武器类型：{weapon_type}")
    logger.debug(f"正在处理武器列表：{reverse_type_map}")

    # 按武器类型分组收集武器数据
    weapon_groups = defaultdict(list)
    target_type = reverse_type_map.get(weapon_type)
    logger.debug(f"成功处理：{target_type}")

    for weapon_id, data in weapon_id_data.items():
        name = data.get("name", "未知武器")
        star_level = data.get("starLevel", 0)
        w_type = data.get("type", 0)  # 注意：避免与参数同名冲突
        effect_name = data.get("effectName", "")

        # 如果找到目标类型，只收集该类型武器
        if target_type is not None:
            if w_type == target_type:
                weapon_groups[w_type].append(
                    {"id": weapon_id, "name": name, "star_level": star_level, "effect_name": effect_name}
                )
        # 否则收集所有武器
        else:
            weapon_groups[w_type].append(
                {"id": weapon_id, "name": name, "star_level": star_level, "effect_name": effect_name}
            )

    # 按类型从小到大排序
    sorted_groups = sorted(weapon_groups.items(), key=lambda x: x[0])

    # 预取所有武器图标
    all_ids = [w["id"] for _, ws in sorted_groups for w in ws]
    icon_results = await asyncio.gather(*[get_square_weapon(wid) for wid in all_ids])
    icon_map = dict(zip(all_ids, icon_results))

    img = await _compose_weapon_list(sorted_groups, target_type, icon_map)
    return await convert_img(img)


@to_thread
def _compose_weapon_list(sorted_groups, target_type, icon_map):
    # 每行武器数量（单类型4列，全部类型9列）
    weapons_per_row = 9 if target_type is None else 4
    # 图标大小
    icon_size = 120
    # 水平间距
    horizontal_spacing = 150

    # 创建更宽的背景图（1800宽度）
    width = horizontal_spacing * (weapons_per_row - 1) + icon_size + 80
    img = get_waves_bg(width, 4000, "bg6")
    draw = ImageDraw.Draw(img)

    # 绘制标题
    if target_type is not None:
        type_name = WEAPON_TYPE_ID_MAP.get(target_type, "")
        title = f"{type_name}武器一览"
    else:
        title = "武器一览"
    draw.text((int(width / 2), 30), title, font=waves_font_24, fill=SPECIAL_GOLD, anchor="mt")
    draw.text(
        (int(width / 2), 63),
        f"使用【{PREFIX}'武器名'图鉴】查询具体介绍",
        font=waves_font_16,
        fill="#AAAAAA",
        anchor="mt",
    )

    # 当前绘制位置
    y_offset = 80

    # 添加组间分隔线
    draw.line((40, y_offset, width - 40, y_offset), fill=SPECIAL_GOLD, width=1)
    # 绘制武器效果名（灰色）y_offset += 20

    # 按武器类型遍历所有分组
    for weapon_type, weapons in sorted_groups:
        # 获取类型名称
        type_name = WEAPON_TYPE_ID_MAP.get(weapon_type, f"未知类型{weapon_type}")

        # 绘制类型标题
        draw.text((50, y_offset), type_name, font=waves_font_24, fill=SPECIAL_GOLD)
        y_offset += 40

        # 按星级降序排序（高星在前）
        weapons.sort(key=lambda x: (-x["star_level"], x["name"]))

        # 计算该组需要的行数
        rows = (len(weapons) + weapons_per_row - 1) // weapons_per_row

        # 计算图标和名称的高度
        name_height = 25
        effect_name_height = 20
        row_height = icon_size + name_height + effect_name_height + 30

        # 绘制武器组
        for row in range(rows):
            row_y = y_offset  # 当前行起始位置

            # 绘制该行所有武器
            for col in range(weapons_per_row):
                index = row * weapons_per_row + col
                if index >= len(weapons):
                    break

                weapon = weapons[index]

                # 计算位置（居中布局）
                x_pos = 40 + col * horizontal_spacing

                # 获取武器图标（预取）
                weapon_icon = icon_map[weapon["id"]]
                weapon_icon = weapon_icon.resize((icon_size, icon_size))

                # 获取并调整武器背景框
                star_img = copy.deepcopy(star_img_map[weapon["star_level"]])
                star_img = star_img.resize((icon_size, icon_size))
                img.alpha_composite(weapon_icon, (x_pos, row_y))
                img.alpha_composite(star_img, (x_pos, row_y))

                # 绘制武器名称
                draw.text(
                    (x_pos + icon_size // 2, row_y + icon_size + 10),
                    weapon["name"],
                    font=waves_font_18,
                    fill="white",
                    anchor="mt",
                )

                # 绘制武器效果名（灰色）
                draw.text(
                    (x_pos + icon_size // 2, row_y + icon_size + 35),
                    weapon["effect_name"],
                    font=waves_font_16,
                    fill="#AAAAAA",  # 灰色
                    anchor="mt",
                )

            # 移动到下一行
            y_offset += row_height

        # 添加组间分隔线
        draw.line((40, y_offset, width - 40, y_offset), fill=SPECIAL_GOLD, width=1)
        y_offset += 20

    # 裁剪图片到实际高度
    img = img.crop((0, 0, width, y_offset + 50))
    img = add_footer(img, int(width / 2), 10)  # 页脚居中
    return img


async def draw_sonata_list(version: str = ""):
    """声骸套装列表 - 优先使用HTML渲染，失败则回退到PIL"""
    # 尝试HTML渲染
    try:
        result = await draw_sonata_list_render(version)
        if result:
            return result
    except Exception as e:
        logger.warning(f"[鸣潮] 套装列表HTML渲染失败，回退到PIL: {e}")

    # 回退到PIL绘制
    return await _draw_sonata_list_pil(version)


async def _draw_sonata_list_pil(version: str = ""):
    """声骸套装列表 - PIL绘制"""
    if not sonata_id_data:
        return "[鸣潮][套装列表]暂无数据"

    if version:
        version = version.split(".")[0] + ".0"

    sonata_groups = defaultdict(list)
    for data in sonata_id_data.values():
        name = data.get("name", "未知套装")
        set_list = data.get("set", {})
        from_version = data.get("version", "10.0")

        if version and from_version != version:
            continue

        sonata_groups[from_version].append({"name": name, "set": set_list})

    if version and not sonata_groups:
        return f"[鸣潮][套装列表]未找到版本 {version} 的套装数据"

    sorted_groups = sorted(sonata_groups.items(), key=lambda x: float(x[0]), reverse=True)

    # 预取所有合鸣效果图标
    all_names = [s["name"] for _, ss in sorted_groups for s in ss]
    icon_results = await asyncio.gather(*[get_attribute_effect(n) for n in all_names])
    icon_map = dict(zip(all_names, icon_results))

    img = await _compose_sonata_list(sorted_groups, version, icon_map)
    return await convert_img(img)


@to_thread
def _compose_sonata_list(sorted_groups, version, icon_map):
    canvas_height = _calc_sonata_canvas_height(sorted_groups)
    img = _get_cover_waves_bg(900, canvas_height, "bg6")
    draw = ImageDraw.Draw(img)

    # 绘制标题
    title = f"声骸套装一览 - {version}版本" if version else "声骸套装一览"
    draw.text((440, 30), title, font=waves_font_24, fill=SPECIAL_GOLD, anchor="mt")

    # 当前绘制位置
    y_offset = 80
    # 添加组间分隔线
    draw.line((40, y_offset, 860, y_offset), fill=SPECIAL_GOLD, width=1)
    y_offset += 20

    # 按字数从小到大遍历所有分组
    for _, sonatas in sorted_groups:
        # 对组内套装按名称排序
        sonatas.sort(key=lambda x: x["name"])

        # 将组内套装分成两列展示
        for i in range(0, len(sonatas), 2):
            current_y = y_offset  # 记录当前行的起始Y位置

            # 第一列套装
            sonata1 = sonatas[i]
            max_height = _draw_sonata_card_sync(img, draw, sonata1, icon_map[sonata1["name"]], 40, current_y)

            # 第二列套装（如果有）
            if i + 1 < len(sonatas):
                sonata2 = sonatas[i + 1]
                max_height = max(max_height, _draw_sonata_card_sync(img, draw, sonata2, icon_map[sonata2["name"]], 460, current_y))

            # 移动到下一行（使用当前行最大高度 + 间距）
            y_offset += max_height + 20  # 增加行间距

        # 添加组间分隔线
        draw.line((40, y_offset, 860, y_offset), fill=SPECIAL_GOLD, width=1)
        y_offset += 20

    # 裁剪图片到实际高度，保留页脚空间，且不超过已经生成的背景画布。
    img = img.crop((0, 0, 900, min(img.height, y_offset + 90)))
    img = add_footer(img, 450, 10)
    return img
