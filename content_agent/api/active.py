import threading


class ActiveRuns:
    """Run IDs with a graph.invoke in progress in THIS process.

    Guards against two invokes on the same thread (e.g. a double-clicked resume).
    Only correct with a single uvicorn worker: each worker process has its own set.
    """

    def __init__(self) -> None:
        self._ids: set[str] = set()
        self._lock = threading.Lock()   # background runs and endpoints run in different threads

    def claim(self, run_id: str) -> bool:
        """Mark the run busy. False if it already was: the caller must not invoke."""
        with self._lock:
            if run_id in self._ids:
                return False
            self._ids.add(run_id)
            return True

    def release(self, run_id: str) -> None:
        with self._lock:
            self._ids.discard(run_id)

    def __contains__(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._ids
