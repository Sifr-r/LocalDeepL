import os
from collections.abc import Callable
from typing import Any

from local_deepl.core.translation_config import AsyncTranslationUnavailable

try:
    from celery import Celery as CeleryClass
except ImportError:
    CeleryClass = None

# Allow configuration via environment variables
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class _MissingCeleryTask:
    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        bind: bool = False,
    ) -> None:
        self._func = func
        self._name = name or getattr(func, "__name__", "celery_task")
        self._bind = bind
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__

    @property
    def name(self) -> str:
        """Task name registered with the (stub) Celery app."""
        return self._name

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Calling the task directly mirrors ``.run()`` (parity with celery)."""
        return self.run(*args, **kwargs)

    def run(self, *args: Any, **kwargs: Any) -> Any:
        if self._bind:
            return self._func(self, *args, **kwargs)
        return self._func(*args, **kwargs)

    def delay(self, *args: Any, **kwargs: Any) -> Any:
        """No broker means no async dispatch: run inline.

        When the optional ``celery`` dependency isn't installed (or no worker
        is available) we fall back to executing the task synchronously in the
        caller. This mirrors the production fallback contract used by
        ``process_translation_task`` and keeps tests hermetic.
        """
        return self.run(*args, **kwargs)

    def apply_async(self, *_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover
        raise AsyncTranslationUnavailable(
            "Async translation requires optional dependency 'celery'. "
            "Install the async translation extras to enable background jobs."
        )

    def update_state(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _MissingCeleryApp:
    def task(self, *_args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Any]:
        bind = bool(kwargs.get("bind", False))
        name = kwargs.get("name")

        def decorator(func: Callable[..., Any]) -> _MissingCeleryTask:
            return _MissingCeleryTask(func, name=name, bind=bind)

        return decorator

    def AsyncResult(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AsyncTranslationUnavailable(
            "Async translation status requires optional dependency 'celery'. "
            "Install the async translation extras to enable background jobs."
        )


if CeleryClass is None:
    celery_app = _MissingCeleryApp()
else:
    # Initialize Celery app
    celery_app = CeleryClass(
        "local_deepl_tasks",
        broker=REDIS_URL,
        backend=REDIS_URL,
        include=["local_deepl.api.tasks"],
    )

    # Configure Celery
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        # To prevent OOM errors on a single GPU setup (12GB VRAM), we force a single worker process
        worker_concurrency=1,
    )
