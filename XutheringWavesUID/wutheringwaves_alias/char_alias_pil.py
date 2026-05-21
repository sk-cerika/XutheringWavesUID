import base64
from io import BytesIO
from typing import Dict, List, Sequence

from PIL import Image, ImageDraw

from gsuid_core.pool import to_thread
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import crop_center_img

from ..utils.fonts.waves_fonts import (
    draw_text_with_emoji_fallback,
    text_width_with_emoji_fallback,
    waves_font_12,
    waves_font_14,
    waves_font_16,
    waves_font_18,
    waves_font_30,
)
from ..utils.image import (
    add_footer,
    clean_alpha_matte,
    cropped_square_avatar,
    flatten_rgba,
    get_custom_waves_bg,
    get_square_avatar,
    make_smooth_circle_mask,
)


WHITE = (245, 245, 245, 255)
SUB_TEXT = (178, 182, 190, 255)
ACCENT = (212, 177, 99, 255)
ACCENT_DIM = (212, 177, 99, 150)
PAGE_BG = (15, 17, 21, 255)
PANEL_BG = (30, 34, 42, 235)
HEADER_BG = (255, 255, 255, 12)
CONTENT_BG = (0, 0, 0, 44)
CARD_BG_DARK = (30, 34, 42, 222)
LINE = (255, 255, 255, 45)
TAG_FILL = (255, 255, 255, 22)
AVATAR_BG = (28, 31, 39, 255)


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: object,
    font,
    fill=WHITE,
    anchor: str | None = None,
) -> None:
    draw_text_with_emoji_fallback(draw, xy, str(text), fill=fill, font=font, anchor=anchor)


def _fit_text(text: object, font, max_width: int) -> str:
    text = str(text)
    if text_width_with_emoji_fallback(text, font) <= max_width:
        return text
    while text and text_width_with_emoji_fallback(f"{text}...", font) > max_width:
        text = text[:-1]
    return f"{text}..." if text else ""


def _draw_round_rect(
    base: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    fill,
    outline=None,
    width: int = 1,
) -> None:
    x1, y1, x2, y2 = box
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    scale = 4
    layer = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.rounded_rectangle(
        (0, 0, w * scale - 1, h * scale - 1),
        radius=radius * scale,
        fill=fill,
        outline=outline,
        width=max(1, width * scale),
    )
    layer = layer.resize((w, h), Image.Resampling.LANCZOS)
    base.alpha_composite(layer, (x1, y1))


def _make_dark_bg(width: int, height: int) -> Image.Image:
    base = Image.new("RGBA", (width, height), PAGE_BG)
    bg = get_custom_waves_bg(width, height, "bg12")
    if bg.mode != "RGBA":
        bg = bg.convert("RGBA")
    bg.putalpha(38)
    base.alpha_composite(bg)
    return base


def _circle_avatar(avatar: Image.Image, size: int) -> Image.Image:
    avatar = avatar.convert("RGBA")
    baked = Image.new("RGBA", (size, size), AVATAR_BG)
    baked.alpha_composite(avatar)
    baked.putalpha(make_smooth_circle_mask(size))
    return baked


async def _load_avatar(
    size: int,
    char_id: str = "",
    avatar_url: str = "",
) -> Image.Image | None:
    if char_id:
        try:
            avatar = await get_square_avatar(char_id)
            avatar = await cropped_square_avatar(avatar, size)
            return _circle_avatar(avatar, size)
        except Exception:
            pass

    if not avatar_url:
        return None
    try:
        if "," in avatar_url:
            avatar_url = avatar_url.split(",", 1)[1]
        avatar = Image.open(BytesIO(base64.b64decode(avatar_url))).convert("RGBA")
        avatar = clean_alpha_matte(avatar, AVATAR_BG)
        avatar = crop_center_img(avatar, size, size).convert("RGBA")
        return _circle_avatar(avatar, size)
    except Exception:
        return None


