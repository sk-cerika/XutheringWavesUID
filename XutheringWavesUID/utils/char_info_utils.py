import json
from typing import Any, Dict, Union, Generator

import aiofiles

from gsuid_core.logger import logger

from .api.model import RoleDetailData
from .resource.RESOURCE_PATH import PLAYER_PATH

PATTERN = r"[\u4e00-\u9fa5a-zA-Z0-9\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U00003200-\U000032FF-—·()（）]{1,15}"

async def get_all_role_detail_info_list(
    uid: str,
) -> Union[Generator[RoleDetailData, Any, None], None]:
    path = PLAYER_PATH / uid / "rawData.json"
    if not path.exists():
        return None
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            player_data = json.loads(await f.read())
    except Exception as e:
        logger.exception(f"get role detail info failed {path}:", e)
        path.unlink(missing_ok=True)
        return None

    return iter(RoleDetailData(**r) for r in player_data)


async def get_all_role_detail_info(uid: str) -> Union[Dict[str, RoleDetailData], None]:
    _all = await get_all_role_detail_info_list(uid)
    if not _all:
        return None
    return {r.role.roleName: r for r in _all}


async def get_all_roleid_detail_info(
    uid: str,
) -> Union[Dict[str, RoleDetailData], None]:
    _all = await get_all_role_detail_info_list(uid)
    if not _all:
        return None
    return {str(r.role.roleId): r for r in _all}


async def get_all_roleid_detail_info_int(
    uid: str,
) -> Union[Dict[int, RoleDetailData], None]:
    _all = await get_all_role_detail_info_list(uid)
    if not _all:
        return None
    return {r.role.roleId: r for r in _all}


def parse_skill_levels(skill_str: str) -> list[int]:
    """
    解析技能等级字符串，支持多种格式：
    - 空格分隔: "10 9 10 8 10"
    - 逗号分隔: "10,9,10,8,10"
    - 无分隔: "1010101010" 或 "99999"

    Args:
        skill_str: 技能等级字符串

    Returns:
        包含5个技能等级的列表 [1-10]，不足则补10

    Examples:
        >>> parse_skill_levels("10 9 10 8 10")
        [10, 9, 10, 8, 10]
        >>> parse_skill_levels("1010101010")
        [10, 10, 10, 10, 10]
        >>> parse_skill_levels("99999")
        [9, 9, 9, 9, 9]
    """
    skill_str = skill_str.strip()

    # 处理逗号分隔（转换为空格）
    if "," in skill_str:
        skill_str = skill_str.replace(",", " ")

    # 尝试空格分隔解析
    if " " in skill_str:
        skills = [int(skill) for skill in skill_str.split() if skill and 1 <= int(skill) <= 10]
    else:
        # 无分隔符的连续数字解析
        if skill_str.isdigit():
            skills = []
            i = 0
            while i < len(skill_str) and len(skills) < 5:
                # 贪婪匹配：优先尝试匹配10
                if i + 1 < len(skill_str) and skill_str[i : i + 2] == "10":
                    skills.append(10)
                    i += 2
                # 否则匹配单个数字1-9
                elif skill_str[i].isdigit():
                    level = int(skill_str[i])
                    if 1 <= level <= 9:
                        skills.append(level)
                        i += 1
                    else:
                        break
                else:
                    break
        else:
            skills = []

    # 补全到5个
    while len(skills) < 5:
        skills.append(10)

    return skills[:5]
