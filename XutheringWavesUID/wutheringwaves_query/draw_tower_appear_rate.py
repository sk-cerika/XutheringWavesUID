import time
from typing import Dict, List, Union
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.util import timed_async_cache
from ..utils.image import GREY, get_ICON, add_footer, get_waves_bg, get_square_avatar
from ..utils.api.wwapi import GET_TOWER_APPEAR_RATE, ABYSS_TYPE_MAP_REVERSE
from ..utils.ascension.char import get_char_model
from ..utils.ascension.model import CharacterModel
from ..utils.fonts.waves_fonts import (
    waves_font_20,
    waves_font_30,
    waves_font_36,
    waves_font_58,
)
from ..utils.resource.constant import NAME_ALIAS
from ..wutheringwaves_abyss.period import get_tower_period_number

TEXT_PATH = Path(__file__).parent / "texture2d"


@timed_async_cache(expiration=3600, condition=lambda x: isinstance(x, dict))
async def get_tower_appear_rate_data() -> Union[Dict, None]:
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                GET_TOWER_APPEAR_RATE,
                headers={
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(10),
            )
            if res.status_code == 200:
                return res.json().get("data", [])
        except Exception as e:
            logger.exception(f"获取深塔出场率数据失败: {e}")


async def draw_tower_use_rate(ev: Event):
    data = await get_tower_appear_rate_data()
    if not data:
        return "暂无深塔出场率数据, 请稍后再试"

    filter_type = None
    text = ev.text.strip() if ev.text else ""
    if "左" in text or "残响" in text:
        filter_type = "l4"
    elif "右" in text or "回音" in text:
        filter_type = "r4"
    elif "中" in text or "深境" in text:
        filter_type = "m4"

    title_h = 500
    bar_star_h = 180
    tower_name_bg_h = 100
    footer_h = 50
    if filter_type is None:
        totalNum = 9
        h = title_h + totalNum * bar_star_h + tower_name_bg_h * 3 + footer_h
    else:
        char_num = len(data["appear_rate_list"][0]["rates"])
        totalNum = char_num // 4 + (0 if char_num % 4 == 0 else 1)

        h = title_h + totalNum * bar_star_h + tower_name_bg_h + footer_h

    appear_rate_list = data["appear_rate_list"]

    # 预加载头像
    avatar_cache: Dict[str, Image.Image] = {}
    for i in appear_rate_list:
        if filter_type is not None and i["area_type"] != filter_type:
            continue
        for rate_temp in i["rates"]:
            char_id = rate_temp["char_id"]
            if char_id in avatar_cache:
                continue
            if not get_char_model(char_id):
                continue
            avatar_cache[char_id] = await get_square_avatar(char_id)

    card_img = await _render_tower_use_rate(
        appear_rate_list, filter_type, h, tower_name_bg_h, avatar_cache
    )
    return await convert_img(card_img)


