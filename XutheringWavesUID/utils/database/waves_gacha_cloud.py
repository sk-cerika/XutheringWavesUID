"""云·鸣潮（国服云游戏）登录态表。

独立于 ``WavesUser``，只承载抽卡 recordId 链路所需的云游戏登录信息，用于无短信
复用续期。``login_info`` 为 JSON 文本，含 phone/cuid/username/access_token/
phoneToken/autoToken/app_token/device_num/did。
"""

import time
from typing import Any, Dict, Optional, Type, TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.utils.database.base_models import BaseModel, with_session

T_WavesGachaCloud = TypeVar("T_WavesGachaCloud", bound="WavesGachaCloud")


class WavesGachaCloud(BaseModel, table=True):
    """云·鸣潮登录态表。"""

    __tablename__ = "WavesGachaCloud"
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    uid: str = Field(default="", title="鸣潮UID", index=True)
    login_info: str = Field(default="", title="登录信息")
    is_valid: bool = Field(default=True, title="有效性标记")
    created_time: Optional[int] = Field(default=None, title="创建时间")
    last_used_time: Optional[int] = Field(default=None, title="上次使用时间")

    @classmethod
    @with_session
    async def select_record(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
    ) -> Optional[T_WavesGachaCloud]:
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.bot_id == bot_id,
            cls.uid == uid,
        )
        result = await session.execute(sql)
        return result.scalars().first()

    @classmethod
    @with_session
    async def select_latest_valid(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> Optional[T_WavesGachaCloud]:
        """复用入口：取该用户最近一次使用的有效云登录记录。"""
        sql = (
            select(cls)
            .where(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                col(cls.is_valid).is_(True),
            )
            .order_by(col(cls.last_used_time).desc())
        )
        result = await session.execute(sql)
        return result.scalars().first()

    @classmethod
    async def upsert(
        cls: Type[T_WavesGachaCloud],
        user_id: str,
        bot_id: str,
        uid: str,
        login_info: str,
    ) -> None:
        existed = await cls.select_record(user_id, bot_id, uid)
        now = int(time.time())
        if existed:
            await cls._update_full(user_id, bot_id, uid, login_info, now)
        else:
            await cls._insert(user_id, bot_id, uid, login_info, now)

    @classmethod
    @with_session
    async def _update_full(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
        login_info: str,
        now: int,
    ) -> None:
        sql = (
            update(cls)
            .where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.uid) == uid,
            )
            .values(login_info=login_info, is_valid=True, last_used_time=now)
        )
        await session.execute(sql)

    @classmethod
    @with_session
    async def _insert(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
        login_info: str,
        now: int,
    ) -> None:
        session.add(
            cls(
                user_id=user_id,
                bot_id=bot_id,
                uid=uid,
                login_info=login_info,
                is_valid=True,
                created_time=now,
                last_used_time=now,
            )
        )

    @classmethod
    @with_session
    async def update_login_info(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
        login_info: str,
    ) -> None:
        """续期后回写凭据并刷新使用时间。"""
        sql = (
            update(cls)
            .where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.uid) == uid,
            )
            .values(login_info=login_info, is_valid=True, last_used_time=int(time.time()))
        )
        await session.execute(sql)

    @classmethod
    @with_session
    async def update_last_used(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
    ) -> None:
        sql = (
            update(cls)
            .where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.uid) == uid,
            )
            .values(last_used_time=int(time.time()))
        )
        await session.execute(sql)

    @classmethod
    @with_session
    async def mark_invalid(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
    ) -> None:
        sql = (
            update(cls)
            .where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.uid) == uid,
            )
            .values(is_valid=False)
        )
        await session.execute(sql)

    @classmethod
    @with_session
    async def delete_record(
        cls: Type[T_WavesGachaCloud],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
    ) -> int:
        from sqlalchemy import delete as sql_delete

        sql = sql_delete(cls).where(
            col(cls.user_id) == user_id,
            col(cls.bot_id) == bot_id,
            col(cls.uid) == uid,
        )
        result = await session.execute(sql)
        return result.rowcount or 0
