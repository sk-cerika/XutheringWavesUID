from typing import Dict, List, Union, Optional

from msgspec import json as msgjson
from pydantic import Field, BaseModel

from gsuid_core.logger import logger

from ..resource.RESOURCE_PATH import MAP_PATH, MAP_DETAIL_PATH

MAP_PATH_SONATA = MAP_DETAIL_PATH / "sonata"
SONATA_ID_MAP_PATH = MAP_PATH / "sonata_id.json"

sonata_id_data = {}
sonata_name_to_id = {}  # 中文名称 -> ID 映射
_data_loaded = False


def read_sonata_json_files(directory):
    global sonata_id_data
    files = directory.rglob("*.json")

    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = msgjson.decode(f.read())
                file_name = file.name.split(".")[0]
                sonata_id_data[file_name] = data
        except Exception as e:
            logger.exception(f"[鸣潮·合鸣] read_char_json_files load fail decoding {file}", e)


def load_sonata_name_mapping():
    """加载 sonata_id.json 映射文件"""
    global sonata_name_to_id
    try:
        if SONATA_ID_MAP_PATH.exists():
            with open(SONATA_ID_MAP_PATH, "r", encoding="utf-8") as f:
                id_to_name = msgjson.decode(f.read())
                # 反向映射：名称 -> ID
                sonata_name_to_id = {v: k for k, v in id_to_name.items()}
        else:
            logger.warning(f"[鸣潮·合鸣] sonata_id.json not found at {SONATA_ID_MAP_PATH}")
    except Exception as e:
        logger.exception("[鸣潮·合鸣] Failed to load sonata_id.json mapping", e)


def ensure_data_loaded(force: bool = False):
    """确保合鸣数据已加载

    Args:
        force: 如果为 True，强制重新加载所有数据，即使已经加载过
    """
    global _data_loaded
    if (_data_loaded and not force) or not MAP_PATH_SONATA.exists():
        return
    read_sonata_json_files(MAP_PATH_SONATA)
    load_sonata_name_mapping()
    _data_loaded = True


class SonataSet(BaseModel):
    desc: str = Field(default="")
    effect: str = Field(default="")
    param: List[str] = Field(default_factory=list)


class WavesSonataResult(BaseModel):
    name: str = Field(default="")
    set: Dict[str, SonataSet] = Field(default_factory=dict)

    def piece(self, piece_count: Union[str, int]) -> Optional[SonataSet]:
        """获取件套效果"""
        return self.set.get(str(piece_count), None)

    def full_piece_effect(self) -> int:
        """获取套装最大件数"""
        return max(int(key) for key in self.set.keys())


def get_sonata_detail(sonata_name: Optional[str]) -> WavesSonataResult:
    ensure_data_loaded()
    result = WavesSonataResult()
    if sonata_name is None:
        logger.exception(f"[鸣潮·合鸣] get_sonata_detail sonata_name: {sonata_name} not found")
        return result

    sonata_key = str(sonata_name)

    # 如果输入的是中文名称，转换为ID
    if sonata_key not in sonata_id_data and sonata_key in sonata_name_to_id:
        sonata_key = sonata_name_to_id[sonata_key]

    if sonata_key not in sonata_id_data:
        logger.exception(f"[鸣潮·合鸣] get_sonata_detail sonata_name: {sonata_name} (converted to {sonata_key}) not found")
        return result

    return WavesSonataResult(**sonata_id_data[sonata_key])
