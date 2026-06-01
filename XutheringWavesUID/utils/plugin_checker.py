import inspect
from typing import Optional
from gsuid_core.logger import logger


def is_from_plugin(plugin_name: str = "XutheringWavesUID") -> bool:
    """检查调用是否来自指定插件"""
    current_plugin = get_current_plugin()
    result = current_plugin == plugin_name

    if result:
        logger.debug(f"[鸣潮·插件检查] 调用来自插件 {plugin_name}")

    return result


def get_current_plugin() -> Optional[str]:
    """获取当前执行的插件名称"""
    frame = inspect.currentframe()

    skip_files = ["plugin_checker.py", "bot_send_hook.py"]
    all_plugins = []  # 记录所有遇到的插件

    try:
        frame = frame.f_back

        while frame:
            frame_info = inspect.getframeinfo(frame)
            file_path = frame_info.filename

            # 记录调用栈（只记录插件相关的）
            if "/plugins/" in file_path or "\\plugins\\" in file_path:
                all_plugins.append(f"  -> {file_path}:{frame_info.lineno}")

            # 检查是否在 plugins 目录中
            if "/plugins/" in file_path:
                parts = file_path.split("/plugins/")
                if len(parts) >= 2:
                    plugin_path = parts[1]
                    plugin_name = plugin_path.split("/")[0]
                    # 只记录非工具文件的插件
                    if not any(skip_file in file_path for skip_file in skip_files):
                        all_plugins.append(plugin_name)
            elif "\\plugins\\" in file_path:
                parts = file_path.split("\\plugins\\")
                if len(parts) >= 2:
                    plugin_path = parts[1]
                    plugin_name = plugin_path.split("\\")[0]
                    if not any(skip_file in file_path for skip_file in skip_files):
                        all_plugins.append(plugin_name)

            frame = frame.f_back
    finally:
        del frame

    plugin_names = [p for p in all_plugins if not p.startswith("  ->")]
    if plugin_names:
        result = plugin_names[-1]  # 最后一个就是离 hook 调用最近的
        logger.debug(f"[鸣潮·插件检查] 找到的插件列表: {plugin_names}, 返回: {result}")
        return result

    logger.debug(f"[鸣潮·插件检查] 未找到插件来源")
    return None


def is_from_waves_plugin() -> bool:
    return is_from_plugin("XutheringWavesUID")
