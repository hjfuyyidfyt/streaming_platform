import time
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class SimpleCache:
    """A very simple in-memory cache with expiration."""
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def set(self, key: str, value: Any, ttl: int = 60):
        """Set a value in the cache with a time-to-live in seconds."""
        self._cache[key] = {
            "value": value,
            "expiry": time.time() + ttl
        }
        logger.info(f"Cache SET: {key} (ttl: {ttl}s)")

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache if it exists and has not expired."""
        if key in self._cache:
            item = self._cache[key]
            if time.time() < item["expiry"]:
                logger.debug(f"Cache HIT: {key}")
                return item["value"]
            else:
                logger.debug(f"Cache EXPIRED: {key}")
                del self._cache[key]
        else:
            logger.debug(f"Cache MISS: {key}")
        return None

    def invalidate(self, key_prefix: str = None):
        """Invalidate specific key or all keys starting with prefix."""
        if key_prefix is None:
            self._cache.clear()
        else:
            keys_to_del = [k for k in self._cache.keys() if k.startswith(key_prefix)]
            for k in keys_to_del:
                del self._cache[k]
        logger.info(f"Cache invalidated (prefix: {key_prefix})")

# Global instances
app_cache = SimpleCache()
