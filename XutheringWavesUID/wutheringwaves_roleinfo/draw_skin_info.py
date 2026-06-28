import base64
import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timezone, timedelta

from PIL import Image

from gsuid_core.pool import to_thread
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path

from ..utils.at_help import ruser_id
from ..utils.util import get_hide_uid_pref, hide_uid
from ..utils.waves_api import waves_api
from ..wutheringwaves_config import WutheringWavesConfig, PREFIX
from ..utils.api.model import SkinData, MotorData, AccountBaseInfo
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    render_html,
    image_to_base64,
    get_footer_b64,
    get_image_b64_with_cache,
)
from ..utils.resource.RESOURCE_PATH import BAKE_PATH, waves_templates
from ..utils.image import (
    pil_to_b64,
    get_waves_bg,
    get_event_avatar,
    pic_download_from_url,
)

from .draw_skin_info_pil import (
    SKIN_TEX_PATH,
    SKIN_ICON_CACHE,
    build_skin_blocks,
    build_motor_blocks,
    draw_skin_img as draw_skin_img_pil,
)

# 归一化高度: 裁掉透明边后统一缩放到该高度, 宽度自适应 → 每个 item 主体一样高
NORM_H = 220


@lru_cache(maxsize=64)
def _local_b64(name: str) -> str:
    return image_to_base64(SKIN_TEX_PATH / name)


@to_thread
def _normalize_b64(img: Image.Image, cache_key: str) -> str:
    bake_path = BAKE_PATH / f"skinnorm_{cache_key}_h{NORM_H}.webp"
    if bake_path.exists():
        data = bake_path.read_bytes()
    else:
        ic = img.convert("RGBA")
        bb = ic.getchannel("A").getbbox()
        if bb:
            ic = ic.crop(bb)
        scale = NORM_H / ic.height
        nw, nh = max(1, round(ic.width * scale)), NORM_H
        ic = ic.resize((nw, nh), Image.LANCZOS)
        buf = BytesIO()
        ic.save(buf, "WEBP", quality=85)
        data = buf.getvalue()
        try:
            bake_path.write_bytes(data)
        except Exception:
            pass
    return f"data:image/webp;base64,{base64.b64encode(data).decode()}"


async def _norm_icon_b64(url: str) -> str:
    if not url:
        return ""
    try:
        img = await pic_download_from_url(SKIN_ICON_CACHE, url)
        return await _normalize_b64(img, hashlib.md5(url.encode()).hexdigest()[:12])
    except Exception as e:
        logger.warning(f"[鸣潮·服饰] 处理图标失败: {url}, {e}")
        return ""


async def draw_skin_img(uid: str, ck: str, ev: Event):
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await draw_skin_img_pil(uid, ck, ev)
    user_pref = await get_hide_uid_pref(uid, ruser_id(ev), ev.bot_id)

    try:
        # 服饰数据
        skin_resp = await waves_api.get_skin_data(uid, ck)
        if not skin_resp.success:
            return skin_resp.throw_msg()
        skin_data = SkinData.model_validate(skin_resp.data)

        # 账户数据(仅用于头部, 不请求角色列表)
        account_info = None
        account_resp = await waves_api.get_base_info(uid, ck)
        if account_resp.success and account_resp.data:
            account_info = AccountBaseInfo.model_validate(account_resp.data)

        blocks = build_skin_blocks(skin_data)

        # 科考摩托(涂装/车架/外观定制), 失败不影响服饰图鉴
        try:
            motor_resp = await waves_api.get_motor_data(uid, ck)
            if motor_resp.success:
                blocks += build_motor_blocks(MotorData.model_validate(motor_resp.data))
        except Exception as e:
            logger.warning(f"[鸣潮·服饰] 获取摩托失败: {e}")

        if not blocks:
            return f"未获取到服饰数据, 请尝试【{PREFIX}登录】"

        async def _prep(item):
            item["icon_b64"] = await _norm_icon_b64(item.get("icon"))
            if item.get("type_icon_url"):
                item["type_b64"] = await get_image_b64_with_cache(item["type_icon_url"], SKIN_ICON_CACHE)
            elif item.get("type_icon"):
                item["type_b64"] = _local_b64(item["type_icon"])
            else:
                item["type_b64"] = ""

        await asyncio.gather(*(_prep(it) for b in blocks for it in b["items"]))
        for b in blocks:
            b["header_b64"] = _local_b64(b["header"])
            b["count"] = len(b["items"])

        avatar = await get_event_avatar(ev)
        avatar_url = pil_to_b64(avatar, quality=75)
        bg_img = get_waves_bg(bg="bg", crop=False)
        bg_url = pil_to_b64(bg_img, quality=75)

        current_date = (
            datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        )

        context = {
            "user_name": (account_info.name[:10] if account_info else "鸣潮"),
            "user_id": hide_uid(account_info.id if account_info else uid, user_pref=user_pref),
            "level": (account_info.level if account_info else 0) or 0,
            "world_level": (account_info.worldLevel if account_info else 0) or 0,
            "show_stats": bool(account_info and account_info.is_full),
            "total_count": sum(b["count"] for b in blocks),
            "avatar_url": avatar_url,
            "bg_url": bg_url,
            "current_date": current_date,
            "blocks": blocks,
            "q3_bg": _local_b64("quality_3.png"),
            "q4_bg": _local_b64("quality_4.png"),
            "q5_bg": _local_b64("quality_5.png"),
            "frame_bg": _local_b64("frame_bg.png"),
            "frame_level": _local_b64("frame_level.png"),
            "footer_b64": get_footer_b64(footer_type="white") or "",
        }

        logger.debug("[鸣潮·服饰] 准备通过HTML渲染收藏图鉴")
        img_bytes = await render_html(waves_templates, "roleinfo/skin_card.html", context)
        if img_bytes:
            return img_bytes
        logger.warning("[鸣潮·服饰] Playwright 渲染返回空, 回退到 PIL 渲染")
        return await draw_skin_img_pil(uid, ck, ev)

    except Exception as e:
        logger.exception(f"[鸣潮·服饰] HTML渲染失败: {e}")
        return await draw_skin_img_pil(uid, ck, ev)
