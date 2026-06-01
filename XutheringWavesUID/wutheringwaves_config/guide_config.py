import json
import os
import re
import threading
from typing import Dict, List

from gsuid_core.logger import logger

from ..utils.resource.RESOURCE_PATH import GUIDE_CONFIG_PATH

_GUIDE_LOCK = threading.Lock()


def load_guide_config() -> Dict:
    if not GUIDE_CONFIG_PATH.exists():
        return {}

    try:
        with open(GUIDE_CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception as e:
        logger.exception(f"[鸣潮·配置] 加载攻略配置失败: {e}")
        return {}


def save_guide_config(config: Dict) -> bool:
    try:
        with _GUIDE_LOCK:
            tmp = GUIDE_CONFIG_PATH.with_suffix(GUIDE_CONFIG_PATH.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            os.replace(tmp, GUIDE_CONFIG_PATH)
        return True
    except Exception as e:
        logger.exception(f"[鸣潮·配置] 保存攻略配置失败: {e}")
        return False


def parse_provider_names(names: str) -> List[str]:
    # 支持逗号、中文逗号、空格分隔
    parts = re.split(r'[,，\s]+', names.strip())
    return [p.strip() for p in parts if p.strip()]


def get_excluded_providers(group_id) -> List[str]:
    if not group_id:
        return []
    config = load_guide_config()
    providers = config.get(str(group_id), [])
    return [p.strip() for p in providers if p and p.strip()]
