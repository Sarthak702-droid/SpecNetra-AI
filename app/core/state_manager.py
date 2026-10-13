import asyncio
from typing import Any


class RunStateManager:
    """
    Thread-safe manager for per-run resources and secrets.
    Stores opaque references and actual values isolated per run.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._resources: dict[str, Any] = {}
        self._tokens: dict[str, str] = {}  # key -> secret; NEVER sent to LLM
        self._lock = asyncio.Lock()

    async def store_resource(self, key: str, value: Any) -> None:
        async with self._lock:
            self._resources[key] = value

    async def get_resource(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._resources.get(key, default)

    async def store_token(self, ref_key: str, token: str) -> None:
        async with self._lock:
            self._tokens[ref_key] = token

    async def get_token(self, ref_key: str) -> str | None:
        async with self._lock:
            return self._tokens.get(ref_key)

    async def get_all_resources(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._resources)

    async def stage_resource(self, key: str, value: Any) -> None:
        async with self._lock:
            if not hasattr(self, "_staged_resources"):
                self._staged_resources = {}
            self._staged_resources[key] = value

    async def stage_token(self, ref_key: str, token: str) -> None:
        async with self._lock:
            if not hasattr(self, "_staged_tokens"):
                self._staged_tokens = {}
            self._staged_tokens[ref_key] = token

    async def commit_staged(self) -> None:
        async with self._lock:
            if hasattr(self, "_staged_resources"):
                self._resources.update(self._staged_resources)
                self._staged_resources.clear()
            if hasattr(self, "_staged_tokens"):
                self._tokens.update(self._staged_tokens)
                self._staged_tokens.clear()

    async def discard_staged(self) -> None:
        async with self._lock:
            if hasattr(self, "_staged_resources"):
                self._staged_resources.clear()
            if hasattr(self, "_staged_tokens"):
                self._staged_tokens.clear()

    async def clear(self) -> None:
        async with self._lock:
            self._resources.clear()
            self._tokens.clear()
            if hasattr(self, "_staged_resources"):
                self._staged_resources.clear()
            if hasattr(self, "_staged_tokens"):
                self._staged_tokens.clear()


_RUN_STATE_MANAGERS: dict[str, RunStateManager] = {}


def get_run_state_manager(run_id: str) -> RunStateManager:
    if run_id not in _RUN_STATE_MANAGERS:
        _RUN_STATE_MANAGERS[run_id] = RunStateManager(run_id)
    return _RUN_STATE_MANAGERS[run_id]


def release_run_state_manager(run_id: str) -> None:
    if run_id in _RUN_STATE_MANAGERS:
        del _RUN_STATE_MANAGERS[run_id]
