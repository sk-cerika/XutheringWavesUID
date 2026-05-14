from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.char_info_utils import PATTERN, parse_skill_levels
from ..utils.name_resolve import resolve_char
from .develop import calc_develop_cost

role_develop = SV("waves角色培养")


@role_develop.on_regex(
    rf"^(?P<develop_list>({PATTERN})(?:\s+{PATTERN})*?)\s*(?:养成|培养|培养成本|yc)(?:\s*(?P<skill_levels>[\d,\s]+))?$",
    block=True,
    to_ai="""查询鸣潮角色养成（突破+天赋升级）所需材料一览图。

当用户问「菲比养成 / 长离需要什么材料 / 椿培养成本」时调用。
text 必须是 "<角色名>养成"，可一次查多个：用空格分隔角色名 + 养成关键词。
例：text="菲比养成"、text="长离 椿 养成"。

Args:
    text: 1-N 个角色名 + "养成/培养/yc" 后缀。例: "菲比养成" 或 "长离 椿 养成"。
""",
)
async def calc_develop(bot: Bot, ev: Event):
    develop_list_str = ev.regex_dict.get("develop_list", "")
    develop_list_raw = develop_list_str.split()

    develop_list = []
    fuzzy_matches = []
    for raw in develop_list_raw:
        res = resolve_char(raw)
        if not res.ok:
            continue
        develop_list.append(res.matched)
        if res.fuzzy_used:
            fuzzy_matches.append(res.matched)

    if not develop_list:
        return await bot.send("[鸣潮] 未找到养成角色, 请检查输入是否正确！")

    if fuzzy_matches:
        from ..wutheringwaves_config import PREFIX
        full_cmd = f"{PREFIX}{' '.join(develop_list)} 养成"
        await bot.send(f"[鸣潮] 你可能想查询【{full_cmd}】，已执行该指令")

    logger.info(f"养成列表: {develop_list}")

    # 解析技能等级参数
    skill_levels_str = ev.regex_dict.get("skill_levels", "")
    target_skill_levels = None
    if skill_levels_str:
        try:
            target_skill_levels = parse_skill_levels(skill_levels_str)
            logger.info(f"技能目标等级: {target_skill_levels}")
        except Exception as e:
            logger.warning(f"解析技能等级失败: {e}，使用默认值")
            target_skill_levels = None

    develop_cost = await calc_develop_cost(ev, develop_list, target_skill_levels)
    if isinstance(develop_cost, (str, bytes)):
        return await bot.send(develop_cost)
