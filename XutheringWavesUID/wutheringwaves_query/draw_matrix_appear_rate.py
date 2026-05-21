import math
import time
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.util import timed_async_cache
from ..utils.image import GREY, get_ICON, add_footer, get_waves_bg
from ..utils.image import get_square_avatar
from ..utils.api.wwapi import GET_MATRIX_APPEAR_RATE
from ..utils.ascension.char import get_char_model
from ..utils.fonts.waves_fonts import (
    waves_font_20,
    waves_font_24,
    waves_font_30,
    waves_font_40,
    waves_font_58,
)
from ..utils.name_convert import (
    alias_to_char_name,
    char_name_to_char_id,
    is_valid_char_name,
)
from ..utils.resource.constant import NAME_ALIAS
from ..wutheringwaves_abyss.period import get_matrix_period_number

TEXT_PATH = Path(__file__).parent / "texture2d"

# (响应 key, 节标题, 单元显示模式: "rate" | "score")
SECTIONS = [
    ("count_top", "热门配队 - 出场率", "rate"),
    ("score_top", "高分配队 - 平均得分", "score"),
]

# ── 整体尺寸 ─────────────────────────────────────────────
CARD_W = 1050
TITLE_H = 500

# ── section 标题条（PIL 自绘） ──
SECTION_BAR_H = 90
SECTION_PAD_TOP = 20
SECTION_PAD_BOT = 20
SECTION_HEADER_H = SECTION_PAD_TOP + SECTION_BAR_H + SECTION_PAD_BOT  # = 130

# ── 队伍卡片网格 ──
TEAM_CELL_W = 495
TEAM_CELL_H = 230
TEAM_CELL_GAP_X = 10
TEAMS_PER_ROW = 2
ROWS_PER_SECTION = 4
EMPTY_SECTION_H = 200

GRID_LEFT_X = 25
SECTION_BAR_W = TEAM_CELL_W * TEAMS_PER_ROW + TEAM_CELL_GAP_X  # 1000

INTER_SECTION_GAP = 30
FOOTER_H = 50


@timed_async_cache(expiration=600, condition=lambda x: isinstance(x, dict))
async def get_matrix_appear_rate_data(char_id: int = 0) -> Union[Dict, None]:
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                GET_MATRIX_APPEAR_RATE,
                params={"char_id": char_id},
                headers={"Content-Type": "application/json"},
                timeout=httpx.Timeout(15),
            )
            if res.status_code == 200:
                return res.json().get("data")
        except Exception as e:
            logger.exception(f"获取矩阵出场率数据失败: {e}")
    return None


def _resolve_char_arg(
    text: str,
) -> Tuple[Optional[int], str, Optional[str]]:
    text = text.strip()
    if not text:
        return None, "", None
    if not is_valid_char_name(text):
        return None, "", f"未识别角色: {text}\n请确认角色名/别名后再试"
    name = alias_to_char_name(text)
    char_id_str = char_name_to_char_id(name)
    if not char_id_str:
        return None, "", f"未识别角色: {text}\n请确认角色名/别名后再试"
    try:
        return int(char_id_str), name, None
    except ValueError:
        return None, "", f"角色 id 解析失败: {char_id_str}"


async def draw_matrix_appear_rate(ev: Event):
    text = ev.text.strip() if ev.text else ""
    char_id, filter_name, err = _resolve_char_arg(text)
    if err:
        return err

    data = await get_matrix_appear_rate_data(char_id or 0)
    if not data:
        return "暂无矩阵出场率数据, 请稍后再试"

    max_teams = TEAMS_PER_ROW * ROWS_PER_SECTION
    section_data: List[Tuple[str, str, List[Dict]]] = []
    for key, label, kind in SECTIONS:
        rates = data.get(key, {}).get("rates", [])
        rates = [r for r in rates if r.get("char_ids")][:max_teams]
        section_data.append((label, kind, rates))

    if not any(s[2] for s in section_data):
        if char_id:
            return "暂无含该角色的矩阵队伍数据"
        return "暂无矩阵队伍数据, 请稍后再试"

    avatar_cache: Dict[int, Image.Image] = {}
    for _, _, rates in section_data:
        for r in rates:
            for cid in r["char_ids"]:
                if cid in avatar_cache:
                    continue
                if not get_char_model(cid):
                    continue
                avatar_cache[cid] = await get_square_avatar(cid)

    card_img = await _render_matrix_appear(section_data, avatar_cache, filter_name)
    return await convert_img(card_img)


