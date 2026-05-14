import time
from typing import List, Union
from datetime import datetime

from gsuid_core.logger import logger
from ..utils.waves_api import waves_api
from ..wutheringwaves_config import PREFIX, WutheringWavesConfig
from ..utils.resource.RESOURCE_PATH import waves_templates, ANN_CARD_PATH
from ..utils.render_utils import (
    PLAYWRIGHT_AVAILABLE,
    get_logo_b64,
    get_footer_b64,
    get_image_b64_with_cache,
    render_html,
)


from .ann_card_pil import ann_list_card as ann_list_card_pil
from .ann_card_pil import ann_detail_card as ann_detail_card_pil
from .ann_card_pil import format_date


async def ann_list_card(user_id: str = None) -> bytes:
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await ann_list_card_pil(user_id)

    try:
        logger.debug("[鸣潮] 正在获取公告列表...")

        user_info = None
        if user_id:
            logger.debug(f"[鸣潮] 正在获取用户 {user_id} 的公告列表...")
            ann_list = []
            res = await waves_api.get_bbs_list(user_id, pageIndex=1, pageSize=9)
            if res.success:
                raw_data = res.model_dump()
                post_list = raw_data["data"]["postList"]
                post_list.sort(key=lambda x: x.get("showTime", 0), reverse=True)
                value = [{**x, "id": int(x["postId"]), "eventType": 4} for x in post_list]
                ann_list = value

                if post_list:
                    first_post = post_list[0]
                    user_info = {
                        "userName": first_post.get("userName", ""),
                        "headCodeUrl": first_post.get("userHeadUrl", ""),
                        "ipRegion": first_post.get("ipRegion", "")
                    }
            if not ann_list:
                raise Exception(f"获取用户 {user_id} 的公告失败,请检查用户ID是否正确")
        else:
            ann_list = await waves_api.get_ann_list()
            if not ann_list:
                raise Exception("获取游戏公告失败,请检查接口是否正常")

        grouped = {}
        for item in ann_list:
            t = item.get("eventType")
            if not t:
                continue
            grouped.setdefault(t, []).append(item)

        for data in grouped.values():
            data.sort(key=lambda x: x.get("publishTime", 0), reverse=True)

        CONFIGS = {
            1: {"name": "活动", "color": "#F97316"},
            2: {"name": "资讯", "color": "#3B82F6"},
            3: {"name": "公告", "color": "#10B981"},
            4: {"name": "周边", "color": "#8B5CF6"}
        }

        sections = []
        for t in [1, 2, 3, 4]:
            if t not in grouped:
                continue

            max_items = 9 if user_id else 6
            section_items = []
            for item in grouped[t][:max_items]:
                if not item.get("id") or not item.get("postTitle"):
                    continue

                cover_url = item.get("coverUrl", "")

                if not cover_url:
                    cover_images = item.get("coverImages", [])
                    if cover_images and len(cover_images) > 0:
                        cover_url = cover_images[0].get("url", "")

                if t == 4 and not cover_url:
                    img_content = item.get("imgContent", [])
                    if img_content and len(img_content) > 0:
                        cover_url = img_content[0].get("url", "")

                if not cover_url:
                    video_content = item.get("videoContent", [])
                    if video_content and len(video_content) > 0:
                        cover_url = video_content[0].get("coverUrl") or video_content[0].get("videoCoverUrl", "")

                if not cover_url and user_info:
                    cover_url = user_info.get("headCodeUrl", "")

                cover_b64 = await get_image_b64_with_cache(
                    cover_url, ANN_CARD_PATH, quality=20, cover_size=(400, 200),
                ) if cover_url else ""

                post_id = item.get("postId", "") or str(item.get("id", ""))
                from .utils.post_id_mapper import get_or_create_short_id
                short_id = get_or_create_short_id(post_id)

                if t == 4:
                    date_str = item.get("showTime", "")
                    if not date_str:
                        date_str = format_date(item.get("createTimestamp", 0))
                else:
                    date_str = format_date(item.get("publishTime", 0))

                section_items.append({
                    "id": str(item.get("id", "")),
                    "short_id": short_id,
                    "postTitle": item.get("postTitle", ""),
                    "date_str": date_str,
                    "coverUrl": cover_url,
                    "coverB64": cover_b64,
                })
            
            if section_items:
                sections.append({
                    "name": CONFIGS[t]["name"],
                    "color": CONFIGS[t]["color"],
                    "ann_list": section_items
                })

        if user_id:
            subtitle = f"用户 {user_id} 的公告列表 | 使用 {PREFIX}公告#ID 查看详情"
        else:
            subtitle = f"查看详细内容，使用 {PREFIX}公告#ID 查看详情"

        user_avatar_b64 = ""
        user_name = ""
        user_ip_region = ""
        if user_info:
            user_name = user_info.get("userName", "")
            user_ip_region = user_info.get("ipRegion", "")
            head_url = user_info.get("headCodeUrl", "")
            if head_url:
                user_avatar_b64 = await get_image_b64_with_cache(head_url, ANN_CARD_PATH, quality=60)

        is_user_list = bool(user_id) and user_id != "10011001"

        context = {
            "title": "鸣潮公告",
            "subtitle": subtitle,
            "is_list": True,
            "is_user_list": is_user_list,
            "sections": sections,
            "logo_b64": get_logo_b64(),
            "footer_b64": get_footer_b64(),
            "user_avatar": user_avatar_b64,
            "user_name": user_name,
            "user_ip_region": user_ip_region
        }

        logger.debug(f"[鸣潮] 准备通过HTML渲染列表, sections: {len(sections)}")
        img_bytes = await render_html(waves_templates, "ann_card.html", context)
        if img_bytes:
            return img_bytes
        else:
            logger.warning("[鸣潮] Playwright 渲染返回空, 正在回退到 PIL 渲染")
            return await ann_list_card_pil(user_id)

    except Exception as e:
        logger.exception(f"[鸣潮] HTML渲染失败: {e}")
        return await ann_list_card_pil(user_id)


