import os
import re
import uuid
import asyncio
import hashlib
from typing import Union
from pathlib import Path

import httpx
from pydantic import BaseModel
from async_timeout import timeout
from starlette.responses import HTMLResponse

from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.web_app import app
from gsuid_core.utils.cookie_manager.qrlogin import get_qrcode_base64

from ..utils.util import get_public_ip
from ..utils.cache import TimedCache
from ..utils.constants import WAVES_GAME_ID
from ..utils.waves_api import waves_api
from ..wutheringwaves_user import deal
from ..utils.database.models import WavesBind, WavesUser
from ..wutheringwaves_config import PREFIX, WutheringWavesConfig, ShowConfig
from ..utils.resource.RESOURCE_PATH import (
    MAIN_PATH,
    waves_templates,
    custom_waves_template,
)
from ..wutheringwaves_user.login_succ import login_success_msg

# 登录态用 sqlite 落盘，避免多 worker / 进程重启把内存 cache 清空导致 404
cache = TimedCache(
    timeout=180,
    maxsize=10,
    persist_path=MAIN_PATH / "url_cache.db",
)

game_title = "[鸣潮]"
msg_error = f"{game_title} 登录失败\n1.是否注册过库街区\n2.库街区能否查询当前鸣潮特征码数据"


async def get_url() -> tuple[str, bool]:
    url = WutheringWavesConfig.get_config("WavesLoginUrl").data
    if url:
        if not url.startswith("http"):
            url = f"https://{url}"
        return url.rstrip("/"), WutheringWavesConfig.get_config("WavesLoginUrlSelf").data
    else:
        HOST = core_config.get_config("HOST")
        PORT = core_config.get_config("PORT")

        if HOST == "localhost" or HOST == "127.0.0.1":
            _host = "localhost"
        else:
            _host = await get_public_ip(HOST)

        return f"http://{_host}:{PORT}", True


def is_valid_chinese_phone_number(phone_number):
    # 正则表达式匹配中国大陆的手机号
    pattern = re.compile(r"^1[3-9]\d{9}$")
    return pattern.match(phone_number) is not None


def is_validate_code(code):
    # 正则表达式匹配6位数字
    pattern = re.compile(r"^\d{6}$")
    return pattern.match(code) is not None


def get_token(userId: str):
    return hashlib.sha256(userId.encode()).hexdigest()[:8]


async def send_login(bot: Bot, ev: Event, url):
    at_sender = True if ev.group_id else False

    if WutheringWavesConfig.get_config("WavesQRLogin").data:
        path = Path(__file__).parent / f"{ev.user_id}.gif"

        im = [
            f"{game_title} 您的id为【{ev.user_id}】\n",
            "请用浏览器扫描获取地址，完成后将刷新全部面板，无需立即刷新",
            MessageSegment.image(await get_qrcode_base64(url, path, ev.bot_id)),
        ]

        if WutheringWavesConfig.get_config("WavesLoginForward").data:
            if not ev.group_id and ev.bot_id == "onebot":
                # 私聊+onebot 不转发
                await bot.send(im)
            else:
                await bot.send(MessageSegment.node(im))
        else:
            await bot.send(im, at_sender=at_sender)

        if path.exists():
            path.unlink()
    else:
        if WutheringWavesConfig.get_config("WavesTencentWord").data:
            url = f"https://docs.qq.com/scenario/link.html?url={url}"
        im = [
            f"{game_title} 您的id为【{ev.user_id}】",
            "完成后将刷新全部面板，无需立即刷新",
            f" {url}" if WutheringWavesConfig.get_config("WavesLoginForward").data else url,
            "3分钟内有效",
        ]

        if WutheringWavesConfig.get_config("WavesLoginForward").data:
            if not ev.group_id and ev.bot_id == "onebot":
                # 私聊+onebot 不转发
                await bot.send("\n".join(im))
            else:
                await bot.send(MessageSegment.node(im))
        else:
            await bot.send("\n".join(im), at_sender=at_sender)


async def page_login_local(bot: Bot, ev: Event, url):
    at_sender = True if ev.group_id else False
    user_token = get_token(ev.user_id)
    logger.debug(
        f"[鸣潮登录] page_login_local user_id={ev.user_id} user_token={user_token}"
    )

    # 始终以最新指令为准：直接覆盖任何已有 session（含邮箱），并刷新 TTL。
    # 先写 cache 再发 URL，关掉「URL 已可见但 cache 未写入」的瞬开窗口。
    # 旧的邮箱 waiter 下一次轮询会看到 flow 变了，按 email_login.py 的逻辑静默退出。
    cache.set(user_token, {"mobile": -1, "code": -1, "user_id": ev.user_id})
    await send_login(bot, ev, f"{url}/waves/i/{user_token}")

    text = None
    try:
        async with timeout(180):
            while True:
                result = cache.get(user_token)
                if result is None:
                    # 缓存被另一个 waiter 消费 / 显式清理，静默退出，由外层 timeout 兜底真正的超时
                    return
                if isinstance(result, dict) and result.get("flow") == "email":
                    return
                if result.get("mobile") != -1 and result.get("code") != -1:
                    text = f"{result['mobile']},{result['code']}"
                    logger.debug(
                        f"[鸣潮登录] page_login_local 收到提交 user_id={ev.user_id} "
                        f"user_token={user_token}"
                    )
                    cache.delete(user_token)
                    break
                await asyncio.sleep(1)
    except asyncio.TimeoutError:
        return await bot.send("登录超时!", at_sender=at_sender)
    except Exception as e:
        logger.exception(f"[鸣潮·登录] 异常: {e}")
        return await bot.send("登录失败，请稍后再试", at_sender=at_sender)

    if text is None:
        return
    return await code_login(bot, ev, text, True)