@to_thread
def _render_tower_use_rate(
    appear_rate_list,
    filter_type,
    h,
    tower_name_bg_h,
    avatar_cache: Dict[str, Image.Image],
) -> Image.Image:
    card_img = get_waves_bg(1050, h, "bg9")

    # title
    title_bg = Image.open(TEXT_PATH / "tower.jpg")
    title_bg = title_bg.crop((0, 0, 1050, 500))

    # icon
    icon = get_ICON()
    icon = icon.resize((128, 128))
    title_bg.paste(icon, (60, 240), icon)

    # title
    title_text = "#深塔出场率"
    title_bg_draw = ImageDraw.Draw(title_bg)
    title_bg_draw.text((220, 290), title_text, "white", waves_font_58, "lm")

    # 期次 + 获取时间
    period_label = f"第{get_tower_period_number()}期"
    date_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    title_bg_draw.text((225, 360), period_label, GREY, waves_font_20, "lm")
    try:
        period_w = title_bg_draw.textlength(period_label, font=waves_font_20)
    except Exception:
        period_w = waves_font_20.getsize(period_label)[0]
    title_bg_draw.text(
        (225 + period_w + 16, 360), date_text, GREY, waves_font_20, "lm"
    )

    # 遮罩
    char_mask = Image.open(TEXT_PATH / "char_mask.png").convert("RGBA")
    char_mask_temp = Image.new("RGBA", char_mask.size, (0, 0, 0, 0))
    char_mask_temp.paste(title_bg, (0, 0), char_mask)

    card_img.paste(char_mask_temp, (0, 0), char_mask_temp)

    # 深塔出场率
    start_y = 470
    for i in appear_rate_list:
        area_type: str = i["area_type"]
        if filter_type is not None and area_type != filter_type:
            continue
        rates: List[Dict] = i["rates"]

        tower_name_bg = Image.open(TEXT_PATH / f"tower_name_bg_{area_type}.png")
        tower_name_bg_draw = ImageDraw.Draw(tower_name_bg)
        area_type_text = ABYSS_TYPE_MAP_REVERSE.get(area_type, area_type)
        tower_name_bg_draw.text(
            (170, 50),
            f"{area_type_text}",
            "white",
            waves_font_36,
            "lm",
        )

        card_img.alpha_composite(tower_name_bg, (-50, start_y))

        start_y += tower_name_bg_h

        for rIndex, rate_temp in enumerate(rates):
            char_id = rate_temp["char_id"]
            rate = rate_temp["rate"]
            char_model = get_char_model(char_id)
            if not char_model:
                continue

            avatar = avatar_cache.get(char_id)
            if avatar is None:
                continue
            temp_pic = _build_temp_pic(avatar, char_model, rate)
            temp_pic = temp_pic.resize((200, 157))
            card_img.alpha_composite(
                temp_pic,
                (
                    50 + 240 * (rIndex % 4),
                    start_y + (rIndex // 4) * 180,
                ),
            )

            if filter_type is None and rIndex >= 11:
                break

        if filter_type is None:
            start_y += 180 * 3

    card_img = add_footer(card_img)
    return card_img


def _build_temp_pic(avatar: Image.Image, char_model: CharacterModel, rate: float) -> Image.Image:
    avatar = avatar.resize((180, 180))
    if char_model.starLevel == 5:
        star_fg = Image.open(TEXT_PATH / "star5_fg.png")
        star_bg = Image.open(TEXT_PATH / "star5_bg.png")
    else:
        star_fg = Image.open(TEXT_PATH / "star4_fg.png")
        star_bg = Image.open(TEXT_PATH / "star4_bg.png")

    star_bg_temp = Image.new("RGBA", star_bg.size)
    star_bg_temp.paste(star_bg, (0, 0))
    star_bg_temp.alpha_composite(avatar, (80, -10))

    char_name = NAME_ALIAS.get(char_model.name, char_model.name)
    if len(char_name) <= 2:
        name_bg = Image.new("RGBA", (60, 25), color=(255, 255, 255, 0))
        rank_draw = ImageDraw.Draw(name_bg)
        rank_draw.rectangle([0, 0, 60, 25], fill=(255, 255, 255) + (int(0.9 * 255),))
        rank_draw.text((30, 12), f"{char_name}", "black", waves_font_20, "mm")
    else:
        name_bg = Image.new("RGBA", (80, 25), color=(255, 255, 255, 0))
        rank_draw = ImageDraw.Draw(name_bg)
        rank_draw.rectangle([0, 0, 80, 25], fill=(255, 255, 255) + (int(0.9 * 255),))
        rank_draw.text((40, 12), f"{char_name}", "black", waves_font_20, "mm")

    temp_img = Image.new("RGBA", (256, 200), color=(0, 0, 0, 60))

    temp_img.paste(star_bg_temp, (0, 0))
    temp_img.alpha_composite(star_fg, (0, 0))
    temp_img.alpha_composite(name_bg, (10, 110))
    temp_draw = ImageDraw.Draw(temp_img)
    temp_draw.text((125, 180), f"{rate:.2%}", "white", waves_font_30, "mm")

    return temp_img
