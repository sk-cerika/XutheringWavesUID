from typing import Optional
from datetime import datetime, timezone, timedelta

CHINA_TZ = timezone(timedelta(hours=8))

SLASH_BASE_TIME = datetime(2025, 11, 24, 4, 0, 0, tzinfo=CHINA_TZ)
SLASH_BASE_TIMESTAMP = int(SLASH_BASE_TIME.astimezone(timezone.utc).timestamp())

SLASH_REFRESH_SECONDS = 28 * 24 * 60 * 60

SLASH_BASE_PERIOD = 11


TOWER_BASE_TIME = datetime(2025, 11, 10, 4, 0, 0, tzinfo=CHINA_TZ)
TOWER_BASE_TIMESTAMP = int(TOWER_BASE_TIME.astimezone(timezone.utc).timestamp())

TOWER_REFRESH_SECONDS = 28 * 24 * 60 * 60

TOWER_BASE_PERIOD = 29


MATRIX_BASE_TIME = datetime(2026, 5, 7, 4, 0, 0, tzinfo=CHINA_TZ)
MATRIX_BASE_TIMESTAMP = int(MATRIX_BASE_TIME.astimezone(timezone.utc).timestamp())

MATRIX_REFRESH_SECONDS = 42 * 24 * 60 * 60

MATRIX_BASE_PERIOD = 4


def get_current_slash_cycle_start(reference_time: Optional[datetime] = None) -> datetime:
    """获取当前海墟周期的开始时间"""
    now = reference_time or datetime.now(CHINA_TZ)
    if now <= SLASH_BASE_TIME:
        return SLASH_BASE_TIME

    elapsed_seconds = int((now - SLASH_BASE_TIME).total_seconds())
    cycles = elapsed_seconds // SLASH_REFRESH_SECONDS
    return SLASH_BASE_TIME + timedelta(seconds=cycles * SLASH_REFRESH_SECONDS)


def is_slash_record_expired(
    record_timestamp: Optional[int],
    reference_time: Optional[datetime] = None,
) -> bool:
    """检查海墟记录是否已过期"""
    now = reference_time or datetime.now(CHINA_TZ)
    if now <= SLASH_BASE_TIME:
        return False

    if record_timestamp is None:
        return True

    try:
        record_ts = int(record_timestamp)
    except (TypeError, ValueError):
        return True

    record_time = datetime.fromtimestamp(record_ts, tz=timezone.utc).astimezone(CHINA_TZ)
    if record_time < SLASH_BASE_TIME:
        return True

    cycle_start = get_current_slash_cycle_start(now)
    return record_time < cycle_start


def get_slash_period_number(reference_time: Optional[datetime] = None) -> int:
    """获取当前海墟的期数"""
    ref_time = reference_time or datetime.now(CHINA_TZ)
    if ref_time < SLASH_BASE_TIME:
        return SLASH_BASE_PERIOD

    elapsed_seconds = int((ref_time - SLASH_BASE_TIME).total_seconds())
    cycles = elapsed_seconds // SLASH_REFRESH_SECONDS
    return SLASH_BASE_PERIOD + cycles


def get_current_tower_cycle_start(reference_time: Optional[datetime] = None) -> datetime:
    """获取当前深塔周期的开始时间"""
    now = reference_time or datetime.now(CHINA_TZ)
    if now <= TOWER_BASE_TIME:
        return TOWER_BASE_TIME

    elapsed_seconds = int((now - TOWER_BASE_TIME).total_seconds())
    cycles = elapsed_seconds // TOWER_REFRESH_SECONDS
    return TOWER_BASE_TIME + timedelta(seconds=cycles * TOWER_REFRESH_SECONDS)


def is_tower_record_expired(
    record_timestamp: Optional[int],
    reference_time: Optional[datetime] = None,
) -> bool:
    """检查深塔记录是否已过期"""
    now = reference_time or datetime.now(CHINA_TZ)
    if now <= TOWER_BASE_TIME:
        return False

    if record_timestamp is None:
        return True

    try:
        record_ts = int(record_timestamp)
    except (TypeError, ValueError):
        return True

    record_time = datetime.fromtimestamp(record_ts, tz=timezone.utc).astimezone(CHINA_TZ)
    if record_time < TOWER_BASE_TIME:
        return True

    cycle_start = get_current_tower_cycle_start(now)
    return record_time < cycle_start


def get_tower_period_number(reference_time: Optional[datetime] = None) -> int:
    """获取当前深塔的期数"""
    ref_time = reference_time or datetime.now(CHINA_TZ)
    if ref_time < TOWER_BASE_TIME:
        return TOWER_BASE_PERIOD

    elapsed_seconds = int((ref_time - TOWER_BASE_TIME).total_seconds())
    cycles = elapsed_seconds // TOWER_REFRESH_SECONDS
    return TOWER_BASE_PERIOD + cycles


def get_matrix_period_number(reference_time: Optional[datetime] = None) -> int:
    """获取当前矩阵的期数

    2026-05-07 04:00 (CST) 为第 3 / 第 4 期分界，此前为第 3 期，此后每 42 天进 1 期
    """
    ref_time = reference_time or datetime.now(CHINA_TZ)
    if ref_time < MATRIX_BASE_TIME:
        return MATRIX_BASE_PERIOD - 1

    elapsed_seconds = int((ref_time - MATRIX_BASE_TIME).total_seconds())
    cycles = elapsed_seconds // MATRIX_REFRESH_SECONDS
    return MATRIX_BASE_PERIOD + cycles


def get_current_matrix_cycle_start(reference_time: Optional[datetime] = None) -> datetime:
    """获取当前矩阵周期的开始时间"""
    now = reference_time or datetime.now(CHINA_TZ)
    if now <= MATRIX_BASE_TIME:
        return MATRIX_BASE_TIME

    elapsed_seconds = int((now - MATRIX_BASE_TIME).total_seconds())
    cycles = elapsed_seconds // MATRIX_REFRESH_SECONDS
    return MATRIX_BASE_TIME + timedelta(seconds=cycles * MATRIX_REFRESH_SECONDS)


def is_matrix_record_expired(
    record_timestamp: Optional[int],
    reference_time: Optional[datetime] = None,
) -> bool:
    """检查矩阵记录是否已过期"""
    now = reference_time or datetime.now(CHINA_TZ)
    if now <= MATRIX_BASE_TIME:
        return False

    if record_timestamp is None:
        return True

    try:
        record_ts = int(record_timestamp)
    except (TypeError, ValueError):
        return True

    record_time = datetime.fromtimestamp(record_ts, tz=timezone.utc).astimezone(CHINA_TZ)
    if record_time < MATRIX_BASE_TIME:
        return True

    cycle_start = get_current_matrix_cycle_start(now)
    return record_time < cycle_start