async def page_login_other(bot: Bot, ev: Event, url):
    at_sender = True if ev.group_id else False
    user_token = get_token(ev.user_id)
    logger.debug(
        f"[鸣潮登录] page_login_other user_id={ev.user_id} user_token={user_token} url={url}"
    )

    auth = {"bot_id": ev.bot_id, "user_id": ev.user_id}

    token = cache.get(user_token)
    if isinstance(token, str):
        logger.debug(
            f"[鸣潮登录] page_login_other 命中缓存 token user_id={ev.user_id}"
        )
        await send_login(bot, ev, f"{url}/waves/i/{token}")
        return

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                url + "/waves/token",
                json=auth,
                headers={"Content-Type": "application/json"},
            )
            text = r.text
            if not text or text.strip() == "":
                logger.error(f"请求登录服务失败：服务器返回空响应 (状态码: {r.status_code})")
                token = ""
            else:
                try:
                    token = r.json().get("token", "")
                except Exception as json_err:
                    logger.error(f"请求登录服务失败：{json_err} | 响应内容: {text[:200]}")
                    token = ""
        except Exception as e:
            token = ""
            logger.error(f"请求登录服务失败：{e}")
        if not token:
            return await bot.send("服务请求失败! 请稍后再试\n", at_sender=at_sender)

        await send_login(bot, ev, f"{url}/waves/i/{token}")

        cache.set(user_token, token)
        times = 3
        try:
            async with timeout(180):
                while True:
                    if times <= 0:
                        return await bot.send("服务请求失败! 请稍后再试\n", at_sender=at_sender)

                    result = await client.post(url + "/waves/get", json={"token": token})
                    if result.status_code != 200:
                        times -= 1
                        await asyncio.sleep(5)
                        continue

                    try:
                        text = result.text
                        if not text or text.strip() == "":
                            logger.error("请求登录服务失败：/waves/get返回空响应")
                            times -= 1
                            await asyncio.sleep(5)
                            continue
                        data = result.json()
                    except Exception as json_err:
                        logger.error(f"请求登录服务失败：{json_err} | 响应: {result.text[:200]}")
                        times -= 1
                        await asyncio.sleep(5)
                        continue

                    if not data.get("ck"):
                        await asyncio.sleep(1)
                        continue

                    logger.debug(
                        f"[鸣潮登录] page_login_other 拿到 ck user_id={ev.user_id}"
                    )
                    waves_user, bind_msg = await add_cookie(ev, data["ck"], data["did"])
                    cache.delete(user_token)
                    if "成功" in bind_msg:
                        await bot.send((" " if at_sender else "") + bind_msg.rstrip("\n"), at_sender)
                    if waves_user and isinstance(waves_user, WavesUser):
                        return await login_success_msg(bot, ev, waves_user)
                    else:
                        if "成功" in bind_msg:
                            return
                        return await bot.send(bind_msg if bind_msg else msg_error, at_sender=at_sender)
        except asyncio.TimeoutError:
            cache.delete(user_token)
            return await bot.send("登录超时!", at_sender=at_sender)


async def page_login(bot: Bot, ev: Event):
    url, is_local = await get_url()
    logger.debug(
        f"[鸣潮登录] page_login user_id={ev.user_id} url={url} is_local={is_local}"
    )

    if is_local:
        return await page_login_local(bot, ev, url)
    else:
        return await page_login_other(bot, ev, url)


