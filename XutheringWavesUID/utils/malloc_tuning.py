import os
import sys
import ctypes
import asyncio

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

_M_TRIM_THRESHOLD = -1
_M_ARENA_MAX = -8

_ENABLED = sys.platform == "linux" and os.environ.get("WAVES_MALLOC_TUNING", "1") != "0"


def _load_libc():
    if not _ENABLED:
        return None
    for name in (None, "libc.so.6"):
        try:
            libc = ctypes.CDLL(name, use_errno=True)
            if hasattr(libc, "mallopt") and hasattr(libc, "malloc_trim"):
                libc.mallopt.argtypes = [ctypes.c_int, ctypes.c_int]
                libc.mallopt.restype = ctypes.c_int
                libc.malloc_trim.argtypes = [ctypes.c_size_t]
                libc.malloc_trim.restype = ctypes.c_int
                return libc
        except Exception:
            continue
    return None


_LIBC = _load_libc()


def malloc_trim() -> int:
    if _LIBC is None:
        return 0
    try:
        return int(_LIBC.malloc_trim(0))
    except Exception:
        return 0


if _LIBC is not None:
    try:
        _LIBC.mallopt(_M_ARENA_MAX, 2)
        _LIBC.mallopt(_M_TRIM_THRESHOLD, 131072)
        logger.info("[鸣潮·内存] glibc malloc 已调参 (arena_max=2, trim=128K) + 定期 malloc_trim")
    except Exception as e:
        logger.debug(f"[鸣潮·内存] mallopt 调参跳过: {e}")

    @scheduler.scheduled_job("interval", minutes=10, id="waves_malloc_trim")
    async def _waves_periodic_malloc_trim():
        await asyncio.get_running_loop().run_in_executor(None, malloc_trim)
