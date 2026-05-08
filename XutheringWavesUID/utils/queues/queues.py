import sys
import asyncio
from typing import Any, Dict, List, Tuple, Union, Callable, Coroutine, Optional

from gsuid_core.logger import logger


class TaskDispatcher:
    def __init__(self):
        self.queue: asyncio.Queue[Tuple[str, Any]] = asyncio.Queue()
        self.running = False
        self.handlers: Dict[str, List[Callable]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker: Optional[asyncio.Task] = None
        self._tasks: set = set()

    def register_handler(
        self,
        task_type: str,
        handler: Callable[[Any], Union[Any, Coroutine[Any, Any, Any]]],
    ) -> None:
        handlers = self.handlers.setdefault(task_type, [])
        if any(h.__name__ == handler.__name__ for h in handlers):
            return
        handlers.append(handler)
        logger.info(f"注册任务处理器: {task_type} -> {handler.__name__}")

    def start(
        self,
        daemon: bool = True,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        _ = daemon  # 保留 API 兼容; 不再使用 thread

        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("任务分发器启动失败: 当前无运行中的事件循环")
                return

        if loop.is_closed():
            logger.warning("任务分发器启动失败: 事件循环已关闭")
            return

        # 即使 self.running 被 shutdown 设为 False, 旧 worker 可能还在 cancel 中.
        # 只看 worker 状态, 避免 shutdown-restart 边缘创建第二个 worker.
        if self._worker is not None and not self._worker.done():
            if self._loop is loop:
                return
            logger.warning("任务分发器已在其他事件循环中启动")
            return

        self._loop = loop
        self.running = True
        self._worker = loop.create_task(
            self._process(),
            name="waves-task-dispatcher",
        )
        logger.info("任务分发器已启动")

    def shutdown(self) -> None:
        self.running = False

        worker = self._worker
        loop = self._loop
        if worker is None or worker.done() or loop is None or loop.is_closed():
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            worker.cancel()
        else:
            loop.call_soon_threadsafe(worker.cancel)

    def emit(self, task_type: str, data: Any) -> None:
        if not self.running or self._loop is None:
            logger.warning("任务分发器未启动或已关闭")
            return

        if task_type not in self.handlers:
            return

        loop = self._loop
        if loop.is_closed():
            self.running = False
            logger.warning("任务分发器事件循环已关闭")
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        try:
            if running_loop is loop:
                self._enqueue_nowait(task_type, data)
            else:
                loop.call_soon_threadsafe(self._enqueue_nowait, task_type, data)
        except RuntimeError as e:
            logger.exception(f"任务入队调度异常: {e}")

    def _enqueue_nowait(self, task_type: str, data: Any) -> None:
        if not self.running:
            return
        try:
            self.queue.put_nowait((task_type, data))
        except Exception as e:
            logger.exception(f"任务入队异常: {e}")

    async def _process(self) -> None:
        worker = asyncio.current_task()
        try:
            while self.running:
                task_type, data = await self.queue.get()
                try:
                    handlers = list(self.handlers.get(task_type, []))
                    for handler in handlers:
                        # task retention: keep strong ref + auto-cleanup on done
                        task = asyncio.create_task(self._run_task(handler, data, task_type))
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
                except Exception as e:
                    logger.exception(f"任务处理异常: {e}")
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            # 只有自己仍是当前 _worker 时才清空, 避免 shutdown-restart 后清掉新 worker.
            if self._worker is worker:
                self.running = False
                self._worker = None

    async def _run_task(self, handler: Callable, data: Any, task_type: str) -> None:
        try:
            result = handler(data)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.exception(f"任务执行错误 ({task_type}): {e}")


_DISPATCHER_KEY = "__waves_task_dispatcher__"

# 跨双路径加载防御 + 热重载兼容: 复用旧 dispatcher 或迁移其 handlers
_previous_dispatcher = sys.modules.get(_DISPATCHER_KEY)
if isinstance(_previous_dispatcher, TaskDispatcher):
    dispatcher = _previous_dispatcher
else:
    dispatcher = TaskDispatcher()
    old_handlers = getattr(_previous_dispatcher, "handlers", None)
    if isinstance(old_handlers, dict):
        dispatcher.handlers.update(old_handlers)
    if _previous_dispatcher is not None and hasattr(_previous_dispatcher, "running"):
        try:
            setattr(_previous_dispatcher, "running", False)
        except Exception:
            pass
    sys.modules[_DISPATCHER_KEY] = dispatcher  # type: ignore[assignment]


def register_handler(
    task_type: str,
    handler: Callable[[Any], Union[Any, Coroutine[Any, Any, Any]]],
) -> None:
    dispatcher.register_handler(task_type, handler)


def start_dispatcher(daemon: bool = True) -> None:
    """向后兼容: 由 utils/queues/__init__.py 调用. 在 main loop 内同步调即可."""
    dispatcher.start(daemon=daemon)


def shutdown_dispatcher() -> None:
    dispatcher.shutdown()


def push_item(queue_name: str, item: Any) -> None:
    if not dispatcher.running:
        dispatcher.start()
    dispatcher.emit(queue_name, item)


def event_handler(task_type: str) -> Callable:
    """事件处理器装饰器, 用于本地撰写排行等逻辑.

    Examples:
        @event_handler("score_rank")
        async def handle_score_rank(data):
            ...
    """

    def decorator(func: Callable) -> Callable:
        dispatcher.register_handler(task_type, func)
        return func

    return decorator
