from typing import List, Optional

from pydantic import Field, BaseModel


class MotorSkinItem(BaseModel):
    """摩托外观条目(车架/涂装/外观定制通用)"""

    id: Optional[int] = None
    name: Optional[str] = None
    pictureUrl: Optional[str] = None
    quality: Optional[int] = None
    part: Optional[int] = None  # 涂装/外观定制分部位; 车架无
    sort: Optional[int] = None


class MotorSkinInfo(BaseModel):
    frameList: List[MotorSkinItem] = Field(default_factory=list)  # 车架模组(宽图)
    stickerList: List[MotorSkinItem] = Field(default_factory=list)  # 涂装
    decorationList: List[MotorSkinItem] = Field(default_factory=list)  # 外观定制


class MotorData(BaseModel):
    """科考摩托"""

    motorLevel: int = 0
    motorExp: Optional[int] = None
    motorNextExp: Optional[int] = None
    skinInfo: MotorSkinInfo = Field(default_factory=MotorSkinInfo)
