import os
import gzip
import json
import asyncio
import itertools
from pathlib import Path
from typing import Any, Optional, Union

from gsuid_core.logger import logger

_GZIP_NAMES = {
    "rawData.json",
    "rover.json",
    "gacha_logs.json",
    "link_gacha_logs.json",
    "matrixData.json",
    "slashData.json",
}

PathLike = Union[str, Path]
_tmp_counter = itertools.count()


def _is_gzip(name: str) -> bool:
    return name in _GZIP_NAMES


def _load(p: Path) -> Any:
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _gzip_dump(path: Path, obj: Any, level: int = 6) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    with open(path, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=level, filename="", mtime=0) as f:
            f.write(data)


def resolve_player_path(path: PathLike) -> Optional[Path]:
    """实际落盘路径：.gz 优先,回退明文;都不存在返回 None。"""
    p = Path(path)
    if _is_gzip(p.name):
        gp = p.with_name(p.name + ".gz")
        if gp.exists():
            return gp
    return p if p.exists() else None


def player_json_exists(path: PathLike) -> bool:
    return resolve_player_path(path) is not None


def resolve_readable_player_path(path: PathLike) -> Optional[Path]:
    """能成功读出的落盘路径(.gz 优先,坏则明文);都读不出返回 None。"""
    p = Path(path)
    cands = []
    if _is_gzip(p.name):
        gp = p.with_name(p.name + ".gz")
        if gp.exists():
            cands.append(gp)
    if p.exists():
        cands.append(p)
    for c in cands:
        try:
            _load(c)
            return c
        except Exception:
            continue
    return None


def read_player_json_sync(path: PathLike) -> Any:
    """读 json。.gz 优先, 读坏则回退明文; 都读不到返回 None。"""
    p = Path(path)
    candidates = []
    if _is_gzip(p.name):
        gp = p.with_name(p.name + ".gz")
        if gp.exists():
            candidates.append(gp)
    if p.exists():
        candidates.append(p)
    for c in candidates:
        try:
            return _load(c)
        except Exception as e:
            logger.warning(f"[鸣潮·player_store] 读取失败 {c}: {e}")
    return None


def write_player_json_sync(path: PathLike, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    uniq = f".{os.getpid()}.{next(_tmp_counter)}.tmp"
    if _is_gzip(p.name):
        gp = p.with_name(p.name + ".gz")
        tmp = p.with_name(p.name + ".gz" + uniq)
        try:
            _gzip_dump(tmp, obj)
            tmp.replace(gp)
        finally:
            tmp.unlink(missing_ok=True)
        if p.exists():
            p.unlink()  # 删旧明文
        return
    tmp = p.with_name(p.name + uniq)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        tmp.replace(p)
    finally:
        tmp.unlink(missing_ok=True)


async def read_player_json(path: PathLike) -> Any:
    return await asyncio.to_thread(read_player_json_sync, path)


async def write_player_json(path: PathLike, obj: Any) -> None:
    await asyncio.to_thread(write_player_json_sync, path, obj)


def write_gz_json_sync(path: PathLike, obj: Any, level: int = 9) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{next(_tmp_counter)}.tmp")
    try:
        _gzip_dump(tmp, obj, level)
        tmp.replace(p)
    finally:
        tmp.unlink(missing_ok=True)


async def write_gz_json(path: PathLike, obj: Any, level: int = 9) -> None:
    await asyncio.to_thread(write_gz_json_sync, path, obj, level)


def compress_existing_sync(player_root: PathLike) -> tuple[int, int, int, int]:
    """把 player_root 下白名单明文转 gz。返回 转换数/失败数/前字节/后字节。"""
    root = Path(player_root)
    done = fail = 0
    before = after = 0
    if not root.exists():
        return done, fail, before, after
    for uid_dir in root.iterdir():
        if not uid_dir.is_dir():
            continue
        for name in _GZIP_NAMES:
            plain = uid_dir / name
            gz = uid_dir / (name + ".gz")
            if gz.exists():
                try:
                    _load(gz)
                    plain.unlink(missing_ok=True)  # gz 可读才删明文
                except Exception as e:
                    logger.warning(f"[鸣潮·player_store] 已存 gz 损坏, 保留明文 {gz}: {e}")
                continue
            if not plain.is_file():
                continue
            tmp = gz.with_name(gz.name + f".{os.getpid()}.{next(_tmp_counter)}.tmp")
            try:
                sz = plain.stat().st_size
                obj = _load(plain)
                _gzip_dump(tmp, obj)
                tmp.replace(gz)
                _load(gz)  # 读验通过才删明文
                plain.unlink(missing_ok=True)
                before += sz
                after += gz.stat().st_size
                done += 1
            except Exception as e:
                logger.warning(f"[鸣潮·player_store] 压缩失败 {plain}: {e}")
                fail += 1
            finally:
                tmp.unlink(missing_ok=True)
    return done, fail, before, after
