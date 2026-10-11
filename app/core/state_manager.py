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


_RUN_STATE_MANAGERS: dict[str, RunStateManager] = {}


def get_run_state_manager(run_id: str) -> RunStateManager:
    if run_id not in _RUN_STATE_MANAGERS:
        _RUN_STATE_MANAGERS[run_id] = RunStateManager(run_id)
    return _RUN_STATE_MANAGERS[run_id]