def _draw_section_bar(label: str) -> Image.Image:
    """PIL 自绘章节标题条：圆角深底 + 金色左竖条 + 文字。"""
    bar = Image.new("RGBA", (SECTION_BAR_W, SECTION_BAR_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bar)
    draw.rounded_rectangle(
        [0, 0, SECTION_BAR_W - 1, SECTION_BAR_H - 1],
        radius=18,
        fill=(18, 18, 32, 235),
        outline=(200, 170, 95, 220),
        width=2,
    )
    draw.rounded_rectangle(
        [16, 18, 26, SECTION_BAR_H - 18],
        radius=4,
        fill=(200, 170, 95, 240),
    )
    draw.text(
        (44, SECTION_BAR_H // 2),
        label,
        "white",
        waves_font_40,
        "lm",
    )
    return bar


def _section_body_h(rates_count: int) -> int:
    if rates_count <= 0:
        return EMPTY_SECTION_H
    rows = math.ceil(rates_count / TEAMS_PER_ROW)
    return rows * TEAM_CELL_H


def _draw_empty_panel(height: int) -> Image.Image:
    panel = Image.new("RGBA", (SECTION_BAR_W, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle(
        [10, 10, SECTION_BAR_W - 10, height - 10],
        radius=16,
        fill=(0, 0, 0, 120),
    )
    draw.text(
        (SECTION_BAR_W // 2, height // 2),
        "暂无数据",
        GREY,
        waves_font_30,
        "mm",
    )
    return panel


@to_thread
def _render_matrix_appear(
    sections: List[Tuple[str, str, List[Dict]]],
    avatar_cache: Dict[int, Image.Image],
    filter_name: str,
) -> Image.Image:
    num_sections = len(sections)
    section_body_hs = [_section_body_h(len(rates)) for _, _, rates in sections]
    total_h = (
        TITLE_H
        + sum(SECTION_HEADER_H + bh for bh in section_body_hs)
        + INTER_SECTION_GAP * (num_sections - 1)
        + FOOTER_H
    )
    card_img = get_waves_bg(CARD_W, total_h, "bg9")

    # ── 标题区：matrix.png + 与矩阵排行同样的缩放因子 (1300/960)，
    # 这样无论 CARD_W 是多少，金色框的图像位置与 matrix_rank.py 同步，
    # 文字坐标 (220, 290) 与 (225, 360) 与 rank 完全一致便能落在金框内。──
    title_bg = Image.open(TEXT_PATH / "matrix.png").convert("RGBA")
    title_scale = 1300 / title_bg.width
    title_bg = title_bg.resize(
        (int(title_bg.width * title_scale), int(title_bg.height * title_scale))
    )
    if title_bg.height >= TITLE_H:
        title_bg = title_bg.crop((0, 0, CARD_W, TITLE_H))
    else:
        temp = Image.new("RGBA", (CARD_W, TITLE_H), (0, 0, 0, 0))
        temp.paste(title_bg, (0, TITLE_H - title_bg.height))
        title_bg = temp.crop((0, 0, CARD_W, TITLE_H))

    icon = get_ICON().resize((128, 128))
    title_bg.paste(icon, (60, 240), icon)

    draw = ImageDraw.Draw(title_bg)
    title_text = "#矩阵出场率"
    if filter_name:
        title_text = f"#矩阵出场率 · {filter_name}"
    draw.text((220, 290), title_text, "white", waves_font_58, "lm")

    period_label = f"第{get_matrix_period_number()}期"
    date_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    draw.text((225, 360), period_label, GREY, waves_font_20, "lm")
    try:
        period_w = draw.textlength(period_label, font=waves_font_20)
    except Exception:
        period_w = waves_font_20.getsize(period_label)[0]
    draw.text((225 + period_w + 16, 360), date_text, GREY, waves_font_20, "lm")

    # char_mask 阴影遮罩（参 matrix_rank.py:192-198）
    char_mask = Image.open(TEXT_PATH / "char_mask.png").convert("RGBA")
    char_mask = char_mask.resize(
        (CARD_W, char_mask.height * CARD_W // char_mask.width)
    )
    char_mask = char_mask.crop(
        (0, char_mask.height - TITLE_H, CARD_W, char_mask.height)
    )
    char_mask_temp = Image.new("RGBA", char_mask.size, (0, 0, 0, 0))
    char_mask_temp.paste(title_bg, (0, 0), char_mask)
    card_img.paste(char_mask_temp, (0, 0), char_mask_temp)

    # ── section 循环 ───────────────────────────────────────
    start_y = TITLE_H
    for sec_idx, (section_label, kind, rates) in enumerate(sections):
        if sec_idx > 0:
            start_y += INTER_SECTION_GAP

        section_bar = _draw_section_bar(section_label)
        card_img.alpha_composite(
            section_bar, (GRID_LEFT_X, start_y + SECTION_PAD_TOP)
        )

        cell_area_y = start_y + SECTION_HEADER_H
        body_h = section_body_hs[sec_idx]
        if not rates:
            empty_panel = _draw_empty_panel(body_h)
            card_img.alpha_composite(empty_panel, (GRID_LEFT_X, cell_area_y))
        else:
            for idx, rate_item in enumerate(rates):
                col = idx % TEAMS_PER_ROW
                row = idx // TEAMS_PER_ROW
                x = GRID_LEFT_X + col * (TEAM_CELL_W + TEAM_CELL_GAP_X)
                y = cell_area_y + row * TEAM_CELL_H
                cell = _build_team_cell(idx + 1, rate_item, kind, avatar_cache)
                card_img.alpha_composite(cell, (x, y))

        start_y += SECTION_HEADER_H + body_h

    card_img = add_footer(card_img)
    return card_img


def _build_team_cell(
    rank: int,
    rate_item: Dict,
    kind: str,
    avatar_cache: Dict[int, Image.Image],
) -> Image.Image:
    char_ids: List[int] = rate_item["char_ids"]
    cell = Image.new("RGBA", (TEAM_CELL_W, TEAM_CELL_H), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(cell)
    bg_draw.rounded_rectangle(
        [10, 10, TEAM_CELL_W - 10, TEAM_CELL_H - 10],
        radius=16,
        fill=(0, 0, 0, 120),
    )

    bg_draw.text((35, 35), f"NO.{rank}", "white", waves_font_24, "lm")

    if kind == "rate":
        value_text = f"{rate_item.get('rate', 0) * 100:.2f}%"
    else:
        value_text = f"{rate_item.get('avg_score', 0):.0f}"
    bg_draw.text((TEAM_CELL_W - 35, 35), value_text, "white", waves_font_30, "rm")

    avatar_size = 110
    inner_w = TEAM_CELL_W - 20
    gap = 10
    total_avatars_w = 3 * avatar_size + 2 * gap
    start_x = 10 + (inner_w - total_avatars_w) // 2
    avatar_y = 65

    for i, cid in enumerate(char_ids[:3]):
        ax = start_x + i * (avatar_size + gap)
        char_model = get_char_model(cid)
        avatar = avatar_cache.get(cid)
        if avatar is not None:
            avatar = avatar.resize((avatar_size, avatar_size)).convert("RGBA")
            cell.alpha_composite(avatar, (ax, avatar_y))
        else:
            bg_draw.rectangle(
                [ax, avatar_y, ax + avatar_size, avatar_y + avatar_size],
                outline=(255, 255, 255, 120),
                width=2,
            )

        name = (
            NAME_ALIAS.get(char_model.name, char_model.name)
            if char_model
            else str(cid)
        )
        bg_draw.text(
            (ax + avatar_size // 2, avatar_y + avatar_size + 16),
            name,
            "white",
            waves_font_20,
            "mm",
        )

    return cell
