import importlib

from gsuid_core.logger import logger

from ...damage.abstract import DamageRankRegister, DamageDetailRegister

ID_MAPPING = {
    "1102": "1102",
    "1103": "1103",
    "1104": "1104",
    "1105": "1105",
    "1106": "1106",
    "1107": "1107",
    "1108": "1108",
    "1202": "1202",
    "1203": "1203",
    "1204": "1204",
    "1205": "1205",
    "1206": "1206",
    "1207": "1207",
    "1208": "1208",
    "1209": "1209",
    "1210": "1210",
    "1211": "1211",
    "1301": "1301",
    "1302": "1302",
    "1303": "1303",
    "1304": "1304",
    "1305": "1305",
    "1306": "1306",
    "1307": "1307",
    "1402": "1402",
    "1403": "1403",
    "1404": "1404",
    "1405": "1405",
    "1406": "1406",
    "1407": "1407",
    "1409": "1409",
    "1410": "1410",
    "1411": "1411",
    "1408": "1406",
    "1503": "1503",
    "1504": "1504",
    "1505": "1505",
    "1506": "1506",
    "1507": "1507",
    "1508": "1508",
    "1509": "1509",
    "1510": "1510",
    "1501": "1502",
    "1502": "1502",
    "1601": "1601",
    "1602": "1602",
    "1603": "1603",
    "1606": "1606",
    "1607": "1607",
    "1608": "1608",
    "1604": "1604",
    "1605": "1604",
    "1412": "1412",
}

# 一次完整 reload_all_register 里, 单个 damage_<id>.py 可能被 reload 4-6 次
# (register_damage + register_rank, ID_MAPPING 还有 1408→1406 / 1501→1502 / 1605→1604
# 这种别名共用模块)。把"首装时模块尚未下载完"的初始噪声合并提示一次, 但运行期再发生
# 任何 ImportError 必须能在日志里看到具体是哪个 char / 哪条 import 链。
_INITIAL_IMPORT_NOTICE_SHOWN = False

def _dynamic_load_and_register(attr_name, register_cls, force_reload=False):
    global _INITIAL_IMPORT_NOTICE_SHOWN
    current_globals = globals()
    for char_id, module_suffix in ID_MAPPING.items():
        module_path = f"..waves_build.damage_{module_suffix}"
        try:
            module = importlib.import_module(module_path, package=__package__)
            if force_reload:
                # 编译扩展 (.so/.pyd) reload 行为不稳定, 仅 reload .py / .pyc。
                origin = ""
                spec = getattr(module, "__spec__", None)
                if spec is not None:
                    origin = getattr(spec, "origin", "") or ""
                if origin.endswith((".py", ".pyc")):
                    importlib.reload(module)
                else:
                    logger.debug(
                        f"[鸣潮·伤害注册] 跳过编译扩展 reload module={module_path} "
                        f"origin={origin}"
                    )
            if not hasattr(module, attr_name):
                logger.warning(
                    f"[鸣潮·伤害注册] {module_path} 缺失 attr={attr_name} (char_id={char_id})"
                )
                continue

            target_obj = getattr(module, attr_name)
            if target_obj is None:
                continue
            if isinstance(target_obj, (list, dict)) and not target_obj:
                continue
            register_cls.register_class(char_id, target_obj)
            global_var_name = f"{attr_name.split('_')[0]}_{char_id}"
            current_globals[global_var_name] = target_obj

        except ImportError as e:
            if not _INITIAL_IMPORT_NOTICE_SHOWN and not force_reload:
                logger.warning(
                    "[鸣潮·伤害注册] 计算模块未找到，请观察下载是否进行，"
                    "并等待下载完成后再进行其他操作，除非遇到下载问题。"
                )
                _INITIAL_IMPORT_NOTICE_SHOWN = True
            logger.warning(
                f"[鸣潮·伤害注册] ImportError module={module_path} char_id={char_id} "
                f"attr={attr_name} reload={force_reload}: {e}"
            )
        except Exception as e:
            logger.warning(
                f"[鸣潮·伤害注册] {type(e).__name__} module={module_path} "
                f"char_id={char_id} attr={attr_name} reload={force_reload}: {e}"
            )


def register_damage(reload=False):
    _dynamic_load_and_register(attr_name="damage_detail", register_cls=DamageDetailRegister, force_reload=reload)


def register_rank(reload=False):
    _dynamic_load_and_register(attr_name="rank", register_cls=DamageRankRegister, force_reload=reload)


def reload_all_register():
    # 注册
    from ...queues import init_queues
    from ...damage.register_char import register_char
    from ...damage.register_echo import register_echo
    from ...damage.register_weapon import register_weapon

    register_weapon()
    register_echo()

    register_damage(reload=True)
    register_rank(reload=True)

    register_char()

    # 初始化任务队列
    init_queues()
