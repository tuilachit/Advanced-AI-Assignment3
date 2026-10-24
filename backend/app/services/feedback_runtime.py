"""Application-owned runner. Construction and import never start worker threads."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class FeedbackRuntime:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="feedback")
        self._lock = Lock()
        self._closing = False

    def submit(self, job: Callable[[], None]) -> None:
        with self._lock:
            if self._closing:
                raise RuntimeError("Feedback runtime is shutting down.")
            self._executor.submit(job)

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
        self._executor.shutdown(wait=True, cancel_futures=False)
