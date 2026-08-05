import math
import re
from typing import List, Optional, Sequence, Tuple, TypeVar


RANK_PAGE_SIZE = 20
RANK_MAX_PAGE = 50

T = TypeVar("T")


def normalize_rank_page(page, max_page: int = RANK_MAX_PAGE) -> int:
    try:
        value = int(page or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(value, max_page))


def split_rank_page(
    text: str,
    max_page: int = RANK_MAX_PAGE,
) -> Tuple[str, int]:
    """从带筛选参数的 on_command 剩余文本末尾拆出页码。"""
    value = (text or "").strip()
    match = re.search(r"(\d+)\s*$", value)
    if not match:
        return value, 1
    return (
        value[:match.start()].strip(),
        normalize_rank_page(match.group(1), max_page),
    )


def group_rank_page_count(total: int) -> int:
    return min(RANK_MAX_PAGE, max(1, math.ceil(total / RANK_PAGE_SIZE)))


def paginate_group_rank(
    items: Sequence[T],
    page: int,
    self_rank_id: Optional[int] = None,
    self_item: Optional[T] = None,
) -> Tuple[List[T], List[int], int, int]:
    """返回当前页条目、实际名次、总页数和当前页正常条目数。

    当前用户不在所选页时仍补在末尾，保持原群排行的行为。
    """
    page = normalize_rank_page(page)
    page_count = group_rank_page_count(len(items))
    start = (page - 1) * RANK_PAGE_SIZE
    end = start + RANK_PAGE_SIZE
    display = list(items[start:end])
    rank_ids = list(range(start + 1, start + 1 + len(display)))
    page_item_count = len(display)

    if (
        self_rank_id is not None
        and self_item is not None
        and self_rank_id not in rank_ids
    ):
        display.append(self_item)
        rank_ids.append(self_rank_id)

    return display, rank_ids, page_count, page_item_count


def group_rank_empty_page_message(page: int, page_count: int) -> str:
    return f"本群排行第{page}页暂无数据，当前共{page_count}页"
