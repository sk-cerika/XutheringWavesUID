"""周年庆/周年版/周年回顾 — 调用 xwservice /2nd_report 拉取三张图。"""
from __future__ import annotations
import io
import zipfile
from dataclasses import dataclass
from typing import List, Union

import httpx
from gsuid_core.logger import logger

XWSERVICE_BASE = "https://xwservice.loping151.site"


@dataclass
class AnnivReportResult:
    parts: List[bytes]
    new_token: str = ""
    new_bat: str = ""
    bat_expires_in: int = 0


async def anniv_report(
    uid: str,
    waves_token: str,
    user_token: str,
    did: str = "",
) -> Union[str, AnnivReportResult]:
    """Call /2nd_report; return list of 3 PNG bytes (part1/2 vertical, part3 horizontal) or error msg."""
    if not waves_token:
        return "未配置 WavesToken（总排行 token），请先在配置中填写"
    if not user_token:
        return "未找到该 UID 的登录 token，请先重新登录或添加 token"
    url = XWSERVICE_BASE + "/2nd_report"
    headers = {
        "Authorization": f"Bearer {waves_token}",
        "Content-Type": "application/json",
    }
    body = {"uid": str(uid), "token": user_token, "did": did or ""}
    try:
        async with httpx.AsyncClient(timeout=180, verify=True) as c:
            r = await c.post(url, headers=headers, json=body)
    except Exception as e:
        logger.exception(f"[鸣潮] /2nd_report 网络错误: {e}")
        return f"网络错误: {e}"

    ct = r.headers.get("content-type", "")
    if r.status_code != 200 or "zip" not in ct:
        # Plain text error from server
        try:
            return f"[周年庆] 失败: HTTP {r.status_code} — {r.text[:300]}"
        except Exception:
            return f"[周年庆] 失败: HTTP {r.status_code}"

    try:
        try:
            bat_expires_in = int(r.headers.get("x-xwservice-bat-expires-in", "0") or 0)
        except ValueError:
            bat_expires_in = 0
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        out: List[bytes] = []
        for stem in ("part1", "part2", "part3"):
            # Accept either .jpg or .png in case of future format changes
            match = next((n for n in names if n.startswith(stem + ".")), None)
            if not match:
                return f"[周年庆] 服务返回缺失 {stem}"
            out.append(zf.read(match))
        return AnnivReportResult(
            parts=out,
            new_token=r.headers.get("x-xwservice-new-token", ""),
            new_bat=r.headers.get("x-xwservice-new-bat", ""),
            bat_expires_in=bat_expires_in,
        )
    except Exception as e:
        logger.exception(f"[鸣潮] 周年庆 ZIP 解析失败: {e}")
        return f"解析返回数据失败: {e}"
