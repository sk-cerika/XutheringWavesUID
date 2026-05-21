import time
from typing import List, Union
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.pool import to_thread
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import crop_center_img

from ..utils.hint import error_reply
from ..utils.util import async_func_lock, hide_uid, get_hide_uid_pref
from ..utils.cache import TimedCache
from ..utils.image import (
    RED,
    GOLD,
    GREY,
    CHAIN_COLOR,
    add_footer,
    get_star_bg,
    get_square_avatar,
    draw_text_with_shadow,
    get_random_share_bg_path,
)
from ..utils.button import WavesButton
from ..utils.api.model import RoleDetailData, AccountBaseInfo
from ..utils.imagetool import draw_pic_with_ring
from ..utils.waves_api import waves_api
from ..utils.error_reply import WAVES_CODE_102
from ..utils.expression_ctx import WavesCharRank, get_waves_char_rank
from ..utils.char_info_utils import get_all_role_detail_info_list
from ..utils.database.models import WavesBind
from ..wutheringwaves_config import PREFIX, WutheringWavesConfig
from ..utils.fonts.waves_fonts import (
    waves_font_25,
    waves_font_26,
    waves_font_30,
    waves_font_40,
    waves_font_42,
    waves_font_60,
)
from ..utils.resource.constant import NAME_ALIAS, SPECIAL_CHAR_NAME
from ..utils.refresh_char_detail import refresh_char, save_base_info_cache
from . import base_info_cache

TEXT_PATH = Path(__file__).parent / "texture2d"

refresh_char_bg = Image.open(TEXT_PATH / "refresh_char_bg.png")
refresh_yes = Image.open(TEXT_PATH / "refresh_yes.png")
refresh_yes = refresh_yes.resize((40, 40))
refresh_no = Image.open(TEXT_PATH / "refresh_no.png")
refresh_no = refresh_no.resize((40, 40))


refresh_role_map = {
    "share_02.webp": (1000, 180, 2560, 1320),
    "share_14.webp": (1000, 180, 2560, 1320),
}

# 全部刷新的间隔配置
refresh_interval: int = WutheringWavesConfig.get_config("RefreshInterval").data
# 单角色刷新的间隔配置
refresh_single_char_interval: int = WutheringWavesConfig.get_config("RefreshSingleCharInterval").data

# 全部刷新的缓存
if refresh_interval > 0:
    timed_cache = TimedCache(timeout=refresh_interval, maxsize=10000)
else:
    timed_cache = None

# 单角色刷新的缓存
if refresh_single_char_interval > 0:
    timed_cache_single = TimedCache(timeout=refresh_single_char_interval, maxsize=10000)
else:
    timed_cache_single = None


def can_refresh_card(user_id: str, uid: str, is_single_refresh: bool = False) -> int:
    """检查是否可以刷新角色面板

    Args:
        user_id: 用户ID
        uid: 游戏UID
        is_single_refresh: 是否为单角色刷新

    Returns:
        剩余冷却时间(秒),0表示可以刷新
    """
    key = f"{user_id}_{uid}"
    cache = timed_cache_single if is_single_refresh else timed_cache

    if cache:
        now = int(time.time())
        time_stamp = cache.get(key)
        if time_stamp and time_stamp > now:
            return time_stamp - now
    return 0


def set_cache_refresh_card(user_id: str, uid: str, is_single_refresh: bool = False):
    """设置缓存

    Args:
        user_id: 用户ID
        uid: 游戏UID
        is_single_refresh: 是否为单角色刷新
    """
    cache = timed_cache_single if is_single_refresh else timed_cache
    interval = refresh_single_char_interval if is_single_refresh else refresh_interval

    if cache:
        key = f"{user_id}_{uid}"
        cache.set(key, int(time.time()) + interval)


def get_refresh_interval_notify(time_stamp: int, is_single_refresh: bool = False):
    """获取刷新间隔通知文案

    Args:
        time_stamp: 剩余冷却时间(秒)
        is_single_refresh: 是否为单角色刷新

    Returns:
        通知文案
    """
    try:
        if is_single_refresh:
            value: str = WutheringWavesConfig.get_config("RefreshSingleCharIntervalNotify").data
            default = "请等待{0}s后尝试刷新角色面板！"
        else:
            value: str = WutheringWavesConfig.get_config("RefreshIntervalNotify").data
            default = "请等待{0}s后尝试刷新面板！"
        return value.format(time_stamp)
    except Exception:
        if is_single_refresh:
            return "请等待{0}s后尝试刷新角色面板！".format(time_stamp)
        else:
            return "请等待{0}s后尝试刷新面板！".format(time_stamp)


