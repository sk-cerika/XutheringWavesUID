from typing import Any, Dict, List, Union
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import httpx
from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger
from gsuid_core.utils.image.convert import convert_img

from .model import WavesPool
from ..utils.util import timed_async_cache
from ..utils.image import (
    SPECIAL_GOLD,
    WAVES_MOLTEN,
    get_ICON,
    add_footer,
    get_waves_bg,
    get_square_avatar,
    get_square_weapon,
    get_random_share_bg,
)
from ..utils.api.wwapi import GET_POOL_LIST
from ..utils.name_convert import char_name_to_char_id, easy_id_to_name, weapon_name_to_weapon_id
from ..utils.fonts.waves_fonts import waves_font_30, waves_font_58

TEXT_PATH = Path(__file__).parent / "texture2d"
bar = Image.open(TEXT_PATH / "bar.png")
avatar_mask = Image.open(TEXT_PATH / "avatar_mask.png")


@timed_async_cache(expiration=3600, condition=lambda x: isinstance(x, list))
async def get_pool_data() -> Union[List, None]:
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                GET_POOL_LIST,
                headers={
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(10),
            )
            if res.status_code == 200:
                return res.json().get("data", [])
        except Exception as e:
            logger.exception(f"获取卡池数据失败: {e}")


async def clean_pool_data():
    result_char = {
        "four2num": defaultdict(int),
        "four2endtime": defaultdict(int),
        "five2num": defaultdict(int),
        "five2endtime": defaultdict(int),
    }
    result_weapon = {
        "four2num": defaultdict(int),
        "four2endtime": defaultdict(int),
        "five2num": defaultdict(int),
        "five2endtime": defaultdict(int),
    }

    fixed_four_repeat = set()

    now = datetime.now()
    pools = await get_pool_data()
    if not pools:
        return None, None

    char_up_end_time = None
    weapon_up_end_time = None

    for temp_pool in pools:
        pool = WavesPool.model_validate(temp_pool)

        end_time = datetime.strptime(pool.end_time, "%Y-%m-%d %H:%M:%S")

        total_seconds = int((now - end_time).total_seconds())

        if pool.pool_type == "角色活动唤取":
            if char_up_end_time is not None and total_seconds != char_up_end_time:
                continue

            for five_star in pool.five_star_ids:
                result_char["five2num"][five_star] += 1
                result_char["five2endtime"][five_star] = total_seconds

            if f"{pool.end_time}_{pool.pool_type}" in fixed_four_repeat:
                continue

            for four_star in pool.four_star_ids:
                result_char["four2num"][four_star] += 1
                result_char["four2endtime"][four_star] = total_seconds

            fixed_four_repeat.add(f"{pool.end_time}_{pool.pool_type}")

            # is up
            if total_seconds < 0 and char_up_end_time is None:
                char_up_end_time = total_seconds
        else:
            if weapon_up_end_time is not None and total_seconds != weapon_up_end_time:
                continue

            for five_star in pool.five_star_ids:
                result_weapon["five2num"][five_star] += 1
                result_weapon["five2endtime"][five_star] = total_seconds

            if f"{pool.end_time}_{pool.pool_type}" in fixed_four_repeat:
                continue

            for four_star in pool.four_star_ids:
                result_weapon["four2num"][four_star] += 1
                result_weapon["four2endtime"][four_star] = total_seconds

            fixed_four_repeat.add(f"{pool.end_time}_{pool.pool_type}")

            # is up
            if total_seconds < 0 and weapon_up_end_time is None:
                weapon_up_end_time = total_seconds

    return result_char, result_weapon


async def get_pool_data_by_type(query_type: str, star: int):
    result_char, result_weapon = await clean_pool_data()

    if not result_char or not result_weapon:
        return "未复刻数据获取失败，请稍后再试"

    if query_type == "角色":
        result = result_char
    else:
        result = result_weapon

    if star == 5:
        data_group = result["five2num"]
    else:
        data_group = result["four2num"]

    if len(data_group) == 0:
        return "暂无数据"

    title_h = 500
    bar_star_h = 110
    totalNum = len(data_group)
    h = title_h + totalNum * bar_star_h + 100

    share_bg = await get_random_share_bg()

    # 预加载头像 / 武器图
    data_list = []
    if star == 5:
        for resource_id, num in result["five2num"].items():
            data_list.append((resource_id, num, result["five2endtime"][resource_id]))
    else:
        for resource_id, num in result["four2num"].items():
            data_list.append((resource_id, num, result["four2endtime"][resource_id]))
    data_list.sort(key=lambda x: x[2], reverse=True)

    pic_cache: Dict[str, Image.Image] = {}
    for resource_id, _, _ in data_list:
        if resource_id in pic_cache:
            continue
        if query_type == "角色":
            _id = char_name_to_char_id(resource_id) or resource_id
            pic_cache[resource_id] = await get_square_avatar(_id)
        else:
            _id = weapon_name_to_weapon_id(resource_id) or resource_id
            pic_cache[resource_id] = await get_square_weapon(_id)

    card_img = await _render_pool_card(
        share_bg, query_type, star, h, data_list, pic_cache
    )
    return await convert_img(card_img)


