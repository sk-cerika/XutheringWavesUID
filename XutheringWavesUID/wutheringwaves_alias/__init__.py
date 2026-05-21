from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .char_alias_ops import char_alias_list, action_char_alias
from .char_alias_pil import draw_all_char_alias_pil
from ..utils.name_convert import load_alias_data
from ..utils.char_info_utils import PATTERN

sv_add_char_alias = SV("ww角色名别名", pm=0)
sv_list_char_alias = SV("ww角色名别名列表")


@sv_add_char_alias.on_regex(
    rf"^(?P<action>添加|删除)(?P<name>{PATTERN})别名(?P<aliases>.+)$",
    block=True,
)
async def handle_add_char_alias(bot: Bot, ev: Event):
    import re as _re
    action = ev.regex_dict.get("action")
    if action not in ["添加", "删除"]:
        return
    char_name = ev.regex_dict.get("name")
    raw = ev.regex_dict.get("aliases", "").strip()
    if not char_name or not raw:
        return await bot.send("角色名或别名不能为空")

    alias_list = [a.strip() for a in _re.split(r'[,，\s]+', raw) if a.strip()]
    if not alias_list:
        return await bot.send("别名不能为空")

    msgs = []
    need_reload = False
    for alias in alias_list:
        msg = await action_char_alias(action, char_name, alias)
        msgs.append(msg)
        if "成功" in msg:
            need_reload = True
    if need_reload:
        load_alias_data()
    await bot.send("\n".join(msgs))


@sv_list_char_alias.on_regex(
    rf"^(?P<name>{PATTERN})别名(列表)?$",
    block=True,
    to_ai="""查询某角色已注册的全部别名（俗称、外号、英文缩写）。

当用户问「长离别名 / 维里奈有什么外号」时调用。
text 必须是 "<角色名>别名" 格式（regex 匹配）。例: text="长离别名"、text="椿别名列表"。

Args:
    text: "<角色名>别名" 或 "<角色名>别名列表"。例: "长离别名"。
""",
)
async def handle_list_char_alias(bot: Bot, ev: Event):
    char_name = ev.regex_dict.get("name")
    if not char_name:
        return await bot.send("角色名不能为空")
    char_name = char_name.strip()
    msg = await char_alias_list(char_name)
    await bot.send(msg)


@sv_list_char_alias.on_fullmatch(
    ("别名", "别名列表"),
    block=True,
    to_ai="""查询鸣潮全部角色的别名一览图（所有角色的别名汇总）。

当用户问「鸣潮角色别名列表 / 都有谁的别名 / 别名一览」时调用。
返回包含全部角色的别名表格图，图中含角色 ID。

Args:
    text: 无需参数，留空即可。
""",
)
async def handle_all_char_alias(bot: Bot, ev: Event):
    """Render all character aliases as a single image."""
    from ..utils.name_convert import char_alias_data, alias_to_char_name_list
    from ..utils.name_convert import char_name_to_char_id
    from ..utils.image import get_square_avatar, pil_to_b64
    from ..utils.render_utils import PLAYWRIGHT_AVAILABLE, render_html, get_footer_b64
    from ..utils.resource.RESOURCE_PATH import waves_templates
    from ..wutheringwaves_config import WutheringWavesConfig

    if not char_alias_data:
        load_alias_data()
    if not char_alias_data:
        return await bot.send("暂无别名数据")

    chars = []
    for name in sorted(char_alias_data.keys()):
        char_id = str(char_name_to_char_id(name) or "")
        if len(char_id) != 4 or not char_id.isdigit():
            continue

        aliases = alias_to_char_name_list(name)
        other_aliases = [a for a in aliases if a != name]

        avatar = ""
        try:
            avatar_img = await get_square_avatar(char_id)
            avatar = pil_to_b64(avatar_img, quality=75)
        except Exception:
            pass

        chars.append({
            "name": name,
            "aliases": other_aliases,
            "avatar": avatar,
            "char_id": char_id,
        })

    if not chars:
        return await bot.send("暂无可展示的角色别名数据")

    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if PLAYWRIGHT_AVAILABLE and use_html_render:
        try:
            from ..utils.image import get_custom_waves_bg

            bg_img = get_custom_waves_bg(bg="bg12", crop=False)
            bg_url = pil_to_b64(bg_img, quality=75)
            footer_b64 = get_footer_b64(footer_type="white") or ""

            context = {
                "chars": chars,
                "total": len(chars),
                "bg_url": bg_url,
                "footer_b64": footer_b64,
            }

            img_bytes = await render_html(waves_templates, "alias_all.html", context)
            if img_bytes:
                return await bot.send(img_bytes)
            logger.warning("[鸣潮] 全角色别名HTML渲染返回空，回退到PIL")
        except Exception as e:
            logger.warning(f"[鸣潮] 全角色别名HTML渲染失败: {e}，回退到PIL")

    try:
        return await bot.send(await draw_all_char_alias_pil(chars))
    except Exception as e:
        logger.exception(f"[鸣潮] 全角色别名PIL渲染失败: {e}")

    lines = [
        f"{char['name']}：" + (" ".join(char["aliases"]) if char["aliases"] else "暂无别名")
        for char in chars
    ]
    return await bot.send("\n".join(lines))
