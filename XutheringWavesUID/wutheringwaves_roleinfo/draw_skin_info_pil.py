import asyncio
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.pool import to_thread
from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.image.convert import convert_img

from ..wutheringwaves_config import PREFIX
from ..utils.at_help import ruser_id
from ..utils.util import get_hide_uid_pref, hide_uid
from ..utils.waves_api import waves_api
from ..utils.api.model import SkinData, MotorData, AccountBaseInfo
from ..utils.image import GOLD, GREY, add_footer, get_waves_bg, pic_download_from_url
from ..utils.imagetool import draw_pic_with_ring
from .draw_role_info_pil import draw_identity_header
from ..utils.fonts.waves_fonts import (
    fit_text,
    waves_font_8,
    waves_font_9,
    waves_font_10,
    waves_font_12,
    waves_font_14,
    waves_font_16,
    waves_font_18,
    waves_font_30,
)

TEXT_PATH = Path(__file__).parent / "texture2d"
SKIN_TEX_PATH = TEXT_PATH / "skin"
SKIN_ICON_CACHE = get_res_path("XutheringWavesUID") / "skin_icon"

# 品质底色边框
QUALITY_BORDER = {5: (212, 177, 99), 4: (160, 110, 200), 3: (90, 120, 190)}


def _eff_quality(q):
    """特别定制(501)及 quality>5 视为 5; 兜底下限 3"""
    return min(max(q or 3, 3), 5)


def _sort_items(items):
    """按 quality 降序, 同档用接口 priority 降序"""
    return sorted(items, key=lambda it: (it["quality"], it.get("priority", 0)), reverse=True)


def build_skin_blocks(skin_data: SkinData):
    """按官方收藏图鉴分块: 共鸣者服饰(排除三星) / 服饰饰品 / 武器投影 / 声骸换影 / 终端替换"""
    blocks = [
        {
            "title": "共鸣者服饰",
            "header": "header_role.png",
            "items": _sort_items([
                {
                    "icon": s.skinIcon,
                    "name": s.skinName,
                    "quality": _eff_quality(s.quality),
                    "priority": s.priority or 0,
                    "type_icon": "type_role_weapon.png" if s.isAddition else "type_role.png",
                }
                for s in skin_data.roleSkinList
                if (s.quality or 0) > 3
            ]),
        },
        {
            "title": "服饰饰品",
            "header": "header_decoration.png",
            "items": _sort_items([
                {"icon": d.icon, "name": d.name, "quality": _eff_quality(d.quality), "type_icon": "type_decoration.png"}
                for d in skin_data.roleDecorationList
            ]),
        },
        {
            "title": "武器投影",
            "header": "header_weapon.png",
            "items": _sort_items([
                {
                    "icon": w.skinIcon,
                    "name": w.skinName,
                    "quality": _eff_quality(w.quality),
                    "priority": w.priority or 0,
                    "type_icon": "type_weapon.png",
                }
                for w in skin_data.weaponSkinList
            ]),
        },
        {
            "title": "声骸换影",
            "header": "header_equip.png",
            "items": _sort_items([
                {"icon": e.skinIcon, "name": e.skinName, "quality": _eff_quality(e.quality), "type_icon_url": e.skinTypeIcon}
                for e in skin_data.equipSkinList
            ]),
        },
        {
            "title": "终端替换",
            "header": "header_calabash.png",
            "items": _sort_items([
                {"icon": c.skinIcon, "name": c.skinName, "quality": _eff_quality(c.quality), "type_icon": "type_calabash.png"}
                for c in skin_data.calabashSkinList
            ]),
        },
    ]
    out = [b for b in blocks if b["items"]]
    for b in out:
        b.setdefault("cols", 8)
        b.setdefault("wide", False)
    return out


