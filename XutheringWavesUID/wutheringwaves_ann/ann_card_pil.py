import re
import time
import warnings
from html import unescape
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime

from PIL import Image, ImageOps, ImageDraw, ImageChops

# 忽略PIL解压缩炸弹警告
warnings.filterwarnings('ignore', category=Image.DecompressionBombWarning)

from gsuid_core.logger import logger
from gsuid_core.pool import to_thread
from gsuid_core.utils.image.convert import convert_img

from ..utils.image import (
    add_footer,
    clean_alpha_matte,
    flatten_rgba,
    make_smooth_circle_mask,
    make_smooth_rounded_mask,
    pic_download_from_url,
)
from ..utils.waves_api import waves_api
from ..wutheringwaves_config import PREFIX
from ..utils.fonts.waves_fonts import (
    draw_text_with_emoji_fallback,
    text_width_with_emoji_fallback,
    ww_font_14,
    ww_font_16,
    ww_font_20,
    ww_font_24,
    ww_font_26,
    ww_font_30,
    ww_font_36,
)
from ..utils.resource.RESOURCE_PATH import ANN_CARD_PATH, TEMP_PATH


PAGE_W = 750
PAGE_BG = "#f4f7f9"
PANEL_BG = "#ffffff"
TEXT_MAIN = "#2c3e50"
TEXT_SUB = "#95a5a6"
LINE_COLOR = "#edf2f7"
CONFIGS: Dict[int, Dict[str, str]] = {
    1: {"name": "活动", "en": "ACTIVITY", "color": "#F97316"},
    2: {"name": "资讯", "en": "INFORMATION", "color": "#3B82F6"},
    3: {"name": "公告", "en": "NOTICE", "color": "#10B981"},
    4: {"name": "周边", "en": "MERCHANDISE", "color": "#8B5CF6"},
}


def _load_logo(height: int = 60) -> Optional[Image.Image]:
    logo_path = TEMP_PATH / "imgs" / "kurobbs.png"
    if not logo_path.exists():
        return None
    logo = Image.open(logo_path).convert("RGBA")
    width = int(logo.width * height / logo.height)
    return logo.resize((width, height), Image.Resampling.LANCZOS)


def _text_width(text: str, font) -> int:
    return int(text_width_with_emoji_fallback(str(text), font))


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: Any,
    fill,
    font,
    anchor=None,
) -> None:
    draw_text_with_emoji_fallback(
        draw,
        xy,
        str(text),
        fill=fill,
        font=font,
        anchor=anchor,
    )


def _wrap_text(text: str, font, max_w: int) -> List[str]:
    if not text:
        return [""]

    lines: List[str] = []
    for para in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not para:
            lines.append("")
            continue

        line = ""
        for char in para:
            test = f"{line}{char}"
            if _text_width(test, font) <= max_w:
                line = test
                continue

            if line:
                lines.append(line)
                line = char
            else:
                lines.append(char)
                line = ""

        if line:
            lines.append(line)

    return lines or [""]


def _truncate_line(text: str, font, max_w: int) -> str:
    if _text_width(text, font) <= max_w:
        return text

    suffix = "..."
    while text and _text_width(f"{text}{suffix}", font) > max_w:
        text = text[:-1]
    return f"{text}{suffix}" if text else suffix


def _limit_lines(lines: List[str], font, max_w: int, max_lines: int) -> List[str]:
    if len(lines) <= max_lines:
        return lines
    limited = lines[:max_lines]
    limited[-1] = _truncate_line(limited[-1], font, max_w)
    return limited


def _clean_html_text(content: str) -> str:
    text = str(content or "")
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</\s*(p|div|section|li|h[1-6])\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"<\s*(script|style)[^>]*>.*?</\s*\1\s*>", "", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text).replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _paste_masked(base: Image.Image, img: Image.Image, pos: Tuple[int, int], radius: int = 0) -> None:
    layer = clean_alpha_matte(img, (255, 255, 255, 255))
    if radius:
        mask = make_smooth_rounded_mask(layer.size, radius)
        alpha = ImageChops.multiply(layer.getchannel("A"), mask)
        layer.putalpha(alpha)
    base.alpha_composite(layer, pos)


