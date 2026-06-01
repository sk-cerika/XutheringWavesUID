from typing import Any, Dict, Optional, Type, TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from gsuid_core.utils.database.base_models import BaseModel, with_session
from gsuid_core.utils.database.models import Subscribe

T_WavesSubscribe = TypeVar("T_WavesSubscribe", bound="WavesSubscribe")


class WavesSubscribe(BaseModel, table=True):
    """群组Bot记录表

    自动记录每个群最后使用的bot_self_id
    当检测到bot变化时，自动更新该群所有订阅的bot_id
    """

    __tablename__ = "WavesSubscribe"
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    group_id: str = Field(default="", title="群组ID", unique=True)
    bot_self_id: str = Field(default="", title="BotSelfID")
    updated_at: Optional[int] = Field(default=None, title="最后更新时间")

    @classmethod
    @with_session
    async def check_and_update_bot(
        cls: Type[T_WavesSubscribe],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
        bot_self_id: str,
    ) -> bool:
        """检查并更新群组的bot_self_id

        只要 Subscribe 表中该群的 bot_self_id 与当前不一致就更新
        """
        import time
        from gsuid_core.logger import logger

        current_time = int(time.time())

        # 更新 Subscribe 表：该群所有 bot_self_id 不一致的订阅记录
        update_sql = (
            update(Subscribe)
            .where(
                and_(
                    col(Subscribe.group_id) == group_id,
                    col(Subscribe.bot_self_id) != bot_self_id,
                )
            )
            .values(bot_self_id=bot_self_id)
        )
        update_result = await session.execute(update_sql)
        changed = update_result.rowcount > 0

        if changed:
            logger.info(
                f"[鸣潮·订阅] 群 {group_id} 更新 {update_result.rowcount} 条订阅的bot_self_id -> {bot_self_id}"
            )

        # 使用 INSERT ... ON CONFLICT DO UPDATE 原子操作，避免并发 INSERT 竞态导致索引损坏
        stmt = sqlite_insert(cls).values(
            bot_id=bot_id,
            user_id="",
            group_id=group_id,
            bot_self_id=bot_self_id,
            updated_at=current_time,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["group_id"],
            set_={
                "bot_id": stmt.excluded.bot_id,
                "bot_self_id": stmt.excluded.bot_self_id,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)

        return changed

    @classmethod
    @with_session
    async def get_group_bot(
        cls: Type[T_WavesSubscribe],
        session: AsyncSession,
        group_id: str,
    ) -> Optional[str]:
        """获取群组当前的bot_self_id"""
        sql = select(cls).where(cls.group_id == group_id)
        result = await session.execute(sql)
        record = result.scalars().first()
        return record.bot_self_id if record else None