def build_motor_blocks(motor_data: MotorData):
    """科考摩托: 涂装 / 车架(宽图,一行两个) / 外观定制"""
    si = motor_data.skinInfo

    def items(lst):
        # quality 降序; 同名归并相邻(贴纸 part1/2/3 一组); 同名内按 part/sort
        return sorted(
            [{"icon": it.pictureUrl, "name": it.name or "", "quality": _eff_quality(it.quality), "sort": it.sort or 0} for it in lst],
            key=lambda x: (-x["quality"], x["name"], x["sort"]),
        )

    blocks = [
        {"title": "涂装", "header": "header_motor_sticker.png", "cols": 8, "wide": False, "items": items(si.stickerList)},
        {"title": "车架模组", "header": "header_motor_frame.png", "cols": 2, "wide": True, "items": items(si.frameList)},
        {"title": "摩托饰品", "header": "header_motor_deco.png", "cols": 8, "wide": False, "items": items(si.decorationList)},
    ]
    return [b for b in blocks if b["items"]]


async def _safe_download(url: str) -> Optional[Image.Image]:
    if not url:
        return None
    try:
        return await pic_download_from_url(SKIN_ICON_CACHE, url)
    except Exception as e:
        logger.warning(f"[鸣潮·服饰] 下载图片失败: {url}, {e}")
        return None


async def draw_skin_img(uid: str, ck: str, ev: Event):
    user_pref = await get_hide_uid_pref(uid, ruser_id(ev), ev.bot_id)

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

    # 预取所有图片(异步IO), 留给 PIL 线程
    for b in blocks:
        b["header_img"] = (
            Image.open(SKIN_TEX_PATH / b["header"]).convert("RGBA") if (SKIN_TEX_PATH / b["header"]).exists() else None
        )

        async def _prep(item):
            item["icon_img"] = await _safe_download(item.get("icon"))
            if item.get("type_icon_url"):
                item["type_img"] = await _safe_download(item["type_icon_url"])
            elif item.get("type_icon") and (SKIN_TEX_PATH / item["type_icon"]).exists():
                item["type_img"] = Image.open(SKIN_TEX_PATH / item["type_icon"]).convert("RGBA")
            else:
                item["type_img"] = None

        await asyncio.gather(*(_prep(it) for it in b["items"]))

    # 头像 头像环
    avatar, avatar_ring = await draw_pic_with_ring(ev)

    card_img = await _compose_skin_img(account_info, skin_data, blocks, avatar, avatar_ring, uid, user_pref)
    return await convert_img(card_img)


# 网格参数
COLS = 8
CELL = 108
GAP = 16
MARGIN = 50
HEAD_Y = 300  # base_info_bg 高度


