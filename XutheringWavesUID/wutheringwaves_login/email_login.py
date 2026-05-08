"""鸣潮邮箱登录（launcher SDK 路径）。

`邮箱登录` / `国际服登录` 命令：群里推 3 分钟时效的链接，用户在网页里
完成邮箱密码 + 滑块验证，后端串起 SDK 登录、Token 换取、OAuth Code
颁发、玩家信息查询，单区服直接绑定，多区服弹卡片让用户挑。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from async_timeout import timeout
from pydantic import BaseModel
from starlette.responses import HTMLResponse

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.web_app import app

from ..utils.api.api_sdk import launcher_sdk as sdk_api
from ..utils.api.request_util import PLATFORM_SOURCE
from ..utils.constants import WAVES_GAME_ID
from ..utils.database.models import (
    WavesBind,
    WavesLangSettings,
    WavesUser,
    WavesUserSdk,
)
from ..utils.resource.RESOURCE_PATH import custom_waves_template, waves_templates
from ..wutheringwaves_config import ShowConfig
from ..wutheringwaves_user.login_succ import login_success_msg
from .login import cache as email_cache
from .login import get_token, get_url, send_login

GAME_TITLE = "[鸣潮]"
LOGIN_FLOW = "email"

REGION_LANG_DEFAULTS: Mapping[str, str] = {
    "HMT": "cht",
    "America": "en",
    "Europe": "en",
    "SEA": "en",
    "Asia": "jp",
}


async def email_login_entry(bot: Bot, ev: Event):
    at_sender = True if ev.group_id else False

    url, _ = await get_url()
    url = url.rstrip("/")
    user_token = get_token(ev.user_id)

    email_cache.set(
        user_token,
        {
            "flow": LOGIN_FLOW,
            "phase": "init",
            "user_id": ev.user_id,
            "bot_id": ev.bot_id,
            "group_id": ev.group_id,
        },
    )

    await send_login(bot, ev, f"{url}/waves/i/{user_token}")

    try:
        async with timeout(180):
            while True:
                state = email_cache.get(user_token)
                if state is None:
                    return await bot.send("登录超时!", at_sender=at_sender)

                if not isinstance(state, dict) or state.get("flow") != LOGIN_FLOW:
                    return

                phase = state.get("phase")
                if phase == "done":
                    uid = str(state.get("selected_uid") or "")
                    role_name = ""
                    for r in (state.get("regions") or []):
                        if str(r.get("role_id")) == uid:
                            role_name = str(r.get("role_name") or "")
                            break

                    email_cache.delete(user_token)
                    waves_user = await WavesUser.select_waves_user(
                        uid, ev.user_id, ev.bot_id, game_id=WAVES_GAME_ID
                    )
                    if waves_user:
                        return await login_success_msg(
                            bot, ev, waves_user, role_name=role_name
                        )
                    return await bot.send(
                        f"{GAME_TITLE} 登录已完成，但绑定信息读取失败，请稍后重试",
                        at_sender=at_sender,
                    )

                if phase == "failed":
                    err = state.get("error_msg") or "邮箱登录失败"
                    email_cache.delete(user_token)
                    return await bot.send(
                        (" " if at_sender else "") + f"{GAME_TITLE} {err}",
                        at_sender=at_sender,
                    )

                await asyncio.sleep(1)

    except asyncio.TimeoutError:
        return await bot.send("登录超时!", at_sender=at_sender)
    except Exception as e:
        logger.exception(f"[鸣潮·邮箱登录] 异常: {e}")


async def _persist_login(
    state: Dict[str, Any], role_id: str, region: str, role_name: str
) -> None:
    user_id: str = state["user_id"]
    bot_id: str = state["bot_id"]
    group_id: Optional[str] = state.get("group_id")
    auto_token: str = state["auto_token"]
    access_token: str = state["access_token"]
    device_no: str = state["device_no"]
    expires_in: int = int(state.get("expires_in") or 0)

    existing = await WavesUser.get_user_by_attr(
        user_id, bot_id, "uid", role_id, game_id=WAVES_GAME_ID
    )
    if existing:
        await WavesUser.update_data_by_data(
            select_data={
                "user_id": user_id,
                "bot_id": bot_id,
                "uid": role_id,
                "game_id": WAVES_GAME_ID,
            },
            update_data={
                "cookie": auto_token,
                "bat": access_token,
                "did": device_no,
                "status": "",
                "platform": PLATFORM_SOURCE,
                "game_id": WAVES_GAME_ID,
                "is_login": True,
            },
        )
    else:
        await WavesUser.insert_data(
            user_id,
            bot_id,
            cookie=auto_token,
            uid=role_id,
            bat=access_token,
            did=device_no,
            platform=PLATFORM_SOURCE,
            game_id=WAVES_GAME_ID,
            is_login=True,
        )

    await WavesUser.update_token_by_login(role_id, WAVES_GAME_ID, auto_token, device_no)

    is_first_record = await WavesUserSdk.upsert(
        user_id, bot_id, role_id, region=region
    )
    if expires_in > 0:
        await WavesUserSdk.update_bat_expires_at(
            user_id, bot_id, role_id, int(time.time()) + expires_in
        )

    res = await WavesBind.insert_waves_uid(user_id, bot_id, role_id, group_id, lenth_limit=9)
    if res in (0, -2):
        await WavesBind.switch_uid_by_game(user_id, bot_id, role_id)

    if is_first_record:
        await _maybe_set_initial_lang(user_id, region)


async def _maybe_set_initial_lang(user_id: str, region: str) -> None:
    target = REGION_LANG_DEFAULTS.get(region)
    if not target:
        return
    if await WavesLangSettings.get_lang(user_id):
        return
    await WavesLangSettings.set_lang(user_id, target)
    logger.info(f"[鸣潮·邮箱登录] user_id={user_id} 区服={region} → 初始语言 {target}")


class EmailLoginRequest(BaseModel):
    auth: str
    email: str
    password: str
    captcha: Optional[Dict[str, str]] = None


class EmailBindRequest(BaseModel):
    auth: str
    role_id: str
    region: str


async def render_email_login_page(auth: str, state: Dict[str, Any]) -> HTMLResponse:
    url, _ = await get_url()
    url = url.rstrip("/")

    custom_path = Path(ShowConfig.get_config("LoginIndexEmailHtmlPath").data)
    if custom_path.exists():
        try:
            template = custom_waves_template.get_template("index_email.html")
        except Exception:
            template = waves_templates.get_template("index_email.html")
    else:
        template = waves_templates.get_template("index_email.html")

    return HTMLResponse(
        template.render(
            server_url=url,
            auth=auth,
            userId=state.get("user_id", ""),
        )
    )


def _captcha_form(captcha: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if not captcha:
        return None
    return {
        "geetestCaptchaOutput": captcha.get("captcha_output", ""),
        "geetestGenTime": captcha.get("gen_time", ""),
        "geetestLotNumber": captcha.get("lot_number", ""),
        "geetestPassToken": captcha.get("pass_token", ""),
    }


def _mark_failed(auth: str, state: Dict[str, Any], err: str) -> None:
    state["phase"] = "failed"
    state["error_msg"] = err
    email_cache.set(auth, state)


@app.post("/waves/l/login")
async def waves_launcher_login(data: EmailLoginRequest):
    state = email_cache.get(data.auth)
    if not isinstance(state, dict):
        return {"success": False, "msg": "登录会话已超时，请重新发起命令"}

    device_no = state.get("device_no") or str(uuid.uuid4()).upper()
    captcha = _captcha_form(data.captcha)
    logger.debug(
        f"[鸣潮·邮箱登录] step=email_login email={data.email} device_no={device_no} "
        f"captcha={'yes' if captcha else 'no'}"
    )

    login_resp = await sdk_api.email_login(
        data.email, data.password, device_no=device_no, captcha=captcha
    )
    if not login_resp.success or not login_resp.data:
        logger.debug(f"[鸣潮·邮箱登录] email_login 失败 code={login_resp.code} msg={login_resp.msg!r}")
        return {"success": False, "msg": login_resp.msg or "邮箱登录失败"}
    logger.debug(
        f"[鸣潮·邮箱登录] step=exchange_token user_id={login_resp.data.user_id} "
        f"username={login_resp.data.username!r} login_code_len={len(login_resp.data.code or '')} "
        f"auto_token_len={len(login_resp.data.auto_token or '')}"
    )

    tok_resp = await sdk_api.exchange_access_token(login_resp.data.code, device_no=device_no)
    if not tok_resp.success or not tok_resp.data:
        logger.debug(f"[鸣潮·邮箱登录] exchange_token 失败 code={tok_resp.code} msg={tok_resp.msg!r}")
        return {"success": False, "msg": tok_resp.msg or "Token 换取失败"}
    logger.debug(
        f"[鸣潮·邮箱登录] step=oauth_code access_token_len={len(tok_resp.data.access_token or '')} "
        f"expires_in={tok_resp.data.expires_in}"
    )

    oc_resp = await sdk_api.make_oauth_code(tok_resp.data.access_token, device_no=device_no)
    if not oc_resp.success or not oc_resp.data:
        logger.debug(f"[鸣潮·邮箱登录] oauth_code 失败 code={oc_resp.code} msg={oc_resp.msg!r}")
        return {"success": False, "msg": oc_resp.msg or "OAuth Code 生成失败"}
    logger.debug(
        f"[鸣潮·邮箱登录] step=query_brief oauth_code={oc_resp.data!r}"
    )

    brief_resp = await sdk_api.query_player_brief(oc_resp.data)
    if not brief_resp.success or brief_resp.data is None:
        logger.debug(
            f"[鸣潮·邮箱登录] query_brief 失败 code={brief_resp.code} msg={brief_resp.msg!r}"
        )
        return {"success": False, "msg": brief_resp.msg or "玩家信息查询失败"}
    logger.debug(f"[鸣潮·邮箱登录] query_brief 成功 roles_count={len(brief_resp.data)}")

    roles = brief_resp.data
    if not roles:
        return {"success": False, "msg": "未查询到任何鸣潮角色，请确认账号已创建过角色"}

    state.update(
        {
            "phase": "logging_in",
            "device_no": device_no,
            "auto_token": login_resp.data.auto_token,
            "access_token": tok_resp.data.access_token,
            "expires_in": tok_resp.data.expires_in,
            "regions": [r.model_dump() for r in roles],
        }
    )
    email_cache.set(data.auth, state)

    if len(roles) == 1:
        only = roles[0]
        try:
            await _persist_login(state, only.role_id, only.region, only.role_name)
        except Exception as e:
            logger.exception("[鸣潮·邮箱登录] 自动绑定失败")
            _mark_failed(data.auth, state, f"绑定失败：{e}")
            return {"success": False, "msg": str(e)}

        state["phase"] = "done"
        state["selected_uid"] = only.role_id
        state["selected_region"] = only.region
        email_cache.set(data.auth, state)
        return {"success": True, "bound": True}

    return {
        "success": True,
        "bound": False,
        "regions": [r.model_dump() for r in roles],
    }


@app.post("/waves/l/bind")
async def waves_launcher_bind(data: EmailBindRequest):
    state = email_cache.get(data.auth)
    if not isinstance(state, dict):
        return {"success": False, "msg": "登录会话已超时，请重新发起命令"}

    chosen = next(
        (
            r
            for r in (state.get("regions") or [])
            if str(r.get("role_id")) == str(data.role_id) and r.get("region") == data.region
        ),
        None,
    )
    if chosen is None:
        return {"success": False, "msg": "区服信息不匹配，请重新登录"}

    try:
        await _persist_login(
            state, str(data.role_id), data.region, chosen.get("role_name", "")
        )
    except Exception as e:
        logger.exception("[鸣潮·邮箱登录] 绑定失败")
        _mark_failed(data.auth, state, f"绑定失败：{e}")
        return {"success": False, "msg": str(e)}

    state["phase"] = "done"
    state["selected_uid"] = str(data.role_id)
    state["selected_region"] = data.region
    email_cache.set(data.auth, state)
    return {"success": True}
