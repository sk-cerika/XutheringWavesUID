import asyncio
from pathlib import Path
from typing import Any, Dict

import httpx
from async_timeout import timeout
from pydantic import BaseModel
from starlette.responses import HTMLResponse

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.web_app import app

from ..utils.constants import WAVES_GAME_ID
from ..utils.database.models import WavesUser
from ..utils.resource.RESOURCE_PATH import custom_waves_template, waves_templates
from ..wutheringwaves_config import ShowConfig
from ..wutheringwaves_login.login import (
    cache,
    get_url,
    get_token,
    evict_user_login,
    send_login,
)
from . import deal
from .login_succ import login_success_msg

ADD_TOKEN_FLOW = "add_token"


async def add_token_web(bot: Bot, ev: Event):
    url, is_local = await get_url()
    url = url.rstrip("/")
    if is_local:
        return await _add_token_web_local(bot, ev, url)
    return await _add_token_web_other(bot, ev, url)


async def _finish_add_token(bot: Bot, ev: Event, token: str):
    # 拿到 token 后本地落库并回执，本地/外置共用
    at_sender = True if ev.group_id else False
    if not token:
        return
    ck_msg = await deal.add_cookie(ev, token, "", is_login=False)
    # 严格匹配 deal.add_cookie 的成功文案, 避免 "请求成功" 等内部占位被误判为成功
    if isinstance(ck_msg, str) and ("登录成功" in ck_msg or "记录成功" in ck_msg):
        await bot.send((" " if at_sender else "") + ck_msg.rstrip("\n"), at_sender)
        user = await WavesUser.get_user_by_attr(
            ev.user_id, ev.bot_id, "cookie", token, game_id=WAVES_GAME_ID
        )
        if user:
            return await login_success_msg(bot, ev, user)
        return
    ck_msg = ck_msg.rstrip("\n") if isinstance(ck_msg, str) else ck_msg
    await bot.send(
        (" " if at_sender and isinstance(ck_msg, str) else "") + ck_msg
        if isinstance(ck_msg, str)
        else ck_msg,
        at_sender,
    )


async def _add_token_web_local(bot: Bot, ev: Event, url: str):
    at_sender = True if ev.group_id else False
    evict_user_login(ev.user_id)  # 撤销同用户旧登录会话, 新链接唯一有效
    user_token = get_token()

    cache.set(
        user_token,
        {
            "flow": ADD_TOKEN_FLOW,
            "token": None,
            "user_id": ev.user_id,
            "bot_id": ev.bot_id,
            "group_id": ev.group_id,
        },
    )
    await send_login(bot, ev, f"{url}/waves/i/{user_token}")

    token = None
    try:
        async with timeout(180):
            while True:
                result = cache.get(user_token)
                if result is None:
                    return
                if not isinstance(result, dict) or result.get("flow") != ADD_TOKEN_FLOW:
                    return
                if result.get("token") is not None:
                    token = result["token"]
                    cache.delete(user_token)
                    break
                await asyncio.sleep(1)
    except asyncio.TimeoutError:
        return await bot.send("添加Token超时!", at_sender=at_sender)
    except Exception as e:
        logger.exception(f"[鸣潮·添加Token] 异常: {e}")
        return await bot.send("添加Token失败，请稍后再试", at_sender=at_sender)

    return await _finish_add_token(bot, ev, token)


async def _add_token_web_other(bot: Bot, ev: Event, url: str):
    # 外置 ww-login 处理网页，bot 仅领 token、转发链接、轮询结果后本地落库
    at_sender = True if ev.group_id else False
    auth = {"bot_id": ev.bot_id, "user_id": ev.user_id}

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                url + "/waves/t/token",
                json=auth,
                headers={"Content-Type": "application/json"},
            )
            text = r.text
            if not text or text.strip() == "":
                logger.error(
                    f"[鸣潮·添加Token] 取 token 空响应 status={r.status_code}"
                )
                token = ""
            else:
                try:
                    token = r.json().get("token", "")
                except Exception as e:
                    logger.error(f"[鸣潮·添加Token] 取 token 解析失败: {e} | {text[:200]}")
                    token = ""
        except Exception as e:
            token = ""
            logger.error(f"[鸣潮·添加Token] 取 token 请求失败: {e}")
        if not token:
            return await bot.send("服务请求失败! 请稍后再试\n", at_sender=at_sender)

        await send_login(bot, ev, f"{url}/waves/i/{token}")

        times = 3
        try:
            async with timeout(180):
                while True:
                    if times <= 0:
                        return await bot.send(
                            "服务请求失败! 请稍后再试\n", at_sender=at_sender
                        )

                    result = await client.post(
                        url + "/waves/t/get", json={"token": token}
                    )
                    if result.status_code != 200:
                        times -= 1
                        await asyncio.sleep(5)
                        continue

                    try:
                        data = result.json()
                    except Exception as e:
                        logger.error(
                            f"[鸣潮·添加Token] /waves/t/get 解析失败: {e} | {result.text[:200]}"
                        )
                        times -= 1
                        await asyncio.sleep(5)
                        continue

                    if data.get("done") and not data.get("success", True):
                        return await bot.send(
                            (" " if at_sender else "")
                            + (data.get("msg") or "添加Token失败"),
                            at_sender=at_sender,
                        )

                    if not data.get("done"):
                        await asyncio.sleep(1)
                        continue

                    return await _finish_add_token(
                        bot, ev, str(data.get("token") or "")
                    )
        except asyncio.TimeoutError:
            return await bot.send("添加Token超时!", at_sender=at_sender)
        except Exception as e:
            logger.exception(f"[鸣潮·添加Token] 外置异常: {e}")


async def render_add_token_page(auth: str, state: Dict[str, Any]) -> HTMLResponse:
    url, _ = await get_url()
    url = url.rstrip("/")

    custom_path = Path(ShowConfig.get_config("LoginIndexTokenHtmlPath").data)
    template = None
    if custom_path.exists():
        try:
            template = custom_waves_template.get_template("index_token.html")
        except Exception:
            template = None
    if template is None:
        template = waves_templates.get_template("index_token.html")

    return HTMLResponse(
        template.render(
            server_url=url,
            auth=auth,
            userId=state.get("user_id", ""),
        )
    )


class AddTokenModel(BaseModel):
    auth: str
    token: str


@app.post("/waves/add_token")
async def waves_add_token(data: AddTokenModel):
    temp = cache.get(data.auth)
    if temp is None:
        return {"success": False, "msg": "会话已超时"}
    if not isinstance(temp, dict) or temp.get("flow") != ADD_TOKEN_FLOW:
        return {"success": False, "msg": "会话不匹配"}

    temp["token"] = data.token
    cache.set(data.auth, temp)
    return {"success": True}
