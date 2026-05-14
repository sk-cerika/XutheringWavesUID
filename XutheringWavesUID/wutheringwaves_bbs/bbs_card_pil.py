import base64
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from gsuid_core.pool import to_thread
from gsuid_core.utils.image.convert import convert_img

from ..utils.fonts.waves_fonts import (
    draw_text_with_fallback,
    waves_font_18,
    waves_font_20,
    waves_font_32,
    waves_font_42,
)
from ..utils.image import add_footer
from ..utils.render_utils import get_image_b64_with_cache
from ..utils.resource.RESOURCE_PATH import BBS_PATH


WIDTH = 680
HEIGHT = 500
CARD_BOX = (36, 36, 644, 424)


def _decode_data_url(data_url: str) -> Optional[Image.Image]:
    if not data_url:
        return None
    try:
        if "," in data_url:
            data_url = data_url.split(",", 1)[1]
        return Image.open(BytesIO(base64.b64decode(data_url))).convert("RGBA")
    except Exception:
        return None


def _fit_text(text: str, font, max_width: int) -> str:
    text = str(text)
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(f"{text}...") > max_width:
        text = text[:-1]
    return f"{text}..." if text else ""


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: object,
    font,
    fill,
    anchor: Optional[str] = None,
) -> None:
    draw_text_with_fallback(
        draw,
        xy,
        str(text),
        fill=fill,
        font=font,
        anchor=anchor,
    )


def _circle_image(img: Image.Image, size: int) -> Image.Image:
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


async def _load_url_image(url: str) -> Optional[Image.Image]:
    if not url:
        return None
    data_url = await get_image_b64_with_cache(url, BBS_PATH, quality=None)
    return _decode_data_url(data_url)


def _load_coin() -> Optional[Image.Image]:
    coin_path = Path(__file__).parent / "texture2d" / "coin.png"
    if not coin_path.exists():
        return None
    return Image.open(coin_path).convert("RGBA").resize((92, 92), Image.LANCZOS)


def _draw_signature(
    draw: ImageDraw.ImageDraw,
    signature: str,
    x: int,
    y: int,
    max_width: int,
) -> None:
    if not signature:
        return

    words = signature[:58]
    lines = []
    line = ""
    for char in words:
        candidate = f"{line}{char}"
        if waves_font_18.getlength(candidate) <= max_width:
            line = candidate
        else:
            lines.append(line)
            line = char
        if len(lines) >= 2:
            break
    if line and len(lines) < 2:
        lines.append(line)

    if len(words) < len(signature) and lines:
        lines[-1] = _fit_text(lines[-1], waves_font_18, max_width)

    for idx, line in enumerate(lines):
        _draw_text(draw, (x, y + idx * 28), line, waves_font_18, (127, 140, 141, 255))


@to_thread
def _compose_coin_card(
    user_name: str,
    user_id: str,
    gold_num: int,
    signature: str,
    avatar: Optional[Image.Image],
    frame: Optional[Image.Image],
) -> Image.Image:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (244, 247, 249, 255))
    shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow, "RGBA")
    x1, y1, x2, y2 = CARD_BOX
    shadow_draw.rounded_rectangle((x1, y1 + 10, x2, y2 + 10), radius=16, fill=(0, 0, 0, 24))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    canvas.alpha_composite(shadow)

    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle(CARD_BOX, radius=16, fill=(255, 255, 255, 255))

    avatar_x, avatar_y = 78, 78
    if avatar is None:
        draw.ellipse(
            (avatar_x, avatar_y, avatar_x + 128, avatar_y + 128),
            fill=(238, 238, 238, 255),
            outline=(255, 255, 255, 255),
            width=2,
        )
    else:
        draw.ellipse(
            (avatar_x - 2, avatar_y - 2, avatar_x + 130, avatar_y + 130),
            fill=(255, 255, 255, 255),
        )
        canvas.alpha_composite(_circle_image(avatar, 128), (avatar_x, avatar_y))

    if frame is not None:
        frame = frame.resize((152, 152), Image.LANCZOS)
        canvas.alpha_composite(frame, (avatar_x - 12, avatar_y - 12))

    info_x = 246
    _draw_text(
        draw,
        (info_x, 84),
        _fit_text(user_name or "未知", waves_font_32, 360),
        waves_font_32,
        (44, 62, 80, 255),
    )
    if user_id:
        _draw_text(draw, (info_x, 132), f"ID: {user_id}", waves_font_18, (149, 165, 166, 255))
    _draw_signature(draw, signature, info_x, 164, 350)

    asset_box = (74, 278, 606, 390)
    draw.rounded_rectangle(asset_box, radius=14, fill=(31, 31, 31, 255))

    coin = _load_coin()
    if coin is not None:
        glow = Image.new("RGBA", (122, 122), (0, 0, 0, 0))
        glow.alpha_composite(coin, (15, 15))
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        canvas.alpha_composite(glow, (70, 270))
        canvas.alpha_composite(coin, (85, 285))

    _draw_text(draw, (420, 333), "库洛币", waves_font_20, (170, 170, 170, 255), "rm")
    _draw_text(
        draw,
        (570, 333),
        _fit_text(str(gold_num), waves_font_42, 175),
        waves_font_42,
        (223, 174, 95, 255),
        "rm",
    )

    add_footer(canvas, w=260, offset_y=8, color="black")
    return canvas


async def kuro_coin_card_pil(
    user_name: str,
    user_id: str,
    head_url: str,
    head_frame_url: str,
    gold_num: int,
    signature: str,
) -> bytes:
    avatar = await _load_url_image(head_url)
    frame = await _load_url_image(head_frame_url)
    canvas = await _compose_coin_card(user_name, user_id, gold_num, signature, avatar, frame)
    return await convert_img(canvas)