@to_thread
def _render_pool_card(
    share_bg: Image.Image,
    query_type: str,
    star: int,
    h: int,
    data_list,
    pic_cache: Dict[str, Image.Image],
) -> Image.Image:
    card_img = get_waves_bg(1050, h, "bg9")

    # title
    share_bg = share_bg.resize((1080, 607))
    share_bg_crop = share_bg.crop((0, 50, 1050, 550))

    # icon
    icon = get_ICON()
    icon = icon.resize((128, 128))
    share_bg_crop.paste(icon, (60, 240), icon)

    # title
    title_text = "卡池倒计时"
    share_bg_draw = ImageDraw.Draw(share_bg_crop)
    share_bg_draw.text((200, 265), title_text, "white", waves_font_58, "lm")

    # 角色/武器
    title_text2 = f"{query_type} {star}星"
    info_block = Image.new("RGBA", (160, 50), color=(255, 255, 255, 0))
    info_block_draw = ImageDraw.Draw(info_block)
    info_block_draw.rounded_rectangle([0, 0, 160, 50], radius=20, fill=WAVES_MOLTEN)
    info_block_draw.text((20, 25), f"{title_text2}", "white", waves_font_30, "lm")
    share_bg_crop.alpha_composite(info_block, (215, 330))

    # 遮罩
    char_mask = Image.open(TEXT_PATH / "char_mask.png").convert("RGBA")
    char_mask_temp = Image.new("RGBA", char_mask.size, (0, 0, 0, 0))
    char_mask_temp.paste(share_bg_crop, (0, 0), char_mask)

    card_img.paste(char_mask_temp, (0, 0), char_mask_temp)

    _draw_pool_char_sync(data_list, query_type, pic_cache, card_img)

    card_img = add_footer(card_img)
    return card_img


def _draw_pool_char_sync(
    data_list,
    query_type: str,
    pic_cache: Dict[str, Image.Image],
    card_img: Image.Image,
):
    for i, data in enumerate(data_list):
        resource_id = data[0]
        up_time = data[1]
        end_time = data[2]

        bar_bg = bar.copy()
        bar_star_draw = ImageDraw.Draw(bar_bg)

        pic = pic_cache[resource_id]

        pic_temp = Image.new("RGBA", pic.size)
        pic_temp.paste(pic.resize((160, 160)), (10, 10))
        pic_temp = pic_temp.resize((160, 160))

        avatar_mask_temp = avatar_mask.copy()
        mask_pic_temp = Image.new("RGBA", avatar_mask_temp.size)
        mask_pic_temp.paste(avatar_mask_temp, (-20, -45), avatar_mask_temp)
        mask_pic_temp = mask_pic_temp.resize((160, 160))
        role_avatar = Image.new("RGBA", (180, 180))
        role_avatar.paste(pic_temp, (0, 0), mask_pic_temp)
        bar_bg.paste(role_avatar, (100, 0), role_avatar)

        color = "white"
        if end_time < 0:
            color = SPECIAL_GOLD

        char_name = easy_id_to_name(resource_id)
        if char_name:
            bar_star_draw.text((300, 50), char_name, color, waves_font_30, "mm")

        # up 次数
        bar_star_draw.text((500, 50), f"UP次数: {up_time}", "white", waves_font_30, "mm")

        # 倒计时
        if end_time >= 0:
            bar_star_draw.text((800, 50), f"{seconds_to_human(end_time)}", color, waves_font_30, "mm")
        else:
            bar_star_draw.text((800, 50), f"{seconds_to_human(end_time)}", color, waves_font_30, "mm")

        card_img.paste(bar_bg, (-20, i * 110 + 530), bar_bg)


def seconds_to_human(seconds: int) -> str:
    if seconds >= 0:
        if seconds >= 86400:
            days = seconds // 86400
            return f"已有 {days} 天未UP"
        elif seconds >= 3600:
            hours = seconds // 3600
            return f"已有 {hours} 小时未UP"
        elif seconds >= 60:
            minutes = seconds // 60
            return f"已有 {minutes} 分钟未UP"
        else:
            return f"已有 {seconds} 秒未UP"
    else:
        if seconds <= -86400:
            days = seconds // 86400
            return f"当前UP({-days}天后关闭)"
        elif seconds <= -3600:
            hours = seconds // 3600
            return f"当前UP({-hours}小时后关闭)"
        elif seconds <= -60:
            minutes = seconds // 60
            return f"当前UP({-minutes}分钟后关闭)"
        else:
            return f"当前UP({-seconds}秒后关闭)"
