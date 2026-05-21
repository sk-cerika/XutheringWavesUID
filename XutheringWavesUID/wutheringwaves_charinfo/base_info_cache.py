"""charinfo 私有的 24h 内存 baseinfo 缓存。"""
import sys
import time
from typing import Dict, Optional, Tuple

from gsuid_core.logger import logger

from ..utils.api.model import AccountBaseInfo

_TTL = 24 * 3600
_cache: Dict[str, Tuple[float, AccountBaseInfo]] = {}


def _entry_bytes(uid: str, info: AccountBaseInfo) -> int:
    """近似单条缓存项内存占用（key 字节 + 模型 JSON 字节 + 元组开销）。"""
    try:
        payload = len(info.model_dump_json().encode("utf-8"))
    except Exception:
        payload = 0
    return sys.getsizeof(uid) + payload + 64  # 64 ≈ tuple+float overhead


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / 1024 / 1024:.2f}MB"


def stats() -> Tuple[int, int]:
    """返回 (条目数, 估算总字节数)。"""
    total = 0
    for uid, (_, info) in _cache.items():
        total += _entry_bytes(uid, info)
    return len(_cache), total


def _log_stats(action: str, uid: str) -> None:
    count, total = stats()
    logger.info(
        f"[charinfo base_info_cache] {action} uid={uid} entries={count} ~{_fmt_bytes(total)}"
    )


def get(uid: str) -> Optional[AccountBaseInfo]:
    entry = _cache.get(uid)
    if not entry:
        return None
    ts, info = entry
    if time.time() - ts > _TTL:
        _cache.pop(uid, None)
        _log_stats("expire", uid)
        return None
    return info


def set(uid: str, info: AccountBaseInfo) -> None:
    _cache[uid] = (time.time(), info)
    _log_stats("set", uid)


def invalidate(uid: str) -> None:
    if _cache.pop(uid, None) is not None:
        _log_stats("invalidate", uid)
