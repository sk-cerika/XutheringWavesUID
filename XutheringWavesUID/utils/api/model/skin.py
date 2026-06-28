from typing import List, Optional

from pydantic import BaseModel


class CalabashSkin(BaseModel):
    """数据坞服饰"""

    quality: Optional[int] = None
    qualityIcon: Optional[str] = None
    skinIcon: Optional[str] = None
    skinId: Optional[int] = None
    skinName: Optional[str] = None


class EquipSkin(BaseModel):
    """声骸/翼装服饰"""

    quality: Optional[int] = None
    skinIcon: Optional[str] = None
    skinId: Optional[int] = None
    skinName: Optional[str] = None
    skinType: Optional[str] = None
    skinTypeIcon: Optional[str] = None


class RoleDecoration(BaseModel):
    """角色挂件"""

    icon: Optional[str] = None
    id: Optional[int] = None
    name: Optional[str] = None
    quality: Optional[int] = None
    skinOwners: List[int] = []


class RoleSkinItem(BaseModel):
    """角色服饰"""

    acronym: Optional[str] = None
    isAddition: Optional[bool] = None
    picUrl: Optional[str] = None
    priority: Optional[int] = None
    quality: Optional[int] = None
    qualityName: Optional[str] = None
    roleId: Optional[int] = None
    roleName: Optional[str] = None
    skinIcon: Optional[str] = None
    skinId: Optional[int] = None
    skinName: Optional[str] = None


class WeaponSkin(BaseModel):
    """武器服饰"""

    isAddition: Optional[bool] = None
    priority: Optional[int] = None
    quality: Optional[int] = None
    qualityName: Optional[str] = None
    skinIcon: Optional[str] = None
    skinId: Optional[int] = None
    skinName: Optional[str] = None
    weaponTypeIcon: Optional[str] = None
    weaponTypeId: Optional[int] = None
    weaponTypeName: Optional[str] = None


class SkinData(BaseModel):
    """服饰数据"""

    calabashSkinList: List[CalabashSkin] = []
    equipSkinList: List[EquipSkin] = []
    roleDecorationList: List[RoleDecoration] = []
    roleSkinList: List[RoleSkinItem] = []
    weaponSkinList: List[WeaponSkin] = []
    showToGuest: Optional[bool] = None