def _paste_avatar(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    size: int,
    avatar: Image.Image | None = None,
    ring: bool = True,
) -> None:
    if ring:
        draw.ellipse(
            (x - 5, y - 5, x + size + 5, y + size + 5),
            fill=(0, 0, 0, 95),
            outline=ACCENT_DIM,
            width=2,
        )
    else:
        draw.ellipse(
            (x, y, x + size, y + size),
            fill=AVATAR_BG,
            outline=(212, 177, 99, 76),
            width=1,
        )
    if avatar:
        base.alpha_composite(avatar, (x, y))
    else:
        draw.ellipse((x, y, x + size, y + size), fill=AVATAR_BG)
    draw.ellipse(
        (x - 1, y - 1, x + size + 1, y + size + 1),
        outline=(255, 255, 255, 36),
        width=1,
    )


def _layout_tags(
    tags: Sequence[str],
    font,
    max_width: int,
    pad_x: int,
    gap: int,
) -> List[List[tuple[str, int]]]:
    rows: List[List[tuple[str, int]]] = []
    current: List[tuple[str, int]] = []
    current_w = 0
    for raw_tag in tags:
        tag = _fit_text(raw_tag, font, max_width - pad_x * 2)
        tag_w = min(max_width, int(text_width_with_emoji_fallback(tag, font)) + pad_x * 2)
        next_w = tag_w if not current else current_w + gap + tag_w
        if current and next_w > max_width:
            rows.append(current)
            current = []
            current_w = 0
        if current:
            current_w += gap
        current.append((tag, tag_w))
        current_w += tag_w
    if current:
        rows.append(current)
    return rows


