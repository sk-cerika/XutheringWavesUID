from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFont

FONT_ORIGIN_PATH = Path(__file__).parent / "waves_fonts.ttf"
FONT2_ORIGIN_PATH = Path(__file__).parent / "arial-unicode-ms-bold.ttf"
EMOJI_ORIGIN_PATH = Path(__file__).parent / "NotoColorEmoji.ttf"
FONT_BACK_PATH = (
    Path(__file__).parent.parent.parent / "templates" / "fonts" / "SourceHanSansCN-Regular.ttc"
)


def waves_font_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_ORIGIN_PATH), size=size)


def ww_font_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT2_ORIGIN_PATH), size=size)


def emoji_font_origin(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(EMOJI_ORIGIN_PATH), size=size)


def waves_font_back_origin(size: int) -> ImageFont.FreeTypeFont:
    """加载 Noto Sans CJK SC (index=2) 作为 fallback 字体"""
    return ImageFont.truetype(str(FONT_BACK_PATH), size=size, index=2)


# 构建字体 cmap 集合，用于快速判断字符是否需要 fallback
_waves_cmap: Set[int] = set()
_emoji_cmap: Set[int] = set()
try:
    from fontTools.ttLib import TTFont

    _waves_cmap = set(TTFont(str(FONT_ORIGIN_PATH)).getBestCmap().keys())
    _emoji_cmap = set(TTFont(str(EMOJI_ORIGIN_PATH)).getBestCmap().keys())
except ImportError:
    import logging

    logging.getLogger("XutheringWavesUID").warning(
        "[鸣潮] 未安装fonttools，多语言字体fallback将不可用，日韩文可能显示为方框。"
    )
    logging.getLogger("XutheringWavesUID").info(
        "[鸣潮] 安装方法 Linux/Mac: 在当前目录下执行 source .venv/bin/activate && uv pip install fonttools"
    )
    logging.getLogger("XutheringWavesUID").info(
        "[鸣潮] 安装方法 Windows: 在当前目录下执行 .venv\\Scripts\\activate; uv pip install fonttools"
    )
except Exception:
    pass

# fallback 字体缓存 (按 size 缓存)
_font_back_cache: Dict[int, ImageFont.FreeTypeFont] = {}
_EMOJI_FONT_SIZE = 109


def _get_font_back(size: int) -> ImageFont.FreeTypeFont:
    if size not in _font_back_cache:
        _font_back_cache[size] = waves_font_back_origin(size)
    return _font_back_cache[size]


def _get_emoji_font() -> ImageFont.FreeTypeFont:
    return emoji_font


def get_fallback_font(font: ImageFont.FreeTypeFont) -> ImageFont.FreeTypeFont:
    """根据主字体的 size 获取对应的 fallback 字体"""
    return _get_font_back(font.size)


def _need_fallback(text: str) -> bool:
    """快速判断文本是否包含主字体缺失的字符"""
    for char in text:
        if ord(char) not in _waves_cmap:
            return True
    return False


def _is_emoji_base(char: str) -> bool:
    cp = ord(char)
    if cp <= 0x7E or _is_emoji_modifier(char):
        return False
    if _emoji_cmap:
        return cp in _emoji_cmap

    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2B00 <= cp <= 0x2BFF
        or 0x2300 <= cp <= 0x23FF
    )


def _is_emoji_modifier(char: str) -> bool:
    cp = ord(char)
    return (
        cp in (0x200D, 0x20E3, 0xFE0E, 0xFE0F)
        or 0x1F3FB <= cp <= 0x1F3FF
        or 0xE0020 <= cp <= 0xE007F
    )


def _split_emoji_segments(text: str) -> List[Tuple[str, bool]]:
    segments: List[Tuple[str, bool]] = []
    normal = ""
    i = 0
    while i < len(text):
        char = text[i]
        if not _is_emoji_base(char):
            normal += char
            i += 1
            continue

        if normal:
            segments.append((normal, False))
            normal = ""

        cluster = char
        i += 1
        while i < len(text):
            next_char = text[i]
            if _is_emoji_modifier(next_char):
                cluster += next_char
                i += 1
                if next_char == "\u200d" and i < len(text):
                    cluster += text[i]
                    i += 1
                continue
            break
        segments.append((cluster, True))

    if normal:
        segments.append((normal, False))
    return segments


