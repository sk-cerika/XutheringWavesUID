"""把插件源码里 `skills/` 目录下的 SKILL.md 同步到 AI Core 的 SKILLS_PATH 并触发 reload。"""

from __future__ import annotations

import shutil
from pathlib import Path

from gsuid_core.logger import logger

SKILLS_SRC: Path = Path(__file__).parent / "skills"


def register_endgame_advisor_skill() -> None:
    """把本插件 skills/ 下的每个 SKILL.md 同步到 data/ai_core/skills/。"""
    try:
        from gsuid_core.ai_core.resource import SKILLS_PATH
        from gsuid_core.ai_core.skills.operations import _reload_skills
    except ImportError:
        logger.debug("🧠 [鸣潮-RAG] AI Core skills 模块不可用，跳过 skill 注册")
        return

    if not SKILLS_SRC.exists():
        return

    skills_root = Path(SKILLS_PATH)
    skills_root.mkdir(parents=True, exist_ok=True)

    changed: list[str] = []
    for src_dir in SKILLS_SRC.iterdir():
        if not src_dir.is_dir():
            continue
        src_md = src_dir / "SKILL.md"
        if not src_md.exists():
            continue

        dst_dir = skills_root / src_dir.name
        dst_md = dst_dir / "SKILL.md"
        dst_dir.mkdir(parents=True, exist_ok=True)

        new_content = src_md.read_text(encoding="utf-8")
        old_content = dst_md.read_text(encoding="utf-8") if dst_md.exists() else ""
        if new_content == old_content:
            continue

        # 同步整个 skill 目录：用 copytree 才能带上 resources/ scripts/ 之类的子目录，
        # 这里 SKILL.md 只是必备入口，未来若有附属资源也能一起带过去
        for item in src_dir.iterdir():
            target = dst_dir / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        changed.append(src_dir.name)

    if not changed:
        return

    try:
        _reload_skills()
    except Exception:
        logger.exception("🧠 [鸣潮-RAG] _reload_skills 失败")
        return
    logger.info(f"🧠 [鸣潮-RAG] 已同步 skill: {', '.join(changed)}")