async def get_refresh_role_img(width: int, height: int):
    path = await get_random_share_bg_path()
    return await _render_refresh_role_img(path, width, height)


@to_thread
def _render_refresh_role_img(path: Path, width: int, height: int):
    img = Image.open(path).convert("RGBA")
    if path.name in refresh_role_map:
        img = img.crop(refresh_role_map[path.name])
    else:
        # 2560, 1440
        img = img.crop((700, 100, 2300, 1340))
    if height > img.height:
        img = crop_center_img(img, width, height)
    else:
        img = img.resize((width, int(width / img.width * img.height)))

    # 创建毛玻璃效果
    blur_img = img.filter(ImageFilter.GaussianBlur(radius=2))
    blur_img = ImageEnhance.Brightness(blur_img).enhance(0.35)
    blur_img = ImageEnhance.Contrast(blur_img).enhance(0.9)

    # 合并图层
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    result.paste(blur_img, (0, 0))

    # 计算角色区域位置和尺寸
    char_panel_y = 470  # 角色区域开始的Y坐标
    char_panel_height = height - char_panel_y - 50  # 角色区域高度
    char_panel_width = width - 100  # 角色区域宽度

    # 创建毛玻璃面板
    char_panel = Image.new("RGBA", (char_panel_width, char_panel_height), (0, 0, 0, 0))
    char_panel_draw = ImageDraw.Draw(char_panel)

    # 绘制圆角矩形毛玻璃背景
    char_panel_draw.rounded_rectangle(
        [(0, 0), (char_panel_width, char_panel_height)],
        radius=30,
        fill=(0, 0, 0, 90),
    )

    # 添加内部渐变效果
    inner_panel = Image.new("RGBA", (char_panel_width - 20, char_panel_height - 20), (0, 0, 0, 0))
    inner_panel_draw = ImageDraw.Draw(inner_panel)
    inner_panel_draw.rounded_rectangle(
        [(0, 0), (char_panel_width - 20, char_panel_height - 20)],
        radius=25,
        fill=(255, 255, 255, 20),
    )

    # 合并渐变到角色面板
    char_panel.alpha_composite(inner_panel, (10, 10))

    # 添加角色面板到结果图像
    result.alpha_composite(char_panel, (50, char_panel_y))

    return result