async def ann_detail_card(ann_id: Union[int, str], is_check_time=False) -> Union[bytes, str, List[bytes]]:
    use_html_render = WutheringWavesConfig.get_config("UseHtmlRender").data
    if not PLAYWRIGHT_AVAILABLE or not use_html_render:
        return await ann_detail_card_pil(ann_id, is_check_time)

    try:
        logger.debug(f"[鸣潮] 正在获取公告详情: {ann_id}")
        ann_list = await waves_api.get_ann_list(True)
        if not ann_list:
            raise Exception("获取游戏公告失败,请检查接口是否正常")

        if isinstance(ann_id, int):
            content = [x for x in ann_list if x["id"] == ann_id]
        else:
            content = [x for x in ann_list if str(x.get("postId", "")) == str(ann_id) or str(x.get("id", "")) == str(ann_id)]

        if content:
            postId = content[0]["postId"]
        else:
            return "未找到该公告"
            # postId = str(ann_id)

        res = await waves_api.get_ann_detail(postId)
        if not res:
            return "未找到该公告"

        if is_check_time:
            post_time = format_post_time(res["postTime"])
            now_time = int(time.time())
            if post_time < now_time - 86400:
                return "该公告已过期"

        post_content = res["postContent"]
        
        content_type2_first = [x for x in post_content if x["contentType"] == 2]
        if not content_type2_first and "coverImages" in res:
            _node = res["coverImages"][0]
            _node["contentType"] = 2
            post_content.insert(0, _node)

        if not post_content:
            return "未找到该公告"

        long_image_urls = []
        for item in post_content:
            if item.get("contentType") == 2 and "url" in item:
                img_width = item.get("imgWidth", 0)
                img_height = item.get("imgHeight", 0)
                if img_width > 0 and img_height / img_width > 5:
                    long_image_urls.append(item["url"])

        result_images = []
        if long_image_urls:
            from ..utils.image import pic_download_from_url
            from gsuid_core.utils.image.convert import convert_img

            logger.info(f"[鸣潮] 检测到 {len(long_image_urls)} 张超长图片，将单独发送")
            for img_url in long_image_urls:
                try:
                    img = await pic_download_from_url(ANN_CARD_PATH, img_url)
                    img_bytes = await convert_img(img)
                    result_images.append(img_bytes)
                except Exception as e:
                    logger.warning(f"[鸣潮] 下载超长图片失败: {img_url}, {e}")

            post_content = [
                item for item in post_content
                if not (item.get("contentType") == 2 and item.get("url") in long_image_urls)
            ]
            logger.info(f"[鸣潮] 过滤后剩余 {len(post_content)} 个内容项")

        processed_content = []
        for item in post_content:
            ctype = item.get("contentType")
            if ctype == 1:
                processed_content.append({
                    "contentType": 1,
                    "content": item.get("content", "")
                })
            elif ctype == 2 and "url" in item:
                img_url = item["url"]
                img_b64 = await get_image_b64_with_cache(img_url, ANN_CARD_PATH, quality=60)
                processed_content.append({
                    "contentType": 2,
                    "url": img_url,
                    "urlB64": img_b64,
                })
            else:
                cover_url = item.get("coverUrl") or item.get("videoCoverUrl")
                if cover_url:
                    cover_b64 = await get_image_b64_with_cache(cover_url, ANN_CARD_PATH, quality=60)
                    processed_content.append({
                        "contentType": "video",
                        "coverUrl": cover_url,
                        "coverB64": cover_b64,
                    })

        user_name = res.get("userName", "鸣潮")
        head_code_url = res.get("headCodeUrl", "")
        user_avatar = ""
        if head_code_url:
            user_avatar = await get_image_b64_with_cache(head_code_url, ANN_CARD_PATH, quality=60)

        context = {
            "title": res.get("postTitle", "公告详情"),
            "subtitle": f"发布时间: {res.get('postTime', '未知')}",
            "post_time": res.get('postTime', '未知'),
            "user_name": user_name,
            "user_avatar": user_avatar,
            "is_list": False,
            "content": processed_content,
            "logo_b64": get_logo_b64(),
            "footer_b64": get_footer_b64()
        }

        logger.debug(f"[鸣潮] 准备通过HTML渲染详情, content items: {len(processed_content)}")
        img_bytes = await render_html(waves_templates, "ann_card.html", context)
        if img_bytes:
            if result_images:
                result_images = [img_bytes] + result_images
                logger.info(f"[鸣潮] 返回 {len(result_images)} 张图片（包含 {len(long_image_urls)} 张超长图和1张公告卡片）")
                return result_images
            return img_bytes
        else:
            logger.warning("[鸣潮] Playwright 渲染返回空, 正在回退到 PIL 渲染")
            return await ann_detail_card_pil(ann_id, is_check_time)

    except Exception as e:
        logger.exception(f"[鸣潮] HTML渲染失败: {e}")
        return await ann_detail_card_pil(ann_id, is_check_time)


def format_post_time(post_time: str) -> int:
    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d %H:%M").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d %H:%M:%S").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    return 0