def _draw_tag_rows(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    rows: Sequence[Sequence[tuple[str, int]]],
    x: int,
    y: int,
    tag_h: int,
    gap: int,
    row_gap: int,
    font,
    first_highlight: bool = False,
    radius: int | None = None,
) -> int:
    cur_y = y
    item_idx = 0
    for row in rows:
        cur_x = x
        for tag, tag_w in row:
            is_first = first_highlight and item_idx == 0
            fill = (212, 177, 99, 42) if is_first else TAG_FILL
            outline = (212, 177, 99, 110) if is_first else (255, 255, 255, 42)
            text_fill = WHITE if is_first else (238, 238, 238, 255)
            _draw_round_rect(
                base,
                (cur_x, cur_y, cur_x + tag_w, cur_y + tag_h),
                radius if radius is not None else tag_h // 2,
                fill,
                outline,
                1,
            )
            _draw_text(draw, (cur_x + tag_w // 2, cur_y + tag_h // 2), tag, font, text_fill, "mm")
            cur_x += tag_w + gap
            item_idx += 1
        cur_y += tag_h + row_gap
    return cur_y - row_gap if rows else y


async def draw_char_alias_pil(
    char_name: str,
    alias_list: List[str],
    avatar_url: str = "",
    char_id: str = "",
) -> bytes:
    avatar = await _load_avatar(80, char_id, avatar_url)
    canvas = await _compose_char_alias(char_name, alias_list, avatar)
    return await convert_img(flatten_rgba(canvas, PAGE_BG))


@to_thread
def _compose_char_alias(char_name: str, alias_list: List[str], avatar) -> Image.Image:
    width = 600
    tags = alias_list or [char_name]
    main_x = 25
    main_y = 25
    main_w = width - main_x * 2
    header_h = 120
    tag_rows = _layout_tags(tags, waves_font_16, main_w - 50, 14, 8)
    tag_area_h = len(tag_rows) * 32 + max(0, len(tag_rows) - 1) * 8
    content_h = 20 + 18 + 12 + tag_area_h + 24
    card_bottom = main_y + header_h + content_h
    height = max(305, card_bottom + 64)

    canvas = _make_dark_bg(width, height)
    draw = ImageDraw.Draw(canvas, "RGBA")

    card_box = (main_x, main_y, width - main_x, card_bottom)
    _draw_round_rect(canvas, card_box, 16, PANEL_BG, LINE, 1)
    _draw_round_rect(canvas, (main_x, main_y, width - main_x, main_y + 4), 2, (212, 177, 99, 205))
    draw.rectangle((main_x + 1, main_y + 4, width - main_x - 1, main_y + header_h), fill=HEADER_BG)
    draw.line((main_x, main_y + header_h, width - main_x, main_y + header_h), fill=(255, 255, 255, 28), width=1)

    _paste_avatar(canvas, draw, 50, 45, 80, avatar=avatar)
    _draw_text(draw, (155, 66), "CHARACTER NAME", waves_font_12, ACCENT_DIM, "lm")
    _draw_text(draw, (155, 98), _fit_text(char_name, waves_font_30, 370), waves_font_30, WHITE, "lm")

    content_top = main_y + header_h
    draw.rectangle((main_x + 1, content_top + 1, width - main_x - 1, card_bottom - 1), fill=CONTENT_BG)
    label_y = content_top + 31
    _draw_round_rect(canvas, (50, label_y - 7, 53, label_y + 7), 2, ACCENT)
    _draw_text(draw, (62, label_y), "ALIASES", waves_font_16, SUB_TEXT, "lm")
    _draw_tag_rows(canvas, draw, tag_rows, 50, label_y + 25, 32, 8, 8, waves_font_16, first_highlight=True, radius=6)
    add_footer(canvas, w=260, offset_y=8, color="white")
    return canvas


def _prepare_all_cards(chars: List[Dict]) -> List[Dict]:
    cards = []
    card_w = 232
    for char in chars:
        aliases = char.get("aliases") or ["暂无别名"]
        tag_rows = _layout_tags(aliases, waves_font_12, card_w - 32, 8, 6)
        card_h = max(106, 72 + len(tag_rows) * 22 + max(0, len(tag_rows) - 1) * 6 + 10)
        cards.append(
            {
                **char,
                "tag_rows": tag_rows,
                "card_h": card_h,
            }
        )
    return cards


def _draw_all_card(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    char: Dict,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    _draw_round_rect(base, (x, y, x + w, y + h), 8, CARD_BG_DARK, (255, 255, 255, 18), 1)
    _paste_avatar(
        base,
        draw,
        x + 16,
        y + 14,
        40,
        avatar=char.get("avatar_img"),
        ring=False,
    )
    char_id = str(char.get("char_id") or "")
    _draw_text(
        draw,
        (x + 66, y + 22),
        _fit_text(char.get("name", ""), waves_font_18, w - 82),
        waves_font_18,
        WHITE,
        "lm",
    )
    if char_id:
        _draw_text(
            draw,
            (x + 66, y + 44),
            f"ID {char_id}",
            waves_font_12,
            ACCENT_DIM,
            "lm",
        )
    draw.line((x + 16, y + 62, x + w - 16, y + 62), fill=(255, 255, 255, 18), width=1)
    _draw_tag_rows(base, draw, char["tag_rows"], x + 16, y + 74, 22, 6, 6, waves_font_12, radius=3)


async def draw_all_char_alias_pil(chars: List[Dict]) -> bytes:
    for char in chars:
        char["avatar_img"] = await _load_avatar(
            40,
            str(char.get("char_id") or ""),
            str(char.get("avatar") or ""),
        )
    canvas = await _compose_all_char_alias(chars)
    return await convert_img(flatten_rgba(canvas, PAGE_BG))


@to_thread
def _compose_all_char_alias(chars: List[Dict]) -> Image.Image:
    width = 800
    cards = _prepare_all_cards(chars)
    cols = 3
    gap = 12
    card_w = 232
    rows = [cards[i : i + cols] for i in range(0, len(cards), cols)]
    row_heights = [max(card["card_h"] for card in row) for row in rows] if rows else [108]
    content_h = sum(row_heights) + gap * max(0, len(row_heights) - 1)
    top = 116
    height = max(380, top + content_h + 88)

    canvas = _make_dark_bg(width, height)
    draw = ImageDraw.Draw(canvas, "RGBA")

    _draw_text(draw, (40, 58), "角色别名表", waves_font_30, ACCENT, "lm")
    _draw_text(draw, (40, 92), f"ALIAS TABLE // {len(chars)} CHARACTERS", waves_font_14, (139, 139, 139, 255), "lm")

    y = top
    for row, row_h in zip(rows, row_heights):
        x = 40
        for card in row:
            _draw_all_card(canvas, draw, card, x, y, card_w, row_h)
            x += card_w + gap
        y += row_h + gap

    footer_top = height - 60
    draw.rectangle((0, footer_top, width, height), fill=(10, 10, 12, 250))
    draw.line((0, footer_top, width, footer_top), fill=(232, 201, 99, 52), width=1)
    add_footer(canvas, w=320, offset_y=8, color="white")
    return canvas
