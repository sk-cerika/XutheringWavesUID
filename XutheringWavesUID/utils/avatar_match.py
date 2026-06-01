"""通过opencv分块直方图相似度将角色头像URL匹配到角色ID"""

from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from gsuid_core.logger import logger

from .resource.RESOURCE_PATH import AVATAR_PATH


def _try_import_cv2():
    try:
        import cv2  # type: ignore

        return cv2
    except Exception:
        logger.warning(
            "[鸣潮·头像匹配] 未安装opencv-python，矩阵排行将无法解析角色ID。"
        )
        return None


def _try_import_np():
    try:
        import numpy as np  # type: ignore

        return np
    except Exception:
        return None


_cv2 = _try_import_cv2()
_np = _try_import_np()

# 匹配图像尺寸
_MATCH_SIZE = 128
# 分块数 (4x4 = 16块)
_BLOCK_NUM = 4
# HSV直方图 bins
_H_BINS = 16
_S_BINS = 16
# 相似度阈值
_MATCH_THRESHOLD = 0.3

# 缓存: char_id_str -> feature vector
_ref_feat_cache: Dict[str, object] = {}


def _compute_block_feature(img_bgr):
    """计算4x4分块HSV直方图特征向量"""
    img_bgr = _cv2.resize(img_bgr, (_MATCH_SIZE, _MATCH_SIZE))
    h, w = img_bgr.shape[:2]
    bh, bw = h // _BLOCK_NUM, w // _BLOCK_NUM
    hists = []
    for r in range(_BLOCK_NUM):
        for c in range(_BLOCK_NUM):
            block = img_bgr[r * bh : (r + 1) * bh, c * bw : (c + 1) * bw]
            hsv = _cv2.cvtColor(block, _cv2.COLOR_BGR2HSV)
            hist = _cv2.calcHist(
                [hsv], [0, 1], None, [_H_BINS, _S_BINS], [0, 180, 0, 256]
            )
            _cv2.normalize(hist, hist, 0, 1, _cv2.NORM_MINMAX)
            hists.append(hist.flatten())
    return _np.concatenate(hists)


def _cosine_similarity(a, b):
    """余弦相似度"""
    dot = _np.dot(a, b)
    norm = _np.linalg.norm(a) * _np.linalg.norm(b)
    if norm < 1e-10:
        return 0.0
    return float(dot / norm)


def _pil_to_cv2_bgr(pil_img: Image.Image):
    """PIL Image -> cv2 BGR array"""
    rgb = _np.array(pil_img.convert("RGB"))
    return _cv2.cvtColor(rgb, _cv2.COLOR_RGB2BGR)


def _load_reference_features() -> Dict[str, object]:
    """加载本地头像并计算分块特征（带内存缓存）"""
    if _ref_feat_cache:
        return _ref_feat_cache

    if not AVATAR_PATH.exists():
        logger.warning(f"[鸣潮·头像匹配] 头像目录不存在: {AVATAR_PATH}")
        return {}

    for avatar_file in AVATAR_PATH.glob("role_head_*.png"):
        char_id_str = avatar_file.stem.replace("role_head_", "")
        try:
            img = _cv2.imread(str(avatar_file))
            if img is None:
                continue
            feat = _compute_block_feature(img)
            _ref_feat_cache[char_id_str] = feat
        except Exception as e:
            logger.debug(f"[鸣潮·头像匹配] 加载头像失败 {avatar_file}: {e}")

    logger.info(f"[鸣潮·头像匹配] 加载了 {len(_ref_feat_cache)} 个参考头像用于矩阵匹配")
    return _ref_feat_cache


def match_avatar_image(pil_img: Image.Image) -> Optional[int]:
    """将一个头像PIL Image匹配到角色ID

    Returns:
        匹配到的角色ID (int), 未匹配到返回 None
    """
    if _cv2 is None or _np is None:
        return None

    try:
        bgr = _pil_to_cv2_bgr(pil_img)
        query_feat = _compute_block_feature(bgr)

        ref_feats = _load_reference_features()
        if not ref_feats:
            return None

        best_score = -1.0
        best_char_id = None
        for char_id_str, ref_feat in ref_feats.items():
            score = _cosine_similarity(query_feat, ref_feat)
            if score > best_score:
                best_score = score
                best_char_id = char_id_str

        if best_char_id and best_score >= _MATCH_THRESHOLD:
            return int(best_char_id)

        logger.debug(f"[鸣潮·头像匹配] 头像匹配分数过低: {best_score:.3f}")
        return None

    except Exception as e:
        logger.warning(f"[鸣潮·头像匹配] 头像匹配失败: {e}")
        return None


async def match_role_icons_to_char_ids(
    role_icons: List[str],
    cache_path: Path,
) -> List[int]:
    """批量将角色头像URL匹配到角色ID列表

    Args:
        role_icons: 角色头像URL列表
        cache_path: 图片下载缓存目录

    Returns:
        匹配到的角色ID列表（长度可能小于输入）
    """
    if _cv2 is None or _np is None:
        return []

    from .image import pic_download_from_url

    char_ids: List[int] = []
    for icon_url in role_icons:
        if not icon_url:
            continue
        try:
            pil_img = await pic_download_from_url(cache_path, icon_url)
            char_id = match_avatar_image(pil_img)
            if char_id is not None:
                char_ids.append(char_id)
        except Exception as e:
            logger.warning(f"[鸣潮·头像匹配] 下载/匹配角色头像失败: {e}")

    return char_ids