# TODO: PIL 卸到线程池 (await/PIL 深度交错, draw_pic 已单独卸载)
@async_func_lock(keys=["user_id", "uid"])
async def draw_refresh_char_detail_img(
    bot: Bot,
    ev: Event,
    user_id: str,
    uid: str,
    buttons: List[WavesButton],
    refresh_type: Union[str, List[str]] = "all",
):
    # 判断是单角色刷新还是全部刷新
    is_single_refresh = refresh_type != "all"

    time_stamp = can_refresh_card(user_id, uid, is_single_refresh)
    if time_stamp > 0:
        return get_refresh_interval_notify(time_stamp, is_single_refresh), 0, None
    self_ck, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
    if not ck:
        return error_reply(WAVES_CODE_102), 0, None
    user_pref = await get_hide_uid_pref(uid, user_id, ev.bot_id)
    # 账户数据
    account_info = await waves_api.get_base_info(uid, ck)
    if not account_info.success:
        return account_info.throw_msg(), 0, None
    if not account_info.data:
        return f"用户未展示数据, 请尝试【{PREFIX}登录】", 0, None
    account_info = AccountBaseInfo.model_validate(account_info.data)
    # 缓存账户基本信息
    await save_base_info_cache(uid, account_info)
    base_info_cache.set(uid, account_info)
    # 更新group id
    await WavesBind.insert_waves_uid(user_id, ev.bot_id, uid, ev.group_id, lenth_limit=9)

    waves_map = {"refresh_update": {}, "refresh_unchanged": {}, "top_improver": None}
    if ev.command in ["面板", "面包", "🍞", "mb"]:
        all_waves_datas = await get_all_role_detail_info_list(uid)
        if not all_waves_datas:
            return "暂无面板数据", 0, None
        waves_map = {
            "refresh_update": {},
            "refresh_unchanged": {i.role.roleId: i.model_dump() for i in all_waves_datas},
            "top_improver": None,
        }
    else:
        waves_datas = await refresh_char(
            ev,
            uid,
            user_id,
            ck,
            waves_map=waves_map,
            is_self_ck=self_ck,
            refresh_type=refresh_type,
        )
        if isinstance(waves_datas, str):
            return waves_datas, 0, None

    role_detail_list = [
        RoleDetailData(**r) for key in ["refresh_update", "refresh_unchanged"] for r in waves_map[key].values()
    ]

    # 总角色个数
    role_len = len(role_detail_list)
    # 刷新个数
    role_update = len(waves_map["refresh_update"])
    shadow_title = "刷新成功!"
    shadow_color = GOLD
    if role_update == 0:
        shadow_title = "数据未更新"
        shadow_color = RED

    cols = 4 if is_single_refresh else 6
    card_spacing = 280 if is_single_refresh else 300
    card_margin = 40 if is_single_refresh else 80
    role_high = role_len // cols + (0 if role_len % cols == 0 else 1)
    height = 470 + 75 + role_high * 330
    width = 1200 if is_single_refresh else 2000
    # img = get_waves_bg(width, height, "bg3")
    img = Image.new("RGBA", (width, height))
    img.alpha_composite(await get_refresh_role_img(width, height), (0, 0))

    # 提示文案
    title = f"共刷新{role_update}个角色，可以使用"
    name = role_detail_list[0].role.roleName
    name = NAME_ALIAS.get(name, name)
    title2 = f"{PREFIX}{name}面板"
    title3 = "来查询该角色的具体面板"
    info_block = Image.new("RGBA", (980, 50), color=(255, 255, 255, 0))
    info_block_draw = ImageDraw.Draw(info_block)
    info_block_draw.rounded_rectangle([0, 0, 980, 50], radius=15, fill=(128, 128, 128, int(0.3 * 255)))
    t1_w = info_block_draw.textlength(title, waves_font_30)
    t2_w = info_block_draw.textlength(title2, waves_font_30)
    t3_w = info_block_draw.textlength(title3, waves_font_30)
    start_x = (980 - t1_w - 20 - t2_w - 10 - t3_w) / 2
    info_block_draw.text((start_x, 24), f"{title}", GREY, waves_font_30, "lm")
    info_block_draw.text((start_x + t1_w + 20, 24), f"{title2}", (255, 180, 0), waves_font_30, "lm")
    info_block_draw.text((start_x + t1_w + 20 + t2_w + 10, 24), f"{title3}", GREY, waves_font_30, "lm")
    img.alpha_composite(info_block, ((width - 980) // 2, 400))

    waves_char_rank = await get_waves_char_rank(uid, role_detail_list)

    map_update = []
    map_unchanged = []
    for _, char_rank in enumerate(waves_char_rank):
        isUpdate = True if char_rank.roleId in waves_map["refresh_update"] else False
        if isUpdate:
            map_update.append(char_rank)
        else:
            map_unchanged.append(char_rank)

    map_update.sort(key=lambda x: x.score if x.score else 0, reverse=True)
    map_unchanged.sort(key=lambda x: x.score if x.score else 0, reverse=True)

    rIndex = 0
    for char_rank in map_update:
        pic = await draw_pic(char_rank, True)  # type: ignore
        img.alpha_composite(pic, (card_margin + card_spacing * (rIndex % cols), 470 + (rIndex // cols) * 330))
        rIndex += 1
        if rIndex <= 5:
            name = SPECIAL_CHAR_NAME.get(str(char_rank.roleId), char_rank.roleName)
            b = WavesButton(name, f"{name}面板")  # type: ignore
            buttons.append(b)

    for char_rank in map_unchanged:
        pic = await draw_pic(char_rank, False)  # type: ignore
        img.alpha_composite(pic, (card_margin + card_spacing * (rIndex % cols), 470 + (rIndex // cols) * 330))
        rIndex += 1

        if len(map_update) == 0 and rIndex <= 5:
            name = SPECIAL_CHAR_NAME.get(str(char_rank.roleId), char_rank.roleName)
            b = WavesButton(name, f"{name}面板")  # type: ignore
            buttons.append(b)

    buttons.append(WavesButton("练度统计", "练度统计"))

    # 基础信息 名字 特征码
    base_info_bg = Image.open(TEXT_PATH / "base_info_bg.png")
    base_info_draw = ImageDraw.Draw(base_info_bg)
    base_info_draw.text((275, 120), f"{account_info.name[:10]}", "white", waves_font_30, "lm")
    base_info_draw.text((226, 173), f"特征码:  {hide_uid(account_info.id, user_pref=user_pref)}", GOLD, waves_font_25, "lm")
    img.paste(base_info_bg, (15, 20), base_info_bg)

    # 头像 头像环
    avatar, avatar_ring = await draw_pic_with_ring(ev)
    img.paste(avatar, (25, 70), avatar)
    img.paste(avatar_ring, (35, 80), avatar_ring)

    # 账号基本信息，由于可能会没有，放在一起
    if account_info.is_full:
        title_bar = Image.open(TEXT_PATH / "title_bar.png")
        title_bar_draw = ImageDraw.Draw(title_bar)
        title_bar_draw.text((660, 125), "账号等级", GREY, waves_font_26, "mm")
        title_bar_draw.text((660, 78), f"Lv.{account_info.level}", "white", waves_font_42, "mm")

        title_bar_draw.text((810, 125), "世界等级", GREY, waves_font_26, "mm")
        title_bar_draw.text((810, 78), f"Lv.{account_info.worldLevel}", "white", waves_font_42, "mm")
        img.paste(title_bar, (-20, 70), title_bar)

    # bar
    refresh_bar = Image.open(TEXT_PATH / "refresh_bar_single.png") if is_single_refresh else Image.open(TEXT_PATH / "refresh_bar.png")
    if is_single_refresh and refresh_bar.width > width:
        refresh_bar = refresh_bar.crop((0, 0, width, refresh_bar.height))
    refresh_bar_draw = ImageDraw.Draw(refresh_bar)
    bar_title_x = 600 if is_single_refresh else 1010
    bar_login_x = 970 if is_single_refresh else 1700
    bar_icon_x = 1050 if is_single_refresh else 1800
    draw_text_with_shadow(
        refresh_bar_draw,
        f"{shadow_title}",
        bar_title_x,
        40,
        waves_font_60,
        shadow_color=shadow_color,
        offset=(2, 2),
        anchor="mm",
    )
    draw_text_with_shadow(
        refresh_bar_draw,
        "登录状态:",
        bar_login_x,
        20,
        waves_font_40,
        shadow_color=GOLD,
        offset=(2, 2),
        anchor="mm",
    )
    if self_ck:
        refresh_bar.alpha_composite(refresh_yes.resize((60, 60)), (bar_icon_x, -8))
    else:
        refresh_bar.alpha_composite(refresh_no.resize((60, 60)), (bar_icon_x, -8))

    img.paste(refresh_bar, (0, 300), refresh_bar)
    img = add_footer(img, 600, 20)
    img = await convert_img(img)
    set_cache_refresh_card(user_id, uid, is_single_refresh)
    return img, role_update, waves_map.get("top_improver")


async def draw_pic(char_rank: WavesCharRank, isUpdate=False):
    pic = await get_square_avatar(char_rank.roleId)
    star_bg = await get_star_bg(char_rank.starLevel)
    return await _compose_refresh_char_pic(char_rank, pic, star_bg, isUpdate)


@to_thread
def _compose_refresh_char_pic(char_rank: WavesCharRank, pic, star_bg, isUpdate=False):
    resize_pic = pic.resize((200, 200))
    img = refresh_char_bg.copy()
    img_draw = ImageDraw.Draw(img)
    img.alpha_composite(resize_pic, (50, 50))
    star_bg = star_bg.resize((220, 220))
    img.alpha_composite(star_bg, (40, 30))

    # 遮罩
    mask = Image.new("RGBA", (220, 70), color=(0, 0, 0, 128))
    img.alpha_composite(mask, (40, 255))

    # 名字
    roleName = SPECIAL_CHAR_NAME.get(str(char_rank.roleId), char_rank.roleName)

    img_draw.text((150, 290), f"{roleName}", "white", waves_font_40, "mm")
    # 命座
    info_block = Image.new("RGBA", (80, 40), color=(255, 255, 255, 0))
    info_block_draw = ImageDraw.Draw(info_block)
    fill = CHAIN_COLOR[char_rank.chain] + (int(0.9 * 255),)
    info_block_draw.rounded_rectangle([0, 0, 80, 40], radius=5, fill=fill)
    info_block_draw.text((12, 20), f"{char_rank.chainName}", "white", waves_font_30, "lm")
    img.alpha_composite(info_block, (200, 15))

    # 评分
    if char_rank.score > 0.0:
        name_len = len(roleName)
        _x = 150 + int(43 * (name_len / 2))
        score_bg = Image.open(TEXT_PATH / f"refresh_{char_rank.score_bg}.png")
        img.alpha_composite(score_bg, (_x, 265))

    if isUpdate:
        name_len = len(roleName)
        _x = 100 - int(43 * (name_len / 2))
        img.alpha_composite(refresh_yes, (_x, 270))

    return img
