from typing import Any, Dict, Union, Generator

from .api.model import RoleDetailData
from .player_store import read_player_json
from .resource.constant import SPECIAL_CHAR, SPECIAL_CHAR_RANK_MAP
from .resource.RESOURCE_PATH import PLAYER_PATH

PATTERN = r"[\u4e00-\u9fa5a-zA-Z0-9\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U00003200-\U000032FF-—·()（）]{1,15}"

async def get_all_role_detail_info_list(
    uid: str,
) -> Union[Generator[RoleDetailData, Any, None], None]:
    path = PLAYER_PATH / uid / "rawData.json"
    player_data = await read_player_json(path)
    if not player_data:
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


async def get_rover_detail_map(uid: str) -> Dict[str, RoleDetailData]:
    """读 rover.json → {canonical_id: RoleDetailData}。"""
    data = await read_player_json(PLAYER_PATH / uid / "rover.json")
    if not data:
        return {}
    out: Dict[str, RoleDetailData] = {}
    for k, v in data.items():
        try:
            out[str(k)] = RoleDetailData(**v)
        except Exception:
            continue
    return out


def lookup_chain(role_detail_info_map, role_id) -> tuple[int, str]:
    """从 role_detail_info_map 取角色共鸣链 (num, name)，无数据返回 (0, '')"""
    if role_detail_info_map and str(role_id) in role_detail_info_map:
        temp: RoleDetailData = role_detail_info_map[str(role_id)]
        return temp.get_chain_num(), temp.get_chain_name()
    return 0, ""


def lookup_chain_with_rover(rawdata_map, rover_map, role_id) -> tuple[int, str, bool]:
    """共鸣链 (num, name, hide)。漂泊者按 canonical 查 rover_map，缺失则 hide=True。"""
    rid = str(role_id)
    if rid in SPECIAL_CHAR:
        temp = (rover_map or {}).get(SPECIAL_CHAR_RANK_MAP[rid])
        if temp is None:
            return 0, "", True
        return temp.get_chain_num(), temp.get_chain_name(), False
    num, name = lookup_chain(rawdata_map, role_id)
    return num, name, False


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