def _emoji_image(text: str, target_size: int) -> Optional[Image.Image]:
    font = _get_emoji_font()
    try:
        bbox = font.getbbox(text)
    except Exception:
        return None
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    if width > height * 8:
        return None
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.text((-bbox[0], -bbox[1]), text, font=font, embedded_color=True)
    target_h = max(1, target_size)
    target_w = max(1, round(width * target_h / height))
    return image.resize((target_w, target_h), Image.Resampling.LANCZOS)


def text_width_with_emoji_fallback(
    text: str,
    font: ImageFont.FreeTypeFont,
    fallback_font: Optional[ImageFont.FreeTypeFont] = None,
) -> float:
    width = 0.0
    for segment, is_emoji in _split_emoji_segments(str(text)):
        if is_emoji:
            emoji = _emoji_image(segment, font.size)
            if emoji is not None:
                width += emoji.width
                continue
            is_emoji = False

        if not is_emoji:
            width += draw_text_with_fallback(
                ImageDraw.Draw(Image.new("RGBA", (1, 1))),
                (0, 0),
                segment,
                font=font,
                fallback_font=fallback_font,
            )
    return width


def draw_text_with_emoji_fallback(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    fill=None,
    font: Optional[ImageFont.FreeTypeFont] = None,
    anchor=None,
    fallback_font: Optional[ImageFont.FreeTypeFont] = None,
    **kwargs,
) -> float:
    """在原 i18n 字体 fallback 基础上补充彩色 emoji fallback。"""
    if font is None:
        draw.text(xy, text, fill=fill, font=font, anchor=anchor, **kwargs)
        return 0

    text = str(text)
    segments = _split_emoji_segments(text)
    if not any(is_emoji for _, is_emoji in segments):
        return draw_text_with_fallback(draw, xy, text, fill, font, anchor, fallback_font, **kwargs)

    total_width = text_width_with_emoji_fallback(text, font, fallback_font)
    x, y = xy
    h_anchor = (anchor or "l")[0]
    v_anchor = (anchor or "la")[1] if anchor and len(anchor) > 1 else "a"
    if h_anchor == "m":
        x -= total_width / 2
    elif h_anchor == "r":
        x -= total_width

    text_anchor = "l" + v_anchor if anchor else None
    base_image = getattr(draw, "_image", None)
    for segment, is_emoji in segments:
        if is_emoji:
            emoji = _emoji_image(segment, font.size)
            if emoji is not None:
                if v_anchor == "m":
                    top = int(y - emoji.height / 2)
                elif v_anchor in ("b", "d"):
                    top = int(y - emoji.height)
                else:
                    top = int(y)
                if base_image is not None:
                    base_image.alpha_composite(emoji, (round(x), top))
                x += emoji.width
                continue

        if not is_emoji or emoji is None:
            width = draw_text_with_fallback(
                draw,
                (round(x), y),
                segment,
                fill=fill,
                font=font,
                anchor=text_anchor,
                fallback_font=fallback_font,
                **kwargs,
            )
            x += width
    return total_width


