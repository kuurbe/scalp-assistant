"""
Lightweight TTL cache — in-memory with optional disk persistence.
"""
import time
import functools
import pickle
import os
import hashlib

DISK_CACHE_DIR = "/tmp/scalp_v3_cache"


class TTLCache:
    """In-memory cache with per-key TTL."""

    def __init__(self, default_ttl: int = 300):
        self.default_ttl = default_ttl
        self._store: dict = {}

    def get(self, key: str):
        if key in self._store:
            value, expiry = self._store[key]
            if time.time() < expiry:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value, ttl: int = None):
        expiry = time.time() + (ttl or self.default_ttl)
        self._store[key] = (value, expiry)

    def invalidate(self, key: str):
        self._store.pop(key, None)

    def clear_expired(self):
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired:
            del self._store[k]


# Global cache instance
_cache = TTLCache()


_SENTINEL = object()  # Distinguishes cache miss from cached None

def cached(ttl: int = 300):
    """Decorator that caches function results with TTL.

    Caches None results with a shorter TTL (60s) to avoid retrying
    failed fetches every call while still allowing recovery.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__module__}.{func.__name__}:{hashlib.md5(str((args, sorted(kwargs.items()))).encode()).hexdigest()}"
            result = _cache.get(key)
            if result is not _SENTINEL and result is not None:
                return result
            # Check if we have a cached None (negative cache)
            neg_key = f"_neg_{key}"
            if _cache.get(neg_key) is True:
                return None
            result = func(*args, **kwargs)
            if result is not None:
                _cache.set(key, result, ttl)
            else:
                # Cache None for 60s to avoid hammering failed endpoints
                _cache.set(neg_key, True, min(ttl, 60))
            return result
        return wrapper
    return decorator


def disk_cache_get(key: str):
    """Read from disk cache."""
    os.makedirs(DISK_CACHE_DIR, exist_ok=True)
    path = os.path.join(DISK_CACHE_DIR, f"{hashlib.md5(key.encode()).hexdigest()}.pkl")
    if os.path.exists(path):
        try:
            age = time.time() - os.path.getmtime(path)
            if age < 86400:  # 24 hour disk cache
                with open(path, "rb") as f:
                    return pickle.load(f)
        except Exception:
            pass
    return None


def disk_cache_set(key: str, value):
    """Write to disk cache."""
    os.makedirs(DISK_CACHE_DIR, exist_ok=True)
    path = os.path.join(DISK_CACHE_DIR, f"{hashlib.md5(key.encode()).hexdigest()}.pkl")
    try:
        with open(path, "wb") as f:
            pickle.dump(value, f)
    except Exception:
        pass
