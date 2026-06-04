import logging
import os
import time

logger = logging.getLogger(__name__)


class KeyRotator:
    """Rotates through up to 5 API keys on a fixed time interval."""

    HOLD_SECONDS = 120

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.keys: list[str] = []
        self._index = 0
        self._key_start_time: float = time.time()
        self._calls_per_key: dict[int, int] = {}

        for i in range(1, 6):
            key = os.environ.get(f"{prefix}_{i}", "").strip()
            if key:
                self.keys.append(key)

        if not self.keys:
            single = os.environ.get(prefix, "").strip()
            if single:
                self.keys.append(single)

        if not self.keys:
            raise ValueError(
                f"No API keys found. Set {prefix}_1 through {prefix}_5, "
                f"or set {prefix} as a fallback."
            )

        for i in range(len(self.keys)):
            self._calls_per_key[i] = 0

        logger.info("KeyRotator[%s]: loaded %d key(s)", prefix, len(self.keys))

    def record_usage(self, key_idx: int, tokens: int) -> None:
        self._calls_per_key[key_idx] = self._calls_per_key.get(key_idx, 0) + 1

    def next(self, estimated_tokens: int = 5000) -> tuple[str, int]:
        now = time.time()
        elapsed = now - self._key_start_time

        if elapsed >= self.HOLD_SECONDS and len(self.keys) > 1:
            self._index = (self._index + 1) % len(self.keys)
            self._key_start_time = now
            logger.debug("Rotated to key %d after %.1fs", self._index + 1, elapsed)

        return self.keys[self._index], self._index

    @property
    def current_index(self) -> int:
        return self._index + 1

    @property
    def count(self) -> int:
        return len(self.keys)

    def status(self) -> str:
        elapsed = time.time() - self._key_start_time
        remaining = max(0, self.HOLD_SECONDS - elapsed)
        lines = []
        for i in range(len(self.keys)):
            calls = self._calls_per_key.get(i, 0)
            marker = f" ◄ active ({remaining:.0f}s left)" if i == self._index else ""
            lines.append(f"  Key {i+1}: {calls} calls{marker}")
        return "\n".join(lines)
