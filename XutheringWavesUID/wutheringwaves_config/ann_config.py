import json
import os
import threading
from typing import Dict, List

from gsuid_core.logger import logger

from ..utils.resource.RESOURCE_PATH import ANN_DATA_PATH

_ANN_LOCK = threading.Lock()


def load_ann_data() -> Dict:
    """加载公告数据"""
    if not ANN_DATA_PATH.exists():
        return {"groups": {}, "new_ids": []}

    try:
        with open(ANN_DATA_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"groups": {}, "new_ids": []}
            data = json.loads(content)
            # 确保数据格式正确
            if not isinstance(data, dict):
                return {"groups": {}, "new_ids": []}
            if "groups" not in data:
                data["groups"] = {}
            if "new_ids" not in data:
                data["new_ids"] = []
            return data
    except Exception as e:
        logger.exception(f"[鸣潮·配置] 加载公告数据失败: {e}")
        return {"groups": {}, "new_ids": []}


def save_ann_data(data: Dict) -> bool:
    """保存公告数据 (atomic: tmp + os.replace, 防截断/并发)。"""
    try:
        with _ANN_LOCK:
            tmp = ANN_DATA_PATH.with_suffix(ANN_DATA_PATH.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, ANN_DATA_PATH)
        return True
    except Exception as e:
        logger.exception(f"[鸣潮·配置] 保存公告数据失败: {e}")
        return False


def get_ann_new_ids() -> List:
    """获取新公告ID列表"""
    data = load_ann_data()
    return data.get("new_ids", [])


def set_ann_new_ids(new_ids: List) -> bool:
    """设置新公告ID列表"""
    data = load_ann_data()
    data["new_ids"] = new_ids
    return save_ann_data(data)