def draw_text_with_fallback(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    fill=None,
    font: Optional[ImageFont.FreeTypeFont] = None,
    anchor=None,
    fallback_font: Optional[ImageFont.FreeTypeFont] = None,
    **kwargs,
) -> float:
    """分段 fallback 绘制文本，参数顺序与 PIL draw.text 一致。

    支持 anchor 参数 (lm/mm/rm 等)，支持多行文本（\\n）。
    返回绘制后的总宽度。
    """
    # 多行文本：按 \n 分割后逐行绘制
    if "\n" in text:
        lines = text.split("\n")
        line_height = font.size if font else 16
        total_height = len(lines) * line_height

        x0, y0 = xy
        v_anchor = (anchor or "la")[1] if anchor and len(anchor) > 1 else "a"
        if v_anchor == "m":
            y_start = y0 - total_height / 2
        elif v_anchor in ("b", "d"):
            y_start = y0 - total_height
        else:
            y_start = y0

        h_anchor = (anchor or "l")[0]
        line_anchor = h_anchor + "t"
        max_width = 0.0
        for i, line in enumerate(lines):
            line_y = int(y_start + i * line_height)
            w = draw_text_with_fallback(draw, (x0, line_y), line, fill, font, line_anchor, fallback_font, **kwargs)
            max_width = max(max_width, w)
        return max_width

    if not _waves_cmap or not text or not _need_fallback(text):
        draw.text(xy, text, fill=fill, font=font, anchor=anchor, **kwargs)
        return font.getlength(text) if font else 0

    if fallback_font is None:
        fallback_font = _get_font_back(font.size)

    # 构建分段: [(segment_text, segment_font), ...]
    segments = []
    seg = ""
    seg_font = font
    for char in text:
        f = font if ord(char) in _waves_cmap else fallback_font
        if f is seg_font:
            seg += char
        else:
            if seg:
                segments.append((seg, seg_font))
            seg = char
            seg_font = f
    if seg:
        segments.append((seg, seg_font))

    total_width = sum(f.getlength(s) for s, f in segments)

    # 根据 anchor 的水平分量调整起始 x
    x, y = xy
    h_anchor = (anchor or "l")[0]
    if h_anchor == "m":
        x -= total_width / 2
    elif h_anchor == "r":
        x -= total_width

    # 每段使用左对齐 anchor 绘制
    seg_anchor = "l" + (anchor or "la")[1] if anchor else None
    for seg_text, seg_f in segments:
        draw.text((x, y), seg_text, fill=fill, font=seg_f, anchor=seg_anchor, **kwargs)
        x += seg_f.getlength(seg_text)

    return total_width


waves_font_10 = waves_font_origin(10)
waves_font_12 = waves_font_origin(12)
waves_font_14 = waves_font_origin(14)
waves_font_16 = waves_font_origin(16)
waves_font_15 = waves_font_origin(15)
waves_font_18 = waves_font_origin(18)
waves_font_20 = waves_font_origin(20)
waves_font_22 = waves_font_origin(22)
waves_font_23 = waves_font_origin(23)
waves_font_24 = waves_font_origin(24)
waves_font_25 = waves_font_origin(25)
waves_font_26 = waves_font_origin(26)
waves_font_28 = waves_font_origin(28)
waves_font_30 = waves_font_origin(30)
waves_font_32 = waves_font_origin(32)
waves_font_34 = waves_font_origin(34)
waves_font_36 = waves_font_origin(36)
waves_font_38 = waves_font_origin(38)
waves_font_40 = waves_font_origin(40)
waves_font_42 = waves_font_origin(42)
waves_font_44 = waves_font_origin(44)
waves_font_50 = waves_font_origin(50)
waves_font_58 = waves_font_origin(58)
waves_font_60 = waves_font_origin(60)
waves_font_62 = waves_font_origin(62)
waves_font_70 = waves_font_origin(70)
waves_font_84 = waves_font_origin(84)

ww_font_12 = ww_font_origin(12)
ww_font_14 = ww_font_origin(14)
ww_font_16 = ww_font_origin(16)
ww_font_15 = ww_font_origin(15)
ww_font_18 = ww_font_origin(18)
ww_font_20 = ww_font_origin(20)
ww_font_22 = ww_font_origin(22)
ww_font_23 = ww_font_origin(23)
ww_font_24 = ww_font_origin(24)
ww_font_25 = ww_font_origin(25)
ww_font_26 = ww_font_origin(26)
ww_font_28 = ww_font_origin(28)
ww_font_30 = ww_font_origin(30)
ww_font_32 = ww_font_origin(32)
ww_font_34 = ww_font_origin(34)
ww_font_36 = ww_font_origin(36)
ww_font_38 = ww_font_origin(38)
ww_font_40 = ww_font_origin(40)
ww_font_42 = ww_font_origin(42)
ww_font_44 = ww_font_origin(44)
ww_font_50 = ww_font_origin(50)
ww_font_58 = ww_font_origin(58)
ww_font_60 = ww_font_origin(60)
ww_font_62 = ww_font_origin(62)
ww_font_70 = ww_font_origin(70)
ww_font_84 = ww_font_origin(84)

emoji_font = emoji_font_origin(_EMOJI_FONT_SIZE)
