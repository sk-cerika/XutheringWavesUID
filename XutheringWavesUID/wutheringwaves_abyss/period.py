from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

CHINA_TZ = timezone(timedelta(hours=8))


def parse_rank_date(date_str: str) -> Optional[datetime]:
    """解析远端排行接口返回的 start_date (多格式容错)"""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=CHINA_TZ)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=CHINA_TZ)
        return dt.astimezone(CHINA_TZ)
    except ValueError:
        return None


@dataclass(frozen=True)
class CycleSpec:
    """玩法周期。base_time 是 base_period 开启的边界 (含)；早于 base_time 视为 base_period - 1"""
    base_time: datetime
    refresh_seconds: int
    base_period: int

    @property
    def base_timestamp(self) -> int:
        return int(self.base_time.astimezone(timezone.utc).timestamp())

    def cycle_start(self, ref_time: Optional[datetime] = None) -> datetime:
        now = ref_time or datetime.now(CHINA_TZ)
        if now <= self.base_time:
            return self.base_time
        elapsed = int((now - self.base_time).total_seconds())
        cycles = elapsed // self.refresh_seconds
        return self.base_time + timedelta(seconds=cycles * self.refresh_seconds)

    def is_record_expired(
        self,
        record_timestamp: Optional[int],
        ref_time: Optional[datetime] = None,
    ) -> bool:
        now = ref_time or datetime.now(CHINA_TZ)
        if now <= self.base_time:
            return False
        if record_timestamp is None:
            return True
        try:
            record_ts = int(record_timestamp)
        except (TypeError, ValueError):
            return True
        record_time = datetime.fromtimestamp(record_ts, tz=timezone.utc).astimezone(CHINA_TZ)
        if record_time < self.base_time:
            return True
        return record_time < self.cycle_start(now)

    def period_number(self, ref_time: Optional[datetime] = None) -> int:
        ref = ref_time or datetime.now(CHINA_TZ)
        if ref < self.base_time:
            return self.base_period - 1
        elapsed = int((ref - self.base_time).total_seconds())
        cycles = elapsed // self.refresh_seconds
        return self.base_period + cycles


# 2025-11-24 04:00 为第 11 期开始边界
SLASH_CYCLE = CycleSpec(
    base_time=datetime(2025, 11, 24, 4, 0, 0, tzinfo=CHINA_TZ),
    refresh_seconds=28 * 24 * 60 * 60,
    base_period=11,
)

# 2025-11-10 04:00 为第 29 期开始边界
TOWER_CYCLE = CycleSpec(
    base_time=datetime(2025, 11, 10, 4, 0, 0, tzinfo=CHINA_TZ),
    refresh_seconds=28 * 24 * 60 * 60,
    base_period=29,
)

# 2026-05-07 04:00 为第 3 / 第 4 期分界, 此前第 3 期, 此后每 42 天 +1
MATRIX_CYCLE = CycleSpec(
    base_time=datetime(2026, 5, 7, 4, 0, 0, tzinfo=CHINA_TZ),
    refresh_seconds=42 * 24 * 60 * 60,
    base_period=4,
)


# 老调用方的兼容入口 (常量 + 函数), 实际逻辑都在 CycleSpec
SLASH_BASE_TIME = SLASH_CYCLE.base_time
SLASH_BASE_TIMESTAMP = SLASH_CYCLE.base_timestamp
SLASH_REFRESH_SECONDS = SLASH_CYCLE.refresh_seconds
SLASH_BASE_PERIOD = SLASH_CYCLE.base_period

TOWER_BASE_TIME = TOWER_CYCLE.base_time
TOWER_BASE_TIMESTAMP = TOWER_CYCLE.base_timestamp
TOWER_REFRESH_SECONDS = TOWER_CYCLE.refresh_seconds
TOWER_BASE_PERIOD = TOWER_CYCLE.base_period

MATRIX_BASE_TIME = MATRIX_CYCLE.base_time
MATRIX_BASE_TIMESTAMP = MATRIX_CYCLE.base_timestamp
MATRIX_REFRESH_SECONDS = MATRIX_CYCLE.refresh_seconds
MATRIX_BASE_PERIOD = MATRIX_CYCLE.base_period


def get_current_slash_cycle_start(reference_time: Optional[datetime] = None) -> datetime:
    return SLASH_CYCLE.cycle_start(reference_time)


def is_slash_record_expired(
    record_timestamp: Optional[int],
    reference_time: Optional[datetime] = None,
) -> bool:
    return SLASH_CYCLE.is_record_expired(record_timestamp, reference_time)


def get_slash_period_number(reference_time: Optional[datetime] = None) -> int:
    return SLASH_CYCLE.period_number(reference_time)


def get_current_tower_cycle_start(reference_time: Optional[datetime] = None) -> datetime:
    return TOWER_CYCLE.cycle_start(reference_time)


def is_tower_record_expired(
    record_timestamp: Optional[int],
    reference_time: Optional[datetime] = None,
) -> bool:
    return TOWER_CYCLE.is_record_expired(record_timestamp, reference_time)


def get_tower_period_number(reference_time: Optional[datetime] = None) -> int:
    return TOWER_CYCLE.period_number(reference_time)


def get_current_matrix_cycle_start(reference_time: Optional[datetime] = None) -> datetime:
    return MATRIX_CYCLE.cycle_start(reference_time)


def is_matrix_record_expired(
    record_timestamp: Optional[int],
    reference_time: Optional[datetime] = None,
) -> bool:
    return MATRIX_CYCLE.is_record_expired(record_timestamp, reference_time)


def get_matrix_period_number(reference_time: Optional[datetime] = None) -> int:
    return MATRIX_CYCLE.period_number(reference_time)
