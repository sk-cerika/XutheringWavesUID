# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库性质

`XutheringWavesUID` 是 [gsuid_core (早柚核心)](https://github.com/Genshin-bots/gsuid_core) 的一个**鸣潮 (Wuthering Waves) 插件**，由 `WutheringWavesUID` 衍生而来，主要差别是把权重 / 评分 / 伤害的真类挪到了一个**独立的、需要下载的预编译包 `waves_build`** 里，仓库内只保留占位 stub。

它**不是一个独立可执行的项目**，必须放在 `gsuid_core/plugins/` 目录下由 core 加载运行。仓库里没有 `main.py` / `app.py` / 启动脚本。

仓库根目录命名很迷惑：

- 仓库根 `D:\code\XutheringWavesUID\`（外层）—— 仅包含 `pyproject.toml`、`README.md`、锁文件、`assets/` 等元数据
- `XutheringWavesUID/` 子目录（内层）—— 才是真正的 Python 包，core 加载的就是这个目录

外层根目录还有两个空文件 `__init__.py` / `__nest__.py`，里面只有一个字符串字面量，是 core 识别插件用的标记，**不要往里加逻辑**。

## 关键架构

### 1. 插件注册与命令前缀

所有命令前缀强制为 `ww`，由 `XutheringWavesUID/__init__.py` 顶部的：

```python
Plugins(name="XutheringWavesUID", force_prefix=["ww"], allow_empty_prefix=False)
```

注册。这意味着用户必须发 `ww<命令>`，不接受空前缀。判断 `if "XutheringWavesUID" not in SL.plugins` 是为了对抗跨插件 cross-import 把这块重 exec、把状态覆盖回默认值的场景，**别去掉这个守卫**。

每个 `wutheringwaves_*` 目录就是一个功能模块，模块的 `__init__.py` 直接用 `gsuid_core.sv.SV(...)` 注册命令处理器（`on_prefix` / `on_fullmatch` / `on_regex`）。

### 2. `waves_build` 占位机制（核心坑点）

下面这些文件里看到的类和函数全都是**空壳 stub**：

- `XutheringWavesUID/utils/calc/__init__.py` 的 `WuWaCalc`
- `XutheringWavesUID/utils/calculate.py` 的 `calc_phantom_score` / `calc_phantom_entry` / `get_calc_map` 等
- `XutheringWavesUID/utils/damage/damage.py` 的 `DamageAttribute` / `calc_percent_expression` / `check_char_id`

真类来自 `XutheringWavesUID/utils/waves_build/`，这个目录**不在 git 里**，由用户通过 `ww下载全部资源` 命令下载得到。`reload_wuwacalc_module` / `reload_damage_module` 负责把真类注入回占位类的位置。

如果用户报"评分不对 / 伤害是 0 / WuWaCalc 报错"，**不要去仓库里改这些 stub** —— 真实计算代码在另一个不在本仓库的预编译包里。本仓库能做的最多是改占位的 fallback 行为或调用方逻辑。

### 3. 资源 / 数据路径

`XutheringWavesUID/utils/resource/RESOURCE_PATH.py` 是**所有路径的单一来源**。

- `MAIN_PATH = get_res_path() / "XutheringWavesUID"` —— 用户数据根，落在 `gsuid_core/data/XutheringWavesUID/`
- `BUILD_PATH = utils/waves_build`、`MAP_BUILD_PATH = utils/map/waves_build` —— 预编译包落地点（仓库内）
- `BUILD_TEMP / MAP_BUILD_TEMP` —— 下载中转目录，校验通过后再覆盖到 BUILD_PATH
- `CUSTOM_DIRS = {"card": ..., "bg": ..., "stamina": ...}` —— 三类自定义图（面板图 / MR 背景图 / MR 体力图）的根目录映射，**唯一来源**，`card_utils.CUSTOM_PATH_MAP` / `card_hash_index.TYPE_BASES` / `panel_editor/storage.TYPE_PATHS` 都从这里读
- `IMAGE_EXTS` —— 自定义图允许后缀，同样唯一来源

新加路径或自定义图 type 时，先改这里，别在调用处搞硬编码。

### 4. 数据库迁移

`XutheringWavesUID/utils/database/models.py` 顶部用：

```python
exec_list.extend([...])
```

塞了一长串 `ALTER TABLE` / `UPDATE` / `DELETE` SQL，core 启动时会按顺序执行。

**新加字段或迁移**：

- 表新字段：先在 SQLModel 类加 `Field(default=...)`，再往 `exec_list` 末尾追加对应的 `ALTER TABLE ... ADD COLUMN ... DEFAULT ...`
- 数据修补：直接追加到 `exec_list`，注意**幂等**（重复执行不会出错）
- 删字段：用 `DROP COLUMN`，但这条已经能看出 SQLite 旧版本不支持，得评估目标 SQLite 版本

### 5. 配置体系

- `WutheringWavesConfig` 全局插件配置（StringConfig，默认值见 `wutheringwaves_config/config_default.py`，落盘在 `MAIN_PATH/config.json`）
- `ShowConfig` 显示配置（在 `MAIN_PATH/show_config.json`）
- `guide_config.json` / `gacha_config.json` / `ann_data.json` 等模块级配置走自家的 `load_*` / `save_*` helper
- 用户级偏好（如指定面板图）由 `utils/panel_card_pref.py` 落到 sqlite

不要在业务代码里 `open(config.json)` 直接读，统一走 `WutheringWavesConfig.get_config(...)`。

### 6. Web 面板编辑器

`wutheringwaves_resource/panel_editor/` 在导入时就把路由 `/waves/panel-edit/` 挂到 core 的 FastAPI 上，使用 HTTP Basic Auth（用户名固定 `admin`），密码 = `WutheringWavesConfig` 中 `WavesPanelEditPassword`。空密码视为未启用，访问只显示提示页。

### 7. Hook 与活跃度缓冲

`__init__.py` 里：

- 安装 bot 发送 hook（`install_bot_hooks`），区分本插件触发的消息
- `_activity_buffer` 是内存里的"用户活跃度"去重缓冲，`_FLUSH_INTERVAL = 60` 秒批写一次到 `WavesUserActivity`
- `on_core_shutdown` 回调里会再 flush 一次防止丢数据

**改这块要小心**：直接在 hook 里同步写库会被高并发打爆 SQLite，缓冲方案是有意为之。

### 8. 模板渲染

`XutheringWavesUID/templates/` 是 Jinja2 HTML 模板，配合 `playwright`（chromium）截图生成图片消息。`playwright` 是 optional 依赖，core 会尝试自动 `pip install`，但浏览器内核 `playwright install chromium` **必须用户手动跑一次**。涉及模板渲染的功能在用户没装 chromium 时会直接挂掉，错误别想糊弄过去。

### 9. 国际化

`utils/localization/` 提供本地化加载，在 `__init__.py` 里 `init_localization()` 启动时初始化。语言 key：`chs / cht / en / jp / kr`，存储到 `WavesLangSettings` 表。

### 10. 插件入口模块速查

| 模块 | 用途 |
|------|------|
| `wutheringwaves_charinfo` | 面板图上传 / 查看 / 删除、角色面板查询 |
| `wutheringwaves_abyss / explore / period / calendar / ann` | 深境 / 探索 / 期数 / 日历 / 公告 |
| `wutheringwaves_gachalog` | 抽卡记录、抽卡分析、排行 |
| `wutheringwaves_sign / login / bbs` | 签到 / 登录 / 库街区 |
| `wutheringwaves_alias / wiki / help` | 别名、wiki、帮助 |
| `wutheringwaves_config / user / start` | 用户配置 / 绑定 / 引导 |
| `wutheringwaves_resource` | 资源下载 + 网页面板编辑器 |
| `wutheringwaves_master / develop / rank / up / status / stamina` | 主人命令、养成、排行、UP、状态、体力 |
| `wutheringwaves_code / query / roleinfo / charlist / echo` | 兑换码 / 查询 / 角色信息 / 角色列表 / 声骸 |

## 常用命令

仓库**没有**自己的测试套件 / 构建脚本 / Makefile / CI 配置。能跑的就这些：

```bash
# Lint + format（pre-commit 配的 ruff）
pre-commit run --all-files

# 单文件 lint
ruff check XutheringWavesUID/<file>.py
ruff format XutheringWavesUID/<file>.py

# import 排序（pyproject 里配了 isort，但 pre-commit hook 没启用，必要时手动跑）
isort XutheringWavesUID/<file>.py
```

**没有 `pytest` / `unittest` 测试**，整个仓库 `find -name 'test_*.py'` 是空的。所谓的"验证"主要靠：

1. 装到 `gsuid_core/plugins/` 下重启 core 看日志
2. 在 bot 里发 `ww<命令>` 实际触发
3. 关键路径（评分 / 伤害）依赖 `waves_build`，本地复现需要先 `ww下载全部资源`

锁文件 `pdm.lock` / `poetry.lock` / `uv.lock` 都存在但**几乎是空的**（`package = []`）—— 实际依赖在 `pyproject.toml` 的 `[project].dependencies` 字段，core 启动时会自动按这里 `pip install` 缺的。改依赖只改 `pyproject.toml`，不需要重新生成锁文件。

## 代码风格

- `pyproject.toml` 配了 isort：`profile = "black"`、`line_length = 79`、`length_sort = true`、`force_sort_within_sections = true`、`extra_standard_library = ["typing_extensions"]`
- pre-commit 跑 ruff（v0.14.8）`--fix` 和 `ruff-format`
- 注释、提示文案、log 大量使用中文，跟现有风格保持一致即可
- 新增模块的注册一律走 `SV(...).on_prefix / on_fullmatch / on_regex`，不要去碰 core 的 dispatch 内部

## 依赖与供应链

`pyproject.toml [project].dependencies` 当前列了：

```
pypinyin>=0.50.0
rapidfuzz>=3.0.0
playwright>=1.40.0
opencv-python>=4.8.0
```

core 会按这个列表自动装。**新增依赖**：先核对版本发布日期与是否有已知供应链事件，再写 `pyproject.toml`。playwright 装完还得提示用户 `uv run playwright install chromium`。

## Git 工作流

**当前仓库禁止任何推送到远端的操作**，包括但不限于：

- `git push` / `git push --force`
- 创建或更新远端分支、标签
- 发起 PR / MR
- 任何会向远端写入的 git 命令

本地 `commit` / `branch` / `rebase` / 本地 `reset` 不受影响。除非用户在具体任务里**显式重新授权**，否则一律不动远端。

## 常见坑点速查

- 改了 `wutheringwaves_*/__init__.py` 的 SV 注册：core **不会热加载**，必须重启 core
- 在仓库内动 `utils/calc/`、`utils/damage/damage.py`、`utils/calculate.py` 想"修评分"：方向错了，真类在 `waves_build` 里，本仓库的是占位
- 新加路径硬编码：先看 `RESOURCE_PATH.py` / `CUSTOM_DIRS` / `IMAGE_EXTS` 有没有现成常量
- 表新字段没追加 `exec_list` 迁移：老用户库会缺列直接炸，必须加
- 直接同步写 `WavesUserActivity`：跟现有的批量缓冲机制冲突，会坏数据，沿用 `_activity_buffer`
- `playwright` 渲染失败：99% 是用户没跑 `playwright install chromium`，不要在代码里瞎补
- 改面板图 / 自定义图相关：注意三个来源（仓库代码、`waves_build` 提供的索引、用户的 `MAIN_PATH/custom_*` 实际文件）要保持一致
