"""XW @ai_tools 集合（导入子模块即触发 @ai_tools 注册）。

公开:
- `invalidate_caches()` —— 资源 reload 后清缓存。
"""

from . import catalog as _catalog  # noqa: F401
from . import kb as _kb            # noqa: F401
from . import monster as _monster  # noqa: F401
from . import period as _period    # noqa: F401
from . import user as _user        # noqa: F401

from ._cache import invalidate_caches

__all__ = ["invalidate_caches"]