async def code_login(bot: Bot, ev: Event, text: str, isPage=False):
    at_sender = True if ev.group_id else False
    game_title = "[鸣潮]"
    # 手机+验证码
    try:
        phone_number, code = text.split(",")
        if not is_valid_chinese_phone_number(phone_number):
            raise ValueError("Invalid phone number")
    except ValueError as _:
        logger.debug(
            f"[鸣潮登录] code_login 格式错误 user_id={ev.user_id} isPage={isPage}"
        )
        return await bot.send(
            f"{game_title} 手机号+验证码登录失败\n\n请参照以下格式:\n{PREFIX}登录 手机号,验证码\n",
            at_sender=at_sender,
        )

    did = str(uuid.uuid4()).upper()
    logger.debug(
        f"[鸣潮登录] code_login 提交 user_id={ev.user_id} isPage={isPage}"
    )
    result = await waves_api.login(phone_number, code, did)
    logger.debug(
        f"[鸣潮登录] code_login waves_api.login 返回 user_id={ev.user_id} "
        f"success={result.success} msg={result.msg!r}"
    )
    if not result.success:
        return await bot.send(result.throw_msg(), at_sender=at_sender)

    if result.msg == "系统繁忙，请稍后再试":
        # 可能是没注册库街区。 -_-||
        return await bot.send(msg_error, at_sender=at_sender)

    if not result.data or not isinstance(result.data, dict):
        return await bot.send(message=result.throw_msg(), at_sender=at_sender)

    token = result.data.get("token", "")
    waves_user, bind_msg = await add_cookie(ev, token, did)
    if "成功" in bind_msg:
        await bot.send((" " if at_sender else "") + bind_msg.rstrip("\n"), at_sender)
    if waves_user and isinstance(waves_user, WavesUser):
        return await login_success_msg(bot, ev, waves_user)
    else:
        if "成功" in bind_msg:
            return
        return await bot.send(bind_msg if bind_msg else msg_error, at_sender=at_sender)


async def add_cookie(ev, token, did) -> tuple[Union[WavesUser, None], str]:
    """返回 (WavesUser 或 None, 绑定概要消息)"""
    ck_res = await deal.add_cookie(ev, token, did, is_login=True)
    success = "成功" in ck_res
    logger.debug(
        f"[鸣潮登录] add_cookie user_id={ev.user_id} success={success} "
        f"summary={ck_res[:80]!r}"
    )
    if success:
        user = await WavesUser.get_user_by_attr(ev.user_id, ev.bot_id, "cookie", token, game_id=WAVES_GAME_ID)
        if user:
            data = await WavesBind.insert_waves_uid(ev.user_id, ev.bot_id, user.uid, ev.group_id, lenth_limit=9)
            if data == 0 or data == -2:
                await WavesBind.switch_uid_by_game(ev.user_id, ev.bot_id, user.uid)
        logger.debug(
            f"[鸣潮登录] add_cookie 绑定 user_id={ev.user_id} uid={getattr(user, 'uid', None)}"
        )
        return user, ck_res
    return None, ck_res


@app.get("/waves/i/{auth}")
async def waves_login_index(auth: str):
    state = cache.get(auth)
    logger.debug(
        f"[鸣潮登录] waves_login_index auth={auth} state_type={type(state).__name__} "
        f"flow={(state.get('flow') if isinstance(state, dict) else None)!r}"
    )

    if isinstance(state, dict) and state.get("flow") == "email":
        from .email_login import render_email_login_page

        return await render_email_login_page(auth, state)

    temp = state
    if temp is None:
        # 多 worker / 进程重启 / TTL 过期都会走这里，打点便于排查
        logger.info(
            f"[登录404] auth={auth} pid={os.getpid()} "
            f"mem_keys={len(cache.cache)} persist={cache.persist_path is not None}"
        )
        # 检查自定义404页面路径
        custom_404_path = Path(ShowConfig.get_config("Login404HtmlPath").data)
        if custom_404_path.exists():
            # 尝试使用自定义模板
            try:
                template = custom_waves_template.get_template("404.html")
            except Exception:
                # 使用默认模板
                template = waves_templates.get_template("404.html")
        else:
            # 路径不存在，使用默认模板
            template = waves_templates.get_template("404.html")
        return HTMLResponse(template.render())
    else:
        from ..utils.api.api import MAIN_URL

        url, _ = await get_url()

        # 检查自定义登录页面路径
        custom_index_path = Path(ShowConfig.get_config("LoginIndexHtmlPath").data)
        if custom_index_path.exists():
            # 尝试使用自定义模板
            try:
                template = custom_waves_template.get_template("index.html")
            except Exception:
                # 使用默认模板
                template = waves_templates.get_template("index.html")
        else:
            # 路径不存在，使用默认模板
            template = waves_templates.get_template("index.html")

        return HTMLResponse(
            template.render(
                server_url=url,
                auth=auth,
                userId=temp.get("user_id", ""),
                kuro_url=MAIN_URL,
            )
        )


class LoginModel(BaseModel):
    auth: str
    mobile: str
    code: str


@app.post("/waves/login")
async def waves_login(data: LoginModel):
    temp = cache.get(data.auth)
    logger.debug(
        f"[鸣潮登录] waves_login POST auth={data.auth} cache_hit={temp is not None}"
    )
    if temp is None:
        return {"success": False, "msg": "登录超时"}

    temp.update(data.model_dump())
    cache.set(data.auth, temp)
    return {"success": True}