@to_thread
def _compose_skin_img(
    account_info: Optional[AccountBaseInfo],
    skin_data: SkinData,
    blocks,
    avatar,
    avatar_ring,
    uid,
    user_pref,
):
    grid_w = COLS * CELL + (COLS - 1) * GAP
    w = MARGIN * 2 + grid_w
    block_title_h = 70
    NAME_H = 40  # 名称区高度

    def _dims(block):
        """每块的列数/格子宽高: 车架(wide)宽图矮一行两个, 其余方形一行六个"""
        cols = block.get("cols", COLS)
        cw = (grid_w - (cols - 1) * GAP) // cols
        ch = round(cw * 214 / 690) if block.get("wide") else cw  # 车架对齐大背景框比例
        return cols, cw, ch

    # 预算高度
    h = HEAD_Y
    for b in blocks:
        cols, _cw, ch = _dims(b)
        rows = (len(b["items"]) + cols - 1) // cols
        h += block_title_h + rows * (ch + NAME_H) + 30
    h += 100

    card_img = get_waves_bg(w, h)

    # 顶部: 与卡片一致
    draw_identity_header(
        card_img,
        account_info.name[:10] if account_info else "鸣潮",
        f"特征码:  {hide_uid(account_info.id if account_info else uid, user_pref=user_pref)}",
        avatar,
        avatar_ring,
    )

    def _draw_title(_y: int, title: str, header_img):
        bar = Image.new("RGBA", (grid_w, 50), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar)
        bd.rounded_rectangle([0, 0, grid_w, 50], radius=8, fill=(20, 22, 26, 200))
        bd.rectangle([0, 0, 5, 50], fill=GOLD)
        tx = 20
        if header_img is not None:
            ic = header_img.resize((34, 34))
            bar.paste(ic, (tx, 8), ic)
            tx += 44
        bd.text((tx, 25), title, "white", waves_font_30, "lm")
        card_img.paste(bar, (MARGIN, _y), bar)

    def _draw_item(_x: int, _y: int, item, cw: int, ch: int, wide: bool):
        quality = item.get("quality", 3)
        # 底图: 车架用官方专门大背景框, 其余按品质
        if wide:
            bgpath = SKIN_TEX_PATH / "frame_bg.png"
        else:
            bgpath = SKIN_TEX_PATH / f"quality_{quality if quality in (3, 4, 5) else 3}.png"
        if bgpath.exists():
            bg = Image.open(bgpath).convert("RGBA").resize((cw, ch))
        else:
            bg = Image.new("RGBA", (cw, ch), (40, 44, 52, 255))
        cell = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cell.paste(bg, (0, 0), bg)

        icon_img = item.get("icon_img")
        if icon_img is not None:
            ic = icon_img.convert("RGBA")
            bb = ic.getchannel("A").getbbox()  # 裁掉透明边
            if bb:
                ic = ic.crop(bb)
            if wide:  # 车架宽图: 整体 contain 完整展示
                scale = min((cw - 20) / ic.width, (ch - 20) / ic.height)
            else:  # 方形: 统一主体高度, 宽度自适应
                scale = (ch - 30) / ic.height
            nw, nh = max(1, round(ic.width * scale)), max(1, round(ic.height * scale))
            ic = ic.resize((nw, nh))
            cell.paste(ic, ((cw - nw) // 2, (ch - nh) // 2), ic)

        # 车架品质长条(底部)
        if wide:
            flp = SKIN_TEX_PATH / "frame_level.png"
            if flp.exists():
                fl = Image.open(flp).convert("RGBA")
                fh = max(1, round(fl.height * cw / fl.width))
                cell.alpha_composite(fl.resize((cw, fh)), (0, ch - fh))

        # 左上角类型图标
        type_img = item.get("type_img")
        if type_img is not None:
            t = type_img.convert("RGBA").resize((32, 32))
            t.putalpha(t.getchannel("A").point(lambda a: int(a * 0.82)))
            cell.paste(t, (6, 6), t)

        # 品质边框
        cd = ImageDraw.Draw(cell)
        cd.rounded_rectangle([1, 1, cw - 2, ch - 2], radius=10, outline=QUALITY_BORDER.get(quality, GREY), width=2)

        card_img.paste(cell, (_x, _y), cell)

        # 名称: 实测宽度自适应字号, 过窄才截断
        nd = ImageDraw.Draw(card_img)
        name_font, nm = fit_text(
            nd,
            item.get("name") or "",
            cw - 8,
            (waves_font_18, waves_font_16, waves_font_14, waves_font_12, waves_font_10, waves_font_9, waves_font_8),
        )
        nd.text((_x + cw // 2, _y + ch + 18), nm, "white", name_font, "mm")

    y = HEAD_Y
    for b in blocks:
        _draw_title(y, b["title"], b.get("header_img"))
        y += block_title_h
        cols, cw, ch = _dims(b)
        wide = b.get("wide", False)
        for idx, item in enumerate(b["items"]):
            _x = MARGIN + (idx % cols) * (cw + GAP)
            _y = y + (idx // cols) * (ch + NAME_H)
            _draw_item(_x, _y, item, cw, ch, wide)
        rows = (len(b["items"]) + cols - 1) // cols
        y += rows * (ch + NAME_H) + 30

    card_img = add_footer(card_img, 600, 20)
    return card_img