def _resize_contain(img: Image.Image, max_size: Tuple[int, int]) -> Image.Image:
    image = img.convert("RGBA")
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return image


async def _load_cover(url: str, size: Tuple[int, int], fit: bool = True) -> Optional[Image.Image]:
    if not url:
        return None

    try:
        img = await pic_download_from_url(ANN_CARD_PATH, url)
        if not img:
            return None
        img = img.convert("RGBA")
        if fit:
            return ImageOps.fit(img, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        return _resize_contain(img, size)
    except Exception as e:
        logger.debug(f"公告图片加载失败: {url}, {e}")
        return None


async def _load_avatar(url: str, size: int) -> Optional[Image.Image]:
    img = await _load_cover(url, (size, size), fit=True)
    if not img:
        return None
    img = clean_alpha_matte(img, (238, 246, 255, 255))
    img.putalpha(make_smooth_circle_mask(size))
    return img


def _paste_id_badge(card: Image.Image, text: str, color: str) -> None:
    badge_h = 26
    radius = 10
    pad_x = 10
    badge_w = int(_text_width(text, ww_font_14) + pad_x * 2)

    scale = 4
    sw, sh, sr = badge_w * scale, badge_h * scale, radius * scale
    mask = Image.new("L", (sw, sh), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle((0, 0, sw - sr, sh), fill=255)
    mask_draw.rectangle((0, 0, sw, sh - sr), fill=255)
    mask_draw.pieslice((sw - sr * 2, sh - sr * 2, sw, sh), 0, 90, fill=255)
    mask = mask.resize((badge_w, badge_h), Image.Resampling.LANCZOS)

    shadow_alpha = mask.point(lambda value: value * 38 // 255)
    shadow = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha)
    card.alpha_composite(shadow, (2, 2))

    badge = Image.new("RGBA", (badge_w, badge_h), color)
    badge.putalpha(mask)
    card.alpha_composite(badge, (0, 0))

    draw = ImageDraw.Draw(card, "RGBA")
    _draw_text(draw, (pad_x, 5), text, (0, 0, 0, 85), ww_font_14)
    _draw_text(draw, (pad_x, 4), text, "#ffffff", ww_font_14)


def _extract_cover_url(item: Dict[str, Any], event_type: int, user_info: Optional[Dict[str, Any]] = None) -> str:
    cover_url = item.get("coverUrl", "") or ""

    if not cover_url:
        cover_images = item.get("coverImages", [])
        if cover_images:
            cover_url = cover_images[0].get("url", "") or ""

    if event_type == 4 and not cover_url:
        img_content = item.get("imgContent", [])
        if img_content:
            cover_url = img_content[0].get("url", "") or ""

    if not cover_url:
        video_content = item.get("videoContent", [])
        if video_content:
            cover_url = video_content[0].get("coverUrl") or video_content[0].get("videoCoverUrl", "") or ""

    if not cover_url and user_info:
        cover_url = user_info.get("headCodeUrl", "") or ""

    return cover_url


def _get_item_date(item: Dict[str, Any], event_type: int) -> str:
    if event_type == 4:
        date_str = item.get("showTime", "")
        if date_str:
            return str(date_str)
        return format_date(item.get("createTimestamp", 0))
    return format_date(item.get("publishTime", 0))


def _draw_header(img: Image.Image, title: str, subtitle: str = "", title_right: bool = False) -> int:
    logo = _load_logo(60)
    title_x = 30 + ((logo.width + 20) if logo else 0)
    title_w = PAGE_W - title_x - 30
    title_lines: List[str] = _limit_lines(_wrap_text(title, ww_font_30, title_w), ww_font_30, title_w, 3)
    if title_right:
        content_h = max(60, len(title_lines) * 38)
        header_h = max(100, content_h + 40)
    else:
        header_h = 136

    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle((0, 0, PAGE_W, header_h), fill="#121212")
    draw.rectangle((0, header_h - 3, PAGE_W, header_h), fill="#3498db")

    if title_right:
        row_h = max(60, len(title_lines) * 38)
        row_y = (header_h - row_h) // 2
        if logo:
            img.alpha_composite(logo, (30, row_y + (row_h - logo.height) // 2))
        else:
            _draw_text(draw, (30, row_y + 10), "鸣潮公告", "#ffffff", ww_font_30)

        y = row_y + (row_h - len(title_lines) * 38) // 2
        for line in title_lines:
            _draw_text(draw, (title_x + 1, y + 2), line, (0, 0, 0, 150), ww_font_30)
            _draw_text(draw, (title_x, y), line, "#ffffff", ww_font_30)
            y += 38
        return header_h

    brand_x = 30
    if logo:
        img.alpha_composite(logo, (brand_x, 20))
    else:
        _draw_text(draw, (brand_x + 18, 22), "鸣潮公告", (0, 0, 0, 150), ww_font_36)
        _draw_text(draw, (brand_x + 16, 20), "鸣潮公告", "#ffffff", ww_font_36)
    if subtitle:
        _draw_text(
            draw,
            (34, 96),
            _truncate_line(subtitle, ww_font_14, PAGE_W - 68),
            (255, 255, 255, 185),
            ww_font_14,
        )

    return header_h


def _draw_user_info_sync(
    img: Image.Image,
    y: int,
    user_name: str,
    user_time: str,
    avatar: Optional[Image.Image] = None,
) -> int:
    draw = ImageDraw.Draw(img)
    section_h = 104
    draw.rectangle((0, y, PAGE_W, y + section_h), fill=PANEL_BG)
    draw.line((0, y + section_h - 1, PAGE_W, y + section_h - 1), fill=LINE_COLOR)

    if avatar:
        img.alpha_composite(avatar, (30, y + 17))
    else:
        draw.ellipse((30, y + 17, 100, y + 87), fill="#eef6ff", outline="#3498db", width=2)
        _draw_text(draw, (65, y + 52), "潮", "#3498db", ww_font_24, "mm")

    _draw_text(draw, (118, y + 28), user_name or "鸣潮", TEXT_MAIN, ww_font_24)
    if user_time:
        _draw_text(draw, (118, y + 60), user_time, TEXT_SUB, ww_font_16)
    return y + section_h


async def _draw_user_info(
    img: Image.Image,
    y: int,
    user_name: str,
    user_time: str,
    avatar_url: str = "",
) -> int:
    avatar = await _load_avatar(avatar_url, 70)
    return _draw_user_info_sync(img, y, user_name, user_time, avatar)


async def _prepare_sections(
    ann_list: List[Dict[str, Any]],
    user_id: Optional[str],
    user_info: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for item in ann_list:
        event_type = item.get("eventType")
        if not event_type:
            continue
        grouped.setdefault(int(event_type), []).append(item)

    for data in grouped.values():
        data.sort(key=lambda x: x.get("publishTime") or x.get("showTime") or 0, reverse=True)

    sections: List[Dict[str, Any]] = []
    for event_type in [1, 2, 3, 4]:
        items = grouped.get(event_type, [])
        if not items:
            continue

        max_items = 9 if user_id else 6
        ann_items = []
        for item in items[:max_items]:
            if not item.get("id") or not item.get("postTitle"):
                continue

            post_id = item.get("postId", "") or str(item.get("id", ""))
            short_id = ""
            if event_type == 4:
                from .utils.post_id_mapper import get_or_create_short_id

                short_id = get_or_create_short_id(str(post_id))

            ann_items.append(
                {
                    "id": str(item.get("id", "")),
                    "short_id": short_id,
                    "postTitle": item.get("postTitle", ""),
                    "date_str": _get_item_date(item, event_type),
                    "coverUrl": _extract_cover_url(item, event_type, user_info),
                    "eventType": event_type,
                }
            )

        if ann_items:
            sections.append({**CONFIGS[event_type], "ann_list": ann_items})

    return sections


async def ann_list_card(user_id: Optional[str] = None) -> bytes:
    user_info: Optional[Dict[str, Any]] = None
    if user_id:
        logger.debug(f"[鸣潮] 正在获取用户 {user_id} 的公告列表(PIL)...")
        ann_list: List[Dict[str, Any]] = []
        res = await waves_api.get_bbs_list(user_id, pageIndex=1, pageSize=9)
        if res.success:
            raw_data = res.model_dump()
            post_list = raw_data["data"]["postList"]
            post_list.sort(key=lambda x: x.get("showTime", 0), reverse=True)
            ann_list = [{**x, "id": int(x["postId"]), "eventType": 4} for x in post_list]
            if post_list:
                first_post = post_list[0]
                user_info = {
                    "userName": first_post.get("userName", ""),
                    "headCodeUrl": first_post.get("userHeadUrl", ""),
                    "ipRegion": first_post.get("ipRegion", ""),
                }
        if not ann_list:
            raise Exception(f"获取用户 {user_id} 的公告失败,请检查用户ID是否正确")
    else:
        ann_list = await waves_api.get_ann_list()
        if not ann_list:
            raise Exception("获取游戏公告失败,请检查接口是否正常")

    sections = await _prepare_sections(ann_list, user_id, user_info)
    subtitle = f"用户 {user_id} 的公告列表 | 使用 {PREFIX}公告#ID 查看详情" if user_id else f"查看详细内容，使用 {PREFIX}公告#ID 查看详情"

    card_w, card_h = 220, 214

    # 预取所有卡片封面
    for section in sections:
        for item in section["ann_list"]:
            item["_cover_img"] = await _load_cover(item.get("coverUrl", ""), (card_w, 110), fit=True)

    user_avatar = None
    if user_info:
        user_avatar = await _load_avatar(user_info.get("headCodeUrl", ""), 70)

    img = await _compose_ann_list(sections, subtitle, user_info, user_id, user_avatar, card_w, card_h)
    return await convert_img(flatten_rgba(img, PANEL_BG))


@to_thread
def _compose_ann_list(sections, subtitle, user_info, user_id, user_avatar, card_w, card_h) -> Image.Image:
    grid_x, grid_gap = 25, 15
    section_title_h = 50 if not user_id else 10
    total_h = 136
    if user_info:
        total_h += 104
    for section in sections:
        rows = (len(section["ann_list"]) + 2) // 3
        total_h += 20 + section_title_h + rows * card_h + max(rows - 1, 0) * grid_gap + 18
    total_h += 78

    img = Image.new("RGBA", (PAGE_W, max(total_h, 300)), PANEL_BG)
    y = _draw_header(img, "鸣潮公告", subtitle)

    if user_info:
        y = _draw_user_info_sync(
            img,
            y,
            user_info.get("userName", ""),
            user_info.get("ipRegion", ""),
            user_avatar,
        )

    for section in sections:
        y += 20
        draw = ImageDraw.Draw(img)
        if not user_id:
            color = section["color"]
            draw.rounded_rectangle((25, y + 5, 31, y + 39), radius=3, fill=color)
            _draw_text(draw, (43, y + 4), section["name"], "#1a1a1a", ww_font_26)
            _draw_text(
                draw,
                (43 + _text_width(section["name"], ww_font_26) + 12, y + 15),
                section["en"],
                TEXT_SUB,
                ww_font_14,
            )
            y += section_title_h

        for index, item in enumerate(section["ann_list"]):
            row, col = divmod(index, 3)
            x = grid_x + col * (card_w + grid_gap)
            item_y = y + row * (card_h + grid_gap)
            card = _create_item_card_sync(
                card_w, card_h, item, section["color"], section["name"] == "周边", item.get("_cover_img")
            )
            _paste_masked(img, card, (x, item_y), 10)

        rows = (len(section["ann_list"]) + 2) // 3
        y += rows * card_h + max(rows - 1, 0) * grid_gap + 18

    img = add_footer(img, PAGE_W // 2, 8, color="black")
    return img


def _create_item_card_sync(w, h, info, color, use_short_id, cover):
    """创建公告列表卡片 (同步)"""
    card = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=10, fill=PANEL_BG)

    cover_h = 110
    cover_bg = (236, 240, 241, 255)
    draw.rectangle((0, 0, w, cover_h), fill=cover_bg)
    if cover:
        card.alpha_composite(clean_alpha_matte(cover, cover_bg), (0, 0))
    else:
        _draw_text(draw, (w // 2, cover_h // 2), "No Image", "#bdc3c7", ww_font_16, "mm")

    id_text = info["short_id"] if use_short_id and info.get("short_id") else info.get("id", "")
    _paste_id_badge(card, f"ID: {id_text}", color)

    info_y = cover_h + 12
    max_title_w = w - 24
    lines = _limit_lines(_wrap_text(info.get("postTitle", "未知公告"), ww_font_16, max_title_w), ww_font_16, max_title_w, 3)
    for line in lines:
        _draw_text(draw, (12, info_y), line, TEXT_MAIN, ww_font_16)
        info_y += 22

    date_text = info.get("date_str", "未知")
    date_w = _text_width(date_text, ww_font_14)
    _draw_text(draw, (w - 12 - date_w, h - 28), date_text, TEXT_SUB, ww_font_14)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=10, outline=(0, 0, 0, 14), width=1)
    return card


async def create_item_card(w, h, info, color, use_short_id):
    """创建公告列表卡片"""
    cover = await _load_cover(info.get("coverUrl", ""), (w, 110), fit=True)
    return _create_item_card_sync(w, h, info, color, use_short_id, cover)


def format_date(ts) -> str:
    """格式化日期"""
    if not ts:
        return "未知"

    if isinstance(ts, str):
        text = ts.strip()
        if not text:
            return "未知"
        if not text.isdigit():
            return text[:10]
        ts = int(text)

    try:
        value = float(ts)
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value).strftime("%m-%d")
    except Exception:
        return "未知"


def _is_image_url(url: str) -> bool:
    return str(url).lower().split("?")[0].endswith(("jpg", "jpeg", "png", "webp"))


async def ann_detail_card(ann_id: Union[int, str], is_check_time=False) -> Union[bytes, str, List[bytes]]:
    ann_list = await waves_api.get_ann_list(True)
    if not ann_list:
        raise Exception("获取游戏公告失败,请检查接口是否正常")

    if isinstance(ann_id, int):
        content = [x for x in ann_list if x["id"] == ann_id]
    else:
        content = [x for x in ann_list if str(x.get("postId", "")) == str(ann_id) or str(x.get("id", "")) == str(ann_id)]

    if content:
        post_id = content[0]["postId"]
    else:
        return "未找到该公告"

    res = await waves_api.get_ann_detail(post_id)
    if not res:
        return "未找到该公告"

    if is_check_time:
        post_time = format_post_time(res["postTime"])
        now_time = int(time.time())
        logger.debug(f"公告id: {ann_id}, post_time: {post_time}, now_time: {now_time}, delta: {now_time - post_time}")
        if post_time < now_time - 86400:
            return "该公告已过期"

    post_content = res["postContent"]
    content_type2_first = [x for x in post_content if x.get("contentType") == 2]
    if not content_type2_first and "coverImages" in res and res["coverImages"]:
        node = dict(res["coverImages"][0])
        node["contentType"] = 2
        post_content.insert(0, node)

    if not post_content:
        return "未找到该公告"

    result_images: List[bytes] = []
    long_image_urls = []
    for item in post_content:
        if item.get("contentType") == 2 and item.get("url"):
            img_width = item.get("imgWidth", 0)
            img_height = item.get("imgHeight", 0)
            if img_width > 0 and img_height / img_width > 5:
                long_image_urls.append(item["url"])

    if long_image_urls:
        for img_url in long_image_urls:
            try:
                img = await pic_download_from_url(ANN_CARD_PATH, img_url)
                if img:
                    result_images.append(await convert_img(flatten_rgba(img, PANEL_BG)))
            except Exception as e:
                logger.warning(f"[鸣潮] 下载超长公告图片失败: {img_url}, {e}")

        post_content = [
            item
            for item in post_content
            if not (item.get("contentType") == 2 and item.get("url") in long_image_urls)
        ]

    blocks = await _prepare_detail_blocks(post_content)
    card = await _draw_detail_page(res, blocks)
    if result_images:
        return [card] + result_images
    return card


async def _prepare_detail_blocks(post_content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    content_w = PAGE_W - 40

    for item in post_content:
        content_type = item.get("contentType")
        if content_type == 1:
            text = _clean_html_text(item.get("content", ""))
            if text:
                lines = _wrap_text(text, ww_font_20, content_w)
                blocks.append({"type": "text", "lines": lines})
            continue

        if content_type == 2 and item.get("url") and _is_image_url(item["url"]):
            image = await _load_cover(item["url"], (content_w, 4200), fit=False)
            if image:
                blocks.append({"type": "image", "image": image})
            continue

        cover_url = item.get("coverUrl") or item.get("videoCoverUrl")
        if cover_url:
            image = await _load_cover(cover_url, (content_w, 500), fit=False)
            if image:
                blocks.append({"type": "video", "image": image})

    return blocks


async def _draw_detail_page(res: Dict[str, Any], blocks: List[Dict[str, Any]]) -> bytes:
    user_avatar = await _load_avatar(res.get("headCodeUrl", ""), 70)
    img = await _compose_detail_page(res, blocks, user_avatar)
    return await convert_img(flatten_rgba(img, PANEL_BG))


@to_thread
def _compose_detail_page(res: Dict[str, Any], blocks: List[Dict[str, Any]], user_avatar) -> Image.Image:
    title = res.get("postTitle", "公告详情")
    logo = _load_logo(60)
    title_x = 30 + ((logo.width + 20) if logo else 0)
    title_w = PAGE_W - title_x - 30
    title_lines = _limit_lines(_wrap_text(title, ww_font_30, title_w), ww_font_30, title_w, 3)
    header_h = max(100, max(60, len(title_lines) * 38) + 40)
    user_h = 104
    content_top = 10

    total_h = header_h + user_h + content_top
    for block in blocks:
        if block["type"] == "text":
            total_h += max(32, len(block["lines"]) * 30) + 10
        else:
            image = block["image"]
            total_h += image.height + 18
    total_h += 78

    img = Image.new("RGBA", (PAGE_W, max(total_h, 320)), PANEL_BG)
    y = _draw_header(img, title, title_right=True)
    y = _draw_user_info_sync(
        img,
        y,
        res.get("userName", "鸣潮"),
        f"发布于 {res.get('postTime', '未知')}",
        user_avatar,
    )
    y += content_top

    draw = ImageDraw.Draw(img)
    for block in blocks:
        if block["type"] == "text":
            y = _draw_text_detail_block(draw, block["lines"], y)
        elif block["type"] == "image":
            y = _draw_image_detail_block(img, block["image"], y)
        elif block["type"] == "video":
            y = _draw_image_detail_block(img, block["image"], y, video=True)

    img = add_footer(img, PAGE_W // 2, 8, color="black")
    return img


def _draw_text_detail_block(draw: ImageDraw.ImageDraw, lines: List[str], y: int) -> int:
    x = 20
    line_h = 30
    for line in lines:
        if line:
            _draw_text(draw, (x, y), line, "#333333", ww_font_20)
        y += line_h if line else 18
    return y + 10


def _draw_image_detail_block(img: Image.Image, image: Image.Image, y: int, video: bool = False) -> int:
    draw = ImageDraw.Draw(img)
    x = (PAGE_W - image.width) // 2
    shadow_box = (x + 2, y + 3, x + image.width + 2, y + image.height + 3)
    draw.rounded_rectangle(shadow_box, radius=8, fill=(0, 0, 0, 12))
    _paste_masked(img, image, (x, y), 8)
    draw.rounded_rectangle((x, y, x + image.width, y + image.height), radius=8, outline=(0, 0, 0, 18), width=1)
    if video:
        label = "▶ 视频内容"
        label_w = _text_width(label, ww_font_14) + 20
        lx = x + image.width - label_w - 10
        ly = y + image.height - 32
        draw.rounded_rectangle((lx, ly, lx + label_w, ly + 24), radius=12, fill=(0, 0, 0, 190))
        _draw_text(draw, (lx + 10, ly + 5), label, "#ffffff", ww_font_14)
    return y + image.height + 18


def format_post_time(post_time: str) -> int:
    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d %H:%M").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d %H:%M:%S").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    return 0
