"""共享缓存 + 加载函数。
- detail_json 加载只在首次访问时执行，后续 O(1)
- `invalidate_caches()` 由 reload_ai_rag 调用，资源更新后下次访问重建
"""

import json
from typing import Any, Dict, List, Optional, Set

from gsuid_core.logger import logger

from ...utils.resource.RESOURCE_PATH import MAP_DETAIL_PATH, MAP_CHALLENGE_PATH, MAP_PATH
from ...utils.resource.constant import ATTRIBUTE_ID_MAP, WEAPON_TYPE_ID_MAP

ATTR_MAP = ATTRIBUTE_ID_MAP
WEAPON_TYPE_MAP = WEAPON_TYPE_ID_MAP
ATTR_VALID = set(ATTR_MAP.values())
WEAPON_VALID = set(WEAPON_TYPE_MAP.values())
ALL_ATTRS: List[str] = list(ATTR_MAP.values())

_chars_cache: Optional[List[Dict[str, Any]]] = None
_weapons_cache: Optional[List[Dict[str, Any]]] = None
_echoes_cache: Optional[List[Dict[str, Any]]] = None
_monster_resist_cache: Optional[Dict[str, Set[str]]] = None
_weapon_alias_cache: Optional[Dict[str, List[str]]] = None
_char_id_to_name_cache: Optional[Dict[str, str]] = None


def _read_json(p) -> Any:
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[鸣潮-Tools] read {p}: {e}")
        return None


def load_chars() -> List[Dict[str, Any]]:
    global _chars_cache
    if _chars_cache is not None:
        return _chars_cache
    out: List[Dict[str, Any]] = []
    char_dir = MAP_DETAIL_PATH / "char"
    if char_dir.exists():
        for p in sorted(char_dir.glob("*.json")):
            d = _read_json(p)
            if not isinstance(d, dict):
                continue
            out.append({
                "cid": p.stem,
                "name": d.get("name", p.stem),
                "star": d.get("starLevel"),
                "attr": ATTR_MAP.get(d.get("attributeId"), "?"),
                "wt": WEAPON_TYPE_MAP.get(d.get("weaponTypeId"), "?"),
            })
    _chars_cache = out
    return out


def load_weapons() -> List[Dict[str, Any]]:
    global _weapons_cache
    if _weapons_cache is not None:
        return _weapons_cache
    out: List[Dict[str, Any]] = []
    w_dir = MAP_DETAIL_PATH / "weapon"
    if w_dir.exists():
        for p in sorted(w_dir.glob("*.json")):
            d = _read_json(p)
            if not isinstance(d, dict):
                continue
            out.append({
                "wid": p.stem,
                "name": d.get("name", p.stem),
                "star": d.get("starLevel"),
                "wt": WEAPON_TYPE_MAP.get(d.get("type"), "?"),
            })
    _weapons_cache = out
    return out


def load_echoes() -> List[Dict[str, Any]]:
    global _echoes_cache
    if _echoes_cache is not None:
        return _echoes_cache
    out: List[Dict[str, Any]] = []
    e_dir = MAP_DETAIL_PATH / "echo"
    if e_dir.exists():
        for p in sorted(e_dir.glob("*.json")):
            d = _read_json(p)
            if not isinstance(d, dict):
                continue
            groups = d.get("group") or {}
            group_names = [
                g.get("name") for g in groups.values()
                if isinstance(g, dict) and g.get("name")
            ]
            out.append({
                "eid": p.stem,
                "name": d.get("name", p.stem),
                "cost": d.get("intensityCode"),
                "groups": group_names,
            })
    _echoes_cache = out
    return out


def load_monster_resist() -> Dict[str, Set[str]]:
    """聚合 tower (Element) + matrix (Waves[].Tags) 抗性数据。"""
    global _monster_resist_cache
    if _monster_resist_cache is not None:
        return _monster_resist_cache
    out: Dict[str, Set[str]] = {}
    tower_dir = MAP_CHALLENGE_PATH / "tower"
    if tower_dir.exists():
        for p in sorted(tower_dir.glob("*.json")):
            d = _read_json(p)
            if not isinstance(d, dict):
                continue
            for area in (d.get("Area") or {}).values():
                for floor in (area.get("Floor") or {}).values():
                    for m in (floor.get("Monsters") or {}).values():
                        n = m.get("Name")
                        e = m.get("Element")
                        if n and e in ATTR_MAP:
                            out.setdefault(n, set()).add(ATTR_MAP[e])
    matrix_dir = MAP_CHALLENGE_PATH / "matrix"
    if matrix_dir.exists():
        for p in sorted(matrix_dir.glob("*.json")):
            d = _read_json(p)
            if not isinstance(d, dict):
                continue
            for lv in d.get("Levels") or []:
                if not isinstance(lv, dict):
                    continue
                for w in lv.get("Waves") or []:
                    if not isinstance(w, dict):
                        continue
                    n = w.get("Name")
                    if not n:
                        continue
                    for t in w.get("Tags") or []:
                        if isinstance(t, dict):
                            tn = (t.get("Name") or "").replace("抗性", "")
                            if tn in ATTR_VALID:
                                out.setdefault(n, set()).add(tn)
    _monster_resist_cache = out
    return out


def load_weapon_alias() -> Dict[str, List[str]]:
    global _weapon_alias_cache
    if _weapon_alias_cache is not None:
        return _weapon_alias_cache
    p = MAP_PATH / "alias" / "weapon_alias.json"
    d = _read_json(p) if p.exists() else None
    _weapon_alias_cache = d if isinstance(d, dict) else {}
    return _weapon_alias_cache


def load_char_id_to_name() -> Dict[str, str]:
    """从 chars 缓存推导 cid → 角色名 的反查表，给 charListData (按 roleId) 用。"""
    global _char_id_to_name_cache
    if _char_id_to_name_cache is not None:
        return _char_id_to_name_cache
    _char_id_to_name_cache = {c["cid"]: c["name"] for c in load_chars()}
    return _char_id_to_name_cache


def invalidate_caches():
    """resource reload 后清缓存，下次访问重建。"""
    global _chars_cache, _weapons_cache, _echoes_cache
    global _monster_resist_cache, _weapon_alias_cache, _char_id_to_name_cache
    _chars_cache = None
    _weapons_cache = None
    _echoes_cache = None
    _monster_resist_cache = None
    _weapon_alias_cache = None
    _char_id_to_name_cache = None
